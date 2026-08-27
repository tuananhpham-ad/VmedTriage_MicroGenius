"""Kênh báo tiến trình của part 3. MỘT cơ chế, ba mặt hiển thị: CLI, SSE, và log.

VÌ SAO CẦN. Part 3 chạy mất hàng chục giây và trong phần lớn thời gian đó nó KHÔNG có chữ nào để
phát ra: bước 1 và bước 6 trả JSON, bước 3-4 là search/fetch/embed - không phải văn bản. Người ngồi
đợi trước một màn hình im lặng không phân biệt được "đang fetch trang thứ tư" với "treo". Streaming
token của bước 7 KHÔNG giải quyết việc đó, vì bước 7 nằm ở cuối, sau khi phần lớn thời gian đã trôi
qua. Thứ giải quyết được là báo tiến trình - và nó phải báo NGAY khi việc xảy ra, không gom lại.

THAM SỐ TƯỜNG MINH, KHÔNG DÙNG CONTEXTVAR. Bước 6 chấm verdict trong `ThreadPoolExecutor`, mà
contextvar không tự sang luồng con - dùng contextvar thì đúng cái bước tốn thời gian nhất lại là
bước im lặng. Truyền `on_progress` qua chữ ký hàm thì chỗ nào quên truyền là chỗ đó nhìn thấy được.

CALLBACK HỎNG KHÔNG ĐƯỢC LÀM HỎNG CA. Sink là code hiển thị của người gọi - một `BrokenPipeError` vì
người dùng đóng tab không có lý do gì để giết luôn phần trích nguồn. `ProgressReporter.emit` nuốt mọi
lỗi của sink và ghi log, đúng một lần cho mỗi reporter để không làm ngập log.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("vmedtriage.source_support")


@dataclass(frozen=True)
class ProgressEvent:
    """Một mốc trong lượt chạy.

    `text` là câu tiếng Việt ĐÃ viết sẵn chứ không phải mã để người gọi tra bảng: ba mặt hiển thị
    (CLI, SSE, log) cần đúng một câu như nhau, và bắt mỗi mặt tự dựng câu từ `phase` + `detail` là
    cách ba mặt trôi ra ba cách diễn đạt khác nhau cho cùng một việc.

    `detail` giữ số liệu thô cho mặt nào muốn hiển thị khác - UI có thể vẽ thanh tiến trình từ
    `index`/`total` mà không phải bóc chuỗi."""

    phase: str
    text: str
    detail: dict[str, object] = field(default_factory=dict)
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"phase": self.phase, "text": self.text, "elapsed_ms": self.elapsed_ms, **self.detail}


Progress = Callable[[ProgressEvent], None]
"""Sink của người gọi. Nhận đúng một sự kiện, trả về `None`, và KHÔNG được chặn lâu - nó chạy ngay
trên luồng đang làm việc thật (kể cả luồng con của bước 6)."""


class ProgressReporter:
    """Bọc sink của người gọi: khoá, đồng hồ, và nuốt lỗi.

    KHOÁ VÌ BƯỚC 6 CHẤM SONG SONG. Ba luồng cùng gọi `print()` sẽ cho ra ba dòng cài răng lược nhau;
    khoá ở đây thì mọi sink - kể cả sink ngây thơ nhất - đều thấy sự kiện đến tuần tự."""

    def __init__(self, sink: Progress | None = None) -> None:
        self._sink = sink
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._sink_broken = False

    @property
    def enabled(self) -> bool:
        """Cho phép chỗ gọi bỏ qua việc dựng chuỗi mô tả khi không ai nghe."""
        return self._sink is not None and not self._sink_broken

    def emit(self, phase: str, text: str, **detail: object) -> None:
        if not self.enabled:
            return
        event = ProgressEvent(
            phase=phase,
            text=text,
            detail=detail,
            elapsed_ms=int((time.monotonic() - self._started) * 1000),
        )
        with self._lock:
            if self._sink_broken:
                return
            try:
                self._sink(event)  # type: ignore[misc]
            except Exception as error:
                # Tắt hẳn sink thay vì thử lại: nếu nó hỏng vì tab đã đóng thì mọi sự kiện sau cũng
                # hỏng y hệt, và ghi log cho từng cái là biến một lỗi thành hàng chục dòng nhiễu.
                self._sink_broken = True
                logger.warning(
                    "source_support.progress_sink_failed phase=%s reason=%s: %s",
                    phase, type(error).__name__, error,
                )


def reporter_for(on_progress: Progress | ProgressReporter | None) -> ProgressReporter:
    """Chuẩn hoá đầu vào của người gọi. Nhận `None`, một hàm, hoặc một reporter đã dựng.

    Nhận sẵn cả `ProgressReporter` để đồng hồ `elapsed_ms` đếm từ ĐẦU CA chứ không reset ở mỗi bước:
    `pipeline.run` dựng một reporter rồi chuyền chính nó xuống, nên số giây trên màn hình luôn là
    tổng thời gian người dùng đã chờ."""
    if isinstance(on_progress, ProgressReporter):
        return on_progress
    return ProgressReporter(on_progress)


__all__ = ["Progress", "ProgressEvent", "ProgressReporter", "reporter_for"]

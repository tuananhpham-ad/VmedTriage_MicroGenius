"""Đồng hồ SLA cho ca nghi ngờ red-flag (ADR-007, §4.12 `_guidance/what_to_do_next.md`).

`SLA_BREACH_MESSAGE` vô nghĩa nếu không có trần thời gian, và cam kết "điều dưỡng trực 24/7" không
kiểm chứng được nếu không ai đo. Module này là chỗ DUY NHẤT biết hai mốc đó - THUẦN, không I/O,
không model: cho hai dấu thời gian, trả về ca này đang ở nấc nào.

**Hai số, không phải một — chỗ dễ sai nhất khi hiệu chỉnh sau này.**

| Số | Nghĩa | Suy ra từ | Dùng để |
| --- | --- | --- | --- |
| `SLA_CLINICAL_SECONDS` | Ca nghi ngờ cấp cứu **được phép** chờ bao lâu | Nhu cầu lâm sàng | Kích hoạt `SLA_BREACH_MESSAGE` |
| `p99_observed` | Ca trực **đang** đáp ứng bao lâu | Đo | Biết có đủ người trực không |

Quan hệ đúng: `SLA_CLINICAL_SECONDS` quyết TRƯỚC bằng lý do y tế, rồi bố trí nhân sự để
`p99_observed` chui xuống dưới nó. Đặt `SLA = p99 quan sát được` thì theo đúng định nghĩa
`sla_breach_rate` luôn ≈ 1%, và SLA thôi không còn là yêu cầu an toàn - nó trở thành bản mô tả năng
lực hiện tại, và chỉ số này không còn phát hiện được điều gì. `p99_observed` **cố ý không có** trong
module này: nó là số ĐO, thuộc về dashboard, không thuộc về ngưỡng.

Mốc tính là lúc điều dưỡng **MỞ** ca, không phải lúc duyệt xong - mở ca là lúc có người thật nhìn
thấy nó, và đó mới là thứ SLA an toàn quan tâm.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from src.services.symptom_protocol.common_safety.emergency_message import SLA_BREACH_MESSAGE

SLA_BREACH_MESSAGE_TEXT = SLA_BREACH_MESSAGE
"""Tái xuất câu tĩnh ngay cạnh ngưỡng sinh ra nó: caller chỉ phải import MỘT module để vừa biết
"đã quá hạn chưa" vừa biết "thì nói gì". Hai thứ đó luôn đi cùng nhau."""

SLA_CLINICAL_SECONDS = 300
"""**Chốt tạm 2026-08-19: 5 phút.** Đây là câu hỏi cho PM và người tổ chức ca trực, không phải cho
engineering - nhưng nó phải có một giá trị, vì thiếu nó thì `SLA_BREACH_MESSAGE` không bao giờ bắn và
cam kết 24/7 chỉ có trên giấy. Cấu hình được, hiệu chỉnh sau khi có thống kê THẬT (không phải dữ liệu
demo: p99 đo trên vài chục ca thử nghiệm sẽ đẹp một cách giả tạo vì lúc đó ai cũng đang nhìn màn hình,
và p99 dưới ~300 ca chỉ là một hai điểm dữ liệu ngoài rìa)."""

SLA_WARNING_RATIO = 0.6
"""Cảnh báo NỘI BỘ ở 60% SLA (3 phút) - báo cho ca trực TRƯỚC khi chạm trần, để
`SLA_BREACH_MESSAGE` là ngoại lệ chứ không phải chuyện thường ngày. Đây là cảnh báo cho nhân viên,
KHÔNG hiển thị cho bệnh nhân."""

SLA_WARNING_SECONDS = int(SLA_CLINICAL_SECONDS * SLA_WARNING_RATIO)


class SlaState(str, Enum):
    """Nấc của đồng hồ. `OK`/`WARNING` là chuyện nội bộ; chỉ `BREACHED` mới đổi thứ bệnh nhân đọc."""

    NOT_APPLICABLE = "not_applicable"
    """Ca không phải nghi ngờ red-flag, hoặc điều dưỡng đã mở rồi - đồng hồ dừng."""
    OK = "ok"
    WARNING = "warning"
    BREACHED = "breached"


@dataclass(frozen=True, slots=True)
class SlaStatus:
    state: SlaState
    waited_seconds: int
    remaining_seconds: int
    """Còn bao lâu tới trần. Âm = đã quá trần bao lâu."""

    @property
    def notify_patient(self) -> bool:
        """Đã tới lúc phát `SLA_BREACH_MESSAGE` cho bệnh nhân chưa."""
        return self.state is SlaState.BREACHED

    @property
    def notify_shift(self) -> bool:
        """Đã tới lúc báo ca trực chưa (nội bộ)."""
        return self.state in (SlaState.WARNING, SlaState.BREACHED)


def evaluate(
    *,
    queued_at: datetime | None,
    first_opened_at: datetime | None = None,
    is_red_flag: bool = True,
    now: datetime | None = None,
) -> SlaStatus:
    """Ca này đang ở nấc nào của đồng hồ SLA.

    `now` là tham số chứ không đọc `datetime.now()` bên trong: một hàm phụ thuộc đồng hồ hệ thống thì
    chỉ test được bằng cách chờ 5 phút thật, hoặc bằng cách vá `datetime` - cả hai đều tệ hơn là
    truyền vào một mốc.

    Đồng hồ **dừng khi điều dưỡng mở ca**, không phải khi duyệt xong: mở ca là lúc có người thật nhìn
    thấy nó. Ca đã mở rồi mà chưa duyệt là vấn đề thông lượng, không phải vấn đề an toàn tức thì -
    và trộn hai thứ đó vào một chỉ số làm `sla_breach_rate` mất khả năng phát hiện cái thứ hai."""
    if not is_red_flag or queued_at is None or first_opened_at is not None:
        return SlaStatus(SlaState.NOT_APPLICABLE, 0, SLA_CLINICAL_SECONDS)

    moment = now or datetime.now(timezone.utc)
    waited = int((moment - _aware(queued_at)).total_seconds())
    remaining = SLA_CLINICAL_SECONDS - waited
    if waited >= SLA_CLINICAL_SECONDS:
        return SlaStatus(SlaState.BREACHED, waited, remaining)
    if waited >= SLA_WARNING_SECONDS:
        return SlaStatus(SlaState.WARNING, waited, remaining)
    return SlaStatus(SlaState.OK, waited, remaining)


def deadline_for(queued_at: datetime) -> datetime:
    """Mốc mà `SLA_BREACH_MESSAGE` sẽ bắn - cho UI đếm ngược mà không phải tự tính lại ngưỡng."""
    return _aware(queued_at) + timedelta(seconds=SLA_CLINICAL_SECONDS)


def _aware(moment: datetime) -> datetime:
    """Mốc thiếu timezone coi như UTC. `TriageCase.created_at` sinh ra đã aware, nhưng dữ liệu đọc
    lại từ SQLite có thể mất tzinfo - và trừ hai datetime lệch awareness thì ném `TypeError` giữa
    đường chạy chứ không phải lúc test."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)

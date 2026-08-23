"""Kho câu hỏi thăm đã chắt lọc sẵn — Memory **M3**, phần "hỏi luôn khi mở hội thoại".

Đường đi của một câu hỏi thăm, và lý do nó bị cắt làm hai nửa ở hai thời điểm khác nhau:

```text
Phiên N đóng  ->  chắt lọc 3 phiếu gần nhất  ->  GHI vào `followup_questions`   (chỗ RẢNH)
Phiên N+1 mở  ->  ĐỌC một hàng theo khoá chính -> ghép vào câu mở                (chỗ ĐANG CHỜ)
```

Nửa đắt (truy vấn 3 hàng + chắt lọc) nằm ở lượt không ai chờ; lượt mở chỉ còn một `SELECT` theo khoá
chính. Đó là toàn bộ lý do bảng này tồn tại thay vì gọi thẳng `history_recall.recall()` ở lượt mở.

Như mọi store khác trong thư mục này, **không hàm nào ở đây được phép ném**: câu hỏi thăm là phần
thêm vào của lượt mở, còn lượt mở thì không - mất câu hỏi thăm là mất một câu xã giao, còn ném ra
ngoài là chặn người bệnh bắt đầu kể bệnh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.database import session_scope
from src.models.case_record import FollowupQuestionRow

logger = logging.getLogger("vmedtriage.followup_store")

GUEST_USER_ID = 0


@dataclass(frozen=True, slots=True)
class PendingFollowup:
    """Câu hỏi thăm đang chờ. Cùng lý do hình dạng với `PastConversation`: chỉ có CHỮ, không có
    `answers`, không có `TriState` - không có gì để tầng gọi nhét nhầm vào snapshot phiên mới."""

    user_id: int
    question: str
    generated_at: datetime


class SqliteFollowupStore:
    """API ba hàm: `save` / `pending` / `mark_asked`."""

    def save(self, user_id: int, question: str, *, source_ids: list[str] | None = None) -> None:
        """Ghi đè câu hỏi thăm hiện tại của người dùng, và đặt lại `asked_at = None`.

        Ghi đè chứ không thêm hàng: thứ lượt mở cần là câu hỏi HIỆN TẠI. Đặt lại `asked_at` vì câu
        vừa sinh là câu MỚI - nó được chắt lọc từ một phiên vừa đóng mà câu cũ chưa từng biết tới.

        `question` rỗng vẫn GHI một hàng (rỗng). "Đã chắt lọc rồi, không có gì để hỏi" là một trạng
        thái khác với "chưa từng chắt lọc", và chỉ có hàng rỗng mới phân biệt được hai cái - thiếu nó
        thì `exists()` trả `False` và lượt mở của một người dùng chưa có lịch sử sẽ chạy lại phép
        chắt lọc ở MỌI lần mở, đúng thứ bảng này sinh ra để tránh."""
        try:
            with session_scope() as db:
                row = db.get(FollowupQuestionRow, user_id)
                if row is None:
                    row = FollowupQuestionRow(user_id=user_id)
                    db.add(row)
                row.question = question.strip()
                row.generated_at = datetime.now(timezone.utc)
                row.asked_at = None
                row.source_conversation_ids = list(source_ids or [])
        except Exception as error:
            logger.warning("followup persist failed user=%s: %s", user_id, error)

    def pending(self, user_id: int, *, max_age_days: int | None = None) -> PendingFollowup | None:
        """Câu hỏi CHƯA HỎI của chính người dùng này, hoặc `None`.

        `max_age_days` là trần tuổi ở ĐƯỜNG ĐỌC, không phải ở đường ghi: câu hỏi được sinh lúc phiên
        trước đóng, còn nó có còn hợp lý hay không thì chỉ biết được lúc người bệnh quay lại."""
        if user_id == GUEST_USER_ID:
            return None
        try:
            with session_scope() as db:
                row = db.get(FollowupQuestionRow, user_id)
                if row is None or row.asked_at is not None or not (row.question or "").strip():
                    return None
                generated_at = _aware(row.generated_at)
                if max_age_days is not None:
                    age = datetime.now(timezone.utc) - generated_at
                    if age.days > max_age_days:
                        return None
                return PendingFollowup(
                    user_id=user_id, question=row.question.strip(), generated_at=generated_at,
                )
        except Exception as error:
            logger.warning("followup read failed user=%s: %s", user_id, error)
            return None

    def exists(self, user_id: int) -> bool:
        """Đã từng chắt lọc cho người dùng này chưa - KHÁC với "có câu đang chờ".

        Hai câu hỏi khác nhau và lượt mở cần cả hai: chưa từng chắt lọc thì phải chắt lọc bù (người
        dùng đã có lịch sử từ trước khi bảng này tồn tại); còn đã chắt lọc rồi mà không có câu đang
        chờ thì im lặng - hỏi lại đúng câu vừa hỏi lần trước là tiếng ồn, không phải quan tâm."""
        try:
            with session_scope() as db:
                return db.get(FollowupQuestionRow, user_id) is not None
        except Exception as error:
            logger.warning("followup exists failed user=%s: %s", user_id, error)
            return True  # lỗi DB ⇒ coi như đã có, để lượt mở KHÔNG chạy thêm phép chắt lọc bù

    def mark_asked(self, user_id: int) -> None:
        """Đóng dấu đã hỏi. Tách khỏi `pending` chứ không đóng dấu ngay trong lúc đọc: `pending` được
        gọi ở cả chỗ chỉ muốn XEM (log, màn hình điều dưỡng), và một hàm đọc có tác dụng phụ sẽ âm
        thầm tiêu mất câu hỏi ở đúng những chỗ đó."""
        try:
            with session_scope() as db:
                row = db.get(FollowupQuestionRow, user_id)
                if row is not None:
                    row.asked_at = datetime.now(timezone.utc)
        except Exception as error:
            logger.warning("followup mark failed user=%s: %s", user_id, error)


followup_store = SqliteFollowupStore()


def _aware(value: datetime) -> datetime:
    """SQLite trả `datetime` NAIVE kể cả với `DateTime(timezone=True)` - trừ thẳng cho một mốc aware
    sẽ ném `TypeError` giữa lượt mở phiên. Coi bản ghi naive là UTC, đúng thứ `save` đã ghi."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

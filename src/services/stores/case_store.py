"""Kho case, lưu bằng SQLite (`triage_cases`).

API công khai (`get`/`save`/`list_cases`) GIỮ NGUYÊN so với bản in-memory - mọi caller không phải sửa
gì. Chỉ chỗ lưu là đổi: case sống qua restart, thay vì mất sạch cùng tiến trình.

Vì sao trước đây in-memory là hỏng chứ không chỉ bất tiện: một ca cấp cứu đang chờ điều dưỡng duyệt
sẽ biến mất khi Render redeploy, và không ai biết nó từng tồn tại. `/chat` có sẵn nhánh "phiên đã mất
do restart thì mở phiên mới" - nhánh đó vá được phần hội thoại, không vá được phần case đã bàn giao.

Hình dạng bảng và lý do dùng cột JSON: xem `src/models/case_record.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from src.database import session_scope
from src.models.case_record import TriageCaseRow
from src.models.schemas import TriageCase


class SqliteCaseStore:
    def get(self, case_id: str) -> TriageCase | None:
        with session_scope() as session:
            row = session.get(TriageCaseRow, case_id)
            return TriageCase.model_validate(row.payload) if row else None

    def save(self, triage_case: TriageCase) -> TriageCase:
        triage_case.updated_at = datetime.now(timezone.utc)
        with session_scope() as session:
            row = session.get(TriageCaseRow, triage_case.case_id)
            if row is None:
                row = TriageCaseRow(case_id=triage_case.case_id, created_at=triage_case.created_at)
                session.add(row)
            self._write_columns(row, triage_case)
        return triage_case

    def list_cases(self) -> list[TriageCase]:
        with session_scope() as session:
            rows = session.execute(select(TriageCaseRow).order_by(TriageCaseRow.created_at)).scalars()
            return [TriageCase.model_validate(row.payload) for row in rows]

    def _write_columns(self, row: TriageCaseRow, triage_case: TriageCase) -> None:
        """Cột phẳng chỉ để TRUY VẤN; `payload` mới là bản ghi thật.

        Ghi đè lại toàn bộ cột phẳng mỗi lần lưu chứ không chỉ khi thấy đổi: `TriageCase` được dựng
        lại từ đầu mỗi lượt chat (`symptom_case_bridge` là hàm thuần), nên "giá trị cũ" trong row
        không phải nguồn đáng tin để so."""
        row.patient_id = triage_case.patient_id
        row.status = triage_case.status.value
        row.priority = (
            triage_case.triage_proposal.priority.value if triage_case.triage_proposal else None
        )
        row.has_red_flag = bool(triage_case.red_flags)
        row.updated_at = triage_case.updated_at
        row.payload = triage_case.model_dump(mode="json")


class InMemoryCaseStore:
    """Bản dict thuần, CÙNG API với `SqliteCaseStore`.

    Không phải tàn dư: `TriagePipeline` nhận `store=` tường minh, và test của nó cần một kho cô lập
    mà không phải dựng DB tạm cho từng ca. Đây là chỗ dùng duy nhất - code sản phẩm luôn đi qua
    singleton `case_store` bên dưới. Đặt cạnh nhau trong một file để hai bản không lệch API: sửa
    `SqliteCaseStore` mà quên bản này thì test dựng `InMemoryCaseStore()` sẽ đỏ ngay."""

    def __init__(self) -> None:
        self._cases: dict[str, TriageCase] = {}

    def get(self, case_id: str) -> TriageCase | None:
        return self._cases.get(case_id)

    def save(self, triage_case: TriageCase) -> TriageCase:
        triage_case.updated_at = datetime.now(timezone.utc)
        self._cases[triage_case.case_id] = triage_case
        return triage_case

    def list_cases(self) -> list[TriageCase]:
        return list(self._cases.values())


case_store = SqliteCaseStore()

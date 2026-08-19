"""Điều dưỡng sửa được MỌI trường của phiếu, kể cả red flag (§4.4 + §7.3 mục 5-7).

Trước đây red flag là banner đọc-chỉ và form duyệt chỉ có ba ô, tức là người có thẩm quyền lâm sàng
cao nhất trong luồng lại là người duy nhất không sửa được phiếu. Việc mở quyền đó KHÔNG được kéo
theo hai thứ khác, và phần lớn test ở đây canh đúng hai thứ đó:

- bản ghi do hệ thống sinh phải BẤT BIẾN (`generated_value` sống sót qua mọi lần sửa);
- `escalation_lock` của agent (chặn MODEL tự hạ escalation TRONG phiên) không được nới theo.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.database import configure_database, create_tables, dispose_database
from src.models.schemas import (
    CaseStatus,
    HITLAction,
    NurseFieldEditRequest,
    NurseReviewRequest,
    RedFlagFinding,
    TriageCase,
    TriagePriority,
    TriageProposal,
)
from src.services.sessions.hitl_review import human_review_service
from src.services.stores.approval_store import approval_store
from src.services.stores.case_store import case_store

NURSE_ID = 42
RED_FLAG_CODE = "RF-07"


@pytest.fixture(autouse=True)
def _fresh_database(tmp_path):
    configure_database(f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}")
    create_tables()
    try:
        yield
    finally:
        dispose_database()


def _case(*, notice_sent: bool = False) -> TriageCase:
    triage_case = TriageCase(
        case_id="case-1",
        patient_id=1,
        status=CaseStatus.NEEDS_NURSE_REVIEW,
        created_at=datetime.now(timezone.utc),
        triage_proposal=TriageProposal(priority=TriagePriority.URGENT, reason="test"),
        red_flags=[RedFlagFinding(code=RED_FLAG_CODE, label="Co giật đang diễn ra", matched_fields=[])],
        emergency_notice_sent=notice_sent,
    )
    case_store.save(triage_case)
    return triage_case


def _review(**kwargs) -> None:
    human_review_service.review(
        "case-1",
        NurseReviewRequest(action=HITLAction.APPROVE, approved_response="ok", **kwargs),
        nurse_id=NURSE_ID,
        nurse_name="DD A",
    )


def _lower_red_flag(reason: str = "Đã gọi lại xác minh, người bệnh không co giật.") -> None:
    _review(field_edits=[NurseFieldEditRequest(field=f"red_flags.{RED_FLAG_CODE}", value=False, reason=reason)])


# --- §7.3 mục 5: hạ được, nhưng bản gốc phải còn -------------------------------------------------


def test_nurse_can_lower_a_red_flag_and_the_generated_value_survives():
    _case()

    _lower_red_flag()

    edits = case_store.get("case-1").nurse_field_edits
    assert len(edits) == 1
    assert edits[0].generated_value is True, "mất `generated_value` là mất khả năng trả lời 'hệ thống có bắt được không'"
    assert edits[0].current_value is False
    assert edits[0].edited_by == str(NURSE_ID)
    assert edits[0].reason


def test_the_generated_record_itself_is_never_overwritten():
    """Overlay, không phải ghi đè: `red_flags` của case vẫn nguyên như AI sinh ra."""
    _case()

    _lower_red_flag()

    assert [flag.code for flag in case_store.get("case-1").red_flags] == [RED_FLAG_CODE]


def test_editing_the_same_field_twice_keeps_the_original_generated_value():
    """Sửa hai lần liên tiếp thì `generated_value` vẫn là giá trị của AI, không phải giá trị điều
    dưỡng đặt ở lần đầu - nếu không, sau hai lần sửa phiếu đọc ra như thể AI vốn đã nói thế."""
    _case()

    _lower_red_flag()
    _review(field_edits=[NurseFieldEditRequest(field=f"red_flags.{RED_FLAG_CODE}", value=True, reason="")])

    edits = case_store.get("case-1").nurse_field_edits
    assert len(edits) == 2
    assert all(edit.generated_value is True for edit in edits)


def test_lowering_a_red_flag_without_a_reason_is_refused():
    """Ma sát CỐ Ý, và là loại ma sát duy nhất được giữ trong §4.4."""
    _case()

    with pytest.raises(ValueError):
        _lower_red_flag(reason="   ")

    assert case_store.get("case-1").nurse_field_edits == []


def test_a_refused_edit_does_not_let_the_approval_through():
    """Sửa trường chạy TRƯỚC hành động: hạ cờ thiếu lý do phải làm hỏng CẢ lời gọi, không được để
    `approve` đi qua rồi mới báo lỗi phần sửa."""
    _case()

    with pytest.raises(ValueError):
        _lower_red_flag(reason="")

    assert case_store.get("case-1").status is CaseStatus.NEEDS_NURSE_REVIEW
    assert approval_store.get("case-1") is None


def test_raising_a_field_that_is_not_a_red_flag_needs_no_reason():
    """Ma sát chỉ đặt ở chỗ đắt. Sửa một trường thường mà cũng bắt ghi lý do thì điều dưỡng sẽ gõ
    cho xong, và lý do trên red flag mất luôn giá trị."""
    _case()

    _review(field_edits=[NurseFieldEditRequest(field="summary.onset", value="2 ngày trước")])

    assert case_store.get("case-1").nurse_field_edits[0].current_value == "2 ngày trước"


# --- §7.3 mục 5: audit ---------------------------------------------------------------------------


def test_each_edited_field_leaves_its_own_audit_line():
    """Câu hỏi cần trả lời sau sự cố là "ai đã bỏ dấu hiệu nào đi vì lý do gì" - một dòng ghi cả năm
    trường thì không trả lời được."""
    _case()

    _review(
        field_edits=[
            NurseFieldEditRequest(field=f"red_flags.{RED_FLAG_CODE}", value=False, reason="đã xác minh lại"),
            NurseFieldEditRequest(field="summary.onset", value="2 ngày trước"),
        ]
    )

    actions = [entry.action for entry in approval_store.audit_for_case("case-1")]
    assert f"edit_field:red_flags.{RED_FLAG_CODE}" in actions
    assert "edit_field:summary.onset" in actions


def test_the_audit_line_carries_the_reason_for_lowering():
    _case()

    _lower_red_flag(reason="Đã gọi lại xác minh.")

    entry = next(e for e in approval_store.audit_for_case("case-1") if e.action.startswith("edit_field:red_flags"))
    assert entry.old_value == "True"
    assert entry.new_value == "False"
    assert entry.reason == "Đã gọi lại xác minh."


# --- §7.3 mục 7: việc không rút lại được ---------------------------------------------------------


def test_lowering_after_the_patient_already_saw_the_emergency_message_is_marked_irreversible():
    """Hạ cờ về sau chỉ đổi phiếu và luồng xử trí - KHÔNG xoá được cái người bệnh đã đọc. Cờ này là
    thứ UI dựa vào để nói rõ điều đó tại chỗ."""
    _case(notice_sent=True)

    _lower_red_flag()

    assert case_store.get("case-1").nurse_field_edits[0].notice_already_sent is True


def test_the_notice_flag_is_one_way():
    """Nó ghi lại một SỰ KIỆN đã xảy ra, không phải trạng thái hiện tại của ca."""
    _case(notice_sent=True)

    _lower_red_flag()

    assert case_store.get("case-1").emergency_notice_sent is True


# --- §7.3 mục 6: khoá của agent KHÔNG được nới theo ----------------------------------------------


def test_the_review_path_cannot_touch_a_running_session_escalation_lock():
    """Hai khái niệm bị gộp làm một trước đây, và tách chúng ra chính là nội dung §4.4:

    - `escalation_lock` chặn MODEL tự hạ escalation TRONG phiên -> giữ nguyên, không có công tắc tắt;
    - quyền của điều dưỡng ở bước duyệt -> mở.

    Ràng buộc này đang được giữ bằng KIẾN TRÚC chứ không bằng một câu `if`: đường duyệt chỉ đọc/ghi
    `TriageCase` trong `case_store`, nó không có tham chiếu nào tới `symptom_protocol.session`. Test
    canh đúng điều đó, vì nếu một hôm ai đó nối hai bên lại thì `escalation_lock` mất ý nghĩa."""
    import ast
    import inspect

    from src.services.sessions import hitl_review

    tree = ast.parse(inspect.getsource(hitl_review))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    # Kiểm IMPORT chứ không grep văn bản: docstring của module CÓ nhắc `escalation_lock` - đúng chỗ
    # nên nhắc, vì nó giải thích tại sao hai khái niệm không được gộp.
    assert not any("symptom_protocol" in name for name in imported)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "escalation_lock"
        for node in ast.walk(tree)
    )

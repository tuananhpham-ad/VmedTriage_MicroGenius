"""Hai output summary (§4.3 + ADR-006): `summary_text` và `summary_json`.

Bất biến của cả file: **cả hai đọc CÙNG MỘT snapshot đã validate.** Đó là điều kiện duy nhất khiến
chúng không mâu thuẫn nhau, và cũng là lý do bản render theo field dùng được làm BẢN ĐỐI CHỨNG cho
bản văn xuôi.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.models.schemas import HandoffSummary, RedFlagFinding, TriagePriority
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.sessions import narrative, summary_render
from src.services.symptom_protocol import output_guard

ADULT: dict[str, object] = {
    "age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self",
}


# --- chế độ (b): render TẤT ĐỊNH theo field ------------------------------------------------------


def test_only_true_and_false_values_are_rendered_to_summary_text():
    """`unknown` vẫn được giữ nội bộ để biết thiếu gì, nhưng không được dùng để VIẾT summary."""
    answers = dict(ADULT, fever_reported="true", rigors="false")

    result = summary_render.field_summary(FEVER_PROTOCOL, answers)
    text = result.as_text()

    assert any("sốt" in label.casefold() for label in result.reported)
    assert result.denied, "field = false phải vào nhóm PHỦ NHẬN, không biến mất"
    assert result.unknown_safety, "field an toàn chưa hỏi vẫn được giữ cho guard nội bộ"
    assert "Triệu chứng ghi nhận" in text
    assert "Người bệnh phủ nhận" in text
    assert "Chưa xác định" not in text
    assert "unknown" not in text.casefold()


def test_only_safety_fields_show_up_as_unknown():
    """Unknown chỉ còn là dữ liệu guard nội bộ, không phải block được render vào summary."""
    result = summary_render.field_summary(FEVER_PROTOCOL, dict(ADULT))
    safety = {FEVER_PROTOCOL.fields_by_key[key].label for key in FEVER_PROTOCOL.safety_signal_fields}

    assert set(result.unknown_safety).issubset(safety)
    assert result.as_text() == ""


def test_an_empty_block_is_not_rendered():
    """Quy tắc render ADR-006: trường rỗng không xuất."""
    text = summary_render.FieldSummary(reported=["Sốt"]).as_text()

    assert "Triệu chứng ghi nhận" in text
    assert "Người bệnh phủ nhận" not in text


# --- chế độ (b) là BẢN ĐỐI CHỨNG của chế độ (a) --------------------------------------------------


def test_a_narrative_backed_by_no_field_is_flagged_as_ungrounded():
    """Nếu văn xuôi nói một điều mà không field nào đỡ thì nó đang bịa - kiểm tra RẺ và nên chạy
    tự động (§4.3)."""
    summary = summary_render.FieldSummary(reported=["Sốt"], denied=["Nôn"])

    assert summary_render.narrative_is_grounded("Người bệnh báo sốt từ sáng.", summary) is True
    assert summary_render.narrative_is_grounded("Người bệnh gãy chân trái.", summary) is False


def test_an_empty_record_is_never_called_a_fabrication():
    """Phiếu không có field nào thì không có gì để đối chứng - báo "bịa" ở đó là báo sai."""
    assert summary_render.narrative_is_grounded("bất cứ gì", summary_render.FieldSummary()) is True


def test_the_narrative_guard_does_not_demand_a_question_mark():
    """Guard của VĂN XUÔI khác guard của CÂU HỎI. Chạy bản tóm tắt qua `output_guard.check` thì mọi
    bản tóm tắt đều bị chặn vì thiếu dấu hỏi, và cách "sửa" nhanh nhất là nới guard của câu hỏi."""
    verdict = output_guard.check_narrative("Người bệnh báo sốt hai ngày, phủ nhận nôn.")

    assert verdict.ok is True


@pytest.mark.parametrize(
    "text",
    ["Người bệnh bị sốt xuất huyết.", "Người bệnh nên uống paracetamol và đi khám ngay."],
)
def test_the_narrative_guard_still_blocks_diagnosis_and_advice(text: str):
    """Ba kiểm tra an toàn giữ nguyên - chúng không dính gì tới việc văn bản là câu hỏi hay không."""
    assert output_guard.check_narrative(text).ok is False


# --- fallback: model chết thì phiếu vẫn đọc được -------------------------------------------------


def test_a_dead_model_falls_back_to_the_deterministic_text(monkeypatch):
    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=TimeoutError("chết")))
    summary = summary_render.field_summary(FEVER_PROTOCOL, dict(ADULT, fever_reported="true"))

    text, source = narrative.build_narrative(summary)

    assert source == "provider_unavailable"
    assert text == summary.as_text(), "phiếu vẫn phải đọc được khi provider hỏng"


def test_a_fabricated_narrative_is_replaced_by_the_deterministic_text(monkeypatch):
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(
            text="Người bệnh gãy tay phải sau tai nạn giao thông.", provider="f", model="f",
        )),
    )
    summary = summary_render.field_summary(FEVER_PROTOCOL, dict(ADULT, fever_reported="true"))

    text, source = narrative.build_narrative(summary)

    assert output_guard.VIOLATION_UNGROUNDED in source
    assert text == summary.as_text()


def test_an_empty_record_produces_no_narrative_at_all():
    """Chưa thu được field nào - bịa ra một đoạn văn ở đây là đúng thứ nguyên tắc 3 cấm."""
    text, source = narrative.build_narrative(summary_render.FieldSummary())

    assert text == ""
    assert source == "empty_record"


# --- summary_json -> bảng ISBAR ------------------------------------------------------------------


def _summary(**kwargs) -> HandoffSummary:
    return HandoffSummary(chief_complaint="Sốt 39 độ", **kwargs)


def test_isbar_maps_the_flat_schema_into_five_blocks():
    """ADR-006 mục 1: schema lưu trữ vẫn PHẲNG, việc nhóm xảy ra ở renderer. Đổi bố cục bảng là sửa
    hàm này, không phải migrate dữ liệu."""
    blocks = summary_render.to_isbar(
        _summary(
            age="30 tuổi", sex="Nam", onset="2 ngày trước",
            allergies="false", comorbidities=["Tăng huyết áp"],
            red_flags=[RedFlagFinding(code="RF-07", label="Khó thở nặng", matched_fields=[])],
            proposed_action="Đề xuất khám sớm",
        )
    )

    assert set(blocks) <= set(summary_render.ISBAR_BLOCKS)
    assert "Tuổi" in blocks["I"]
    assert "Lý do vào viện" in blocks["S"]
    assert "Bệnh nền" in blocks["B"]
    assert "Dấu hiệu nguy hiểm phát hiện" in blocks["A"]
    assert "Đề xuất xử trí" in blocks["R"]


def test_an_empty_field_is_not_rendered_but_a_false_one_is():
    """`False` và `0` KHÔNG phải rỗng: `is_complete=False` là đúng thứ điều dưỡng cần thấy, mà một
    phép kiểm `if not value` sẽ nuốt mất nó."""
    blocks = summary_render.to_isbar(_summary(is_complete=False, stop_reason="USER_UNCOOPERATIVE"))

    assert blocks["A"]["Phiếu đã đầy đủ"] is False
    assert "Khởi phát" not in blocks.get("A", {})


def test_isbar_does_not_render_unknown_or_missing_information():
    blocks = summary_render.to_isbar(
        _summary(allergies="unknown", missing_information=["cyanosis"], is_complete=False),
    )

    assert "Dị ứng" not in blocks.get("B", {})
    assert "Thông tin còn thiếu" not in blocks.get("A", {})
    assert blocks["A"]["Phiếu đã đầy đủ"] is False


def test_the_triage_label_says_plainly_that_code_filled_it():
    """`Triage Category` nằm trong khối [I] đúng như template - và nó do CODE tất định điền, không do
    LLM. Đó là chỗ dễ bị hiểu nhầm nhất khi người mới đọc phiếu."""
    blocks = summary_render.to_isbar(_summary(proposed_priority=TriagePriority.URGENT))

    label = next(key for key in blocks["I"] if "ưu tiên đề xuất" in key)
    assert "KHÔNG do LLM" in label


def test_the_r_block_is_a_proposal_not_a_completed_action():
    """Template viết `AI Action: Khuyên bệnh nhân đến bệnh viện ngay` - đọc theo mặt chữ thì AI đã
    khuyên bệnh nhân TRƯỚC khi điều dưỡng duyệt, ngược `CLAUDE.md` nguyên tắc 1."""
    blocks = summary_render.to_isbar(_summary(proposed_action="Khám sớm"))

    assert "Đề xuất xử trí" in blocks["R"]
    assert blocks["R"]["Trạng thái duyệt"] == "pending_nurse_review"


# --- lỗi bịa phủ định: ca thật gặp ngày 2026-08-19 -----------------------------------------------


def test_a_narrative_that_denies_an_unknown_field_is_rejected():
    """CA CHẶN, và nó KHÔNG phải giả định - đây là nguyên văn model trả về khi chạy ca "bé 2 tháng
    sốt 38" qua provider thật.

    Toàn bộ field bị "không ghi nhận" ở đây đang là `unknown` - chưa ai hỏi tới. Phiếu đọc ra như thể
    đã hỏi và người nhà nói không có, mà đó là hai hồ sơ lâm sàng khác hẳn nhau."""
    summary = summary_render.FieldSummary(
        reported=["Người dùng khai có sốt"],
        unknown_safety=["Cứng gáy", "Đang co giật", "Mức tỉnh táo"],
    )
    text = (
        "Người bệnh khai nhận có tình trạng sốt. "
        "Người bệnh không ghi nhận các triệu chứng như co giật, cứng gáy, yếu liệt."
    )

    invented = summary_render.narrative_invents_denials(text, summary)

    assert "Cứng gáy" in invented
    verdict = output_guard.check_narrative(text, invented_denials=tuple(invented))
    assert verdict.ok is False
    assert output_guard.VIOLATION_INVENTED_DENIAL in verdict.violations


def test_saying_a_field_is_undetermined_is_not_an_invented_denial():
    """Chống báo nhầm: "chưa xác định được có cứng gáy hay không" là câu ĐÚNG, dù nó chứa chữ
    "không". Không có ngoại lệ này thì guard chặn cả những bản tóm tắt viết chuẩn."""
    summary = summary_render.FieldSummary(unknown_safety=["Cứng gáy"])

    assert summary_render.narrative_invents_denials(
        "Chưa xác định được người bệnh có cứng gáy hay không.", summary,
    ) == []


def test_denying_a_field_the_patient_actually_denied_is_fine():
    """Field = `false` là dữ kiện THẬT - viết "người bệnh phủ nhận nôn" ở đó là đúng, không phải bịa."""
    summary = summary_render.FieldSummary(denied=["Nôn"], unknown_safety=["Cứng gáy"])

    assert summary_render.narrative_invents_denials("Người bệnh không có nôn.", summary) == []


def test_the_check_reads_clause_by_clause_not_whole_text():
    """Một đoạn nói đúng ở câu đầu và bịa ở câu ba sẽ lọt hết nếu chỉ kiểm toàn văn."""
    summary = summary_render.FieldSummary(unknown_safety=["Cứng gáy"])
    text = "Chưa xác định được nhiều thông tin. Người bệnh không có cứng gáy."

    assert summary_render.narrative_invents_denials(text, summary) == ["Cứng gáy"]


def test_a_red_flag_ticket_is_not_marked_complete():
    """Sửa sau khi chạy thật: ca escalate ở lượt 1 có hơn 30 field M0/M1 còn `unknown` mà phiếu vẫn
    ghi "đã đầy đủ". Dừng vì chốt đỏ là kết thúc ĐÚNG, nhưng phiếu thì vẫn CHƯA ĐẦY ĐỦ - hai chuyện
    khác nhau."""
    from src.services.sessions import symptom_case_bridge

    assert "RED_FLAG" in symptom_case_bridge._INCOMPLETE_STOP_REASONS


def test_a_blanket_denial_with_no_named_field_is_also_rejected():
    """CA CHẶN THỨ HAI, cũng là nguyên văn model trả về khi chạy thật ngày 2026-08-19:

        "Người bệnh nói không có các triệu chứng khác."

    trong khi `denied` RỖNG - người bệnh chưa phủ nhận điều gì cả. Bản detector đầu tiên không bắt
    được vì nó đi tìm NHÃN FIELD trong câu, mà câu này cố tình không nêu tên gì. Đây là ca tệ hơn:
    nó đóng sạch mọi field còn lại trong đầu người đọc và không để lại cái tên nào để truy ngược."""
    summary = summary_render.FieldSummary(
        reported=["Người dùng khai có sốt"], unknown_safety=["Cứng gáy"],
    )

    invented = summary_render.narrative_invents_denials(
        "Người bệnh có sốt. Người bệnh nói không có các triệu chứng khác.", summary,
    )

    assert invented, "phủ định gộp không có gì đỡ phải bị bắt"
    assert output_guard.check_narrative("x", invented_denials=tuple(invented)).ok is False


def test_a_denial_naming_a_genuinely_denied_field_passes():
    """Quy tắc là "có field đỡ hay không", không phải "có chữ không hay không". Người bệnh đã phủ
    nhận nôn thì viết "không có nôn" là ĐÚNG, không phải bịa."""
    summary = summary_render.FieldSummary(denied=["Nôn"], unknown_safety=["Cứng gáy"])

    assert summary_render.narrative_invents_denials("Người bệnh không có nôn.", summary) == []


def test_a_narrative_with_no_denial_at_all_is_left_alone():
    summary = summary_render.FieldSummary(reported=["Sốt"], unknown_safety=["Cứng gáy"])

    assert summary_render.narrative_invents_denials("Người bệnh có sốt cao từ sáng.", summary) == []

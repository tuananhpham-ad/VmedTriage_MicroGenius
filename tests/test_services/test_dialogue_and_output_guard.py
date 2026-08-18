"""`DialoguePolicy` (§6.1-6.3) + `output_guard` (§6.5).

Hai tầng này là phần "trải nghiệm hội thoại" của §8.1 loại 2 - nới CÁCH DIỄN ĐẠT, không đụng tầng an
toàn. Vì thế file này kiểm hai điều tách bạch:

- policy có ĐỦ hàng cho mọi `dialogue_act` (bảng thiếu một tổ hợp là một nhánh hội thoại không ai
  viết, và nó sẽ lẩn trong `else` cho tới lúc gặp người bệnh thật);
- guard có chặn đúng thứ phải chặn, và KHÔNG chặn nhầm câu hợp lệ - chặn nhầm không gây mất an toàn
  (rơi về `script_hint`) nhưng làm mất đúng thứ P3 vừa xây, nên nó cũng là lỗi.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import dialogue, output_guard
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.protocol import clusters_by_id
from src.services.symptom_protocol.session import ProtocolSessionStore


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    output_guard.reset_rejection_counts()


_CLUSTER = QuestionCluster("T-01", "1", ("fever_reported", "temp_c"), script_hint="Có sốt không, bao nhiêu độ")


def _plan(act: dialogue.DialogueAct, **kwargs) -> dialogue.ResponsePlan:
    plan = dialogue.build_response_plan(FEVER_PROTOCOL, _CLUSTER, act=act, answers={}, **kwargs)
    assert plan is not None
    return plan


# --- bảng policy ----------------------------------------------------------------------------------


def test_every_dialogue_act_has_a_policy_row() -> None:
    """Bài test mà cả thiết kế "bảng tra cứu" tồn tại để có được: duyệt TOÀN BẢNG, không phải nghĩ
    ra từng ca. Thêm một `DialogueAct` mà quên thêm hàng thì đỏ ngay tại đây."""
    assert set(dialogue.DIALOGUE_POLICY) == set(dialogue.DialogueAct)


@pytest.mark.parametrize("act", list(dialogue.DialogueAct))
def test_build_response_plan_works_for_every_act(act: dialogue.DialogueAct) -> None:
    plan = _plan(act)
    assert plan.act is act
    assert plan.cluster_id == "T-01"
    assert plan.max_questions >= 1


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ("answered", dialogue.DialogueAct.ANSWER),
        ("partial", dialogue.DialogueAct.PARTIAL_ANSWER),
        ("correction", dialogue.DialogueAct.CORRECTION),
        ("asks_question", dialogue.DialogueAct.ASKS_CLARIFICATION),
        ("evasive", dialogue.DialogueAct.CANNOT_ANSWER),
        ("non_answer", dialogue.DialogueAct.OFF_TOPIC),
    ],
)
def test_answer_quality_maps_to_a_dialogue_act(quality: str, expected: dialogue.DialogueAct) -> None:
    assert dialogue.dialogue_act_from_quality(quality) is expected


def test_an_unknown_quality_label_falls_back_to_answer() -> None:
    """Nhãn lạ do model bịa không được kích hoạt nhánh UX đặc biệt nào."""
    assert dialogue.dialogue_act_from_quality("hallucinated") is dialogue.DialogueAct.ANSWER
    assert dialogue.dialogue_act_from_quality("") is dialogue.DialogueAct.ANSWER


def test_new_symptom_is_decided_by_code_not_by_the_model_label() -> None:
    """`new_symptom` là căn cứ chuyển protocol nên phải do CODE quyết, không lấy từ nhãn model."""
    assert dialogue.dialogue_act_from_quality("answered", new_symptom=True) is dialogue.DialogueAct.NEW_SYMPTOM


def test_a_correction_outranks_new_symptom_when_the_protocol_switches() -> None:
    """Protocol đổi vì hai lý do TRÁI NGƯỢC: nêu thêm triệu chứng, hoặc RÚT LẠI lời khai cũ. Gộp cả
    hai thành `new_symptom` khiến đúng lượt đính chính được chào đón như một triệu chứng mới."""
    assert (
        dialogue.dialogue_act_from_quality("correction", new_symptom=True)
        is dialogue.DialogueAct.CORRECTION
    )


def test_the_acknowledgement_can_name_a_field_the_new_protocol_does_not_declare() -> None:
    """Đúng lượt đổi protocol, dữ kiện GÂY RA việc đổi thường không có trong protocol mới: "mình
    không sốt" đẩy phiên sang `general`, mà `general` không khai `fever_reported`. Không có
    `label_protocol` thì lượt đính chính quan trọng nhất lại là lượt duy nhất không được công nhận."""
    from src.services.engines.generic_protocol import GENERIC_PROTOCOL

    assert "fever_reported" not in GENERIC_PROTOCOL.fields_by_key
    plan = dialogue.build_response_plan(
        GENERIC_PROTOCOL, GENERIC_PROTOCOL.clusters[0],
        act=dialogue.DialogueAct.CORRECTION,
        answers={"fever_reported": "false"},
        recent_fields=frozenset({"fever_reported"}),
        label_protocol=FEVER_PROTOCOL,
    )
    assert plan is not None
    assert FEVER_PROTOCOL.fields_by_key["fever_reported"].label in plan.acknowledge


# --- nội dung plan --------------------------------------------------------------------------------


def test_a_meta_question_is_answered_before_asking_again() -> None:
    """§6.2: trả lời câu hỏi của người dùng TRƯỚC, rồi mới hỏi lại một ý - không xin lỗi rồi lặp."""
    plan = _plan(dialogue.DialogueAct.ASKS_CLARIFICATION)
    assert plan.answer_user_question
    assert "GIẢI THÍCH NGẮN" in plan.answer_user_question
    assert plan.rephrase is True


def test_cannot_answer_does_not_repeat_the_same_request() -> None:
    """"Quên/không đo được" là kết quả hợp lệ - lượt sau phải hỏi cách khác, không lặp yêu cầu đo."""
    plan = _plan(dialogue.DialogueAct.CANNOT_ANSWER)
    assert plan.rephrase is True
    assert "cách khác" in plan.answer_user_question


def test_a_correction_is_acknowledged_with_the_corrected_fact() -> None:
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.CORRECTION,
        answers={"fever_reported": "false"},
        recent_fields=frozenset({"fever_reported"}),
    )
    assert plan is not None
    assert "ĐÍNH CHÍNH" in plan.acknowledge_instruction
    assert FEVER_PROTOCOL.fields_by_key["fever_reported"].label in plan.acknowledge
    assert "false" in plan.acknowledge


def test_the_acknowledgement_carries_data_only_never_text_to_copy() -> None:
    """Trộn hướng dẫn ngôi thứ ba vào cùng chuỗi với dữ kiện thì model chép thẳng ra tin nhắn, và
    người bệnh đọc được một câu nói VỀ mình - lỗi đo được trên transcript thật với deepseek-chat."""
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.ANSWER,
        answers={"fever_reported": "true"},
        recent_fields=frozenset({"fever_reported"}),
    )
    assert plan is not None
    assert "Người bệnh" not in plan.acknowledge
    assert plan.acknowledge == f"{FEVER_PROTOCOL.fields_by_key['fever_reported'].label} = true"


def test_the_acknowledgement_stays_short_and_only_mentions_new_facts() -> None:
    """§6.3: công nhận NGẮN điều vừa nhận được, không đọc lại toàn bộ hồ sơ."""
    answers = {"fever_reported": "true", "temp_c": "39", "age_value": "20", "sex": "male"}
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.ANSWER,
        answers=answers,
        recent_fields=frozenset({"fever_reported", "temp_c", "age_value"}),
    )
    assert plan is not None
    assert plan.acknowledge.count(";") == dialogue._ACKNOWLEDGE_LIMIT - 1
    # Field đã biết từ lượt TRƯỚC không được nhắc lại - nó không phải điều vừa nghe.
    assert FEVER_PROTOCOL.fields_by_key["sex"].label not in plan.acknowledge


def test_an_unknown_recent_field_is_not_acknowledged() -> None:
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.ANSWER,
        answers={"fever_reported": "unknown"},
        recent_fields=frozenset({"fever_reported"}),
    )
    assert plan is not None
    assert plan.acknowledge == ""


def test_a_greeting_acknowledges_nothing() -> None:
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.GREETING,
        answers={"fever_reported": "true"},
        recent_fields=frozenset({"fever_reported"}),
    )
    assert plan is not None
    assert plan.acknowledge == ""


def test_switching_protocol_adds_a_transition_sentence() -> None:
    """§6.3: không để người dùng thấy hệ thống đột ngột hỏi một checklist mới."""
    plan = _plan(dialogue.DialogueAct.NEW_SYMPTOM, protocol_switched=True)
    assert plan.transition_note == dialogue.PROTOCOL_SWITCH_NOTE


def test_missing_fields_and_max_questions_come_from_the_cluster_and_batch() -> None:
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, _CLUSTER,
        act=dialogue.DialogueAct.ANSWER,
        answers={"fever_reported": "true"},
        parts=3,
    )
    assert plan is not None
    assert plan.missing_fields == ("temp_c",)
    assert plan.max_questions == 3


def test_no_cluster_means_no_plan() -> None:
    """Hết cụm thì không có gì để nói - bịa ra một câu là cách nhanh nhất hỏi ngoài checklist."""
    assert dialogue.build_response_plan(FEVER_PROTOCOL, None, act=dialogue.DialogueAct.ANSWER, answers={}) is None


# --- output_guard ---------------------------------------------------------------------------------


def _check(text: str, *, answers: dict | None = None, cluster: QuestionCluster = _CLUSTER, parts: int = 1):
    plan = dialogue.build_response_plan(
        FEVER_PROTOCOL, cluster, act=dialogue.DialogueAct.ANSWER, answers=answers or {}, parts=parts,
    )
    assert plan is not None
    return output_guard.check(
        text, plan=plan, protocol=FEVER_PROTOCOL, cluster=cluster, answers=answers or {},
    )


def test_a_clean_question_passes() -> None:
    assert _check("Hiểu rồi ạ.\n\nHiện tại mình có thấy sốt không ạ?").ok


def test_a_message_without_a_question_is_blocked() -> None:
    result = _check("Cảm ơn bạn đã chia sẻ.")
    assert not result.ok
    assert output_guard.VIOLATION_NOT_A_QUESTION in result.violations


def test_more_questions_than_the_plan_allows_is_blocked() -> None:
    result = _check("Bạn sốt không? Bao nhiêu độ? Từ khi nào? Có ho không?")
    assert not result.ok
    assert output_guard.VIOLATION_TOO_MANY_QUESTIONS in result.violations


def test_a_batched_plan_allows_more_question_marks() -> None:
    assert _check("Bạn sốt không? Bao nhiêu độ? Từ khi nào?", parts=3).ok


def test_naming_a_disease_is_blocked() -> None:
    result = _check("Có thể bạn bị sốt xuất huyết, bạn sốt bao nhiêu độ?")
    assert not result.ok
    assert output_guard.VIOLATION_DIAGNOSIS in result.violations


def test_a_disease_name_that_the_checklist_itself_asks_about_is_allowed() -> None:
    """Fever Q4-07 hỏi "xung quanh có ai bị SXHD/cúm/sởi/tay chân miệng không" - đó là bối cảnh phơi
    nhiễm, không phải chẩn đoán. Ngoại lệ xử lý bằng CƠ CHẾ (bám `script_hint`), không bằng danh sách."""
    exposure = clusters_by_id(FEVER_PROTOCOL)["Q4-07"]
    assert "cúm" in exposure.script_hint.casefold()
    assert _check("Xung quanh nhà mình có ai bị cúm hay sởi gần đây không ạ?", cluster=exposure).ok


def test_treatment_advice_is_blocked_even_when_the_checklist_asks_about_medicines() -> None:
    """Checklist được phép HỎI đang dùng thuốc gì; hệ thống không bao giờ được KHUYÊN dùng thuốc."""
    medicine = clusters_by_id(FEVER_PROTOCOL)["Q5-05b"]
    assert _check("Hiện mình có đang dùng kháng sinh nào không ạ?", cluster=medicine).ok
    result = _check("Bạn nên uống thuốc hạ sốt nhé, mình hỏi thêm là sốt mấy ngày rồi?", cluster=medicine)
    assert not result.ok
    assert output_guard.VIOLATION_DIAGNOSIS in result.violations


@pytest.mark.parametrize(
    "text",
    [
        "**Quan trọng**: bạn sốt bao nhiêu độ?",
        "# Câu hỏi\nBạn sốt bao nhiêu độ?",
        "| a | b |\n| --- | --- |\nBạn sốt bao nhiêu độ?",
        "```\nBạn sốt bao nhiêu độ?\n```",
    ],
)
def test_markdown_that_breaks_when_streamed_is_blocked(text: str) -> None:
    """Output đi qua `/chat/stream` nên markdown phải hợp lệ theo TỪNG MẨU - cú pháp cần ký tự đóng
    ở cuối sẽ hiện ra dạng ký tự trần khi người bệnh mới nhận được nửa câu."""
    result = _check(text)
    assert not result.ok
    assert output_guard.VIOLATION_UNSAFE_MARKDOWN in result.violations


def test_bullet_lists_and_line_breaks_are_allowed() -> None:
    """Gạch đầu dòng đóng bằng newline nên an toàn khi stream - đây là định dạng §6.4 khuyến khích."""
    assert _check("Mình hỏi nhanh hai ý:\n- Có sốt không?\n- Bao nhiêu độ?", parts=2).ok


def test_asking_a_field_that_is_already_known_is_blocked() -> None:
    answers = {"access_to_care_minutes": "15"}
    label = FEVER_PROTOCOL.fields_by_key["access_to_care_minutes"].label
    result = _check(f"Cho mình hỏi {label} là bao lâu ạ?", answers=answers)
    assert not result.ok
    assert output_guard.VIOLATION_ASKS_KNOWN_FIELD in result.violations


def test_a_one_word_label_does_not_trigger_a_false_block() -> None:
    """Nhãn một từ xuất hiện tự nhiên trong mọi câu hỏi lâm sàng - dò theo chúng sẽ chặn nhầm, mà
    chặn nhầm là mất đúng thứ P3 vừa làm ra."""
    short = [key for key, spec in FEVER_PROTOCOL.fields_by_key.items() if len(spec.label.split()) == 1]
    assert short, "protocol khong con nhan mot tu - test nay het y nghia"
    key = short[0]
    label = FEVER_PROTOCOL.fields_by_key[key].label
    assert _check(f"Mình hỏi về {label} nhé, bạn thấy thế nào ạ?", answers={key: "true"}).ok


def test_an_empty_message_is_blocked() -> None:
    result = _check("   ")
    assert not result.ok
    assert result.violations == [output_guard.VIOLATION_EMPTY]


def test_rejections_are_counted_for_the_dashboard() -> None:
    """§12: "tỉ lệ bị `output_guard` chặn" là metric của SYNTHESIS. Chặn nhiều = prompt sai, không
    phải guard tốt."""
    _check("Cảm ơn bạn.")
    _check("Cảm ơn bạn.")
    assert output_guard.rejection_counts()[output_guard.VIOLATION_NOT_A_QUESTION] == 2


# --- nối vào luồng thật ---------------------------------------------------------------------------


def _fake_llm(monkeypatch, question_text: str) -> None:
    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text=question_text, provider="fake", model="fake")
        return provider_router.CompletionResult(text=json.dumps({}), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))


def test_a_rendered_question_that_names_a_disease_falls_back_to_the_script_hint(monkeypatch) -> None:
    """Fail thì rơi về văn bản tất định: khô hơn, nhưng chắc chắn nằm trong checklist đã duyệt."""
    _fake_llm(monkeypatch, "Có thể bạn bị sốt xuất huyết rồi, bạn thấy trong người thế nào?")
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session()

    store.submit_message(session.session_id, "Bé 3 tuổi, nam")

    assert session.current_cluster is not None
    assert session.last_question == session.current_cluster.script_hint
    assert output_guard.rejection_counts().get(output_guard.VIOLATION_DIAGNOSIS)


def test_a_clean_rendered_question_is_used_as_is(monkeypatch) -> None:
    _fake_llm(monkeypatch, "Dạ cho mình hỏi bé là nam hay nữ ạ?")
    store = ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.start_session()

    store.submit_message(session.session_id, "Bé 3 tuổi")

    assert session.last_question == "Dạ cho mình hỏi bé là nam hay nữ ạ?"
    assert output_guard.rejection_counts() == {}

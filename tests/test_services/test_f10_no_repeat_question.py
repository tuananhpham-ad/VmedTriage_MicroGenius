"""F10 Fix D: không hỏi lại thứ người bệnh vừa khai.

Lỗi thật: khai đau ngực ở lượt mở rồi vẫn bị hỏi "có bị đau ngực không". Hai lớp cùng thủng, và
phải vá cả hai - lớp một quyết định model được ĐỌC gì, lớp hai quyết định câu sai có RA được tới
người bệnh không:

1. Prompt sinh câu hỏi kèm `script_hint` NGUYÊN VĂN CẢ CỤM kể cả khi cụm chỉ còn thiếu vài field.
   `CP-03` có `script_hint` hỏi cả "đau ngực, khó thở, ho ra máu", mà `chest_pain` nằm trong cả
   `CP-01` lẫn `CP-03` nên nó thường đã được khai từ trước.
2. `output_guard` check 3 bỏ qua mọi nhãn dưới 3 từ, mà nhãn của `chest_pain` là "Đau ngực" - 2 từ.
   Field trung tâm của nhóm trở nên VÔ HÌNH với lưới cuối cùng.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import dialogue, intake_agent, output_guard


def _cluster(protocol, cluster_id: str):
    found = next((c for c in protocol.clusters if c.id == cluster_id), None)
    assert found is not None, f"{cluster_id} không còn trong {protocol.name}"
    return found


# --- lớp 1: prompt của cụm điền dở -----------------------------------------------------------------


def _captured_prompt(monkeypatch, protocol, cluster, answers: dict[str, str]) -> str:
    seen: list[str] = []

    def complete(messages, **kwargs):
        seen.append(messages[0]["content"])
        return provider_router.CompletionResult(
            text="Cơn khó chịu bắt đầu từ khi nào vậy?", provider="fake", model="fake",
        )

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    plan = dialogue.build_response_plan(
        protocol, cluster, act=dialogue.DialogueAct.ANSWER, answers=answers,
    )
    assert plan is not None
    intake_agent.generate_question(
        protocol, cluster, answers=answers, plan=plan, credential=None,
    )
    assert seen, "phải gọi model đúng một lần"
    return seen[-1]


def test_a_partly_filled_cluster_does_not_carry_the_whole_script_hint_into_the_prompt(monkeypatch):
    """Ca đo được: `chest_pain` đã "true" từ lượt mở, `CP-03` chỉ còn thiếu phần triệu chứng kèm.

    Để nguyên `script_hint` thì prompt chứa ba tín hiệu chọi nhau - câu viết sẵn hỏi cả cụm, dòng
    `CHỈ CÒN THIẾU`, và `ĐÃ BIẾT VỀ NGƯỜI BỆNH` - và model bám vào cái cụ thể nhất."""
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-03")
    filled = cluster.fields[0]
    answers = {filled: "true"}

    prompt = _captured_prompt(monkeypatch, CHEST_PAIN_PROTOCOL, cluster, answers)

    assert cluster.script_hint not in prompt
    assert "CHỈ CÒN THIẾU" in prompt
    # Phần CÒN THIẾU vẫn phải có mặt, nếu không thì lượt này không hỏi được gì.
    remaining = CHEST_PAIN_PROTOCOL.fields_by_key[cluster.fields[-1]].label
    assert remaining in prompt


def test_an_untouched_cluster_still_gets_the_script_hint(monkeypatch):
    """Cụm chưa ai chạm vào thì `script_hint` là câu chuẩn lâm sàng - không được bỏ nó đi cùng lúc.

    Fix D chỉ thu hẹp đúng trường hợp `missing` là tập con THẬT SỰ của `cluster.fields`."""
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-03")

    prompt = _captured_prompt(monkeypatch, CHEST_PAIN_PROTOCOL, cluster, {})

    assert cluster.script_hint in prompt
    assert "CHỈ CÒN THIẾU" not in prompt


def test_the_deterministic_fallback_still_speaks_the_whole_script_hint(monkeypatch):
    """Guard chặn / model chết -> vẫn phải phát `script_hint`. Đường này lấy `cluster.script_hint`
    trực tiếp chứ không qua prompt, nên Fix D không được làm nó câm."""
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-03")
    monkeypatch.setattr(
        provider_router, "complete", Mock(side_effect=RuntimeError("provider down")),
    )
    answers = {cluster.fields[0]: "true"}
    plan = dialogue.build_response_plan(
        CHEST_PAIN_PROTOCOL, cluster, act=dialogue.DialogueAct.ANSWER, answers=answers,
    )

    text, llm_used = intake_agent.generate_question(
        CHEST_PAIN_PROTOCOL, cluster, answers=answers, plan=plan, credential=None,
    )

    assert text == cluster.script_hint
    assert llm_used is False


# --- lớp 2: `output_guard` nhìn thấy nhãn hai từ ---------------------------------------------------


def _guard(protocol, cluster, text: str, answers: dict[str, str]):
    plan = dialogue.build_response_plan(
        protocol, cluster, act=dialogue.DialogueAct.ANSWER, answers=answers,
    )
    assert plan is not None
    return output_guard.check(
        text, plan=plan, protocol=protocol, cluster=cluster, answers=answers,
    )


def test_guard_blocks_a_question_that_reaches_back_for_a_known_two_word_label():
    """"Đau ngực" là nhãn 2 từ - ngưỡng cũ (3 từ) làm nó vô hình với check 3."""
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-02")
    result = _guard(
        CHEST_PAIN_PROTOCOL, cluster, "Bạn có bị đau ngực không?", {"chest_pain": "true"},
    )

    assert result.ok is False
    assert output_guard.VIOLATION_ASKS_KNOWN_FIELD in result.violations


@pytest.mark.parametrize("label_key", ["chest_pain", "breathing_difficulty"])
def test_the_five_central_two_word_labels_are_visible_to_the_guard(label_key):
    """Nhãn của field trung tâm mỗi nhóm đều 2 từ. Không được có cái nào lọt lưới."""
    spec = CHEST_PAIN_PROTOCOL.fields_by_key[label_key]
    assert len(spec.label.split()) == 2
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-02")

    result = _guard(
        CHEST_PAIN_PROTOCOL, cluster, f"Bạn có {spec.label.lower()} không?", {label_key: "true"},
    )

    assert output_guard.VIOLATION_ASKS_KNOWN_FIELD in result.violations


def test_guard_does_not_block_a_legitimate_question_about_a_generic_two_word_label():
    """Ca chặn nhầm đo được với `deepseek-chat` và là lý do ngưỡng 2 bị bỏ lần trước.

    "Loại sốt" mô tả một THUỘC TÍNH, nên nó xuất hiện tự nhiên trong câu hỏi hợp lệ về chính thuộc
    tính đó. `_GENERIC_LABEL_WORDS` xử lý riêng ca này thay vì hạ cả ngưỡng."""
    cluster = _cluster(FEVER_PROTOCOL, FEVER_PROTOCOL.clusters[0].id)
    result = _guard(
        FEVER_PROTOCOL, cluster,
        "Cơn sốt của bạn thuộc loại sốt nào - liên tục hay từng cơn?",
        {"fever_status": "objective"},
    )

    assert output_guard.VIOLATION_ASKS_KNOWN_FIELD not in result.violations


def test_guard_still_lets_through_a_question_about_a_field_that_is_still_missing():
    """Check 3 chỉ bắn cho field ĐÃ điền và KHÔNG nằm trong `missing_fields` - hạ ngưỡng không được
    làm nó chặn chính câu hỏi mà plan yêu cầu."""
    cluster = _cluster(CHEST_PAIN_PROTOCOL, "CP-01")
    result = _guard(CHEST_PAIN_PROTOCOL, cluster, "Cơn đau ngực của bạn thế nào?", {})

    assert output_guard.VIOLATION_ASKS_KNOWN_FIELD not in result.violations


# --- một định nghĩa "còn thiếu" duy nhất ------------------------------------------------------------


def test_missing_fields_uses_the_same_definition_as_the_stage_machine():
    """`dialogue` tính `missing` bằng `is_filled`, `cluster_needs_answer` dùng `field_is_settled` -
    hai định nghĩa lệch nhau thì prompt kéo vào đúng những field stage machine đã coi là xong.

    Field con của một field cha đã bị phủ định là câu hỏi VÔ NGHĨA, không phải câu hỏi còn thiếu."""
    parent, dependents = next(iter(CHEST_PAIN_PROTOCOL.field_dependencies.items()))
    cluster = next(
        (c for c in CHEST_PAIN_PROTOCOL.clusters if set(c.fields) & set(dependents)), None,
    )
    if cluster is None:
        pytest.skip("không cụm nào của chest_pain chứa field phụ thuộc")

    answers = {parent: "false"}
    plan = dialogue.build_response_plan(
        CHEST_PAIN_PROTOCOL, cluster, act=dialogue.DialogueAct.ANSWER, answers=answers,
    )

    assert plan is not None
    assert not set(plan.missing_fields) & set(dependents)

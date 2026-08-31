"""F10 Fix E: xưng hô nhất quán cả phiên.

Lỗi thật: agent lúc xưng "mình", lúc xưng "em", trong cùng một hội thoại. Nguyên nhân không phải một
template nào viết sai - mọi template TĨNH đều đã dùng đúng cặp `mình`/`bạn` - mà là KHÔNG CÓ prompt
sinh câu hỏi nào quy định đại từ. `_QUESTION_ONLY_SYSTEM` sinh ra đa số câu người bệnh đọc, chạy ở
temperature 0.7, được đọc lại lịch sử hội thoại, lại còn bị ép "PHẢI viết khác đi cho tự nhiên hơn"
mà không nói rõ "khác đi" chừa cái gì ra. Ngôi xưng là sản phẩm phụ ngẫu nhiên.

Hai nhóm test: (1) mọi prompt sinh văn bản gửi người bệnh phải mang `PERSONA_RULE`; (2) mọi template
tĩnh chỉ dùng đúng cặp đại từ đã chốt - đây là phần đang đúng và cần được KHOÁ LẠI, vì mỗi biến thể
mới viết thêm là một cơ hội cho một "em" lọt vào.
"""

from __future__ import annotations

import re
from unittest.mock import Mock

import pytest

from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.infra import provider_router
from src.services.sessions import followup_writer
from src.services.symptom_protocol import (
    batching,
    chitchat,
    controller,
    dialogue,
    intake_agent,
    non_clinical,
    phrasing,
    registry,
    screening,
    session,
    user_intent,
)
from src.services.symptom_protocol.common_safety import emergency_message, text_safety_signals


def test_the_persona_is_one_constant_not_three_hand_written_lines():
    assert phrasing.AGENT_PRONOUN == "mình"
    assert phrasing.PATIENT_PRONOUN == "bạn"
    assert f'"{phrasing.AGENT_PRONOUN}"' in phrasing.PERSONA_RULE
    assert f'"{phrasing.PATIENT_PRONOUN}"' in phrasing.PERSONA_RULE


@pytest.mark.parametrize(
    ("name", "template"),
    [
        ("intake_agent._QUESTION_ONLY_SYSTEM", intake_agent._QUESTION_ONLY_SYSTEM),
        ("chitchat._SYSTEM_PROMPT", chitchat._SYSTEM_PROMPT),
    ],
)
def test_every_formatted_patient_facing_prompt_takes_the_persona_rule(name, template):
    """Hai prompt này đi qua `.format`, nên chúng nhận `PERSONA_RULE` qua chỗ giữ."""
    assert "{persona_rule}" in template, name


def test_the_followup_prompt_carries_the_persona_rule_verbatim():
    """`followup_writer._SYSTEM_PROMPT` KHÔNG đi qua `.format` (nó được nối bằng f-string), nên chỗ
    giữ `{persona_rule}` sẽ ra nguyên văn dấu ngoặc trong prompt gửi model - phải nối chuỗi."""
    assert phrasing.PERSONA_RULE in followup_writer._SYSTEM_PROMPT
    assert "{" not in followup_writer._SYSTEM_PROMPT


def test_the_generated_question_prompt_really_contains_the_rule(monkeypatch):
    """Có chỗ giữ trong template chưa đủ - phải có ai đó truyền giá trị vào."""
    seen: list[str] = []

    def complete(messages, **kwargs):
        seen.append(messages[0]["content"])
        return provider_router.CompletionResult(text="Bạn thấy sao?", provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    cluster = CHEST_PAIN_PROTOCOL.clusters[0]
    plan = dialogue.build_response_plan(
        CHEST_PAIN_PROTOCOL, cluster, act=dialogue.DialogueAct.ANSWER, answers={},
    )
    intake_agent.generate_question(
        CHEST_PAIN_PROTOCOL, cluster, answers={}, plan=plan, credential=None,
    )

    assert seen and phrasing.PERSONA_RULE in seen[-1]


def test_the_rephrase_instruction_no_longer_licenses_changing_the_pronoun(monkeypatch):
    """Chỉ thị cũ nói trống "đổi từ ngữ", mà đại từ cũng là từ ngữ. Lượt hỏi lại là lượt dễ trôi ngôi
    xưng nhất, vì nó là lượt DUY NHẤT model được lệnh viết khác hẳn lần trước."""
    seen: list[str] = []

    def complete(messages, **kwargs):
        seen.append(messages[0]["content"])
        return provider_router.CompletionResult(text="Bạn thấy sao?", provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))
    cluster = CHEST_PAIN_PROTOCOL.clusters[0]
    intake_agent.generate_question(
        CHEST_PAIN_PROTOCOL, cluster, answers={}, rephrase=True, credential=None,
    )

    assert seen
    assert "Đại từ xưng hô giữ NGUYÊN" in seen[-1]


# --- mọi template tĩnh chỉ dùng đúng cặp đại từ đã chốt --------------------------------------------

_FORBIDDEN = re.compile(r"\b(em|anh|chị|cô|chú|quý khách|tôi)\b", re.IGNORECASE)
"""Đại từ KHÔNG được xuất hiện trong văn bản agent gửi người bệnh.

"tôi" nằm trong danh sách vì nó là ngôi thứ nhất cạnh tranh với "mình" - agent dùng nó là đổi giọng
giữa phiên. Người bệnh tự xưng "tôi" thì không sao: đây chỉ soi văn bản do AGENT phát ra."""

_STATIC_TEMPLATES: tuple[tuple[str, object], ...] = (
    ("registry.OPENING_QUESTIONS", registry.OPENING_QUESTIONS),
    ("screening.PROBE_INTRO", screening.PROBE_INTRO),
    ("screening.PROBE_OUTRO", screening.PROBE_OUTRO),
    ("session.CATCH_ALL_QUESTION", session.CATCH_ALL_QUESTION),
    ("session.RETRACTION_TEMPLATES", session.RETRACTION_TEMPLATES),
    ("batching.BATCH_INTRO", batching.BATCH_INTRO),
    ("dialogue.PROTOCOL_SWITCH_NOTE", dialogue.PROTOCOL_SWITCH_NOTE),
    # Ba hằng số của controller nằm trong danh sách dù chỉ HANDOFF_MESSAGE là câu người bệnh đọc:
    # hai cái còn lại là mã lý do, và ngày nào đó có người biến chúng thành câu tiếng Việt.
    ("controller.HANDOFF_MESSAGE", controller.HANDOFF_MESSAGE),
    ("controller.FAIL_CLOSED_NO_CLUSTER", controller.FAIL_CLOSED_NO_CLUSTER),
    ("controller.FAIL_CLOSED_NO_PROTOCOL", controller.FAIL_CLOSED_NO_PROTOCOL),
    ("user_intent.UNCOOPERATIVE_PROMPTS", user_intent.UNCOOPERATIVE_PROMPTS),
    ("non_clinical.LIFESTYLE_REPLIES", non_clinical.LIFESTYLE_REPLIES),
    ("non_clinical.META_REPLIES", non_clinical.META_REPLIES),
    ("non_clinical.LOW_CONTENT_REPLIES", non_clinical.LOW_CONTENT_REPLIES),
    ("non_clinical.NO_SYMPTOMS_REPLIES", non_clinical.NO_SYMPTOMS_REPLIES),
    ("non_clinical.OUT_OF_SCOPE_REPLIES", non_clinical.OUT_OF_SCOPE_REPLIES),
    ("non_clinical.CHITCHAT_REPLIES", non_clinical.CHITCHAT_REPLIES),
    ("emergency_message.EMERGENCY_MESSAGE", emergency_message.EMERGENCY_MESSAGE),
    ("emergency_message.SUSPECTED_RED_FLAG_MESSAGE", emergency_message.SUSPECTED_RED_FLAG_MESSAGE),
    ("emergency_message.SLA_BREACH_MESSAGE", emergency_message.SLA_BREACH_MESSAGE),
    ("text_safety_signals.CONFIRMATION_TEMPLATES", text_safety_signals.CONFIRMATION_TEMPLATES),
)


@pytest.mark.parametrize(("name", "value"), _STATIC_TEMPLATES)
def test_static_templates_use_only_the_agreed_pronoun_pair(name, value):
    """Phần này ĐANG đúng - test tồn tại để khoá nó lại.

    Mỗi biến thể diễn đạt mới (`phrasing.pick` khuyến khích viết thêm bản) là một cơ hội cho một
    "em" lọt vào, và một "em" lọt vào thì cả phiên đọc như hai người khác nhau đang nhắn."""
    for text in (value,) if isinstance(value, str) else value:
        assert isinstance(text, str)
        found = _FORBIDDEN.findall(text)
        assert not found, f"{name}: {sorted(set(found))} trong {text[:80]!r}"

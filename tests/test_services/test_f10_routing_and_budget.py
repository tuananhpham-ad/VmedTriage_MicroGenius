"""F10 §5 mục 4-5: chọn đúng nhóm ngay lượt mở, và ngân sách không được cấp lại khi đổi protocol.

Hai lỗi được vá ở đây có cùng một hình dạng: một con số đúng bị tính lại từ đầu ở đúng chỗ nó phải
được mang theo. Fix A mang lời khai tự do sang quyết định chọn protocol (trước đây chỉ có 3 chuỗi
literal được nhìn thấy); Fix B mang số cụm đã hỏi sang protocol mới (trước đây `asked_count` về 0,
tức cấp lại trọn vẹn 13-16 cụm nữa cho một người bệnh đã trả lời chán chê).

LLM được thay bằng fake: phần cần kiểm là cơ chế, không phải khả năng đọc tiếng Việt của model.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.abdominal_protocol import ABDOMINAL_PROTOCOL
from src.services.engines.breathing_protocol import BREATHING_PROTOCOL
from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.headache_protocol import HEADACHE_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import intake_agent, registry, stage_machine
from src.services.symptom_protocol.registry import PRIMARY_SYMPTOM_FIELD
from src.services.symptom_protocol.session import ProtocolSessionStore


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


# --- Fix A: lưới đỡ bằng LUẬT (model chết hoặc trả "unknown") -------------------------------------

_PHRASINGS: dict[str, tuple[str, ...]] = {
    CHEST_PAIN_PROTOCOL.name: (
        "đau ngực",
        "đau tức vùng ngực trái",
        "tức ngực từ sáng",
        "nặng ngực khó chịu",
        "nhói bên ngực trái",
        "đau ở giữa ngực",
        "tức phía sau lồng ngực",
        "đau vùng xương ức",
        "bóp nghẹt trong lồng ngực",
        "đè ép vùng tim",
        "rát vùng ngực khi hít sâu",
    ),
    BREATHING_PROTOCOL.name: (
        "khó thở",
        "mấy hôm nay hụt hơi",
        "nghẹt thở khi nằm",
        "tức thở về đêm",
        "thở gấp sau khi đi bộ",
        "thở nhanh và mệt",
        "cảm giác thiếu không khí",
        "không thở được",
        "thở không ra hơi",
        "lên cơn hen từ tối qua",
        "nghẹn thở từng lúc",
    ),
    HEADACHE_PROTOCOL.name: (
        "đau đầu",
        "nhức đầu ba hôm nay",
        "đau nửa đầu bên phải",
        "đau nửa sọ",
        "buốt đầu từng cơn",
        "đau vùng trán",
        "đau vùng gáy lan lên",
        "đau đỉnh đầu",
        "đau thái dương bên trái",
        "bị migraine từ lâu",
        "nặng đầu cả ngày",
    ),
    ABDOMINAL_PROTOCOL.name: (
        "đau bụng",
        "đau quanh rốn",
        "quặn bụng từng cơn",
        "đau vùng thượng vị",
        "rát dạ dày sau khi ăn",
        "đau hạ sườn phải",
        "tức bụng dưới",
        "đau vùng hố chậu phải",
        "khó chịu vùng rốn",
        "đau bụng âm ỉ vùng ruột",
        "nhói vùng bụng trên",
    ),
}


@pytest.mark.parametrize(
    ("expected", "complaint"),
    [(name, text) for name, texts in _PHRASINGS.items() for text in texts],
)
def test_free_text_complaint_routes_to_the_right_group_without_the_model(expected, complaint):
    """Không có `primary_symptom_group` (model tắt hoặc trả "unknown") thì luật vẫn phải chọn đúng.

    `INVARIANTS.md` §5: tắt hoàn toàn SLM thì hệ thống vẫn phải chạy đúng. Bản cũ khớp đúng 3 chuỗi
    literal nên "đau tức vùng ngực trái" rơi về `general`."""
    assert registry.select_protocol({"chief_complaint": complaint}) == expected


def test_chest_pain_beats_an_incidental_fever_mention():
    """Ca đo được sinh ra F10 lỗi 1: khai đau ngực kèm hơi sốt -> câu hỏi đầu tiên lại là câu nhóm SỐT.

    `_has_chest_pain_evidence` trượt ("đau tức vùng ngực trái" không phải chuỗi literal nào), còn
    `fever_reported` thì bắt được ngay cùng lượt -> `candidates = ('fever',)`."""
    answers = {
        "chief_complaint": "đau tức vùng ngực trái, hơi sốt",
        "fever_reported": "true",
        "temp_c": "37.8",
    }
    assert registry.protocol_candidates(answers)[0] == CHEST_PAIN_PROTOCOL.name
    assert registry.select_protocol(answers) == CHEST_PAIN_PROTOCOL.name


@pytest.mark.parametrize(
    "name",
    [
        CHEST_PAIN_PROTOCOL.name, BREATHING_PROTOCOL.name, HEADACHE_PROTOCOL.name,
        ABDOMINAL_PROTOCOL.name, FEVER_PROTOCOL.name,
    ],
)
def test_the_model_label_alone_is_enough_evidence_for_every_group(name):
    """`primary_symptom_group` phải là căn cứ DƯƠNG TÍNH tự đứng được.

    `select_protocol` chỉ dùng `preferred` khi `preferred in candidates`, nên nếu nhãn model không
    tự sinh ra một candidate thì field này vô hiệu đúng lúc cần nhất - lúc lưới từ vựng trượt."""
    assert registry.select_protocol({PRIMARY_SYMPTOM_FIELD.key: name}) == name


def test_the_model_label_loses_to_an_explicit_retraction():
    """Lời phủ định tường minh ở lượt sau thắng nhãn model gán từ lượt trước."""
    answers = {PRIMARY_SYMPTOM_FIELD.key: CHEST_PAIN_PROTOCOL.name, "chest_pain": "false"}
    assert CHEST_PAIN_PROTOCOL.name not in registry.protocol_candidates(answers)


def test_the_model_label_decides_between_two_groups_that_both_have_evidence():
    """Lưới từ vựng bắt cả hai nhóm; nhãn model là thứ phá thế hoà, không phải `PROTOCOL_PRIORITY`."""
    answers: dict[str, object] = {"chief_complaint": "đau bụng và hơi tức ngực"}
    assert len(registry.protocol_candidates(answers)) >= 2
    assert registry.select_protocol(answers) == CHEST_PAIN_PROTOCOL.name  # theo ưu tiên lâm sàng
    answers[PRIMARY_SYMPTOM_FIELD.key] = ABDOMINAL_PROTOCOL.name
    assert registry.select_protocol(answers) == ABDOMINAL_PROTOCOL.name


def test_primary_symptom_group_is_in_the_opening_extraction_schema():
    """Field đã tồn tại và `select_protocol` đã ưu tiên nó từ trước - lỗ hổng là nó KHÔNG nằm trong
    schema lượt mở, nên extractor không bao giờ có ô để điền."""
    assert PRIMARY_SYMPTOM_FIELD.key in registry.OPENING_HARVEST_EXTRA_FIELDS
    assert PRIMARY_SYMPTOM_FIELD.key in registry.OPENING_HARVEST_FIELDS


def test_retracting_chest_pain_also_clears_the_duration_that_keeps_it_alive():
    """Lỗ ping-pong: `_has_chest_pain_evidence` đọc `chest_pain_duration_min`, nhưng field đó không
    nằm trong `FIELD_DEPENDENCIES["chest_pain"]` -> rút lời "tôi không đau ngực" xoá được tính chất và
    hướng lan mà thời lượng sống sót, tức bằng chứng đau ngực KHÔNG BAO GIỜ tắt."""
    assert "chest_pain_duration_min" in CHEST_PAIN_PROTOCOL.field_dependencies["chest_pain"]


# --- Fix B: đổi protocol không cấp lại ngân sách ---------------------------------------------------


def _fake_llm(monkeypatch, extracted: dict[str, tuple[object, str]]) -> None:
    def complete(messages, *, credential=None, temperature=None, max_attempts=3, role=None):
        system = messages[0]["content"]
        if "Hãy diễn đạt lại Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(
                text="Cho mình hỏi thêm nhé?", provider="fake", model="fake",
            )
        body = {
            key: {"value": value, "evidence_span": evidence}
            for key, (value, evidence) in extracted.items()
            if key in system
        }
        return provider_router.CompletionResult(text=json.dumps(body), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))


def test_switching_protocol_does_not_hand_the_patient_a_fresh_budget(monkeypatch):
    """`advance` tính `count = len(asked_ids)` khi không được truyền `asked_count`, và `asked_ids`
    phải rỗng ở nhánh này (mã cụm dùng chung giữa các protocol) -> ngân sách về 0.

    Ngân sách là kiên nhẫn của NGƯỜI BỆNH; đổi protocol không làm họ có thêm kiên nhẫn."""
    calls: list[dict[str, object]] = []
    real_advance = stage_machine.advance

    def spy(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(intake_agent.stage_machine, "advance", spy)

    store = ProtocolSessionStore()
    _fake_llm(monkeypatch, {"chief_complaint": ("mệt", "mệt")})
    session = store.start_session()
    session = store.submit_message(session.session_id, "Mấy hôm nay tôi mệt")

    calls.clear()
    _fake_llm(monkeypatch, {"temp_c": ("39.2", "39.2 độ"), "fever_status": ("objective", "39.2 độ")})
    session = store.submit_message(session.session_id, "Tôi sốt 39.2 độ, đo ở nách")

    assert session.protocol_name == FEVER_PROTOCOL.name
    assert calls, "lượt đổi protocol phải đi qua `stage_machine.advance`"
    assert calls[-1].get("asked_count", 0) > 0, (
        "đổi protocol mà `asked_count` về 0 là cấp lại trọn vẹn 13-16 cụm nữa"
    )

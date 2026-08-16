"""Protocol generic, lượt mở, và việc đổi protocol giữa chừng.

Ba thứ này ra đời cùng nhau vì chúng vá cùng một lỗ hổng: `/chat` chỉ có protocol SỐT, nên than phiền
ngoài sốt vừa bị hỏi sai hướng vừa KHÔNG được luật đỏ nào quét (`_guidance/need_to_check_agent.md`,
mục "LỖ HỔNG ĐÃ TẠO RA").

LLM được thay bằng fake trong toàn bộ file - phần cần kiểm ở đây là cơ chế (chọn protocol, chuyển
trạng thái, luật nào chạy), không phải khả năng hiểu tiếng Việt của model.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import batching, registry, rule_engine, stage_machine
from src.services.symptom_protocol.session import ProtocolSessionStore, SessionPhase, SessionState


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


def _fake_llm(monkeypatch, extracted: dict[str, tuple[object, str]] | None = None):
    """LLM giả trả về `{"<key>": {"value": ..., "evidence_span": ...}}` cho các field CÓ trong prompt.

    Phải kèm `evidence_span` thật: ở lượt mở mọi field đều là "chưa được hỏi", nên enum/số và mọi
    `"false"` không có trích dẫn sẽ bị loại - đúng như thiết kế."""
    payload = extracted or {}

    def complete(messages, *, credential=None, temperature=None, max_attempts=3):
        system = messages[0]["content"]
        if "Hãy diễn đạt lại Ý CẦN HỎI" in system:
            return provider_router.CompletionResult(text="Dạ cho em hỏi thêm ạ?", provider="fake", model="fake")
        body = {
            key: {"value": value, "evidence_span": evidence}
            for key, (value, evidence) in payload.items()
            if key in system
        }
        return provider_router.CompletionResult(text=json.dumps(body), provider="fake", model="fake")

    monkeypatch.setattr(provider_router, "complete", Mock(side_effect=complete))


# --- protocol generic: hợp đồng HẸP --------------------------------------------------------------


def test_generic_protocol_never_concludes_self_care():
    """Hệ quả CÓ Ý THỨC: protocol này chỉ quét được tập dấu hiệu phổ quát, nó không có căn cứ nào để
    nói "cứ ở nhà". Không tuyên bố an toàn là điều đúng duy nhất làm được."""
    spotless = {key: "false" for key in GENERIC_PROTOCOL.fields_by_key}
    assert GENERIC_PROTOCOL.self_care_checklist_satisfied(spotless) is False
    assert rule_engine.evaluate(GENERIC_PROTOCOL, spotless).triage_level == "EARLY_VISIT"


def test_generic_protocol_falls_back_to_early_visit_when_nothing_matched():
    """Hồ sơ trống trơn - không rule nào khớp - vẫn ra "khám sớm", không ra "tự chăm sóc"."""
    result = rule_engine.evaluate(GENERIC_PROTOCOL, {})
    assert result.triage_level == "EARLY_VISIT"
    assert result.triggered_rules == ("R-G-02",)


def test_generic_protocol_stops_with_budget_exhausted_not_sufficient_evidence():
    spotless = {key: "false" for key in GENERIC_PROTOCOL.fields_by_key}
    step = stage_machine.advance(
        GENERIC_PROTOCOL, GENERIC_PROTOCOL.stage_order[-1], spotless, asked_count=99,
    )
    assert step.cluster is None
    assert step.stop_reason == "BUDGET_EXHAUSTED"


def test_generic_protocol_has_no_fever_specific_field():
    for key in ("temp_c", "fever_reported", "antipyretic_taken", "malaria_risk_area"):
        assert key not in GENERIC_PROTOCOL.fields_by_key


def test_generic_clusters_only_reference_declared_fields():
    for cluster in GENERIC_PROTOCOL.clusters:
        for key in cluster.fields:
            assert key in GENERIC_PROTOCOL.fields_by_key, f"{cluster.id} -> {key}"


def test_universal_red_flags_escalate_on_generic_protocol():
    """Đúng ca đã mất lưới an toàn: đau ngực + khó thở nặng."""
    result = rule_engine.evaluate(
        GENERIC_PROTOCOL, {"chest_pain": "true", "breathing_difficulty": "severe"},
    )
    assert result.triage_level == "EMERGENCY"


# --- chọn protocol -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answers",
    [
        {"fever_reported": "true"},
        {"fever_status": "objective"},
        {"temp_c": "38.5"},
    ],
)
def test_select_protocol_picks_fever_on_positive_evidence(answers):
    assert registry.select_protocol(answers, None) == FEVER_PROTOCOL.name


def test_select_protocol_keeps_current_when_there_is_no_evidence():
    """Im lặng KHÔNG phải bằng chứng đổi hướng - đổi protocol vì hồ sơ chưa nhắc tới gì sẽ vứt bỏ cả
    nhánh câu hỏi đang dở."""
    assert registry.select_protocol({"chest_pain": "true"}, FEVER_PROTOCOL.name) == FEVER_PROTOCOL.name
    assert registry.select_protocol({}, GENERIC_PROTOCOL.name) == GENERIC_PROTOCOL.name


def test_select_protocol_leaves_fever_when_the_patient_retracts_the_fever_claim():
    assert registry.select_protocol({"fever_reported": "false"}, FEVER_PROTOCOL.name) == GENERIC_PROTOCOL.name


def test_unknown_protocol_name_falls_back_to_generic_not_to_fever():
    """Rơi về generic là an toàn (không bao giờ kết luận nhẹ); rơi về fever là hỏi sai hướng cả phiên."""
    assert registry.protocol_for("khong-ton-tai").name == GENERIC_PROTOCOL.name
    assert registry.protocol_for(None).name == GENERIC_PROTOCOL.name


def test_opening_cluster_forbids_batch_negation():
    """Người bệnh chưa được hỏi gì nên không có "cụm" nào để một câu phủ định gộp áp vào - cho phép ở
    đây là mở lại lỗ hổng C1 ở quy mô lớn nhất."""
    assert registry.OPENING_CLUSTER.batch_negation is False


# --- lượt mở --------------------------------------------------------------------------------------


def _open_store() -> ProtocolSessionStore:
    return ProtocolSessionStore(default_protocol=None)


def test_new_session_starts_in_opening_phase_with_the_static_question():
    session = _open_store().start_session()
    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.last_question == registry.OPENING_QUESTION


def test_poor_opening_message_repeats_the_open_question_and_picks_no_protocol(monkeypatch):
    _fake_llm(monkeypatch, {})
    store = _open_store()
    session = store.start_session()

    session = store.submit_message(session.session_id, "xin chào")

    assert session.phase is SessionPhase.OPENING
    assert session.protocol_name == ""
    assert session.last_question == registry.OPENING_QUESTION


def test_opening_message_about_fever_selects_the_fever_protocol(monkeypatch):
    _fake_llm(monkeypatch, {"fever_reported": ("true", "sốt"), "temp_c": ("39", "39 độ")})
    store = _open_store()
    session = store.start_session()

    session = store.submit_message(session.session_id, "Con em sốt 39 độ từ hôm qua")

    assert session.phase is SessionPhase.COLLECTING
    assert session.protocol_name == FEVER_PROTOCOL.name
    assert session.current_cluster is not None
    assert session.last_question  # KHÔNG được trả tin nhắn rỗng


def test_opening_message_about_another_complaint_selects_the_generic_protocol(monkeypatch):
    _fake_llm(monkeypatch, {"chief_complaint": ("đau bụng", "đau bụng")})
    store = _open_store()
    session = store.start_session()

    session = store.submit_message(session.session_id, "Tôi đau bụng hai hôm nay")

    assert session.protocol_name == GENERIC_PROTOCOL.name
    assert session.answers["chief_complaint"] == "đau bụng"


def test_red_flag_in_the_opening_message_escalates_immediately(monkeypatch):
    _fake_llm(monkeypatch, {"seizure_active_now": ("true", "đang co giật")})
    store = _open_store()
    session = store.start_session()

    session = store.submit_message(session.session_id, "Bé đang co giật")

    assert session.state is SessionState.EMERGENCY
    assert session.triage_level == "EMERGENCY"
    assert "115" in session.last_question


def test_opening_turn_rejects_a_negation_the_patient_never_uttered(monkeypatch):
    """Lượt mở là lượt dễ bịa nhất (schema rộng, tin nhắn tự do) nên cũng phải siết nhất: model khai
    "không co giật" mà không trích được câu nào thì field giữ `unknown`, không thành `false`."""
    _fake_llm(monkeypatch, {
        "chief_complaint": ("đau bụng", "đau bụng"),
        "seizure_occurred": ("false", "bệnh nhân phủ nhận co giật"),
    })
    store = _open_store()
    session = store.start_session()

    session = store.submit_message(session.session_id, "Tôi đau bụng hai hôm nay")

    assert session.answers.get("seizure_occurred") in (None, "unknown")


# --- đổi protocol giữa chừng ----------------------------------------------------------------------


def test_session_switches_from_fever_to_generic_when_the_claim_is_retracted(monkeypatch):
    """"À tôi nhầm, tôi không sốt" - ở lại protocol sốt nghĩa là tiếp tục hỏi nhiệt độ, thuốc hạ sốt,
    ngày khởi phát sốt cho một người vừa nói rõ là không sốt."""
    store = _open_store()
    _fake_llm(monkeypatch, {"fever_reported": ("true", "sốt")})
    session = store.start_session()
    session = store.submit_message(session.session_id, "Tôi bị sốt")
    assert session.protocol_name == FEVER_PROTOCOL.name

    _fake_llm(monkeypatch, {"fever_reported": ("false", "tôi không sốt")})
    session = store.submit_message(session.session_id, "À tôi nhầm, tôi không sốt")

    assert session.protocol_name == GENERIC_PROTOCOL.name
    assert session.current_cluster is not None
    # Cụm kế tiếp phải THUỘC generic - đây là điều test canh: không được sót lại cụm của fever. Cụm
    # có thể là một GÓI (`batching`) gồm 2-3 cụm generic, nên kiểm theo cụm thành phần.
    generic_ids = {cluster.id for cluster in GENERIC_PROTOCOL.clusters}
    asked_ids = (
        set(batching._components_of(session.current_cluster.id))
        if batching.is_batch(session.current_cluster)
        else {session.current_cluster.id}
    )
    assert asked_ids and asked_ids <= generic_ids
    assert session.last_question  # vẫn phải có câu hỏi, không được trả tin nhắn rỗng
    # Phần đặc điểm sốt đã bị xoá khỏi hồ sơ (`retraction.apply_retraction`), không còn gửi cho
    # điều dưỡng như một sự thật.
    assert session.answers.get("fever_reported") == "false"


def test_generic_session_can_switch_to_fever_when_the_patient_mentions_it_later(monkeypatch):
    """Lời khai sốt đến ở lượt thứ ba, khi phiên đang chạy `general`.

    Lỗi thật đo được khi chạy LLM thật: `temp_c` không nằm trong registry của `general` nên câu "bé
    sốt 39.2 độ" KHÔNG có chỗ nào để ghi, `select_protocol` không bao giờ thấy bằng chứng, và phiên
    kẹt ở `general` suốt dù người bệnh nói rõ nhiệt độ."""
    store = _open_store()
    _fake_llm(monkeypatch, {"chief_complaint": ("mệt", "mệt")})
    session = store.start_session()
    session = store.submit_message(session.session_id, "Mấy hôm nay bé mệt")
    assert session.protocol_name == GENERIC_PROTOCOL.name

    _fake_llm(monkeypatch, {"temp_c": ("39.2", "39.2 độ"), "fever_status": ("objective", "39.2 độ")})
    session = store.submit_message(session.session_id, "Bé sốt 39.2 độ, đo ở nách")

    assert session.protocol_name == FEVER_PROTOCOL.name
    assert session.answers["temp_c"] == "39.2"


def test_switch_detection_fields_never_leak_into_the_generic_field_registry():
    """Field nhận diện chỉ có mặt trong SCHEMA TRÍCH XUẤT, không được vào registry thật - nếu không,
    JSON gửi bên triage của một ca đau bụng lại có `temp_c`."""
    augmented = registry.with_switch_detection(GENERIC_PROTOCOL)
    assert "temp_c" in augmented.fields_by_key
    assert "temp_c" not in GENERIC_PROTOCOL.fields_by_key
    assert "temp_c" not in registry.protocol_for(GENERIC_PROTOCOL.name).fields_by_key


def test_switching_protocol_does_not_mark_the_new_protocol_clusters_as_already_asked(monkeypatch):
    """Mã cụm dùng chung giữa các protocol (`Q3-03` là cụm co giật ở cả hai), nên trạng thái cụm phải
    lưu kèm tên protocol - nếu không, phiên vừa đổi sẽ bỏ qua sạch phần quét đỏ của protocol mới."""
    store = _open_store()
    _fake_llm(monkeypatch, {"fever_reported": ("true", "sốt")})
    session = store.start_session()
    session = store.submit_message(session.session_id, "Tôi bị sốt")
    session.completed_cluster_ids.add(session.cluster_key("Q3-03"))

    _fake_llm(monkeypatch, {"fever_reported": ("false", "không sốt")})
    session = store.submit_message(session.session_id, "Tôi không sốt")

    assert "Q3-03" not in session.closed_ids_for_current_protocol()
    assert f"{FEVER_PROTOCOL.name}:Q3-03" in session.completed_cluster_ids


def test_fever_endpoint_session_is_pinned_and_has_no_opening_turn():
    """Lối vào chuyên biệt (`/api/v1/fever/*`) đã tuyên bố đây là ca sốt - không đoán lại protocol."""
    session = _open_store().start_session(protocol_name=FEVER_PROTOCOL.name)
    assert session.phase is SessionPhase.COLLECTING
    assert session.protocol_name == FEVER_PROTOCOL.name
    assert session.protocol_pinned is True
    assert session.current_cluster is not None


def test_pinned_session_never_switches_protocol_even_when_fever_is_denied(monkeypatch):
    """Người bệnh nói "không sốt" trên endpoint sốt: hồ sơ ghi nhận đúng, nhưng phiên KHÔNG bị kéo
    sang protocol khác. Caller đã tuyên bố đây là ca sốt; nhánh không còn phù hợp đã có `skip_rule`
    bỏ qua, không cần đổi cả protocol."""
    store = _open_store()
    _fake_llm(monkeypatch, {"fever_reported": ("false", "không sốt")})
    session = store.start_session(protocol_name=FEVER_PROTOCOL.name)

    session = store.submit_message(session.session_id, "Cháu không sốt đâu")

    assert session.protocol_name == FEVER_PROTOCOL.name
    assert session.answers.get("fever_reported") == "false"

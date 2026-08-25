"""Sổ độ phủ + xếp hạng cụm tất định (§8) - nhóm test "Linh hoạt và độ phủ" ở §11.

Hai mục tiêu của §8 nghe như đánh đổi nhưng không phải, và chính file này là chỗ chứng minh: nới
THỨ TỰ hỏi (để agent đi theo mạch người bệnh) không được làm mất field M0/M1 nào. Bất biến quan
trọng nhất nằm ở `test_every_ranking_order_still_covers_the_mandatory_fields` - nếu bài đó đỏ thì
việc nới thứ tự đã ăn vào độ phủ và phải dừng lại, không phải sửa test.

Toàn bộ file KHÔNG gọi model: xếp hạng là code thuần, nên nó phải kiểm được bằng đúng cách này.
"""

from __future__ import annotations

import random

import pytest

from src import paths
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.symptom_protocol import coverage, ranking, stage_machine
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


# --- protocol tối giản để bảng điểm đọc được bằng mắt --------------------------------------------

_FIELDS = {
    "age_value": FieldSpec("age_value", "Tuổi", "M0", "Số tuổi", tri_state=False),
    "seizure_occurred": FieldSpec("seizure_occurred", "Co giật", "M0", "Có co giật không"),
    "breathing_difficulty": FieldSpec("breathing_difficulty", "Khó thở", "M0", "Có khó thở không"),
    "cough": FieldSpec("cough", "Ho", "M1", "Có ho không"),
    "appetite": FieldSpec("appetite", "Ăn uống", "O", "Ăn uống thế nào"),
    "travel_history": FieldSpec("travel_history", "Đi lại", "O", "Gần đây có đi đâu không"),
}

# Thứ tự khai báo cố ý đặt cụm khó thở ĐỨNG SAU - đó là tình huống §8.3 mô tả: người bệnh kể về khó
# thở nhưng cụm khó thở đứng cuối danh sách nên vẫn phải trả lời mọi cụm khác trước.
_CLUSTERS = (
    QuestionCluster("D0-01", "0", ("age_value",), script_hint="Bao nhiêu tuổi"),
    QuestionCluster("D1-01", "1", ("cough",), script_hint="Có ho không"),
    QuestionCluster("D1-02", "1", ("appetite",), script_hint="Ăn uống thế nào"),
    QuestionCluster("D1-03", "1", ("travel_history",), script_hint="Gần đây có đi đâu không"),
    QuestionCluster("D1-04", "1", ("breathing_difficulty",), script_hint="Có khó thở không"),
    QuestionCluster("D2-01", "2", ("seizure_occurred",), script_hint="Có co giật không"),
)


def _never(_a: dict[str, object]) -> bool:
    return False


def _demo_protocol() -> SymptomProtocol:
    """Stage "2" là gate quét đỏ ⇒ `seizure_occurred` là field an toàn theo `safety_field_keys`."""
    return SymptomProtocol(
        name="demo",
        fields_by_key=_FIELDS,
        clusters=_CLUSTERS,
        stage_order=("0", "1", "2"),
        gate_stages=("2", "2"),
        budget={"DEFAULT": (1, 4)},
        budget_floor_stage="1",
        determine_route=lambda _a: "ROUTE",
        budget_key=lambda _a, _r, _k: "DEFAULT",
        provisional_emergency_signal=_never,
        self_care_checklist_satisfied=_never,
        skip_rule=lambda _c, _a: False,
        rule_catalog=(),
        fallback_rule=lambda _a: None,
        self_care_default_rule=lambda _a: None,
        patient_red_flag_message="EMERGENCY",
        safety_signal_fields=(),
        opportunistic_keywords=(),
    )


def _context(**kwargs) -> ranking.RankingContext:
    return ranking.RankingContext(**kwargs)


def _pick(protocol: SymptomProtocol, stage: str, answers: dict[str, object], context, asked=frozenset()) -> str | None:
    choice = stage_machine.select_cluster(protocol, stage, answers, asked_ids=asked, context=context)
    return choice.cluster.id if choice.cluster is not None else None


# --- ranking: hành vi cũ là trường hợp đặc biệt ---------------------------------------------------


def test_no_signal_keeps_the_declaration_order_of_the_old_first_fit() -> None:
    """Không tín hiệu nào ⇒ cùng nhóm điểm ⇒ hoà ⇒ thứ tự khai báo. Đây là điều kiện để bộ test
    hiện có không phải viết lại khi first-fit bị thay."""
    protocol = _demo_protocol()
    assert _pick(protocol, "1", {}, None) == "D1-01"
    assert _pick(protocol, "1", {}, _context()) == "D1-01"


def test_ranking_is_deterministic_across_repeated_calls() -> None:
    protocol = _demo_protocol()
    context = _context(recent_fields=frozenset({"breathing_difficulty"}), deferred={"D1-02": 2})
    first = _pick(protocol, "1", {}, context)
    second = _pick(protocol, "1", {}, context)
    assert first == second


def test_a_mandatory_cluster_outranks_an_optional_one_regardless_of_position() -> None:
    """`yield` nhị phân: cụm mang field M0/M1 đứng trước cụm thuần tier O, dù khai báo sau."""
    protocol = _demo_protocol()
    # D1-01 (M1) đã xong ⇒ còn D1-02 (O), D1-03 (O), D1-04 (M0). Cụm M0 phải thắng dù đứng cuối.
    assert _pick(protocol, "1", {"cough": "false"}, _context()) == "D1-04"


# --- follow-the-user (§8.4) -----------------------------------------------------------------------


def test_the_next_question_follows_what_the_patient_just_mentioned() -> None:
    """Người bệnh vừa tự nêu thông tin thuộc cụm khó thở ⇒ hỏi tiếp cụm đó, không quay về cụm kế
    tiếp theo vị trí. Đây là thay đổi tạo khác biệt lớn nhất về trải nghiệm trong §8."""
    protocol = _demo_protocol()
    context = _context(recent_fields=frozenset({"breathing_difficulty"}))
    assert _pick(protocol, "1", {}, context) == "D1-04"


def test_relevance_does_not_beat_a_safety_cluster() -> None:
    """§8.2 bất biến 2: cụm chứa field an toàn không bao giờ bị hoãn, bất kể người bệnh đang nói
    chuyện gì."""
    protocol = _demo_protocol()
    candidates = (_CLUSTERS[4], _CLUSTERS[5])  # D1-04 (relevance) vs D2-01 (safety)
    ordered = ranking.rank_clusters(
        protocol, "2", {}, candidates, _context(recent_fields=frozenset({"breathing_difficulty"})),
    )
    assert ordered[0].id == "D2-01"


def test_safety_fields_are_derived_from_the_emergency_scan_stage() -> None:
    protocol = _demo_protocol()
    assert ranking.safety_field_keys(protocol) == frozenset({"seizure_occurred"})
    assert ranking.cluster_is_safety_critical(protocol, _CLUSTERS[5]) is True
    assert ranking.cluster_is_safety_critical(protocol, _CLUSTERS[1]) is False


# --- sổ nợ (§8.5) ---------------------------------------------------------------------------------


def test_a_cluster_deferred_past_the_limit_wins_the_next_turn() -> None:
    """Hoãn được, nhưng không hoãn mãi: chạm trần thì cụm đó chắc chắn được hỏi ở lượt kế tiếp."""
    protocol = _demo_protocol()
    ledger = coverage.CoverageLedger()
    for _ in range(coverage.DEFERRAL_LIMIT):
        ledger.record_turn("D1-04", frozenset({"D1-02"}))

    assert ledger.deferral_count("D1-02") == coverage.DEFERRAL_LIMIT
    assert ledger.overdue_ids() == frozenset({"D1-02"})
    context = _context(
        recent_fields=frozenset({"breathing_difficulty"}),
        deferred=dict(ledger.deferred), overdue=ledger.overdue_ids(),
    )
    # Cụm tier O đã quá hạn thắng cả `relevance` của cụm M0 - nợ không được phép biến mất.
    assert _pick(protocol, "1", {}, context) == "D1-02"


def test_the_chosen_cluster_clears_its_debt() -> None:
    ledger = coverage.CoverageLedger()
    ledger.record_turn("D1-01", frozenset({"D1-02", "D1-03"}))
    ledger.record_turn("D1-02", frozenset({"D1-03"}))

    assert ledger.deferral_count("D1-02") == 0
    assert ledger.deferral_count("D1-03") == 2


def test_switching_protocol_drops_the_old_debt() -> None:
    """Mã cụm dùng chung giữa các protocol - giữ nợ cũ là gán nợ nhầm cụm."""
    ledger = coverage.CoverageLedger()
    ledger.record_turn(None, frozenset({"Q3-03"}))
    ledger.reset()
    assert ledger.deferred == {}


def test_mandatory_remaining_ignores_optional_tiers() -> None:
    protocol = _demo_protocol()
    remaining = coverage.mandatory_remaining(protocol, {"age_value": "20"})
    assert set(remaining) == {"seizure_occurred", "breathing_difficulty", "cough"}
    assert "appetite" not in remaining


def test_the_ledger_snapshot_separates_debt_from_unanswerable_questions() -> None:
    """"Không biết" là kết quả hợp lệ, không phải nợ (§8.5 quy tắc 3) - hai khái niệm không được trộn."""
    protocol = _demo_protocol()
    ledger = coverage.CoverageLedger()
    ledger.record_turn("D1-01", frozenset({"D1-02"}))
    snapshot = ledger.snapshot(protocol, {"cough": "false"}, unresolved=frozenset({"D1-03"}))

    assert snapshot["deferred"] == {"D1-02": 1}
    assert snapshot["asked_but_unanswered"] == ["D1-03"]
    assert "D1-03" not in snapshot["deferred"]


# --- bất biến độ phủ ------------------------------------------------------------------------------


def _fill(protocol: SymptomProtocol, cluster: QuestionCluster, answers: dict[str, object]) -> None:
    for key in cluster.fields:
        spec = protocol.fields_by_key[key]
        answers[key] = spec.allowed_values[0] if spec.allowed_values else ("false" if spec.tri_state else "2")


def _drive_to_close(protocol: SymptomProtocol, rng: random.Random) -> tuple[str | None, dict[str, object]]:
    """Chạy một phiên giả tới lúc đóng, với thứ tự hỏi bị XÁO bằng `recent_fields` ngẫu nhiên.

    Xáo qua `recent_fields` chứ không qua việc tự chọn cụm: đây đúng là kênh mà người bệnh dùng để
    đổi thứ tự hỏi trong hệ thống thật, nên tính chất kiểm được ở đây cũng là tính chất thật."""
    answers: dict[str, object] = {}
    asked: set[str] = set()
    stage = protocol.stage_order[0]
    all_keys = list(protocol.fields_by_key)
    for _ in range(50):
        context = ranking.RankingContext(
            recent_fields=frozenset(rng.sample(all_keys, rng.randint(0, len(all_keys)))),
        )
        step = stage_machine.advance(
            protocol, stage, answers, asked_ids=frozenset(asked), context=context,
        )
        if step.cluster is None:
            return step.stop_reason, answers
        stage = step.stage
        _fill(protocol, step.cluster, answers)
        asked.add(step.cluster.id)
    raise AssertionError("phiên không đóng sau 50 lượt - nghi vòng lặp trong xếp hạng")


@pytest.mark.parametrize("seed", range(25))
def test_every_ranking_order_still_covers_the_mandatory_fields(seed: int) -> None:
    """BẤT BIẾN QUAN TRỌNG NHẤT của §8: linh hoạt tới đâu, phiên đóng bình thường vẫn phải đủ M0/M1."""
    protocol = _demo_protocol()
    stop_reason, answers = _drive_to_close(protocol, random.Random(seed))

    if stop_reason not in {"RED_FLAG", "USER_CANNOT_CONTINUE"}:
        assert stage_machine.mandatory_fields_covered(protocol, answers), (
            f"đóng phiên với stop_reason={stop_reason} khi còn thiếu "
            f"{coverage.mandatory_remaining(protocol, answers)}"
        )


def test_the_budget_cannot_close_a_session_while_a_mandatory_cluster_remains() -> None:
    """§8.5 quy tắc 2 / §11 mục 7: hết ngân sách chỉ được cắt cụm tier O/H."""
    protocol = _demo_protocol()
    answers: dict[str, object] = {"age_value": "20", "cough": "false"}
    over_budget = protocol.budget["DEFAULT"][1] + 5

    # Cụm ứng viên ngay tại stage này còn mang field M0 ⇒ không được cắt.
    assert stage_machine.should_stop(protocol, "1", answers, asked_count=over_budget) is None
    assert coverage.mandatory_remaining(protocol, answers)


def test_the_budget_cannot_close_before_reaching_a_later_mandatory_stage() -> None:
    """Lỗ hổng thật của bản cũ: stage hiện tại hết cụm ⇒ trả BUDGET_EXHAUSTED ngay, nên `advance`
    không bao giờ đi tới stage quét đỏ đứng sau nó."""
    protocol = _demo_protocol()
    answers: dict[str, object] = {
        "age_value": "20", "cough": "false", "appetite": "false",
        "travel_history": "false", "breathing_difficulty": "false",
    }
    over_budget = protocol.budget["DEFAULT"][1] + 5

    assert stage_machine.eligible_clusters(protocol, "1", answers) == ()
    assert stage_machine.should_stop(protocol, "1", answers, asked_count=over_budget) is None


def test_the_budget_may_close_a_session_once_only_optional_clusters_remain() -> None:
    protocol = _demo_protocol()
    answers: dict[str, object] = {
        "age_value": "20", "cough": "false", "breathing_difficulty": "false",
        "seizure_occurred": "false",
    }
    over_budget = protocol.budget["DEFAULT"][1] + 5

    assert stage_machine.should_stop(protocol, "1", answers, asked_count=over_budget) == "BUDGET_EXHAUSTED"


def test_an_unanswerable_mandatory_field_does_not_make_the_session_unclosable() -> None:
    """Người bệnh không trả lời được một field M0 (cụm đã bỏ dở) thì phiên vẫn phải đóng được.

    Đây là lý do điều kiện tính trên CỤM CÒN LẠI chứ không trên `mandatory_fields_covered`: dùng độ
    phủ field làm điều kiện đóng sẽ tạo ra phiên không bao giờ kết thúc."""
    protocol = _demo_protocol()
    answers: dict[str, object] = {"age_value": "20", "cough": "false", "appetite": "false"}
    abandoned = frozenset({"D1-03", "D1-04", "D2-01"})
    over_budget = protocol.budget["DEFAULT"][1] + 5

    stop = stage_machine.advance(
        protocol, "1", answers, asked_ids=abandoned, asked_count=over_budget,
    )

    assert stop.cluster is None
    assert stop.stop_reason is not None
    assert coverage.mandatory_remaining(protocol, answers)


# --- bước quét sót (§8.6 mục 4) -------------------------------------------------------------------


def test_the_catch_all_question_runs_before_the_session_closes(monkeypatch) -> None:
    """Phiên không được chốt thẳng: phải hỏi một câu mở cuối, kể cả khi lý do dừng là hết ngân sách."""
    from src.services.symptom_protocol import session as session_module

    store = session_module.ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.create()
    session.protocol_name = FEVER_PROTOCOL.name
    session.stage = FEVER_PROTOCOL.stage_order[-1]

    class _Result:
        next_cluster = None
        next_probe = ()
        stop_reason = "BUDGET_EXHAUSTED"
        deferred_cluster_ids = frozenset()
        recent_fields = frozenset()
        dialogue_act = "answer"
        router_trigger = ""

    store._progress(session, _Result())

    assert session.awaiting_catch_all is True
    assert session.state is session_module.SessionState.COLLECTING
    assert session.last_question == session_module.CATCH_ALL_QUESTION

    # Lượt sau chốt thật, và câu quét sót KHÔNG được hỏi lần hai.
    store._progress(session, _Result())
    assert session.state is session_module.SessionState.AWAITING_CONFIRMATION
    assert session.catch_all_asked is True


def test_a_red_flag_stop_skips_the_catch_all_question() -> None:
    """Đã chốt cấp cứu thì việc cần làm là gọi 115, không phải hỏi thêm một câu mở."""
    from src.services.symptom_protocol import session as session_module

    store = session_module.ProtocolSessionStore(default_protocol=FEVER_PROTOCOL)
    session = store.create()
    session.protocol_name = FEVER_PROTOCOL.name

    assert store._ask_catch_all(session, "RED_FLAG") is False
    assert session.catch_all_asked is False


def test_the_catch_all_cluster_only_holds_declared_fields() -> None:
    from src.services.symptom_protocol import session as session_module

    cluster = session_module._catch_all_cluster(FEVER_PROTOCOL, "5")

    assert cluster.id == session_module.CATCH_ALL_CLUSTER_ID
    assert cluster.fields
    assert all(key in FEVER_PROTOCOL.fields_by_key for key in cluster.fields)


# --- protocol thật: không hồi quy trên fever ------------------------------------------------------


def test_fever_safety_fields_come_from_its_emergency_scan_stage() -> None:
    keys = ranking.safety_field_keys(FEVER_PROTOCOL)
    assert {"seizure_occurred", "cyanosis", "consciousness_level"} <= keys
    # Nhiệt độ nằm trong `safety_signal_fields` (nhóm "hay được nói sớm") nhưng KHÔNG phải field an
    # toàn - dùng nhầm tập đó sẽ gắn nhãn an toàn cho cụm hỏi nhiệt độ.
    assert "temp_c" in FEVER_PROTOCOL.safety_signal_fields
    assert "temp_c" not in keys


def test_the_first_active_question_is_the_universal_emergency_scan() -> None:
    """2026-08-22: câu hỏi CHỦ ĐỘNG đầu tiên là quét cấp cứu, KHÔNG phải hỏi tuổi.

    Trước đó ca "đau ngực từ sáng, đi vài bước là hụt hơi" bị hỏi "bé hay người lớn, bao nhiêu
    tuổi" đầu tiên (`registry.py:8`). L0 và `OPENING_CLUSTER` vẫn chạy trước, nhưng cả hai đều THỤ
    ĐỘNG - chúng chỉ bắt được thứ người bệnh tự nói ra."""
    first = stage_machine.next_cluster(FEVER_PROTOCOL, FEVER_PROTOCOL.stage_order[0], {})
    assert first.id in {"Q3-06", "Q3-07", "Q3-12"}
    assert FEVER_PROTOCOL.stage_order[0] == FEVER_PROTOCOL.critical_scan_stage


def test_stage_e_needs_no_demographics_so_it_can_run_at_turn_one() -> None:
    """Điều kiện ĐỂ stage `E` đứng trước nhân khẩu: không cụm nào của nó bị skip theo tuổi/giới.

    Nếu một cụm phụ thuộc tuổi lọt vào `E`, hệ thống sẽ hỏi câu dành cho trẻ sơ sinh cho người lớn
    40 tuổi - đúng loại "hỏi ngu" mà việc chuyển stage này sinh ra để bỏ."""
    for protocol in (FEVER_PROTOCOL, GENERIC_PROTOCOL):
        stage = protocol.critical_scan_stage
        empty = stage_machine.eligible_clusters(protocol, stage, {})
        for age in ({"age_value": 2, "age_unit": "month"}, {"age_value": 40, "age_unit": "year"}):
            assert stage_machine.eligible_clusters(protocol, stage, dict(age)) == empty

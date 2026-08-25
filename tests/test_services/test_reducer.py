"""Reducer L3 (§4/§5) - nguồn sự thật của hồ sơ, và là tầng KHÔNG CÓ MODEL.

Đây là nhóm "Đính chính/rút lời" của §11 cộng bảy quy tắc merge của §5. Toàn bộ file không gọi một
lời model nào: đó chính là điều kiện tồn tại của reducer - nếu việc gộp trạng thái mà phải chạy LLM
mới kiểm được thì sau sự cố không ai dựng lại được hồ sơ để biết chuyện gì đã xảy ra.

Bất biến quan trọng nhất nằm ở `test_snapshot_never_grows_a_fourth_value`: `unset` là OPERATION, và
snapshot vẫn đúng ba giá trị `TriState`. Bài đó đỏ nghĩa là một giá trị thứ tư đã lọt vào tầng luật
an toàn (`rule_engine`, `common_safety/predicates`) - phải dừng lại, không phải sửa test.
"""

from __future__ import annotations

import pytest

from src import paths
from src.services.symptom_protocol import reducer
from src.services.symptom_protocol.models import FieldSpec, QuestionCluster
from src.services.symptom_protocol.protocol import SymptomProtocol


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)


# --- protocol tối giản: chỉ đủ để đọc quan hệ cha-con bằng mắt -----------------------------------

_FIELDS = {
    "fever_reported": FieldSpec("fever_reported", "Có sốt", "M0", "Có sốt không"),
    "temp_c": FieldSpec("temp_c", "Nhiệt độ", "M1", "Bao nhiêu độ", tri_state=False),
    "temp_site": FieldSpec("temp_site", "Vị trí đo", "O", "Đo ở đâu", tri_state=False),
    "cough": FieldSpec("cough", "Ho", "M1", "Có ho không"),
    "seizure_occurred": FieldSpec("seizure_occurred", "Co giật", "M0", "Có co giật không"),
}

_CLUSTERS = (
    QuestionCluster("Q1", "1", ("fever_reported",), script_hint="Có sốt không"),
    QuestionCluster("Q2", "1", ("temp_c", "temp_site"), script_hint="Bao nhiêu độ"),
    QuestionCluster("Q3", "1", ("cough",), script_hint="Có ho không"),
)


def _never(_a: dict[str, object]) -> bool:
    return False


def _protocol(*, confirm: frozenset[str] = frozenset(), derive=None, contradictions=()) -> SymptomProtocol:
    return SymptomProtocol(
        name="demo",
        fields_by_key=_FIELDS,
        clusters=_CLUSTERS,
        stage_order=("1",),
        gate_stages=("1", "1"),
        budget={"DEFAULT": (1, 9)},
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
        field_dependencies={"fever_reported": ("temp_c", "temp_site")},
        confirm_before_retract=confirm,
        contradiction_rules=contradictions,
        derive_fields=derive,
    )


def _set(key: str, value: object, evidence: str = "") -> reducer.FieldEvent:
    """Sự kiện `set` với `certainty` do CODE chấm - đúng đường mà `_emit` đi trong thực tế."""
    return reducer.FieldEvent(
        field=key, operation="set", value=value,
        certainty=reducer.certainty_of(value, evidence), evidence_span=evidence,
    )


def _unset(key: str, evidence: str) -> reducer.FieldEvent:
    return reducer.FieldEvent(field=key, operation="unset", value="unknown", evidence_span=evidence)


# --- §5 quy tắc 1-3: dữ kiện mới thắng, im lặng không xoá được gì ---------------------------------


def test_a_definite_value_overwrites_the_previous_one() -> None:
    """§5 quy tắc 1. Người bệnh có quyền sửa lại lời khai."""
    result = reducer.reduce(_protocol(), {"cough": "true"}, (_set("cough", "false", "mình không ho"),))
    assert result.answers["cough"] == "false"


def test_silence_never_erases_a_known_value() -> None:
    """§5 quy tắc 2. `no_change` là "lượt này không nhắc tới", không phải "rút lại"."""
    events = (reducer.FieldEvent("cough", operation="no_change", value="unknown"),)
    result = reducer.reduce(_protocol(), {"cough": "true"}, events)
    assert result.answers["cough"] == "true"
    assert result.audit == ()


def test_a_never_seen_field_is_still_registered_as_unknown() -> None:
    """Hành vi của `_merge_answers` được giữ nguyên: khoá chưa tồn tại thì `no_change` vẫn tạo nó với
    "unknown". Nhiều chỗ downstream đọc `answers.keys()` để biết field nào đã đi qua schema."""
    events = (reducer.FieldEvent("cough", operation="no_change", value="unknown"),)
    result = reducer.reduce(_protocol(), {}, events)
    assert result.answers["cough"] == "unknown"


def test_the_last_event_of_the_turn_wins() -> None:
    """Caller xếp sự kiện theo thứ tự ưu tiên (safety trước, cụm đang hỏi sau) và reducer tôn trọng
    đúng thứ tự đó - câu trả lời cho chính câu vừa hỏi phải thắng field nhặt bên lề."""
    events = (_set("cough", "true", "hơi ho"), _set("cough", "false", "không ho"))
    assert reducer.reduce(_protocol(), {}, events).answers["cough"] == "false"


# --- §4.2 + §5: `unset` là operation, không phải giá trị thứ tư -----------------------------------


def test_unset_clears_a_known_value_which_no_dict_merge_could_do() -> None:
    """Đây là năng lực MỚI của reducer, và là lý do extractor phải nói bằng sự kiện.

    "Con số 39 độ đó là nhiệt độ phòng, tôi chưa đo lại" không phủ định `fever_reported`, nên không
    có field cha nào để xoá dây chuyền. Trước reducer, `temp_c=39` nằm nguyên trong phiếu bàn giao."""
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(_protocol(), before, (_unset("temp_c", "đó là nhiệt độ phòng"),))
    assert result.answers["temp_c"] == "unknown"
    assert result.answers["fever_reported"] == "true"  # không đụng tới field cha


def test_unset_leaves_an_audit_trail_that_a_dict_cannot_carry() -> None:
    """§5 quy tắc 7: "chưa bao giờ hỏi" và "đã khai rồi rút lại" cùng ra `"unknown"` trong snapshot,
    nên chỉ nhật ký mới phân biệt được hai việc đó."""
    result = reducer.reduce(
        _protocol(), {"temp_c": "39"}, (_unset("temp_c", "đó là nhiệt độ phòng"),),
    )
    entries = [event for event in result.audit if event.kind == reducer.AUDIT_UNSET]
    assert len(entries) == 1
    assert entries[0].field == "temp_c"
    assert entries[0].before == "39"
    assert entries[0].after == "unknown"


def test_unset_on_an_empty_field_is_a_no_op() -> None:
    """Không có gì để rút lại thì không ghi nhật ký - nhật ký đầy dòng vô nghĩa là nhật ký không đọc."""
    result = reducer.reduce(_protocol(), {}, (_unset("temp_c", "chưa đo"),))
    assert result.audit == ()


def test_snapshot_never_grows_a_fourth_value() -> None:
    """§4.2. `rule_engine.evaluate` và `common_safety/predicates` giả định ĐÚNG ba giá trị tri-state;
    thêm giá trị thứ tư là thay đổi lan ra toàn bộ tầng luật an toàn."""
    events = (
        _unset("temp_c", "đó là nhiệt độ phòng"),
        _set("cough", "false", "không ho"),
        reducer.FieldEvent("seizure_occurred", operation="no_change", value="unknown"),
    )
    result = reducer.reduce(_protocol(), {"temp_c": "39", "cough": "true"}, events)
    tri_state_values = {
        value for key, value in result.answers.items() if _FIELDS[key].tri_state
    }
    assert tri_state_values <= {"true", "false", "unknown"}


# --- §5 quy tắc 4: xoá dây chuyền ----------------------------------------------------------------


def test_negating_the_parent_erases_its_dependents() -> None:
    """§11 đính chính mục 1-2: "Tôi sốt 39 độ" -> "39 là nhiệt độ phòng, tôi không sốt"."""
    before = {"fever_reported": "true", "temp_c": "39", "temp_site": "nách"}
    result = reducer.reduce(_protocol(), before, (_set("fever_reported", "false", "tôi không sốt"),))
    assert result.answers["fever_reported"] == "false"
    assert result.answers["temp_c"] == "unknown"
    assert result.answers["temp_site"] == "unknown"


def test_the_cascade_delete_is_recorded_separately_from_what_the_user_said() -> None:
    """Người bệnh nói MỘT câu, hệ thống xoá BA field. Nhật ký phải phân biệt được câu họ nói với hệ
    quả hệ thống tự suy ra - nếu không, phiếu bàn giao trông như người bệnh đã tự rút lại nhiệt độ."""
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(_protocol(), before, (_set("fever_reported", "false", "tôi không sốt"),))
    kinds = {event.field: event.kind for event in result.audit}
    assert kinds["fever_reported"] == reducer.AUDIT_SET
    assert kinds["temp_c"] == reducer.AUDIT_RETRACT_DEPENDENT


def test_the_cluster_holding_an_erased_field_is_reopened() -> None:
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(_protocol(), before, (_set("fever_reported", "false", "tôi không sốt"),))
    assert "Q2" in result.reopened_clusters


# --- §5 quy tắc 5: đính chính rủi ro phải xin xác nhận --------------------------------------------


def test_a_disease_name_never_erases_the_symptom_record() -> None:
    """§11 đính chính mục 3 - và là bug C2 ở dạng nguyên bản.

    "Bé không sốt xuất huyết" phủ định một TÊN BỆNH, không phải triệu chứng sốt. Chuỗi "sốt" nằm
    trong cả hai câu nên không matcher nào phân biệt được nếu không biết danh sách tên bệnh."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(protocol, before, (_set("fever_reported", "false", "bé không sốt xuất huyết"),))
    assert result.answers["fever_reported"] == "true"
    assert result.answers["temp_c"] == "39"
    assert result.pending_confirmation == ("fever_reported",)


def test_a_clear_correction_is_applied_immediately_without_asking() -> None:
    """Cổng xác nhận phải HẸP: mỗi field bị giữ lại tốn của người bệnh một lượt, và một agent hỏi lại
    quá nhiều thì họ bỏ giữa chừng - lúc đó độ phủ bằng 0 (§1 mục 5)."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(protocol, before, (_set("fever_reported", "false", "à nhầm, tôi không sốt"),))
    assert result.answers["fever_reported"] == "false"
    assert result.answers["temp_c"] == "unknown"
    assert result.pending_confirmation == ()


def test_a_first_time_answer_is_not_treated_as_a_correction() -> None:
    """Regression đo được: bản đầu chỉ kiểm `certainty` nên ca lành tính dài thêm một lượt.

    Model trả JSON dạng phẳng (không `evidence_span`) thì MỌI câu "không" đều là `inferred`, kể cả
    lần trả lời ĐẦU TIÊN cho chính câu vừa hỏi. Trả lời lần đầu thì không có gì để rút lại."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "unknown"}
    events = (_set("fever_reported", "false"), _set("temp_c", "38.3"))
    result = reducer.reduce(protocol, before, events)
    assert result.pending_confirmation == ()
    assert result.answers["fever_reported"] == "false"


def test_holding_a_retraction_is_recorded_so_the_gap_is_auditable() -> None:
    """Hệ thống vừa BỎ QUA một câu người bệnh nói. Đó là quyết định đúng ở đây, nhưng nó phải để lại
    dấu vết - một lời khai biến mất không dấu vết là thứ không điều tra được sau sự cố."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(protocol, before, (_set("fever_reported", "false", "không phải sốt xuất huyết"),))
    assert any(event.kind == reducer.AUDIT_RETRACT_HELD for event in result.audit)


def test_the_second_pass_applies_the_retraction_after_the_question_was_asked() -> None:
    """Hỏi ĐÚNG MỘT LẦN. Không có cổng này thì một phiên mà model liên tục trả bằng chứng mờ sẽ lặp
    mãi cùng câu xác nhận, và lời đính chính vẫn không bao giờ vào được hồ sơ."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(
        protocol, before, (_set("fever_reported", "false", "không phải sốt xuất huyết"),),
        confirmed_retractions=frozenset({"fever_reported"}),
    )
    assert result.answers["fever_reported"] == "false"
    assert result.answers["temp_c"] == "unknown"
    assert result.pending_confirmation == ()


def test_a_field_outside_confirm_before_retract_is_never_held() -> None:
    protocol = _protocol(confirm=frozenset())
    before = {"fever_reported": "true", "temp_c": "39"}
    result = reducer.reduce(protocol, before, (_set("fever_reported", "false", "không sốt xuất huyết"),))
    assert result.pending_confirmation == ()
    assert result.answers["fever_reported"] == "false"


# --- §5 quy tắc 6: mâu thuẫn thì hỏi, không tự chọn -----------------------------------------------


def test_a_contradiction_reopens_the_cluster_without_changing_any_value() -> None:
    """Khi hai lời khai chọi nhau, hệ thống không có căn cứ để chọn bên nào."""
    def _detect(answers: dict[str, object]) -> tuple[str, ...]:
        if answers.get("fever_reported") == "false" and answers.get("temp_c") == "39.2":
            return ("fever_reported", "temp_c")
        return ()

    protocol = _protocol(contradictions=(_detect,))
    result = reducer.reduce(protocol, {"fever_reported": "false"}, (_set("temp_c", "39.2", "39.2 độ"),))
    assert result.contradicted == frozenset({"fever_reported", "temp_c"})
    assert result.answers["fever_reported"] == "false"
    assert result.answers["temp_c"] == "39.2"
    assert {"Q1", "Q2"} <= result.reopened_clusters


# --- tất định: cùng input, cùng output ------------------------------------------------------------


def test_the_reducer_is_deterministic() -> None:
    """Tầng "KHÔNG model" của §1 mục 1: chạy hai lần phải bằng nhau, nếu không thì sau sự cố không
    dựng lại được hồ sơ."""
    protocol = _protocol(confirm=frozenset({"fever_reported"}))
    before = {"fever_reported": "true", "temp_c": "39"}
    events = (_set("fever_reported", "false", "tôi không sốt"), _set("cough", "true", "có ho"))
    first = reducer.reduce(protocol, before, events)
    second = reducer.reduce(protocol, before, events)
    assert first.answers == second.answers
    assert first.audit == second.audit
    assert first.pending_confirmation == second.pending_confirmation


def test_the_reducer_does_not_mutate_the_previous_snapshot() -> None:
    """`before` là hồ sơ của lượt TRƯỚC. Sửa tại chỗ thì lịch sử biến mất và `apply_retraction` -
    vốn so `before` với `after` - mất luôn căn cứ để biết field cha có đổi giá trị hay không."""
    protocol = _protocol()
    before = {"fever_reported": "true", "temp_c": "39"}
    reducer.reduce(protocol, before, (_set("fever_reported", "false", "tôi không sốt"),))
    assert before == {"fever_reported": "true", "temp_c": "39"}


# --- `certainty` do code chấm, không lấy nhãn model ------------------------------------------------


@pytest.mark.parametrize("evidence", ["", "không", "Không ạ", "ko", "unknown", "-"])
def test_a_bare_negation_particle_proves_nothing(evidence: str) -> None:
    """Hạt phủ định trần nằm trong hầu hết mọi câu trả lời nên chứng minh được mọi thứ, tức là không
    chứng minh được gì."""
    assert reducer.certainty_of("false", evidence) == "inferred"


def test_a_span_naming_the_symptom_itself_is_explicit() -> None:
    assert reducer.certainty_of("false", "mình không sốt") == "explicit"


def test_an_affirmative_is_never_downgraded() -> None:
    """Cân nhắc bất đối xứng, cùng lý do với `_needs_evidence`: bịa một `"true"` chỉ đẩy ca lên mức
    thận trọng hơn, còn loại nhầm một `"true"` thật là bỏ sót cấp cứu."""
    assert reducer.certainty_of("true", "") == "explicit"


def test_the_disease_vocabulary_is_shared_with_the_output_guard() -> None:
    """Hai bản sao lệch nhau nghĩa là một tên bệnh chặn được ở đầu ra nhưng vẫn xoá được hồ sơ ở đầu
    vào."""
    from src.services.symptom_protocol import output_guard

    for name in output_guard.DISEASE_NAMES:
        assert reducer.mentions_disease_name(f"không bị {name}")


# --- cầu nối cho nguồn chưa nói được ngôn ngữ sự kiện ---------------------------------------------


def test_values_from_a_keyword_scan_never_become_a_retraction() -> None:
    """Quét từ khoá không phân biệt được "rút lại lời khai" với "lượt này không nhắc tới", nên mặc
    định an toàn của `events_from_values` là không xoá gì."""
    events = reducer.events_from_values({"cough": "unknown"}, source=reducer.SOURCE_KEYWORD)
    assert [event.operation for event in events] == ["no_change"]
    result = reducer.reduce(_protocol(), {"cough": "true"}, events)
    assert result.answers["cough"] == "true"


def test_derived_fields_are_recomputed_after_the_merge() -> None:
    def _derive(answers: dict[str, object]) -> dict[str, object]:
        return {"temp_site": "suy ra"} if answers.get("temp_c") else {}

    result = reducer.reduce(_protocol(derive=_derive), {}, (_set("temp_c", "39", "39 độ"),))
    assert result.answers["temp_site"] == "suy ra"

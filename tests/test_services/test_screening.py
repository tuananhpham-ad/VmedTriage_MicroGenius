"""Sàng lọc theo nhóm cơ quan (`symptom_protocol/screening.py`) — Phase 1-4 của plan
`docs-medical-knowledge-fever-knowledge-delightful-cosmos.md`.

Phần lớn test ở đây THUẦN (không LLM): `apply_verdicts`/`unresolved_groups`/`next_probe` là hàm xác
định, và đó chính là lý do cơ chế này được thiết kế để chặn bằng CODE chứ không bằng model mạnh hơn.
Hai test cuối chạy qua `run_turn` với provider giả để canh hai bất biến an toàn không thể kiểm ở tầng
hàm thuần: chốt đỏ vẫn nổ ngay trong lượt sàng lọc, và verdict phủ định không có bằng chứng thì không
đóng được gì.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src import paths
from src.services.checklists.fever_checklist import CLUSTERS_BY_ID
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.engines.generic_protocol import GENERIC_PROTOCOL
from src.services.infra import fever_stage_log, provider_router
from src.services.symptom_protocol import intake_agent, screening
from src.services.symptom_protocol.models import ScreeningGroup

STAGE_3A, STAGE_3B = FEVER_PROTOCOL.gate_stages

GROUPS_3A = tuple(g for g in FEVER_PROTOCOL.screening_groups if g.stage == STAGE_3A)
GROUPS_3B = tuple(g for g in FEVER_PROTOCOL.screening_groups if g.stage == STAGE_3B)

# Stage 3A có 5 nhóm nhưng MỘT câu sàng lọc chỉ được đọc tối đa `MAX_GROUPS_PER_PROBE` nhóm - phần
# dư rơi sang vòng sau. Tính từ hằng số thay vì viết cứng 3: đổi trần là quyết định về UX, không phải
# lý do phải sửa lại từng assert ở đây.
GROUPS_3A_ROUND_1 = GROUPS_3A[: screening.MAX_GROUPS_PER_PROBE]
GROUPS_3A_ROUND_2 = GROUPS_3A[screening.MAX_GROUPS_PER_PROBE :]

ADULT = {"age_value": "30", "age_unit": "year", "sex": "male", "reporter_type": "self"}
# Trạng thái NGAY TRƯỚC lượt sàng lọc đầu tiên của Stage 3A: hai cụm đứng ngoài mọi nhóm (tri giác,
# co giật) đã được hỏi riêng xong, nên cụm kế tiếp là Q3-04 - cụm đầu tiên nằm trong một nhóm.
ADULT_PAST_SOLO_CLUSTERS = dict(
    ADULT,
    consciousness_level="alert", social_response_child="not_applicable",
    seizure_occurred="false", seizure_active_now="false", seizure_features="none",
)
TODDLER = {"age_value": "3", "age_unit": "year", "sex": "female", "reporter_type": "parent_caregiver"}

MESSAGE = "dạ không có dấu hiệu nào trong số đó ạ"


def _always_ok(_evidence: object) -> bool:
    return True


def _verdicts(groups, verdict: str, evidence: str | None = MESSAGE) -> dict:
    body = {"verdict": verdict}
    if evidence is not None:
        body["evidence"] = evidence
    return {"groups": {group.id: dict(body) for group in groups}}


# --- Data của fever: nhóm phải khớp tài liệu -----------------------------------------------------


def test_fever_screening_groups_reference_real_clusters():
    """Mã cụm sai chính tả trong data bị `clusters_of` bỏ qua IM LẶNG (cố ý - không làm sập service vì
    một lỗi gõ), nên phải có test canh, nếu không một nhóm rỗng sẽ âm thầm không đóng được gì."""
    for group in FEVER_PROTOCOL.screening_groups:
        found = {cluster.id for cluster in screening.clusters_of(FEVER_PROTOCOL, group)}
        assert found == set(group.cluster_ids), group.id
        for cluster in screening.clusters_of(FEVER_PROTOCOL, group):
            assert cluster.stage == group.stage, f"{group.id} gộp cụm khác stage: {cluster.id}"


def test_consciousness_and_seizure_clusters_stay_outside_every_group():
    """CS §3.3A cấm suy diễn tri giác (Q3-01) và co giật (Q3-03) từ một câu phủ định gộp. Đây là ràng
    buộc LÂM SÀNG, không phải lựa chọn kỹ thuật - nên nó phải có test riêng chứ không nằm nhờ vào việc
    hai cụm đó tình cờ đứng đầu danh sách."""
    grouped = {cid for group in FEVER_PROTOCOL.screening_groups for cid in group.cluster_ids}
    assert "Q3-01" not in grouped
    assert "Q3-03" not in grouped
    assert "Q3-14" not in grouped  # câu "gut-check" thang 0-10, không phủ định gộp được một con số


def test_every_other_scan_cluster_belongs_to_exactly_one_group():
    outside = {"Q3-01", "Q3-03", "Q3-14"}
    for stage, groups in ((STAGE_3A, GROUPS_3A), (STAGE_3B, GROUPS_3B)):
        expected = {c.id for c in FEVER_PROTOCOL.clusters if c.stage == stage} - outside
        seen: list[str] = [cid for group in groups for cid in group.cluster_ids]
        assert sorted(seen) == sorted(set(seen)), f"{stage}: một cụm nằm trong 2 nhóm"
        assert set(seen) == expected, stage


# --- apply_verdicts ------------------------------------------------------------------------------


def test_negative_verdict_writes_false_and_enum_negatives_for_the_whole_group():
    group = next(g for g in GROUPS_3A if g.id == "G3A-CIRC")
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, (group,), _verdicts((group,), "negative"), dict(ADULT),
        evidence_ok=_always_ok,
    )
    assert outcome.closed_cluster_ids == frozenset({"Q3-08", "Q3-09"})
    assert outcome.negative_group_ids == ("G3A-CIRC",)
    assert outcome.negatives["cold_clammy_skin"] == "false"       # tri-state
    assert outcome.negatives["urine_output"] == "normal"          # enum có giá trị âm tính
    assert outcome.negatives["vomiting_severity"] == "none"


def test_detail_only_enum_fields_get_no_invented_negative_value():
    """`rash_type`/`abdominal_pain_location` chỉ có nghĩa khi DƯƠNG tính. Không có giá trị "không có
    kiểu ban nào" trong enum, nên ghi bừa một giá trị vào đó là dựng dữ liệu lâm sàng không ai khai."""
    groups = tuple(g for g in GROUPS_3A if g.id in ("G3A-BLEED", "G3A-ABDO"))
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, groups, _verdicts(groups, "negative"), dict(ADULT),
        evidence_ok=_always_ok,
    )
    assert "rash_type" not in outcome.negatives
    assert "abdominal_pain_location" not in outcome.negatives
    assert outcome.negatives["abdominal_pain_severity"] == "none"
    # ...nhưng cụm VẪN phải đóng: nếu chỉ dựa vào dữ liệu thì `cluster_needs_answer` còn trả True vì
    # `rash_type` trống, và người bệnh bị hỏi lại đúng thứ vừa phủ định.
    assert "Q3-11" in outcome.closed_cluster_ids
    assert "Q3-13" in outcome.closed_cluster_ids


def test_positive_verdict_writes_nothing_so_clusters_are_asked_one_by_one():
    """`positive` nghĩa là "nhóm này có vấn đề", chưa nói dấu hiệu NÀO. Ghi `"true"` cho cả nhóm sẽ
    chốt cấp cứu trên dữ liệu bịa - hướng hỏng nặng hơn hẳn việc hỏi thừa vài lượt."""
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, GROUPS_3A, _verdicts(GROUPS_3A, "positive"), dict(ADULT),
        evidence_ok=_always_ok,
    )
    assert outcome.negatives == {}
    assert outcome.closed_cluster_ids == frozenset()
    assert set(outcome.positive_group_ids) == {g.id for g in GROUPS_3A}


def test_unknown_verdict_and_missing_group_write_nothing():
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, GROUPS_3A, {"groups": {}}, dict(ADULT), evidence_ok=_always_ok,
    )
    assert outcome.negatives == {}
    assert outcome.closed_cluster_ids == frozenset()
    assert outcome.rejected_group_ids == ()


def test_negative_verdict_without_verifiable_evidence_is_rejected():
    """Đúng chiều lỗi C1 ở quy mô nhóm: model khai "không có gì" nhưng không trích được câu nào trong
    tin nhắn ⇒ bỏ verdict, nhóm vẫn phải hỏi."""
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, GROUPS_3A, _verdicts(GROUPS_3A, "negative", evidence="tôi bịa ra câu này"),
        dict(ADULT), evidence_ok=lambda evidence: intake_agent._evidence_in_message(evidence, MESSAGE, allow_bare=True),
    )
    assert outcome.negatives == {}
    assert outcome.closed_cluster_ids == frozenset()
    assert set(outcome.rejected_group_ids) == {g.id for g in GROUPS_3A}


def test_flat_verdict_string_can_never_close_a_group():
    """Dạng phẳng `"G3A-RESP": "negative"` không kèm trích dẫn nào ⇒ không đủ điều kiện đóng."""
    parsed = {"groups": {group.id: "negative" for group in GROUPS_3A}}
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, GROUPS_3A, parsed, dict(ADULT),
        evidence_ok=lambda evidence: intake_agent._evidence_in_message(evidence, MESSAGE, allow_bare=True),
    )
    assert outcome.closed_cluster_ids == frozenset()


def test_group_negative_never_overwrites_what_the_patient_already_confirmed():
    """Người bệnh đã khai CÓ chảy máu chân răng ở lượt trước; một câu phủ định gộp sau đó không được
    xoá nó đi. Cùng nguyên tắc đơn điệu với `_merge_answers` (vá M3), áp ở tầng nhóm."""
    answers = dict(ADULT, mucosal_bleeding="true", urine_output="reduced")
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, GROUPS_3A, _verdicts(GROUPS_3A, "negative"), answers,
        evidence_ok=_always_ok,
    )
    assert "mucosal_bleeding" not in outcome.negatives
    assert "urine_output" not in outcome.negatives
    assert outcome.negatives["gi_bleeding"] == "false"  # field còn trống của cùng cụm vẫn được ghi


def test_skipped_cluster_is_not_closed_by_a_group_negative():
    """Q3-02 tự loại khi dưới 16 tuổi (`_skip_q3_02`). Nhóm `G3B-COG` chỉ chứa nó, nên với trẻ 3 tuổi
    verdict phủ định không có cụm nào để đóng - và cũng không được ghi `new_confusion=false` cho một
    câu chưa bao giờ áp dụng được."""
    group = next(g for g in GROUPS_3B if g.id == "G3B-COG")
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3B, (group,), _verdicts((group,), "negative"), dict(TODDLER),
        evidence_ok=_always_ok,
    )
    assert outcome.closed_cluster_ids == frozenset()
    assert "new_confusion" not in outcome.negatives


# --- unresolved_groups / next_probe --------------------------------------------------------------


def test_unresolved_groups_ignores_groups_whose_clusters_are_all_closed():
    closed = frozenset({"Q3-04", "Q3-05"})
    remaining = screening.unresolved_groups(FEVER_PROTOCOL, STAGE_3A, dict(ADULT), closed_ids=closed)
    assert "G3A-NEURO" not in {group.id for group in remaining}
    assert len(remaining) == len(GROUPS_3A) - 1


def test_unresolved_groups_respects_skip_rule():
    remaining = {g.id for g in screening.unresolved_groups(FEVER_PROTOCOL, STAGE_3B, dict(TODDLER))}
    assert "G3B-COG" not in remaining  # Q3-02 bị skip ở tuổi 3
    assert {"G3B-FUNC", "G3B-MSK"} <= remaining


def test_no_probe_for_a_cluster_outside_every_group():
    """Q3-01 (tri giác) đứng đầu Stage 3A và không thuộc nhóm nào ⇒ được hỏi riêng đúng script chuẩn.
    Không có luật đặc biệt nào cho việc này - chính điều kiện "candidate phải thuộc một nhóm" lo."""
    assert screening.next_probe(FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-01"]) == ()
    assert screening.next_probe(FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-03"]) == ()


def test_probe_fires_once_the_candidate_is_inside_a_group():
    groups = screening.next_probe(FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"])
    assert [group.id for group in groups] == [group.id for group in GROUPS_3A_ROUND_1]


def test_one_probe_never_reads_more_than_the_length_cap():
    """Cả cơ chế dựa trên tiền đề "người bệnh ĐÃ nhìn thấy danh sách dấu hiệu của nhóm". Tiền đề đó
    yếu dần theo độ dài câu hỏi, nên số dòng đọc lên trong MỘT câu phải có trần."""
    groups = screening.next_probe(FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"])

    assert len(GROUPS_3A) > screening.MAX_GROUPS_PER_PROBE  # nếu không thì test này vô nghĩa
    assert len(groups) == screening.MAX_GROUPS_PER_PROBE


def test_no_probe_when_fewer_than_two_groups_remain():
    closed = frozenset({"Q3-06", "Q3-07", "Q3-08", "Q3-09", "Q3-11", "Q3-12", "Q3-13"})
    assert screening.next_probe(
        FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"], closed_ids=closed,
    ) == ()


def test_no_probe_after_the_round_budget_is_used_up():
    """Hết hạn mức thì tự rơi về đường hỏi từng cụm - không nhánh nào làm hội thoại treo."""
    spent = tuple(frozenset({"G3A-NEURO"}) for _ in range(FEVER_PROTOCOL.max_screening_rounds))
    assert screening.next_probe(
        FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"], history=spent,
    ) == ()


def test_no_second_round_when_every_group_left_was_already_read_out():
    """Vòng đầu không thu được gì ⇒ các nhóm còn lại đều là nhóm vừa đọc ⇒ vòng hai sẽ đọc lại NGUYÊN
    VĂN danh sách đó. Đọc lại là cách nhanh nhất để người bệnh bỏ cuộc, nên đường lùi đúng là hỏi
    từng cụm."""
    same = frozenset(group.id for group in GROUPS_3A)
    assert screening.next_probe(
        FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"], history=(same,),
    ) == ()


def test_second_round_reads_out_the_groups_the_first_round_had_no_room_for():
    """Đây là ca `max_screening_rounds=2` sinh ra để phục vụ, và cũng là lý do điều kiện chặn lặp
    phải là "có nhóm chưa đọc" chứ không phải "tập nhóm co lại": vòng đầu chỉ đủ chỗ cho
    `MAX_GROUPS_PER_PROBE` nhóm, phần dư CHƯA ai nghe nên bắt buộc phải có vòng sau."""
    read_first = frozenset(g.id for g in GROUPS_3A_ROUND_1)
    groups = screening.next_probe(
        FEVER_PROTOCOL, STAGE_3A, dict(ADULT), CLUSTERS_BY_ID["Q3-04"], history=(read_first,),
    )

    assert {g.id for g in GROUPS_3A_ROUND_2} <= {group.id for group in groups}
    assert len(groups) <= screening.MAX_GROUPS_PER_PROBE


def test_probe_is_never_offered_to_a_protocol_without_screening_groups():
    """Bằng chứng cho lời hứa "protocol không khai nhóm chạy y như cũ": `screening.py` không có gì để
    làm nên không lượt nào đổi hành vi.

    Trước đây test này dùng `GENERIC_PROTOCOL` làm ví dụ. Generic giờ ĐÃ khai nhóm (nó phục vụ 6/7
    nhóm triệu chứng, để nó hỏi tuần tự từng cụm quét đỏ là bỏ phí đúng cơ chế này), nên bất biến
    phải được kiểm trên một protocol thật sự không khai nhóm - dựng tại chỗ từ chính generic."""
    from dataclasses import replace

    without_groups = replace(GENERIC_PROTOCOL, screening_groups=())
    for cluster in without_groups.clusters[:5]:
        assert screening.next_probe(without_groups, cluster.stage, {}, cluster) == ()


def test_generic_protocol_screens_the_same_universal_groups_as_fever():
    """Generic dùng lại đúng bộ cụm quét đỏ/quét khám sớm của `common_safety`, chỉ khác tên stage -
    nên phải dùng lại đúng bộ nhóm đó, không được để trống."""
    stages = {group.stage for group in GENERIC_PROTOCOL.screening_groups}

    assert GENERIC_PROTOCOL.screening_groups != ()
    assert set(GENERIC_PROTOCOL.gate_stages) <= stages


# --- câu hỏi sàng lọc ----------------------------------------------------------------------------


def test_probe_question_lists_every_group_hint_verbatim():
    """Bất biến an toàn của cả cơ chế: một nhóm chỉ được đóng khi người bệnh ĐÃ nghe đọc danh sách dấu
    hiệu của nó. Câu hỏi được ghép TĨNH nên phép kiểm này là đủ - nếu đưa qua LLM diễn đạt lại thì
    không có cách nào đảm bảo được điều đó nữa."""
    question = screening.probe_question(GROUPS_3A)
    for group in GROUPS_3A:
        assert group.probe_hint in question
    assert screening.PROBE_INTRO in question


def test_probe_cluster_covers_every_field_of_every_grouped_cluster():
    cluster = screening.probe_cluster(FEVER_PROTOCOL, STAGE_3A, GROUPS_3A)
    assert cluster.id.startswith(screening.PROBE_ID_PREFIX)
    assert cluster.batch_negation is False  # phủ định gộp ở đây đi qua verdict theo NHÓM
    expected = {
        key
        for group in GROUPS_3A
        for c in screening.clusters_of(FEVER_PROTOCOL, group)
        for key in c.fields
    }
    assert set(cluster.fields) == expected
    assert cluster.id not in {c.id for c in FEVER_PROTOCOL.clusters}  # không lẫn vào danh sách thật


def test_parse_verdicts_survives_garbage():
    assert screening.parse_verdicts({}) == {}
    assert screening.parse_verdicts({"groups": "không phải dict"}) == {}
    assert screening.parse_verdicts({"groups": {"X": {"verdict": "chắc là không"}}}) == {"X": ("unknown", None)}


# --- qua `run_turn` với provider giả -------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    yield


def _fake_complete(response_json: dict) -> Mock:
    return Mock(
        return_value=provider_router.CompletionResult(
            text=json.dumps(response_json), provider="scripted", model="scripted",
        )
    )


def _run_probe_turn(monkeypatch, response: dict, message: str, answers: dict):
    monkeypatch.setattr(provider_router, "complete", _fake_complete(response))
    session_id = "screening-turn"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=16)
    probe = GROUPS_3A
    cluster = screening.probe_cluster(FEVER_PROTOCOL, STAGE_3A, probe)
    return intake_agent.run_turn(
        FEVER_PROTOCOL, session_id, turn=1, stage=STAGE_3A, cluster=cluster, message=message,
        answers=answers, probe=probe,
        screening_history={STAGE_3A: (frozenset(group.id for group in probe),)},
    )


def test_red_flag_told_during_a_screening_turn_still_stops_immediately(monkeypatch):
    """P0-5 không được nới ra vì lượt sàng lọc. Người bệnh trả lời câu gộp bằng "môi cháu tím lại" thì
    rule engine phải chốt cấp cứu NGAY trong chính lượt đó, không hỏi nốt các nhóm còn lại."""
    message = "dạ môi cháu tím lại rồi ạ"
    response = {
        "groups": {"G3A-RESP": {"verdict": "positive"}},
        "cyanosis": {"value": "true", "evidence_span": "môi cháu tím lại"},
    }
    result = _run_probe_turn(monkeypatch, response, message, dict(ADULT))

    assert result.emergency is True
    assert result.triage_level == "EMERGENCY"
    assert "RF-08" in result.reason_codes
    assert result.screened_cluster_ids == frozenset()


def test_screening_turn_closes_clusters_and_keeps_them_out_of_the_budget(monkeypatch):
    response = {"groups": {group.id: {"verdict": "negative", "evidence": MESSAGE} for group in GROUPS_3A}}
    result = _run_probe_turn(monkeypatch, response, MESSAGE, dict(ADULT))

    assert result.emergency is False
    # 9 cụm đóng bằng ĐÚNG MỘT câu hỏi - đây là toàn bộ mục đích của cơ chế.
    assert result.screened_cluster_ids == frozenset(
        {"Q3-04", "Q3-05", "Q3-06", "Q3-07", "Q3-08", "Q3-09", "Q3-11", "Q3-12", "Q3-13"}
    )
    assert result.answers["urine_output"] == "normal"
    assert result.answers["non_blanching_rash"] == "false"
    # Không còn nhóm nào chưa giải quyết ⇒ lượt sau là câu hỏi cụm thường, không phải sàng lọc nữa.
    assert result.next_probe == ()
    assert result.next_cluster is not None and not screening.is_probe(result.next_cluster)


def test_a_screening_turn_that_harvests_nothing_falls_back_instead_of_repeating_itself(monkeypatch):
    """Đọc lại đúng danh sách dài đó lần nữa là cách nhanh nhất để người bệnh bỏ cuộc. Đường lùi đúng
    là quay về hỏi từng cụm theo script chuẩn."""
    result = _run_probe_turn(
        monkeypatch, {"groups": {}}, "em không hiểu ý câu hỏi", dict(ADULT_PAST_SOLO_CLUSTERS),
    )

    assert result.retried_same_cluster is False
    assert result.cluster_resolved is True
    assert result.screened_cluster_ids == frozenset()
    assert result.next_cluster is not None and result.next_cluster.id == "Q3-04"


def test_probe_question_is_static_and_costs_no_extra_llm_call(monkeypatch):
    """Lượt phát ra câu sàng lọc chỉ tốn 1 call (trích xuất), không có call thứ hai để diễn đạt lại
    câu hỏi - vừa rẻ hơn, vừa là ràng buộc an toàn (xem `screening.probe_question`)."""
    fake = _fake_complete({"seizure_occurred": "false", "seizure_active_now": "false"})
    monkeypatch.setattr(provider_router, "complete", fake)
    session_id = "screening-static-question"
    fever_stage_log.start(session_id, route="ROUTE_STANDARD", budget=16)

    # Lượt trả lời Q3-03 (cụm cuối cùng đứng ngoài nhóm) - lượt kế tiếp phải là câu sàng lọc gộp.
    result = intake_agent.run_turn(
        FEVER_PROTOCOL, session_id, turn=1, stage=STAGE_3A, cluster=CLUSTERS_BY_ID["Q3-03"],
        message="dạ cháu không co giật gì cả",
        answers=dict(ADULT, consciousness_level="alert", social_response_child="not_applicable"),
        asked_ids=frozenset({"Q3-01"}),
    )

    assert [group.id for group in result.next_probe] == [group.id for group in GROUPS_3A_ROUND_1]
    assert result.agent_message == screening.probe_question(GROUPS_3A_ROUND_1)
    assert fake.call_count == 1


def test_screening_group_may_be_declared_with_no_negative_values():
    """`negative_values` là tuỳ chọn - nhóm chỉ có field tri-state không phải khai gì."""
    group = ScreeningGroup(id="G-X", stage="3A", cluster_ids=("Q3-05",), probe_hint="thử")
    outcome = screening.apply_verdicts(
        FEVER_PROTOCOL, STAGE_3A, (group,), _verdicts((group,), "negative"), dict(ADULT),
        evidence_ok=_always_ok,
    )
    assert outcome.negatives == {"focal_neuro_deficit": "false"}

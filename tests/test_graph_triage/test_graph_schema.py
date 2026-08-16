"""Hợp đồng `patient_graph_v1`: chỉ chấp nhận bằng chứng trích được nguyên văn từ text nguồn.

Đây là lớp chống bịa của nhánh graph - nếu `validate_provenance` nới ra thì mô hình có thể gán cho
bệnh nhân một triệu chứng không hề có trong phiếu tóm tắt.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.graph_triage.graph_schema import NODE_TYPES, ClinicalGraph, edge_triples, validate_provenance
from src.paths import RUNS_DIR

REPORT = "Bố tôi 72 tuổi đau tức giữa ngực từ sáng"

GRAPH_PAYLOAD = {
    "schema_version": "patient_graph_v1",
    "patient": {
        "age": 72,
        "report_source": "family_member",
        "provenance": {"source_span": "Bố tôi 72 tuổi", "source_turn": 1, "source_role": "family_member"},
    },
    "nodes": [
        {
            "id": "chest_pain_1",
            "type": "symptom",
            "concept": "chest_pain",
            "canonical_name": "Chest pain",
            "experiencer": "target_patient",
            "observations": [
                {
                    "surface_form": "đau tức giữa ngực",
                    "status": "present",
                    "onset_text": "từ sáng",
                    "provenance": {"source_span": "đau tức giữa ngực từ sáng", "source_turn": 1, "source_role": "family_member"},
                }
            ],
        },
        {
            "id": "chest_1",
            "type": "body_location",
            "concept": "chest",
            "canonical_name": "Chest",
            "experiencer": "target_patient",
            "observations": [
                {
                    "surface_form": "giữa ngực",
                    "status": "present",
                    "provenance": {"source_span": "đau tức giữa ngực từ sáng", "source_turn": 1, "source_role": "family_member"},
                }
            ],
        },
    ],
    "edges": [
        {"source": "patient", "relation": "has_symptom", "target": "chest_pain_1", "provenance": {"source_span": "đau tức giữa ngực từ sáng", "source_turn": 1, "source_role": "family_member"}},
        {"source": "chest_pain_1", "relation": "located_at", "target": "chest_1", "provenance": {"source_span": "đau tức giữa ngực từ sáng", "source_turn": 1, "source_role": "family_member"}},
    ],
}


def test_valid_graph_round_trips_and_passes_provenance():
    graph = ClinicalGraph.model_validate(GRAPH_PAYLOAD)
    validate_provenance(graph, REPORT)
    assert ClinicalGraph.model_validate(graph.model_dump(mode="json")) == graph


def test_provenance_span_absent_from_report_is_rejected():
    payload = ClinicalGraph.model_validate(GRAPH_PAYLOAD).model_dump(mode="json")
    payload["nodes"][0]["observations"][0]["surface_form"] = "khó thở"
    payload["nodes"][0]["observations"][0]["provenance"]["source_span"] = "khó thở nhiều"
    graph = ClinicalGraph.model_validate(payload)
    with pytest.raises(ValueError, match="not a contiguous verbatim substring"):
        validate_provenance(graph, REPORT)


def test_surface_form_must_sit_inside_its_own_source_span():
    payload = ClinicalGraph.model_validate(GRAPH_PAYLOAD).model_dump(mode="json")
    payload["nodes"][0]["observations"][0]["surface_form"] = "sốt cao"
    with pytest.raises(ValidationError, match="is not a contiguous substring of its source_span"):
        ClinicalGraph.model_validate(payload)


def test_target_patient_symptom_requires_its_patient_edge():
    payload = ClinicalGraph.model_validate(GRAPH_PAYLOAD).model_dump(mode="json")
    payload["edges"] = [edge for edge in payload["edges"] if edge["relation"] != "has_symptom"]
    with pytest.raises(ValidationError, match='"relation":"has_symptom"'):
        ClinicalGraph.model_validate(payload)


def test_whitespace_normalisation_lets_summary_template_spans_match():
    """Phiếu tóm tắt xuống dòng giữa các mục; span vẫn phải khớp sau khi chuẩn hoá khoảng trắng."""
    graph = ClinicalGraph.model_validate(GRAPH_PAYLOAD)
    validate_provenance(graph, "Tóm tắt:\n- Mô tả: Bố tôi 72 tuổi   đau tức giữa ngực\n  từ sáng\n")


def _with_severity(value):
    payload = ClinicalGraph.model_validate(GRAPH_PAYLOAD).model_dump(mode="json")
    payload["nodes"][0]["observations"][0]["subjective_severity"] = value
    return ClinicalGraph.model_validate(payload).nodes[0].observations[0].subjective_severity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(7, 7.0), ("7", 7.0), ("7/10", 7.0), ("7 trên 10", 7.0), ("7.5/10", 7.5), ("6,5", 6.5)],
)
def test_severity_scale_strings_are_parsed(raw, expected):
    """Model hay trả "7/10" thay vì số trần; trước khi có validator thì MỌI ca có điểm đau đều trượt."""
    assert _with_severity(raw) == expected


@pytest.mark.parametrize("raw", ["3/5", "rất đau", "11", "-1"])
def test_severity_that_cannot_be_read_faithfully_is_still_rejected(raw):
    """Thang khác 10 ("3/5") KHÔNG được quy đổi - đổi sang thang 10 là bịa ra mức độ."""
    with pytest.raises(ValidationError):
        _with_severity(raw)


# --- Bảng quan hệ mở rộng (2026-08-16) ------------------------------------------------------------
# Bản cũ khoá cứng located_at/radiates_to là symptom->body_location và triggered_by là symptom->context.
# Cả hai đều hẹp hơn thực tế lâm sàng và làm trượt validate những ca hoàn toàn hợp lệ.

SEIZURE_REPORT = "Con tôi đang sốt cao thì lên cơn co giật, sờ trán thấy nóng"


def _node(node_id: str, node_type: str, concept: str, surface_form: str, span: str) -> dict:
    return {
        "id": node_id, "type": node_type, "concept": concept, "canonical_name": concept.replace("_", " ").title(),
        "experiencer": "target_patient",
        "observations": [{"surface_form": surface_form, "status": "present", "provenance": {"source_span": span}}],
    }


def _edge(source: str, relation: str, target: str, span: str) -> dict:
    return {"source": source, "relation": relation, "target": target, "provenance": {"source_span": span}}


def test_a_finding_can_carry_a_body_location():
    """Bản cũ chỉ cho symptom->body_location, nên "sờ trán thấy nóng" (finding có vị trí) bị trượt."""
    span = "sờ trán thấy nóng"
    graph = ClinicalGraph.model_validate({
        "nodes": [_node("hot_skin_1", "finding", "hot_skin", "nóng", span), _node("forehead_1", "body_location", "forehead", "trán", span)],
        "edges": [_edge("patient", "has_finding", "hot_skin_1", span), _edge("hot_skin_1", "located_at", "forehead_1", span)],
    })
    validate_provenance(graph, SEIZURE_REPORT)


def test_one_stated_fact_can_trigger_another():
    """Co giật do sốt: trigger là một symptom node, không phải context node."""
    span = "đang sốt cao thì lên cơn co giật"
    graph = ClinicalGraph.model_validate({
        "nodes": [_node("fever_1", "symptom", "fever", "sốt cao", span), _node("seizure_1", "symptom", "seizure", "co giật", span)],
        "edges": [
            _edge("patient", "has_symptom", "fever_1", span), _edge("patient", "has_symptom", "seizure_1", span),
            _edge("seizure_1", "triggered_by", "fever_1", span),
        ],
    })
    validate_provenance(graph, SEIZURE_REPORT)


def test_a_body_location_is_still_never_the_source_of_a_structural_relation():
    """Nới bảng quan hệ KHÔNG có nghĩa là bỏ kiểm tra chiều của cạnh."""
    span = "sờ trán thấy nóng"
    with pytest.raises(ValidationError, match="allows only"):
        ClinicalGraph.model_validate({
            "nodes": [_node("hot_skin_1", "finding", "hot_skin", "nóng", span), _node("forehead_1", "body_location", "forehead", "trán", span)],
            "edges": [_edge("patient", "has_finding", "hot_skin_1", span), _edge("forehead_1", "located_at", "hot_skin_1", span)],
        })


def test_encoder_edge_table_matches_the_trained_fusion_checkpoint():
    """`edge_triples()` là metadata dựng HGT. Lệch so với checkpoint là `load_state_dict` hỏng.

    Đổi `ENCODER_RELATION_TYPES` thì phải train lại toàn bộ encoder - test này là chốt chặn cho điều đó.
    """
    schema_path = RUNS_DIR / "fusion_full" / "graph_schema.json"
    if not schema_path.is_file():
        pytest.skip("chưa có artifact runs/fusion_full")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    base = edge_triples()
    all_edges = set(base) | {(target, f"rev_{relation}", source) for source, relation, target in base}
    assert tuple(schema["node_types"]) == NODE_TYPES
    assert all_edges == {tuple(item) for item in schema["edge_types"]}

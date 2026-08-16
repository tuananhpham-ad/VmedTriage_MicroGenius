"""Hợp đồng JSON rộng hơn bảng cạnh mà encoder HGT đã được train.

Hai bảng này CỐ Ý lệch nhau (`STRUCTURAL_RELATION_TYPES` vs `ENCODER_RELATION_TYPES`): nới hợp đồng
JSON là tương thích ngược, còn đổi bảng encoder thì mọi checkpoint đã train thành vô giá trị. Chỗ
lệch đó phải được ĐẾM chứ không được rơi lặng lẽ - nếu không, một quan hệ có thật trong lời kể sẽ
biến mất khỏi feature mà không ai biết.
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch", reason="cần requirements-graph.txt")
pytest.importorskip("torch_geometric", reason="cần requirements-graph.txt")

from src.graph_triage.graph_schema import ClinicalGraph  # noqa: E402
from src.graph_triage.patient_graph import PatientGraphBuilder  # noqa: E402
from tests.test_graph_triage.test_graph_schema import _edge, _node  # noqa: E402

SPAN = "đang sốt cao thì lên cơn co giật"

# symptom -triggered_by-> symptom: hợp lệ theo hợp đồng JSON, nhưng encoder chỉ có ô cho
# symptom -triggered_by-> context.
SEIZURE_GRAPH = {
    "nodes": [_node("fever_1", "symptom", "fever", "sốt cao", SPAN), _node("seizure_1", "symptom", "seizure", "co giật", SPAN)],
    "edges": [
        _edge("patient", "has_symptom", "fever_1", SPAN), _edge("patient", "has_symptom", "seizure_1", SPAN),
        _edge("seizure_1", "triggered_by", "fever_1", SPAN),
    ],
}


def test_edge_outside_the_encoder_is_counted_not_dropped_silently():
    builder = PatientGraphBuilder()
    data = builder.build(ClinicalGraph.model_validate(SEIZURE_GRAPH))
    assert builder.edges_outside_encoder == {("symptom", "triggered_by", "symptom"): 1}
    assert data["patient", "has_symptom", "symptom"].edge_index.shape[1] == 2
    assert builder.audit([ClinicalGraph.model_validate(SEIZURE_GRAPH)])["edges_outside_encoder"] == {"symptom triggered_by symptom": 1}


def test_an_edge_the_encoder_knows_still_reaches_the_feature_tensor():
    span = "sờ trán thấy nóng"
    graph = ClinicalGraph.model_validate({
        "nodes": [_node("hot_skin_1", "finding", "hot_skin", "nóng", span), _node("forehead_1", "body_location", "forehead", "trán", span)],
        "edges": [_edge("patient", "has_finding", "hot_skin_1", span), _edge("hot_skin_1", "located_at", "forehead_1", span)],
    })
    builder = PatientGraphBuilder()
    data = builder.build(graph)
    assert builder.edges_outside_encoder == {}
    assert data["finding", "located_at", "body_location"].edge_index.shape[1] == 1
    assert data["body_location", "rev_located_at", "finding"].edge_index.shape[1] == 1

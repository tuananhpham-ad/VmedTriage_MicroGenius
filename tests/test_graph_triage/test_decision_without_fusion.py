"""`DecisionAgent` phải chạy được khi chưa có model fusion (`runs/fusion_full` - Phần B).

Điểm dễ hỏng nhất: payload gửi cho LLM quyết định. Nếu khoá `fusion` hay `fusion_mean_text_gate` vẫn
xuất hiện với giá trị giả (0.0/None), LLM sẽ đọc nó như một model có thật đang rất thiếu tự tin và
lấy đó làm căn cứ - phải bỏ hẳn khoá đi.

Bỏ qua khi chưa cài `requirements-graph.txt`: `agent/decision.py` import torch ở top-level.
"""

from __future__ import annotations

import pytest

# Một lần importorskip cho cả chuỗi torch/transformers/joblib/numpy mà `decision.py` kéo theo.
DecisionAgent = pytest.importorskip(
    "src.graph_triage.agent.decision", reason="cần requirements-graph.txt"
).DecisionAgent
np = pytest.importorskip("numpy")

from src.graph_triage.graph_schema import ClinicalGraph  # noqa: E402
from tests.test_graph_triage.test_graph_schema import GRAPH_PAYLOAD, REPORT  # noqa: E402


class _FakePredictor:
    """Đứng thay LogRegPredictor/BertPredictor: cùng bề mặt `predict()` + `metrics`."""

    def __init__(self, probabilities: list[float]):
        self._probabilities = np.asarray(probabilities, dtype=float)
        self.metrics = {"available": True, "evaluation_scope": "training set only", "metrics": {}}

    def predict(self, text: str) -> np.ndarray:
        assert text, "DecisionAgent phải strip và từ chối text rỗng trước khi tới đây"
        return self._probabilities


class _FakeResolver:
    def __init__(self):
        self.graph = ClinicalGraph.model_validate(GRAPH_PAYLOAD)

    def resolve(self, text: str) -> ClinicalGraph:
        return self.graph


def _agent(logreg: list[float], bert: list[float]) -> DecisionAgent:
    return DecisionAgent(
        logreg=_FakePredictor(logreg),
        bert=_FakePredictor(bert),
        graph_resolver=_FakeResolver(),
    )


def test_fusion_is_optional_and_absent_keys_are_dropped():
    result = _agent([0.7, 0.2, 0.1], [0.6, 0.3, 0.1]).decide(REPORT)
    assert set(result["models"]) == {"logreg", "bert"}
    assert "fusion_mean_text_gate" not in result
    assert result["models"]["logreg"]["predicted_label"] == "theo_doi_tai_nha"


def test_agreement_and_disagreement_are_reported():
    assert _agent([0.7, 0.2, 0.1], [0.6, 0.3, 0.1]).decide(REPORT)["model_disagreement"] is False
    assert _agent([0.7, 0.2, 0.1], [0.1, 0.2, 0.7]).decide(REPORT)["model_disagreement"] is True


def test_evidence_graph_only_carries_spans_from_the_source_text():
    result = _agent([0.7, 0.2, 0.1], [0.6, 0.3, 0.1]).decide(REPORT)
    evidence = result["evidence_graph"]["evidence"]
    assert evidence, "phiếu có triệu chứng thì evidence không được rỗng"
    for item in evidence:
        assert item["source_span"] in REPORT
        assert item["status"] in {"present", "absent", "uncertain"}


def test_empty_text_is_rejected_before_any_api_call():
    with pytest.raises(ValueError, match="must not be empty"):
        _agent([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]).decide("   ")


class _FakeFusion(_FakePredictor):
    """`FusionPredictor.predict` trả thêm mean text gate, nên bề mặt khác hai model text."""

    def predict(self, text: str, graph) -> tuple:
        return self._probabilities, 0.62


def test_fusion_adds_its_own_key_and_the_text_gate():
    agent = _agent([0.7, 0.2, 0.1], [0.6, 0.3, 0.1])
    agent.fusion = _FakeFusion([0.65, 0.25, 0.10])
    result = agent.decide(REPORT)
    assert set(result["models"]) == {"logreg", "bert", "fusion"}
    assert result["fusion_mean_text_gate"] == 0.62
    assert result["models"]["fusion"]["predicted_label"] == "theo_doi_tai_nha"


def test_relations_carry_structural_edges_and_skip_the_has_edges():
    """`relations` là thứ graph có mà text trần không đưa thẳng ra: cái gì gây ra, cái gì làm đỡ, ở đâu.

    Cạnh `has_*` bị bỏ vì chúng chỉ nói lại đúng danh sách evidence.
    """
    relations = _agent([0.7, 0.2, 0.1], [0.6, 0.3, 0.1]).decide(REPORT)["evidence_graph"]["relations"]
    assert relations == [{"source": "chest_pain", "relation": "located_at", "target": "chest", "source_span": "đau tức giữa ngực từ sáng"}]
    for item in relations:
        assert item["source_span"] in REPORT

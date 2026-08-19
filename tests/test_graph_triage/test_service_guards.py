"""`service.decide_for_case` nằm trên đường phản hồi của bệnh nhân - nó không được raise, và không
được gọi API khi không có gì để hỏi.

Các test ở đây cố tình KHÔNG mock mạng: nếu một guard nào hỏng, test sẽ cố dựng model thật/gọi API
thật và fail rõ ràng thay vì lặng lẽ đi qua.
"""

from __future__ import annotations

import pytest

from src.config import Settings, get_settings
from src.graph_triage import service
from src.models.schemas import HandoffSummary, SummaryField, TriageCase


@pytest.fixture(autouse=True)
def _clean_agent_cache():
    service.reset_agent_cache()
    yield
    service.reset_agent_cache()


@pytest.fixture
def feature_on():
    settings = get_settings()
    previous = settings.enable_graph_triage_agent
    settings.enable_graph_triage_agent = True
    yield settings
    settings.enable_graph_triage_agent = previous


def _ready_case() -> TriageCase:
    return TriageCase(
        summary=HandoffSummary(chief_complaint="Sốt 39.5°C"),
        summary_fields=[SummaryField(label="Nhiệt độ đo được", value="39.5")],
        summary_ready=True,
    )


def test_disabled_by_default(monkeypatch):
    """Mặc định của MÃ NGUỒN phải là tắt.

    Kiểm trên `Settings.model_fields` chứ không trên `get_settings()`: `get_settings()` đọc `.env`
    của máy đang chạy, nên khi lập trình viên bật cờ để thử tay thì test sẽ đỏ oan.
    """
    assert Settings.model_fields["enable_graph_triage_agent"].default is False
    monkeypatch.setattr(get_settings(), "enable_graph_triage_agent", False)
    assert service.decide_for_case(_ready_case()) is None


def test_empty_summary_short_circuits_before_touching_the_agent(feature_on, monkeypatch):
    """Không có trường nào được điền -> không dựng model, không gọi DeepSeek."""
    monkeypatch.setattr(service, "_get_agent", lambda: pytest.fail("không được dựng agent"))
    case = TriageCase(summary_fields=[SummaryField(label="Nhiệt độ đo được", is_missing=True)])
    assert service.decide_for_case(case) is None


def test_agent_failure_is_swallowed(feature_on, monkeypatch):
    class _Exploding:
        def decide(self, text: str):
            raise RuntimeError("DeepSeek timeout")

    monkeypatch.setattr(service, "_get_agent", lambda: _Exploding())
    assert service.decide_for_case(_ready_case()) is None


def test_unavailable_agent_is_remembered_and_not_rebuilt(feature_on, monkeypatch):
    """Thiếu artifact/thư viện là trạng thái ổn định - không thử dựng lại mỗi lượt chat."""
    attempts = []

    def _boom():
        attempts.append(1)
        raise ImportError("No module named 'torch'")

    monkeypatch.setattr(service, "_build_agent", _boom)
    assert service.decide_for_case(_ready_case()) is None
    assert service.decide_for_case(_ready_case()) is None
    assert len(attempts) == 1


def test_missing_fusion_artifact_turns_the_feature_off_instead_of_running_two_models(feature_on, tmp_path):
    """Quyết định 2026-08-16: fusion là bắt buộc.

    Ý kiến dựng trên 3 model và ý kiến dựng trên 2 model không so sánh được với nhau, mà màn hình
    điều dưỡng không hề cho thấy sự khác biệt đó - nên thiếu artifact thì tắt hẳn, không chạy tiếp.
    """
    pytest.importorskip("torch", reason="cần requirements-graph.txt")
    (tmp_path / "logreg_full").mkdir()
    (tmp_path / "bert_full").mkdir()
    previous = feature_on.graph_triage_artifact_root
    feature_on.graph_triage_artifact_root = str(tmp_path)
    try:
        assert service.decide_for_case(_ready_case()) is None
    finally:
        feature_on.graph_triage_artifact_root = previous


def test_only_the_final_llm_conclusion_is_kept(feature_on, monkeypatch):
    """Xác suất từng model và evidence graph KHÔNG được lọt ra ngoài service."""
    class _Agent:
        def decide(self, text: str):
            return {
                "model_analysis": {
                    # Đủ các khoá `decide_for_case` đọc để ghi log: thiếu `predicted_label` hay
                    # `model_disagreement` là hàm ném KeyError ngay trên đường phản hồi bệnh nhân.
                    "models": {"logreg": {"predicted_label": "kham_som", "probabilities": {"cap_cuu": 0.91}, "run_metrics": {}}},
                    "model_disagreement": False,
                    "evidence_graph": {"evidence": [{"source_span": "sốt 39.5"}]},
                },
                "llm_decision": {
                    "triage_label": "kham_som",
                    "decision_summary": "Sốt cao nhưng chưa có dấu hiệu nguy hiểm.",
                    "model_agreement_summary": "Hai model đồng thuận.",
                    "uncertainty_summary": "Scope đánh giá khác nhau.",
                    "requires_human_review": True,
                    "disclaimer": "Không thay thế đánh giá của nhân viên y tế.",
                },
                "tool_audit": {"model": "gpt-4o-mini", "called_tools": [], "required_tools": []},
            }

    monkeypatch.setattr(service, "_get_agent", lambda: _Agent())
    result = service.decide_for_case(_ready_case())
    assert set(result) == {"triage_label", "decision_summary", "requires_human_review", "disclaimer", "model"}
    assert result["triage_label"] == "kham_som"
    assert result["model"] == "gpt-4o-mini"
    assert "probabilities" not in str(result)
    assert "source_span" not in str(result)


def test_source_support_adds_only_display_fields(feature_on, monkeypatch):
    """Part 3 bật thì payload có thêm ĐÚNG phần hiển thị - không có `claims[]`, không có `cost`.

    Cùng lý do mục A5 giữ evidence graph khỏi UI: `claims[]` mang `grounded_in` và toàn bộ đường truy
    vết retrieval. Hữu ích để audit, và nó đã nằm trong log ở mức INFO - nhưng không phải thứ điều
    dưỡng cần đọc trên màn hình."""
    from src.source_support import pipeline as source_support_pipeline
    from src.source_support.schemas import (
        Citation,
        Claim,
        ClaimResult,
        Retrieval,
        SourceSupport,
        SupportSummary,
    )

    support = SourceSupport(
        explanation_vi="Tình trạng hiện tại của người bệnh: KHÁM SỚM",
        explanation_citations=[Citation(marker="[1]", url="https://www.nhs.uk/conditions/fever-in-children/",
                                        publisher="nhs.uk", title="Fever", quote="Trust your instincts.")],
        claims=[ClaimResult(
            claim=Claim(claim_en="x", claim_vi="x", claim_kind="red_flag",
                        grounded_in="Sốt cao nhưng chưa có dấu hiệu nguy hiểm."),
            verdict="supports",
            retrieval=Retrieval(from_index=True, searched_web=False, best_score=0.6),
        )],
        summary=SupportSummary(claims_examined=1, claims_with_support=1, requires_human_review=False),
    )
    monkeypatch.setattr(get_settings(), "source_support_enabled", True)
    monkeypatch.setattr(source_support_pipeline, "run", lambda *a, **k: support)
    monkeypatch.setattr(service, "_get_agent", lambda: _decision_agent())

    result = service.decide_for_case(_ready_case())

    assert set(result) == {
        "triage_label", "decision_summary", "requires_human_review", "disclaimer", "model", "source_support",
    }
    assert set(result["source_support"]) == {"explanation_vi", "explanation_citations", "summary", "method"}
    assert "claims" not in result["source_support"]
    assert "grounded_in" not in str(result)
    assert result["source_support"]["method"]["can_change_label"] is False


def test_source_support_can_only_raise_the_review_flag(feature_on, monkeypatch):
    """Đường DUY NHẤT part 3 tác động tới ca. Đảo chiều phép OR ở chỗ nối là cách một ca cần người
    xem lặng lẽ trôi qua - loại lỗi một dòng, không ai đọc ra, không bao giờ báo lỗi."""
    from src.source_support import pipeline as source_support_pipeline
    from src.source_support.schemas import SourceSupport, SupportSummary

    monkeypatch.setattr(get_settings(), "source_support_enabled", True)
    monkeypatch.setattr(service, "_get_agent", lambda: _decision_agent(requires_human_review=False))
    monkeypatch.setattr(
        source_support_pipeline, "run",
        lambda *a, **k: SourceSupport(summary=SupportSummary(requires_human_review=True)),
    )
    assert service.decide_for_case(_ready_case())["requires_human_review"] is True

    # Và không bao giờ HẠ cờ mà part 2 đã dựng lên.
    monkeypatch.setattr(service, "_get_agent", lambda: _decision_agent(requires_human_review=True))
    monkeypatch.setattr(
        source_support_pipeline, "run",
        lambda *a, **k: SourceSupport(summary=SupportSummary(requires_human_review=False)),
    )
    assert service.decide_for_case(_ready_case())["requires_human_review"] is True


def _decision_agent(*, requires_human_review: bool = True):
    class _Agent:
        def decide(self, text: str):
            return {
                "model_analysis": {
                    "models": {"logreg": {"predicted_label": "kham_som", "probabilities": {"cap_cuu": 0.91},
                                          "run_metrics": {}}},
                    "model_disagreement": False,
                    "evidence_graph": {"evidence": [{"source_span": "sốt 39.5"}]},
                },
                "llm_decision": {
                    "triage_label": "kham_som",
                    "decision_summary": "Sốt cao nhưng chưa có dấu hiệu nguy hiểm.",
                    "model_agreement_summary": "Hai model đồng thuận.",
                    "uncertainty_summary": "Scope đánh giá khác nhau.",
                    "requires_human_review": requires_human_review,
                    "disclaimer": "Không thay thế đánh giá của nhân viên y tế.",
                },
                "tool_audit": {"model": "gpt-4o-mini", "called_tools": [], "required_tools": []},
            }
    return _Agent()

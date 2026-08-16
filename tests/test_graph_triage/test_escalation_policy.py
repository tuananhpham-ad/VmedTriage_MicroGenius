"""Chính sách leo thang theo yếu tố nguy cơ của bệnh nhân.

Ba model đều được train trên dân số phần lớn là người lớn, nên chúng có thể rất tự tin mà vẫn sai ở
ca mà mức độ khẩn phụ thuộc vào NGƯỜI BỆNH LÀ AI chứ không phải triệu chứng (trẻ 2 tháng tuổi, người
đang mang thai, người có bệnh nền, người không ăn uống được).

Chính sách này CHỈ bật cờ `requires_human_review`. Nó không bao giờ đổi `triage_label`, và không phải
là safety override đã được thẩm định lâm sàng - mức ưu tiên có hiệu lực vẫn do rule engine quyết.
"""

from __future__ import annotations

import pytest

from src.graph_triage.agent.llm_decision import (
    LLMDecisionResponse,
    RiskModifier,
    apply_escalation_policy,
)


def _decision(label: str, *, requires_human_review: bool, factors: list[str]) -> LLMDecisionResponse:
    return LLMDecisionResponse(
        triage_label=label,
        decision_summary="Tóm tắt.",
        model_agreement_summary="Các model đồng thuận.",
        uncertainty_summary="Scope đánh giá khác nhau.",
        requires_human_review=requires_human_review,
        model_assessments=[
            {"model": "logreg", "predicted_label": label, "role_in_decision": "baseline"},
            {"model": "bert", "predicted_label": label, "role_in_decision": "ngữ cảnh"},
        ],
        risk_modifiers=[
            RiskModifier(factor=factor, source_span="con tôi 2 tháng tuổi", why_it_raises_urgency="Trẻ rất nhỏ.")
            for factor in factors
        ],
        evidence=[],
        disclaimer="Không thay thế đánh giá của nhân viên y tế.",
    )


def test_risk_factor_on_a_non_emergency_label_forces_human_review():
    decision = _decision("theo_doi_tai_nha", requires_human_review=False, factors=["extreme_age"])
    assert apply_escalation_policy(decision) is True
    assert decision.requires_human_review is True
    assert decision.triage_label == "theo_doi_tai_nha", "chính sách bật cờ, KHÔNG được đổi nhãn"


def test_nothing_is_escalated_when_no_risk_factor_is_reported():
    decision = _decision("theo_doi_tai_nha", requires_human_review=False, factors=[])
    assert apply_escalation_policy(decision) is False
    assert decision.requires_human_review is False


def test_an_emergency_label_is_not_reported_as_escalated():
    """Nhãn đã là cấp cứu thì leo thang không thêm được gì - `applied` phải là False để audit không nhiễu."""
    decision = _decision("cap_cuu", requires_human_review=True, factors=["extreme_age"])
    assert apply_escalation_policy(decision) is False


def test_a_flag_the_llm_already_raised_is_not_counted_as_a_policy_escalation():
    decision = _decision("kham_som", requires_human_review=True, factors=["pregnancy"])
    assert apply_escalation_policy(decision) is False
    assert decision.requires_human_review is True


def test_an_unknown_risk_factor_name_is_rejected_by_the_schema():
    """Từ vựng đóng: LLM không được tự nghĩ ra yếu tố nguy cơ mới rồi leo thang theo nó."""
    with pytest.raises(ValueError):
        RiskModifier(factor="gut_feeling", source_span="abc", why_it_raises_urgency="x")

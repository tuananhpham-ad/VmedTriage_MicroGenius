"""Chạy thử Track 2 (`graph_triage_service.decide_for_case`, ADVISORY) trên MỘT case mẫu và in
trace link Braintrust.

Track 2 chạy SAU khi Track 1 (`TriagePipeline`, rule-based, AUTHORITATIVE) đã chốt
`TriageProposal.priority` - xem docs/eval/01_evaluation_units.md mục 1. Script này build một
`TriageCase` đã có `triage_proposal` (giả lập, KHÔNG chạy qua rule engine thật - dùng
`eval/runners/run_traced_example_track1.py` hoặc `run_v0_batch.py` để chạy Track 1 thật) vì
`build_summary_text` cần các field đó để sinh `patient_text` cho agent.

CẢNH BÁO CHI PHÍ/PHỤ THUỘC: `decide_for_case` cần `ENABLE_GRAPH_TRIAGE_AGENT=true`, artifact
`fusion_full/` (torch/transformers, ~vài trăm MB) và `OPENAI_API_KEY`. Nếu bất kỳ điều kiện nào
thiếu, `decide_for_case` trả `None` một cách an toàn (best-effort, không raise) - script vẫn chạy
xong và in rõ lý do, không giả vờ có kết quả.

Chạy: `python eval/runners/run_traced_example.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import get_settings  # noqa: E402
from src.graph_triage import service as graph_triage_service  # noqa: E402
from src.models.schemas import (  # noqa: E402
    ActorRole,
    ConversationMessage,
    HandoffSummary,
    StructuredSymptomData,
    SummaryField,
    TriageCase,
    TriagePriority,
    TriageProposal,
    ValidationResult,
)
from src.observability.braintrust_tracing import braintrust_enabled  # noqa: E402

SAMPLE_PATIENT_TEXT = (
    "Tôi bị đau ngực trái từ khoảng 1 tiếng trước, đau âm ỉ lan lên vai, kèm khó thở nhẹ khi "
    "gắng sức. Không sốt, không ho. Tiền sử cao huyết áp, đang uống thuốc đều."
)


def build_sample_case() -> TriageCase:
    """Dựng một `TriageCase` đã "chốt phiếu" (giả lập Track 1 để có đủ field cho
    `build_summary_text`) - xem docstring module. Priority ở đây là dữ liệu MẪU cho việc trace thử
    Track 2, KHÔNG phải kết quả rule engine thật."""
    structured_data = StructuredSymptomData(
        symptom_group="chest_pain",
        fields={
            "onset": "1 tiếng trước",
            "pain_severity": "vừa",
            "pain_radiation": True,
            "shortness_of_breath": False,
        },
        missing_fields=[],
        confidence=0.82,
        source="rule_based",
    )
    triage_proposal = TriageProposal(
        priority=TriagePriority.URGENT,
        protocol_id="VMED-CP-001",
        reason="Đau ngực không có red flag vẫn cần điều dưỡng/bác sĩ xem sớm.",
        confidence=0.82,
        requires_manual_review=True,  # HITL bắt buộc - luôn True, xem CLAUDE.md.
    )
    summary = HandoffSummary(
        chief_complaint="Đau ngực trái lan lên vai kèm khó thở nhẹ khi gắng sức",
        onset="1 tiếng trước",
        severity="vừa",
        associated_symptoms=["khó thở nhẹ khi gắng sức"],
        missing_information=[],
        red_flags=[],
        proposed_priority=TriagePriority.URGENT,
        protocol_reason=triage_proposal.reason,
    )
    summary_fields = [
        SummaryField(label="Lý do khám", value="Đau ngực trái lan lên vai kèm khó thở nhẹ khi gắng sức"),
        SummaryField(label="Thời điểm khởi phát", value="1 tiếng trước"),
        SummaryField(label="Mức độ đau", value="vừa"),
        SummaryField(label="Lan tỏa", value="Có, lan lên vai"),
        SummaryField(label="Tiền sử", value="Cao huyết áp, đang điều trị"),
    ]
    return TriageCase(
        conversation=[ConversationMessage(role=ActorRole.PATIENT, content=SAMPLE_PATIENT_TEXT)],
        structured_data=structured_data,
        validation=ValidationResult(is_valid=True, missing_fields=[], contradictions=[], low_confidence=False),
        red_flags=[],
        triage_proposal=triage_proposal,
        summary=summary,
        summary_fields=summary_fields,
    )


def main() -> None:
    settings = get_settings()
    print(f"BRAINTRUST_API_KEY set: {braintrust_enabled()}")
    print(f"ENABLE_GRAPH_TRIAGE_AGENT: {settings.enable_graph_triage_agent}")
    print(f"SOURCE_SUPPORT_ENABLED: {settings.source_support_enabled}")

    triage_case = build_sample_case()
    print(f"case_id: {triage_case.case_id}")
    print(f"triage_proposal.priority (Track 1, giả lập cho demo): {triage_case.triage_proposal.priority}")
    print(f"triage_proposal.requires_manual_review: {triage_case.triage_proposal.requires_manual_review}")

    result = graph_triage_service.decide_for_case(triage_case)

    if result is None:
        print(
            "graph_decision: None - Track 2 tắt hoặc không sẵn sàng trong môi trường này "
            "(ENABLE_GRAPH_TRIAGE_AGENT=false, thiếu artifact fusion_full/, hoặc thiếu OPENAI_API_KEY). "
            "Đây là hành vi ĐÚNG theo thiết kế best-effort - không phải lỗi script."
        )
    else:
        print("graph_decision (Track 2, ADVISORY, KHÔNG ghi đè triage_proposal.priority):")
        print(f"  triage_label: {result['triage_label']}")
        print(f"  requires_human_review: {result['requires_human_review']}")
        print(f"  model: {result['model']}")

    if not braintrust_enabled():
        print(
            "\nBraintrust trace: KHÔNG có - BRAINTRUST_API_KEY chưa được set trong môi trường này. "
            "Set biến này rồi chạy lại để lấy trace link thật."
        )
    else:
        print(
            "\nBraintrust trace link được in ở dòng log 'braintrust.trace_link' phía trên (mức INFO) "
            "nếu decide_for_case thực sự chạy tới bước mở root span."
        )


if __name__ == "__main__":
    main()

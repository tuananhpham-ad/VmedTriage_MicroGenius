"""
Full readable pipeline for VMedTriage.

File này gom toàn bộ luồng xử lý vào một nơi để dễ đọc:
FastAPI input -> LangGraph state -> clinical triage services -> nurse HITL.

Code production hiện tại vẫn nằm ở:
- src/api/routes.py
- src/agents/graph.py
- src/agents/nodes/triage_nodes.py
- src/services/triage_pipeline.py

File này dùng lại đúng các service đó, nhưng viết rõ từng step với:
Input, Output, Action, Tech stack.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from src.agents.graph import agent
from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ChatResponse,
    ConversationMessage,
    RedFlagFinding,
    TriageCase,
    ValidationResult,
)
from src.services.case_store import InMemoryCaseStore
from src.services.checklist_validator import ChecklistValidator
from src.services.nurse_queue import NurseQueueService
from src.services.red_flag import RedFlagSafetyLayer
from src.services.semantic_mapper import RuleBackedSemanticMapper
from src.services.summary_generator import SummaryGenerator
from src.services.triage_engine import ProtocolTriageEngine


@dataclass
class PipelineStepLog:
    """Một bản ghi ngắn để biết mỗi step đã nhận gì và tạo ra gì."""

    step: str
    input: dict[str, Any]
    output: dict[str, Any]
    action: str
    techstack: list[str] = field(default_factory=list)


@dataclass
class FullPipelineResult:
    """Kết quả đầy đủ cho đọc/debug, bao gồm cả response giống API."""

    response: ChatResponse
    triage_case: TriageCase
    steps: list[PipelineStepLog]


class FullTriagePipeline:
    """
    Bản pipeline tuyến tính, dễ đọc, dùng lại các service thật của project.

    Khác với src/services/triage_pipeline.py:
    - File kia là service gọn để production/API gọi.
    - File này cố ý viết dài hơn, có step log và comment học thuật.
    """

    def __init__(self, store: InMemoryCaseStore | None = None) -> None:
        self.store = store or InMemoryCaseStore()
        self.mapper = RuleBackedSemanticMapper()
        self.validator = ChecklistValidator()
        self.red_flag_layer = RedFlagSafetyLayer()
        self.triage_engine = ProtocolTriageEngine()
        self.summary_generator = SummaryGenerator()
        self.nurse_queue = NurseQueueService()

    async def run(self, patient_message: str, case_id: str | None = None) -> FullPipelineResult:
        steps: list[PipelineStepLog] = []

        # STEP 01 - Receive patient input
        # Input:
        #   - patient_message: câu mô tả triệu chứng từ bệnh nhân.
        #   - case_id: optional, dùng khi bệnh nhân tiếp tục một case cũ.
        # Output:
        #   - TriageCase mới hoặc case cũ lấy từ store.
        # Action:
        #   - Validate input tối thiểu.
        #   - Load case cũ nếu có, nếu không thì tạo case mới.
        #   - Append message vào conversation với role PATIENT.
        # Tech stack:
        #   - Python async function.
        #   - Pydantic model: TriageCase, ConversationMessage.
        #   - In-memory store: InMemoryCaseStore.
        triage_case = self._load_or_create_case(case_id)
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.PATIENT, content=patient_message)
        )
        steps.append(
            PipelineStepLog(
                step="01_receive_patient_input",
                input={"patient_message": patient_message, "case_id": case_id},
                output={
                    "case_id": triage_case.case_id,
                    "conversation_size": len(triage_case.conversation),
                },
                action="Load/create case and append patient message.",
                techstack=["Python", "Pydantic", "InMemoryCaseStore"],
            )
        )

        # STEP 02 - Semantic mapping
        # Input:
        #   - Raw free-text patient_message.
        # Output:
        #   - StructuredSymptomData:
        #       symptom_group, fields, missing_fields, confidence, source.
        # Action:
        #   - Map text như "đau ngực", "khó thở", "6/10" thành field có cấu trúc.
        #   - Hiện tại dùng rule-backed local mapper.
        #   - LLM/Gemma/OpenAI có thể được gắn sau qua interface SemanticMapper.
        # Tech stack:
        #   - Python regex/rule matching.
        #   - Pydantic schema: StructuredSymptomData.
        structured_data = await self.mapper.map_message(patient_message)
        steps.append(
            PipelineStepLog(
                step="02_semantic_mapping",
                input={"patient_message": patient_message},
                output=structured_data.model_dump(),
                action="Normalize free text into structured symptom fields.",
                techstack=["Python", "Regex", "Pydantic"],
            )
        )

        # STEP 03 - Checklist validation
        # Input:
        #   - StructuredSymptomData từ step 02.
        # Output:
        #   - ValidationResult:
        #       is_valid, missing_fields, contradictions, low_confidence,
        #       follow_up_questions.
        # Action:
        #   - Xác định các field bắt buộc theo symptom_group.
        #   - Tìm thông tin thiếu, mâu thuẫn, confidence thấp.
        #   - Sinh câu hỏi follow-up an toàn cho bệnh nhân.
        # Tech stack:
        #   - Config constants trong src/config.py.
        #   - Pydantic schema: ValidationResult, ValidationIssue.
        validation = self.validator.validate(structured_data)
        steps.append(
            PipelineStepLog(
                step="03_checklist_validation",
                input=structured_data.model_dump(),
                output=validation.model_dump(),
                action="Check missing fields, contradictions, and low confidence.",
                techstack=["Python", "Pydantic", "Config-driven rules"],
            )
        )

        # STEP 04 - Red-flag safety layer
        # Input:
        #   - Structured symptom fields.
        # Output:
        #   - List[RedFlagFinding].
        # Action:
        #   - Match emergency rules như:
        #       đau ngực + khó thở, stroke signs, chảy máu nặng,
        #       co giật, mất ý thức, khó thở nặng.
        #   - Nếu có red flag, pipeline bắt buộc đẩy nurse review ưu tiên cao.
        # Tech stack:
        #   - Rule engine đơn giản trong RedFlagSafetyLayer.
        #   - Config: RED_FLAG_RULES.
        red_flags = self.red_flag_layer.detect(structured_data)
        steps.append(
            PipelineStepLog(
                step="04_red_flag_detection",
                input={"fields": structured_data.fields},
                output={"red_flags": [finding.model_dump() for finding in red_flags]},
                action="Detect emergency red flags before any patient-facing advice.",
                techstack=["Python", "Rule-based safety layer", "Pydantic"],
            )
        )

        # STEP 05 - Protocol triage proposal
        # Input:
        #   - structured_data, validation, red_flags.
        # Output:
        #   - TriageProposal:
        #       priority, protocol_id, reason, confidence,
        #       requires_manual_review.
        # Action:
        #   - Red flag -> Emergency.
        #   - Invalid/incomplete checklist -> Manual review.
        #   - Valid data -> match local protocol rules.
        #   - Proposal luôn cần human review, không tự chẩn đoán.
        # Tech stack:
        #   - ProtocolTriageEngine.
        #   - Config: TRIAGE_PROTOCOL_RULES.
        #   - Pydantic enum/model: TriagePriority, TriageProposal.
        proposal = self.triage_engine.propose(structured_data, validation, red_flags)
        steps.append(
            PipelineStepLog(
                step="05_protocol_triage_proposal",
                input={
                    "structured_data": structured_data.model_dump(),
                    "validation": validation.model_dump(),
                    "red_flags": [finding.model_dump() for finding in red_flags],
                },
                output=proposal.model_dump(),
                action="Create clinician-facing triage proposal with mandatory review.",
                techstack=["Python", "Config-driven protocols", "Pydantic"],
            )
        )

        # STEP 06 - Handoff summary
        # Input:
        #   - structured_data, validation, red_flags, proposal.
        # Output:
        #   - HandoffSummary cho nurse dashboard.
        # Action:
        #   - Tóm tắt chief complaint, onset, severity, associated symptoms,
        #     missing information, red flags, proposed priority.
        # Tech stack:
        #   - SummaryGenerator.
        #   - Pydantic schema: HandoffSummary.
        summary = self.summary_generator.build(
            structured_data,
            validation,
            red_flags,
            proposal,
        )
        steps.append(
            PipelineStepLog(
                step="06_handoff_summary",
                input={
                    "structured_data": structured_data.model_dump(),
                    "validation": validation.model_dump(),
                    "proposal": proposal.model_dump(),
                },
                output=summary.model_dump(),
                action="Build concise nurse-facing handoff summary.",
                techstack=["Python", "Pydantic"],
            )
        )

        # STEP 07 - Nurse queue item
        # Input:
        #   - case_id, structured_data, validation, summary, proposal.
        # Output:
        #   - NurseQueueItem.
        # Action:
        #   - Emergency -> high priority queue.
        #   - Non-emergency -> standard queue / awaiting approval.
        #   - Đây là điểm nối tới dashboard điều dưỡng.
        # Tech stack:
        #   - NurseQueueService.
        #   - Pydantic enum/model: QueuePriority, NurseQueueItem.
        queue_item = self.nurse_queue.build_item(
            case_id=triage_case.case_id,
            data=structured_data,
            validation=validation,
            summary=summary,
            proposal=proposal,
        )
        steps.append(
            PipelineStepLog(
                step="07_nurse_queue",
                input={
                    "case_id": triage_case.case_id,
                    "proposal": proposal.model_dump(),
                    "summary": summary.model_dump(),
                },
                output=queue_item.model_dump(),
                action="Create nurse queue item for human-in-the-loop review.",
                techstack=["Python", "Pydantic", "HITL queue pattern"],
            )
        )

        # STEP 08 - Persist case state
        # Input:
        #   - All artifacts generated above.
        # Output:
        #   - Saved TriageCase.
        # Action:
        #   - Attach structured_data, validation, red_flags, proposal,
        #     summary, queue_item vào TriageCase.
        #   - Derive status:
        #       red_flags -> NEEDS_NURSE_REVIEW
        #       invalid checklist -> COLLECTING_INFORMATION
        #       valid non-red-flag -> AWAITING_APPROVAL
        #   - Save vào store.
        # Tech stack:
        #   - InMemoryCaseStore.
        #   - Pydantic model: TriageCase.
        triage_case.structured_data = structured_data
        triage_case.validation = validation
        triage_case.red_flags = red_flags
        triage_case.triage_proposal = proposal
        triage_case.summary = summary
        triage_case.queue_item = queue_item
        triage_case.status = self._derive_case_status(validation, red_flags)
        triage_case.patient_visible_response = self._build_patient_safe_response(
            validation,
            red_flags,
        )
        saved_case = self.store.save(triage_case)
        steps.append(
            PipelineStepLog(
                step="08_persist_case_state",
                input={"case_id": triage_case.case_id},
                output={
                    "case_id": saved_case.case_id,
                    "status": saved_case.status,
                    "patient_visible_response": saved_case.patient_visible_response,
                },
                action="Persist full triage case state after pipeline processing.",
                techstack=["Python", "Pydantic", "InMemoryCaseStore"],
            )
        )

        # STEP 09 - Build patient-safe response
        # Input:
        #   - Saved case state.
        # Output:
        #   - ChatResponse giống response_model của /api/v1/chat.
        # Action:
        #   - Không trả lời kiểu chẩn đoán/chỉ định điều trị.
        #   - Nếu red flag: báo đã chuyển vào hàng đợi ưu tiên.
        #   - Nếu thiếu thông tin: hỏi follow-up.
        #   - Nếu đủ thông tin: báo đang chờ nurse/doctor duyệt.
        # Tech stack:
        #   - FastAPI response schema: ChatResponse.
        #   - Pydantic serialization.
        response = ChatResponse(
            case_id=saved_case.case_id,
            response=saved_case.patient_visible_response or "",
            status=saved_case.status,
            analysis=self._build_analysis(saved_case),
            structured_data=saved_case.structured_data,
            validation=saved_case.validation,
            red_flags=saved_case.red_flags,
            triage_proposal=saved_case.triage_proposal,
            summary=saved_case.summary,
            requires_human_approval=True,
        )
        steps.append(
            PipelineStepLog(
                step="09_patient_safe_response",
                input={"case_id": saved_case.case_id, "status": saved_case.status},
                output=response.model_dump(),
                action="Return patient-safe API response; clinical approval remains mandatory.",
                techstack=["FastAPI", "Pydantic", "HITL safety policy"],
            )
        )

        return FullPipelineResult(response=response, triage_case=saved_case, steps=steps)

    def _load_or_create_case(self, case_id: str | None) -> TriageCase:
        if case_id:
            existing_case = self.store.get(case_id)
            if existing_case:
                return existing_case
        return TriageCase()

    def _derive_case_status(
        self,
        validation: ValidationResult,
        red_flags: list[RedFlagFinding],
    ) -> CaseStatus:
        if red_flags:
            return CaseStatus.NEEDS_NURSE_REVIEW
        if not validation.is_valid:
            return CaseStatus.COLLECTING_INFORMATION
        return CaseStatus.AWAITING_APPROVAL

    def _build_patient_safe_response(
        self,
        validation: ValidationResult,
        red_flags: list[RedFlagFinding],
    ) -> str:
        if red_flags:
            return (
                "Thông tin của bạn đã được chuyển vào hàng đợi ưu tiên "
                "để nhân viên y tế xem xét."
            )

        if validation.follow_up_questions:
            return "\n".join(validation.follow_up_questions)

        return (
            "Thông tin của bạn đã được ghi nhận và đang chờ "
            "điều dưỡng/bác sĩ duyệt phản hồi."
        )

    def _build_analysis(self, triage_case: TriageCase) -> str:
        proposal = triage_case.triage_proposal
        validation = triage_case.validation
        red_flags = triage_case.red_flags

        parts = [
            f"case_id={triage_case.case_id}",
            f"status={triage_case.status}",
        ]
        if proposal:
            parts.append(f"proposal={proposal.priority}")
        if validation:
            parts.append(f"missing_fields={validation.missing_fields}")
        if red_flags:
            parts.append("red_flags=" + ",".join(finding.code for finding in red_flags))

        return "; ".join(parts)


async def run_full_pipeline(
    patient_message: str,
    case_id: str | None = None,
) -> FullPipelineResult:
    """
    Helper chính để chạy full readable pipeline.

    Input:
        patient_message: nội dung bệnh nhân nhập.
        case_id: optional case id nếu muốn tiếp tục case cũ.
    Output:
        FullPipelineResult gồm response, triage_case, steps.
    Action:
        Gọi FullTriagePipeline.run().
    Tech stack:
        Python async/await, Pydantic models, local triage services.
    """
    pipeline = FullTriagePipeline()
    return await pipeline.run(patient_message=patient_message, case_id=case_id)


async def run_via_langgraph(patient_message: str, case_id: str | None = None) -> dict[str, Any]:
    """
    Helper chạy đúng luồng production qua LangGraph agent.

    Input:
        patient_message: nội dung bệnh nhân nhập.
        case_id: optional case id.
    Output:
        Dict AgentState sau khi LangGraph chạy xong.
    Action:
        Gọi agent.ainvoke({"query": patient_message, "case_id": case_id}).
    Tech stack:
        LangGraph StateGraph, async Python, triage nodes.
    """
    payload: dict[str, Any] = {"query": patient_message}
    if case_id:
        payload["case_id"] = case_id
    return await agent.ainvoke(payload)


async def _demo() -> None:
    """
    Demo CLI nhỏ:
    python -m src.full_pipeline
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    result = await run_full_pipeline("Tôi đau ngực từ sáng, đau 6/10 và khó thở nặng.")

    print("=== PATIENT RESPONSE ===")
    print(result.response.response)
    print()
    print("=== STEP TRACE ===")
    for item in result.steps:
        print(f"{item.step}: {item.action}")
        print(f"  techstack: {', '.join(item.techstack)}")


if __name__ == "__main__":
    asyncio.run(_demo())

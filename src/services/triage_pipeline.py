from __future__ import annotations

from src.models.protocols import SemanticMapper
from src.models.schemas import ActorRole, CaseStatus, ConversationMessage, TriageCase
from src.services.case_store import InMemoryCaseStore, case_store
from src.services.checklist_validator import ChecklistValidator
from src.services.nurse_queue import NurseQueueService
from src.services.red_flag import RedFlagSafetyLayer
from src.services.semantic_mapper import RuleBackedSemanticMapper
from src.services.summary_generator import SummaryGenerator
from src.services.triage_engine import ProtocolTriageEngine


class TriagePipeline:
    def __init__(
        self,
        mapper: SemanticMapper | None = None,
        store: InMemoryCaseStore = case_store,
    ) -> None:
        self.mapper = mapper or RuleBackedSemanticMapper()
        self.validator = ChecklistValidator()
        self.red_flag_layer = RedFlagSafetyLayer()
        self.triage_engine = ProtocolTriageEngine()
        self.summary_generator = SummaryGenerator()
        self.nurse_queue = NurseQueueService()
        self.store = store

    async def handle_patient_message(self, message: str, case_id: str | None = None) -> TriageCase:
        triage_case = self._load_or_create_case(case_id)
        triage_case.conversation.append(
            ConversationMessage(role=ActorRole.PATIENT, content=message)
        )

        structured_data = await self.mapper.map_message(message)
        validation = self.validator.validate(structured_data)
        red_flags = self.red_flag_layer.detect(structured_data)
        proposal = self.triage_engine.propose(structured_data, validation, red_flags)
        summary = self.summary_generator.build(structured_data, validation, red_flags, proposal)
        queue_item = self.nurse_queue.build_item(
            case_id=triage_case.case_id,
            data=structured_data,
            validation=validation,
            summary=summary,
            proposal=proposal,
        )

        triage_case.structured_data = structured_data
        triage_case.validation = validation
        triage_case.red_flags = red_flags
        triage_case.triage_proposal = proposal
        triage_case.summary = summary
        triage_case.queue_item = queue_item
        triage_case.status = self._derive_case_status(validation, red_flags)
        triage_case.patient_visible_response = self._build_patient_safe_response(validation, red_flags)

        return self.store.save(triage_case)

    def _load_or_create_case(self, case_id: str | None) -> TriageCase:
        if case_id:
            existing_case = self.store.get(case_id)
            if existing_case:
                return existing_case
        return TriageCase()

    def _derive_case_status(self, validation, red_flags) -> CaseStatus:
        if red_flags:
            return CaseStatus.NEEDS_NURSE_REVIEW
        if not validation.is_valid:
            return CaseStatus.COLLECTING_INFORMATION
        return CaseStatus.AWAITING_APPROVAL

    def _build_patient_safe_response(self, validation, red_flags) -> str:
        if red_flags:
            return "Thông tin của bạn đã được chuyển vào hàng đợi ưu tiên để nhân viên y tế xem xét."

        if validation.follow_up_questions:
            return "\n".join(validation.follow_up_questions)

        return "Thông tin của bạn đã được ghi nhận và đang chờ điều dưỡng/bác sĩ duyệt phản hồi."


triage_pipeline = TriagePipeline()

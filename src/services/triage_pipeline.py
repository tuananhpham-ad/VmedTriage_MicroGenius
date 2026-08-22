from __future__ import annotations

import logging
from time import perf_counter

from src.config import get_settings
from src.models.protocols import SemanticMapper
from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    RedFlagFinding,
    StructuredSymptomData,
    TriageCase,
)
from src.observability.braintrust_tracing import traced_root_span, traced_span
from src.pipeline.database_update_phase import DatabaseUpdatePhase
from src.services.engines.checklist_validator import ChecklistValidator
from src.services.engines.red_flag import RedFlagSafetyLayer
from src.services.engines.semantic_mapper import RuleBackedSemanticMapper
from src.services.engines.summary_generator import SummaryGenerator
from src.services.engines.triage_engine import ProtocolTriageEngine
from src.services.stores.case_store import InMemoryCaseStore, case_store
from src.services.stores.nurse_queue import NurseQueueService
from src.tool.catalog.orchestrator import ToolOrchestrator, tool_orchestrator

logger = logging.getLogger("vmedtriage.trace")

EMERGENCY_MESSAGE = (
    "Dấu hiệu bạn mô tả có thể là tình trạng cấp cứu. Hãy gọi 115 ngay hoặc đến cơ sở y tế gần nhất. "
    "Không chờ phản hồi trực tuyến."
)


class TriagePipeline:
    def __init__(
        self,
        mapper: SemanticMapper | None = None,
        store: InMemoryCaseStore = case_store,
        orchestrator: ToolOrchestrator = tool_orchestrator,
    ) -> None:
        self.mapper = mapper or RuleBackedSemanticMapper()
        self.validator = ChecklistValidator()
        self.red_flag_layer = RedFlagSafetyLayer()
        self.triage_engine = ProtocolTriageEngine()
        self.summary_generator = SummaryGenerator()
        self.nurse_queue = NurseQueueService()
        self.database_update_phase = DatabaseUpdatePhase()
        self.store = store
        self.orchestrator = orchestrator

    async def handle_patient_message(self, message: str, case_id: str | None = None) -> TriageCase:
        """Track 1 - AUTHORITATIVE, rule-based, chốt `TriageProposal.priority` duy nhất. Instrument
        Braintrust CHỈ để quan sát: mỗi `with traced_span(...)` bọc NGUYÊN VẸN đúng lời gọi hàm đã
        có từ trước, không đổi thứ tự/logic/giá trị nào. 16 unit theo `docs/eval/01_evaluation_units.md`
        mục 8. Toàn bộ Track 1 KHÔNG gọi LLM - mọi span dưới đây có `via_provider_router=False`,
        `llm_used=False`."""
        run_started = perf_counter()
        with traced_root_span(
            "track1_handle_patient_message",
            case_id=case_id or "-",
            input={"message_chars": len(message)},
            metadata={"track": "1_authoritative", "llm_used": False},
        ) as (root_span, trace_link):
            if trace_link:
                logger.info("braintrust.trace_link case_id=%s url=%s", case_id or "-", trace_link)

            # Unit 1 - _load_or_create_case
            with traced_span("load_or_create_case", input={"case_id": case_id or "-"}) as span:
                triage_case = self._load_or_create_case(case_id)
                span.log(output={"case_id": triage_case.case_id, "existing_case": bool(case_id)})

            # Unit 2 - ghép message vào conversation
            with traced_span("append_conversation_message") as span:
                triage_case.conversation.append(
                    ConversationMessage(role=ActorRole.PATIENT, content=message)
                )
                span.log(output={"conversation_turns": len(triage_case.conversation)})

            self._log_stage(
                "input",
                triage_case.case_id,
                "ok",
                message_chars=len(message),
                conversation_turns=len(triage_case.conversation),
                existing_case=bool(case_id),
            )

            # Units 3, 4, 7 - patient_message_normalizer / language_detector / self_harm_risk_detector,
            # abuse_or_violence_detector, risk_factor_extraction_tool. Chạy trong MỘT lời gọi opaque
            # của orchestrator (plan cố định `plan_for_patient_query`) - không tách được thành các
            # await riêng mà không sửa `ToolOrchestrator.run_patient_query`. Mở một span bao trọn, rồi
            # log lại từng tool riêng SAU KHI có kết quả, đúng input/output documented cho mỗi unit.
            stage_started = perf_counter()
            with traced_span(
                "intake_tools_units_3_4_7",
                input={"message_chars": len(message)},
                metadata={
                    "units": [
                        "3: patient_message_normalizer",
                        "4: language_detector",
                        "7: self_harm_risk_detector / abuse_or_violence_detector / risk_factor_extraction_tool",
                    ],
                    "via_provider_router": False,
                    "llm_used": False,
                },
            ) as span:
                intake_run = await self.orchestrator.run_patient_query(message, case_id=triage_case.case_id)
                normalized_message = intake_run.data_for("patient_message_normalizer").get(
                    "normalized_message",
                    message,
                )
                span.log(
                    output={
                        "unit_3_normalized_message_chars": len(normalized_message),
                        "unit_4_language_detector": intake_run.data_for("language_detector"),
                        "unit_7_self_harm_risk_detector": intake_run.data_for("self_harm_risk_detector"),
                        "unit_7_abuse_or_violence_detector": intake_run.data_for("abuse_or_violence_detector"),
                        "unit_7_risk_factor_extraction_tool": intake_run.data_for("risk_factor_extraction_tool"),
                        "tools_run": len(intake_run.results),
                        "failed_tools": [item.tool_name for item in intake_run.results if not item.ok],
                    }
                )
            self._log_stage(
                "intake_tools",
                triage_case.case_id,
                "ok" if intake_run.ok else "partial",
                duration_ms=_elapsed_ms(stage_started),
                tools_run=len(intake_run.results),
                failed_tools=",".join(item.tool_name for item in intake_run.results if not item.ok) or "-",
            )

            # Unit 5 - symptom_extraction_tool / RuleBackedSemanticMapper.map_message
            stage_started = perf_counter()
            with traced_span(
                "symptom_extraction_semantic_mapping",
                input={"normalized_message_chars": len(normalized_message)},
                metadata={"unit": "5: symptom_extraction_tool -> RuleBackedSemanticMapper", "llm_used": False},
            ) as span:
                newly_mapped = await self.mapper.map_message(normalized_message)
                span.log(
                    output={
                        "symptom_group": newly_mapped.symptom_group,
                        "confidence": newly_mapped.confidence,
                        "missing_fields": newly_mapped.missing_fields,
                    }
                )

            # Unit 6 - _merge_structured_data
            with traced_span("merge_structured_data") as span:
                structured_data = self._merge_structured_data(triage_case.structured_data, newly_mapped)
                span.log(
                    output={"symptom_group": structured_data.symptom_group, "confidence": structured_data.confidence}
                )
            self._log_stage(
                "semantic_mapping",
                triage_case.case_id,
                "ok",
                duration_ms=_elapsed_ms(stage_started),
                symptom_group=structured_data.symptom_group,
                confidence=structured_data.confidence,
            )

            # Unit 8 - ChecklistValidator.validate
            stage_started = perf_counter()
            with traced_span(
                "checklist_validation",
                input={"symptom_group": structured_data.symptom_group},
                metadata={"unit": "8: ChecklistValidator.validate", "llm_used": False},
            ) as span:
                validation = self.validator.validate(structured_data)
                span.log(
                    output={"is_valid": validation.is_valid, "missing_fields": validation.missing_fields}
                )
            self._log_stage(
                "checklist_validation",
                triage_case.case_id,
                "ok",
                duration_ms=_elapsed_ms(stage_started),
                is_valid=validation.is_valid,
                missing_fields=",".join(validation.missing_fields) or "-",
            )

            # Unit 9 - RedFlagSafetyLayer.detect
            stage_started = perf_counter()
            with traced_span(
                "red_flag_matching",
                metadata={"unit": "9: RedFlagSafetyLayer.detect", "llm_used": False},
            ) as span:
                red_flags = self.red_flag_layer.detect(structured_data, message, normalized_message)
                span.log(output={"red_flags": [item.code for item in red_flags]})

            # Unit 10 - self-harm red flag augmentation (chỉ BẬT THÊM, đọc lại kết quả unit 7)
            with traced_span(
                "self_harm_red_flag_augmentation",
                metadata={"unit": "10: self-harm red flag augmentation", "llm_used": False},
            ) as span:
                self_harm = intake_run.data_for("self_harm_risk_detector")
                augmented = self_harm.get("risk_level") == "high"
                if augmented:
                    red_flags.append(
                        RedFlagFinding(
                            code="high_self_harm_risk",
                            label="High self-harm risk language detected",
                            matched_fields=["patient_message"],
                        )
                    )
                span.log(output={"augmented": augmented})
            self._log_stage(
                "red_flag_detection",
                triage_case.case_id,
                "ok",
                duration_ms=_elapsed_ms(stage_started),
                red_flags=",".join(item.code for item in red_flags) or "-",
            )

            # Unit 11 - ProtocolTriageEngine.propose (chốt priority - AUTHORITATIVE)
            stage_started = perf_counter()
            with traced_span(
                "priority_assignment",
                input={"red_flags": [item.code for item in red_flags], "is_valid": validation.is_valid},
                metadata={
                    "unit": "11: ProtocolTriageEngine.propose",
                    "llm_used": False,
                    "note": "Duy nhất chốt TriageProposal.priority; requires_manual_review LUÔN True.",
                },
            ) as span:
                proposal = self.triage_engine.propose(structured_data, validation, red_flags)
                span.log(
                    output={
                        "priority": proposal.priority,
                        "protocol_id": proposal.protocol_id,
                        "requires_manual_review": proposal.requires_manual_review,
                    }
                )
            self._log_stage(
                "triage_proposal",
                triage_case.case_id,
                "ok",
                duration_ms=_elapsed_ms(stage_started),
                priority=proposal.priority,
                protocol_id=proposal.protocol_id or "-",
            )

            # Unit 12 - SummaryGenerator.build
            stage_started = perf_counter()
            with traced_span(
                "summary_generation",
                metadata={"unit": "12: SummaryGenerator.build", "llm_used": False},
            ) as span:
                summary = self.summary_generator.build(structured_data, validation, red_flags, proposal)
                span.log(output={"chief_complaint": summary.chief_complaint})

            # Unit 13 - NurseQueueService.build_item
            with traced_span(
                "nurse_queue_build_item",
                metadata={"unit": "13: NurseQueueService.build_item", "llm_used": False},
            ) as span:
                queue_item = self.nurse_queue.build_item(
                    case_id=triage_case.case_id,
                    data=structured_data,
                    validation=validation,
                    summary=summary,
                    proposal=proposal,
                )
                span.log(output={"queue_priority": queue_item.queue_priority})
            self._log_stage(
                "summary_queue",
                triage_case.case_id,
                "ok",
                duration_ms=_elapsed_ms(stage_started),
                queue_priority=queue_item.queue_priority,
            )

            triage_case.structured_data = structured_data
            triage_case.validation = validation
            triage_case.red_flags = red_flags
            triage_case.triage_proposal = proposal
            triage_case.summary = summary
            triage_case.queue_item = queue_item

            # Unit 14 - _derive_case_status
            with traced_span(
                "derive_case_status", metadata={"unit": "14: _derive_case_status", "llm_used": False}
            ) as span:
                triage_case.status = self._derive_case_status(validation, red_flags)
                span.log(output={"status": triage_case.status})

            # Unit 15 - _build_patient_safe_response (KHÔNG có văn bản nào do model sinh)
            with traced_span(
                "build_patient_safe_response",
                metadata={
                    "unit": "15: _build_patient_safe_response",
                    "llm_used": False,
                    "note": "Toàn bộ text là hằng số tĩnh/ghép câu hỏi tĩnh, không phải văn bản sinh bởi model.",
                },
            ) as span:
                triage_case.patient_visible_response = self._build_patient_safe_response(validation, red_flags)
                span.log(output={"response_chars": len(triage_case.patient_visible_response or "")})

            self._log_stage(
                "final_response",
                triage_case.case_id,
                "ok",
                case_status=triage_case.status,
                response_chars=len(triage_case.patient_visible_response or ""),
                requires_human_approval=triage_case.status != CaseStatus.ESCALATED,
            )

            # Unit 16 - store.save (in-memory) + persist Weaviate (best-effort)
            stage_started = perf_counter()
            with traced_span(
                "case_store_and_persist",
                metadata={
                    "unit": "16: InMemoryCaseStore.save + DatabaseUpdatePhase.store_triage_case (best-effort)",
                    "llm_used": False,
                },
            ) as span:
                saved_case = self.store.save(triage_case)
                self._log_stage(
                    "case_store",
                    saved_case.case_id,
                    "ok",
                    duration_ms=_elapsed_ms(stage_started),
                )
                await self._persist_to_weaviate(saved_case)
                span.log(output={"case_id": saved_case.case_id})

            logger.info(
                "trace.run_complete case_id=%s status=ok duration_ms=%s final_status=%s priority=%s",
                saved_case.case_id,
                _elapsed_ms(run_started),
                saved_case.status,
                saved_case.triage_proposal.priority if saved_case.triage_proposal else "-",
            )
            root_span.log(
                output={
                    "case_id": saved_case.case_id,
                    "status": saved_case.status,
                    "priority": saved_case.triage_proposal.priority if saved_case.triage_proposal else None,
                    "requires_manual_review": (
                        saved_case.triage_proposal.requires_manual_review if saved_case.triage_proposal else None
                    ),
                }
            )
            return saved_case

    def _merge_structured_data(
        self,
        previous: StructuredSymptomData | None,
        newly_mapped: StructuredSymptomData,
    ) -> StructuredSymptomData:
        """Gộp dữ liệu triệu chứng mới trích xuất được với dữ liệu đã thu thập ở các lượt trước.

        Mapper chỉ đọc tin nhắn mới nhất mỗi lượt, nên nếu không gộp lại thì các field đã trả lời
        ở lượt trước sẽ bị mất khi bệnh nhân trả lời câu hỏi tiếp theo (hội thoại nhiều lượt).
        """
        if previous is None:
            return newly_mapped

        merged_fields = {**previous.fields, **newly_mapped.fields}
        default_group = get_settings().default_symptom_group
        merged_group = (
            newly_mapped.symptom_group if newly_mapped.symptom_group != default_group else previous.symptom_group
        )

        return StructuredSymptomData(
            symptom_group=merged_group,
            fields=merged_fields,
            confidence=max(previous.confidence, newly_mapped.confidence),
            source=newly_mapped.source,
        )

    def _load_or_create_case(self, case_id: str | None) -> TriageCase:
        if case_id:
            existing_case = self.store.get(case_id)
            if existing_case:
                return existing_case
        return TriageCase()

    def _derive_case_status(self, validation, red_flags) -> CaseStatus:
        if red_flags:
            return CaseStatus.ESCALATED
        if not validation.is_valid:
            return CaseStatus.COLLECTING_INFORMATION
        return CaseStatus.AWAITING_APPROVAL

    def _build_patient_safe_response(self, validation, red_flags) -> str | None:
        """Return only fixed emergency wording for a deterministic red flag.

        Other clinical guidance still needs clinician approval; the red-flag
        message only instructs the patient to seek emergency help immediately.
        """
        if red_flags:
            return EMERGENCY_MESSAGE
        if validation.is_valid:
            return None

        if validation.follow_up_questions:
            return "\n".join(validation.follow_up_questions)

        return None

    async def _persist_to_weaviate(self, triage_case: TriageCase) -> None:
        stage_started = perf_counter()
        try:
            await self.database_update_phase.store_triage_case(triage_case)
        except Exception as exc:
            # Weaviate persistence is best-effort here; the local triage flow still succeeds.
            self._log_stage(
                "weaviate_persist",
                triage_case.case_id,
                "skipped",
                duration_ms=_elapsed_ms(stage_started),
                reason=type(exc).__name__,
            )
            return
        self._log_stage(
            "weaviate_persist",
            triage_case.case_id,
            "ok",
            duration_ms=_elapsed_ms(stage_started),
        )

    def _log_stage(self, stage: str, case_id: str, status: str, **fields) -> None:
        field_text = " ".join(f"{key}={_log_value(value)}" for key, value in fields.items())
        logger.info("trace.stage case_id=%s stage=%s status=%s %s", case_id, stage, status, field_text)


def _elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _log_value(value) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ")
    return text[:160]


triage_pipeline = TriagePipeline()

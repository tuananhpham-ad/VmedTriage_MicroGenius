"""Điểm vào duy nhất của luồng web tới agent quyết định trong `src/graph_triage/`.

VÌ SAO CẦN LỚP NÀY: `agent/run.py` và `agent/run_llm.py` là CLI - chúng parse argv, dựng model mới
mỗi lần chạy rồi thoát. Luồng web cần đúng ngược lại: dựng một lần, dùng lại nhiều request, và không
bao giờ được làm hỏng lượt chat khi hỏng.

BỐN RÀNG BUỘC KHÔNG ĐƯỢC PHÁ:

1. IMPORT PHẢI LAZY. `torch`/`transformers`/`joblib` nằm ở `requirements-graph.txt`, KHÔNG nằm ở
   `requirements.txt`. Import chúng ở top-level module này thì cả app chết lúc khởi động trên môi
   trường chưa cài (kể cả CI). Mọi import nặng nằm trong hàm và `ImportError` được nuốt thành "tính
   năng tắt".

2. MODEL LOAD MỘT LẦN. Thư mục PhoBERT hơn 500 MB - dựng lại mỗi request là không dùng được. Singleton
   lười, khoá bằng `threading.Lock` vì uvicorn chạy nhiều worker thread.

3. BEST-EFFORT. DeepSeek hoặc OpenAI lỗi thì case vẫn phải vào hàng đợi điều dưỡng như thường. Theo
   đúng cách `TriagePipeline._persist_to_weaviate` xử lý Weaviate: bắt hết, log, đi tiếp.

4. MODE TƯỜNG MINH. `graph_triage_mode="ensemble"` chạy ba model cũ để điều dưỡng tham khảo;
   `"c6"` dùng đúng combiner đã benchmark: GPT direct OR Fusion OR documented-rule emergency.
   C6 có thể nâng (không bao giờ hạ) priority sau khi case đã vào hàng đợi. Rule engine của symptom
   protocol vẫn tạo priority tức thời và HITL vẫn bắt buộc.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.graph_triage.summary_text import build_summary_text
from src.models.schemas import TriageCase
from src.observability.braintrust_tracing import traced_root_span, traced_span
from src.paths import RUNS_DIR
from src.services.engines.priority_labels import (
    C6_TRIAGE_LABEL_TO_PRIORITY,
    PRIORITY_RANK,
    c6_label_for_priority,
)
from src.source_support import pipeline as source_support
from src.source_support.schemas import SourceSupport

logger = logging.getLogger("vmedtriage.graph_triage")

_lock = threading.Lock()
_agent: Any | None = None
_unavailable_reason: str | None = None

# C6 deliberately does not construct `DecisionAgent`/`ToolCallingDecisionAgent`: it needs only
# the trained Fusion branch (plus the two independent safety branches below). Keep its singleton
# separate so selecting C6 cannot instantiate LogReg, standalone PhoBERT or the Part-2 aggregate LLM.
_c6_fusion_lock = threading.Lock()
_c6_fusion_gate: Any | None = None
_c6_fusion_unavailable_reason: str | None = None

_C6_DECISION_SUMMARY = ""
_C6_DISCLAIMER = "Đánh giá an toàn hỗ trợ, không thay thế đánh giá của nhân viên y tế."


def _artifact_root() -> Path:
    configured = get_settings().graph_triage_artifact_root.strip()
    return Path(configured) if configured else RUNS_DIR


def _build_agent() -> Any:
    """Dựng `ToolCallingDecisionAgent`. Mọi import nặng nằm trong hàm - xem ràng buộc 1."""
    import torch

    from src.graph_triage.agent.decision import (
        BertPredictor,
        DecisionAgent,
        FusionPredictor,
        GraphResolver,
        LogRegPredictor,
    )
    from src.graph_triage.agent.llm_decision import ToolCallingDecisionAgent

    settings = get_settings()
    root = _artifact_root()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    fusion_dir = root / "fusion_full"

    # Fusion là BẮT BUỘC (quyết định 2026-08-16): thiếu artifact thì tắt hẳn tính năng chứ không âm
    # thầm chạy 2 model. Ý kiến tham khảo dựng trên 3 model và ý kiến dựng trên 2 model không so sánh
    # được với nhau, mà điều dưỡng nhìn màn hình thì không thấy sự khác biệt đó.
    if not fusion_dir.is_dir():
        raise FileNotFoundError(
            f"Thiếu artifact fusion tại {fusion_dir}. Copy runs/fusion_clean từ repo graph vào đó, "
            "hoặc trỏ GRAPH_TRIAGE_ARTIFACT_ROOT sang thư mục có logreg_full/, bert_full/ và fusion_full/."
        )

    ensemble = DecisionAgent(
        logreg=LogRegPredictor(root / "logreg_full" / "model.joblib"),
        bert=BertPredictor(root / "bert_full" / "model", device, settings.graph_triage_max_length),
        # `graph_cache=None` + live extraction: phiếu tóm tắt là văn bản mới sinh mỗi ca, không bao giờ
        # khớp sha256 của cache golden.csv nên tra cache luôn trượt.
        graph_resolver=GraphResolver(None, allow_live_extraction=True),
        fusion=FusionPredictor(fusion_dir, device),
    )
    logger.info("graph_triage.agent_ready device=%s models=logreg,bert,fusion root=%s", device.type, root)
    return ToolCallingDecisionAgent(ensemble)


def _get_agent() -> Any | None:
    global _agent, _unavailable_reason
    if _agent is not None or _unavailable_reason is not None:
        return _agent
    with _lock:
        if _agent is None and _unavailable_reason is None:
            try:
                _agent = _build_agent()
            except Exception as error:  # ImportError, thiếu artifact, thiếu API key - đều là "tắt".
                _unavailable_reason = f"{type(error).__name__}: {error}"
                logger.warning("graph_triage.unavailable reason=%s", _unavailable_reason)
    return _agent


class _C6FusionGate:
    """The Fusion-only C6 branch: summary text -> live/cached graph -> Fusion label."""

    def __init__(self, *, graph_resolver: Any, fusion: Any, labels: tuple[str, ...]):
        self._graph_resolver = graph_resolver
        self._fusion = fusion
        self._labels = labels

    def predict_label(self, summary_text: str) -> str:
        graph = self._graph_resolver.resolve(summary_text)
        probabilities, _mean_gate = self._fusion.predict(summary_text, graph)
        label = self._labels[int(probabilities.argmax())]
        if label not in C6_TRIAGE_LABEL_TO_PRIORITY:
            raise ValueError(f"Fusion returned an unknown triage label: {label!r}")
        return label


def _build_c6_fusion_gate() -> _C6FusionGate:
    """Build only the Fusion artifact required by the evaluated C6 combiner.

    Imports remain lazy because this branch requires graph inference dependencies. Fusion itself
    contains its own text encoder; that is distinct from loading the standalone PhoBERT classifier
    used by the legacy `ensemble` mode.
    """
    import torch

    from src.graph_triage.agent.decision import FusionPredictor, GraphResolver
    from src.graph_triage.labels import TRIAGE_LABELS

    root = _artifact_root()
    fusion_dir = root / "fusion_full"
    if not fusion_dir.is_dir():
        raise FileNotFoundError(
            f"Fusion artifact was not found at {fusion_dir}. "
            "C6 requires runs/fusion_full/ (model.pt and text_encoder/)."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    gate = _C6FusionGate(
        graph_resolver=GraphResolver(None, allow_live_extraction=True),
        fusion=FusionPredictor(fusion_dir, device),
        labels=tuple(TRIAGE_LABELS),
    )
    logger.info("graph_triage.c6_fusion_ready device=%s root=%s", device.type, root)
    return gate


def _get_c6_fusion_gate() -> _C6FusionGate | None:
    """Get the Fusion-only singleton; cache an unavailable dependency/artifact once per process."""
    global _c6_fusion_gate, _c6_fusion_unavailable_reason
    if _c6_fusion_gate is not None or _c6_fusion_unavailable_reason is not None:
        return _c6_fusion_gate
    with _c6_fusion_lock:
        if _c6_fusion_gate is None and _c6_fusion_unavailable_reason is None:
            try:
                _c6_fusion_gate = _build_c6_fusion_gate()
            except Exception as error:
                _c6_fusion_unavailable_reason = f"{type(error).__name__}: {error}"
                logger.warning("graph_triage.c6_fusion_unavailable reason=%s", _c6_fusion_unavailable_reason)
    return _c6_fusion_gate


def _fusion_label_for(summary_text: str) -> str:
    """Run the independent Fusion branch of C6 or expose its stable unavailable reason."""
    gate = _get_c6_fusion_gate()
    if gate is None:
        raise RuntimeError(_c6_fusion_unavailable_reason or "C6 Fusion is unavailable")
    return gate.predict_label(summary_text)


def _direct_decision_for(summary_text: str) -> dict[str, Any]:
    """Run the independent direct C6 branch; imports stay lazy for the normal web startup."""
    from src.graph_triage.agent.direct_decision import decide_direct

    return decide_direct(summary_text, get_settings().graph_triage_safety_model)


def _documented_rule_for(summary_text: str) -> dict[str, Any]:
    """Run the evidence-grounded documented rule branch of C6."""
    from src.graph_triage.agent.rule_gate import extract_and_evaluate
    from src.services.infra.provider_router import LLMCredential

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return extract_and_evaluate(
        summary_text,
        LLMCredential(
            provider="openai",
            api_key=settings.openai_api_key,
            model=settings.graph_triage_safety_model,
        ),
    )


def _run_direct_branch(summary_text: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Run the `direct` C6 arm, catching failure the same way the sequential version did."""
    try:
        direct_decision = _direct_decision_for(summary_text)
        return direct_decision, {"available": True, "triage_label": direct_decision["triage_label"]}
    except Exception as error:
        logger.debug("graph_triage.c6_direct_unavailable error=%s: %s", type(error).__name__, error)
        return None, {"available": False, "error": type(error).__name__}


def _run_fusion_branch(summary_text: str) -> tuple[str | None, dict[str, Any]]:
    """Run the `fusion` C6 arm. Fusion only votes for emergency; a non-emergency Fusion output
    must not replace the GPT-direct label (second arm of the C6 benchmark formula)."""
    try:
        fusion_label = _fusion_label_for(summary_text)
        return fusion_label, {"available": True, "triage_label": fusion_label}
    except Exception as error:
        logger.debug("graph_triage.c6_fusion_unavailable error=%s: %s", type(error).__name__, error)
        return None, {"available": False, "error": type(error).__name__}


def _run_documented_rule_branch(summary_text: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Run the `documented_rule` C6 arm."""
    try:
        documented_rule = _documented_rule_for(summary_text)
        return documented_rule, {
            "available": bool(documented_rule.get("available")),
            "emergency": bool(documented_rule.get("emergency")),
            "protocol": documented_rule.get("protocol"),
            "triggered_rules": documented_rule.get("triggered_rules", []),
            "reason_codes": documented_rule.get("reason_codes", []),
        }
    except Exception as error:
        logger.debug("graph_triage.c6_rule_unavailable error=%s: %s", type(error).__name__, error)
        return None, {"available": False, "error": type(error).__name__}


def _apply_c6_safety_gate(decision: dict[str, Any], summary_text: str) -> dict[str, Any]:
    """Apply the non-lowering C6 emergency combiner and retain a compact audit trail.

    The three arms below never consume each other's output, and each makes its own network call
    (OpenAI direct decision, DeepSeek graph extraction feeding Fusion, OpenAI rule-gate
    extraction). Running them on their own threads turns per-case latency from the SUM of three
    round-trips into the MAX of them. The combining logic still runs single-threaded afterwards,
    in the same direct/fusion/documented_rule order the sequential version used, so the audit
    trail and escalation outcome are unchanged - only wall-clock time drops.
    """
    updated = dict(decision)

    with ThreadPoolExecutor(max_workers=3) as pool:
        direct_future = pool.submit(_run_direct_branch, summary_text)
        fusion_future = pool.submit(_run_fusion_branch, summary_text)
        rule_future = pool.submit(_run_documented_rule_branch, summary_text)
        direct_decision, direct_audit = direct_future.result()
        fusion_label, fusion_audit = fusion_future.result()
        documented_rule, rule_audit = rule_future.result()

    escalated_by: list[str] = []
    if direct_decision is not None and direct_decision["triage_label"] == "cap_cuu":
        escalated_by.append("direct")
    if fusion_label == "cap_cuu":
        escalated_by.append("fusion")
    if documented_rule is not None and documented_rule.get("emergency"):
        escalated_by.append("documented_rule")
    audit: dict[str, Any] = {"direct": direct_audit, "fusion": fusion_audit, "documented_rule": rule_audit}

    if escalated_by and updated["triage_label"] != "cap_cuu":
        updated["triage_label"] = "cap_cuu"
        updated["requires_human_review"] = True
        updated["escalated_by"] = escalated_by
        logger.info("graph_triage.c6_raised sources=%s", "/".join(escalated_by))
    if direct_decision is not None:
        # Part 3 needs an explicit, input-grounded rationale.  The direct branch supplies it without
        # loading the legacy graph/three-model ensemble; its spans were checked in `decide_direct`.
        updated["decision_summary"] = direct_decision["decision_summary"]
        updated["evidence"] = direct_decision["evidence"]
    updated["safety_gate"] = audit
    return updated


def _c6_only_decision(triage_case: TriageCase, summary_text: str) -> dict[str, Any] | None:
    """Run the evaluated C6 combiner without constructing the legacy aggregate agent.

    A documented non-emergency result alone never supplies a triage label.  It is useful only as
    corroborating audit information; a GPT-direct label or emergency from any C6 arm is required
    before a result can affect the nurse queue.
    """
    decision = _apply_c6_safety_gate(
        {
            "triage_label": "theo_doi_tai_nha",
            "decision_summary": _C6_DECISION_SUMMARY,
            "requires_human_review": True,
            "disclaimer": _C6_DISCLAIMER,
        },
        summary_text,
    )
    direct = decision["safety_gate"]["direct"]
    if decision["triage_label"] != "cap_cuu":
        if not direct.get("available"):
            return None
        decision["triage_label"] = direct["triage_label"]
    decision["triage_label"] = _effective_c6_label(triage_case, decision["triage_label"])
    return decision


def _effective_c6_label(triage_case: TriageCase, c6_label: str) -> str:
    """Return the non-lowered final label that Part 3 and the nurse UI must see.

    The C6 label is advisory until compared with the priority synchronously set by the deterministic
    rule engine.  If C6 is lower, preserve the rule-engine label before source support runs, rather
    than citing an urgency that is no longer the one in the nurse queue.
    """
    proposal = triage_case.triage_proposal
    c6_priority = C6_TRIAGE_LABEL_TO_PRIORITY.get(c6_label)
    if proposal is None or c6_priority is None:
        return c6_label
    if PRIORITY_RANK[c6_priority] < PRIORITY_RANK[proposal.priority]:
        return c6_label
    return c6_label_for_priority(proposal.priority) or c6_label


def _compact_payload(
    decision: dict[str, Any],
    *,
    model: str,
    support: SourceSupport | None = None,
) -> dict:
    """Keep the nurse-facing graph decision intentionally small."""
    payload = {
        "triage_label": decision["triage_label"],
        "decision_summary": decision["decision_summary"],
        "requires_human_review": source_support.merge_human_review(
            decision["requires_human_review"], support,
        ),
        "disclaimer": decision["disclaimer"],
        "model": model,
    }
    if "escalated_by" in decision:
        payload["escalated_by"] = decision["escalated_by"]
    if "safety_gate" in decision:
        payload["safety_gate"] = decision["safety_gate"]
    if support is not None:
        payload["source_support"] = {
            "explanation_vi": support.explanation_vi,
            "explanation_citations": [c.model_dump(mode="json") for c in support.explanation_citations],
            "summary": support.summary.model_dump(mode="json"),
            "method": support.method.model_dump(mode="json"),
        }
    return payload


def decide_for_case(triage_case: TriageCase) -> dict | None:
    """Chạy agent quyết định cho một case đã chốt phiếu. `None` = không có gì để lưu.

    Không bao giờ raise: người gọi nằm trên đường phản hồi của bệnh nhân.
    """
    settings = get_settings()
    if settings.graph_triage_mode == "off":
        return None
    summary_text = build_summary_text(triage_case)
    if not summary_text:
        logger.info("graph_triage.skipped case_id=%s reason=empty_summary", triage_case.case_id)
        return None
    if settings.graph_triage_mode == "c6":
        decision = _c6_only_decision(triage_case, summary_text)
        if decision is None:
            return None
        logger.info(
            "graph_triage.c6_decided case_id=%s label=%s sources=%s",
            triage_case.case_id,
            decision["triage_label"],
            ",".join(decision.get("escalated_by", [])) or "direct_label",
        )
        support = _source_support_for(triage_case, decision)
        return _compact_payload(decision, model=settings.graph_triage_safety_model, support=support)

    # `ensemble` is the only remaining enabled mode here.  It intentionally keeps the existing
    # heavy three-model behaviour for research/second-opinion comparisons.
    agent = _get_agent()
    if agent is None:
        return None
    settings = get_settings()
    with traced_root_span(
        "graph_triage_decide_for_case",
        case_id=triage_case.case_id,
        metadata={"track": "2_advisory", "authoritative": False},
    ) as (root_span, trace_link):
        if trace_link:
            logger.info("braintrust.trace_link case_id=%s url=%s", triage_case.case_id, trace_link)
        try:
            # `agent.decide` chạy cả Unit A (model_predictions, không LLM) lẫn Unit B (LLM reasoning,
            # OpenAI trực tiếp) trong một lời gọi opaque duy nhất (xem docs/eval/01_evaluation_units.md
            # mục 2-3) - không tách được thành 2 span BAO QUANH lời gọi mà không sửa nội bộ
            # `ToolCallingDecisionAgent.decide`. Ta mở một span bao trọn cả hai, rồi log lại
            # input/output của từng unit SAU KHI có kết quả, đúng dữ liệu documented cho mỗi unit.
            with traced_span(
                "model_predictions_and_llm_reasoning",
                input={"patient_text_chars": len(summary_text)},
                metadata={
                    "units": ["A: model_predictions", "B: llm_reasoning"],
                    "via_provider_router": False,
                    "provider": "openai_direct",
                    "model": settings.openai_model_name,
                    "note": "opaque single call, xem ToolCallingDecisionAgent.decide "
                    "(src/graph_triage/agent/llm_decision.py)",
                },
            ) as combined_span:
                result = agent.decide(summary_text)
                analysis = result["model_analysis"]
                decision = result["llm_decision"]
                combined_span.log(
                    output={
                        "unit_A_model_predictions": {
                            "models": {
                                name: item.get("predicted_label")
                                for name, item in analysis.get("models", {}).items()
                            },
                            "model_disagreement": analysis.get("model_disagreement"),
                        },
                        "unit_B_llm_decision": {
                            "triage_label": decision["triage_label"],
                            "requires_human_review": decision["requires_human_review"],
                            "model_agreement_summary": decision.get("model_agreement_summary"),
                        },
                    },
                    metadata={"model_used": result["tool_audit"]["model"]},
                )
        except Exception as error:
            logger.warning(
                "graph_triage.failed case_id=%s error=%s: %s", triage_case.case_id, type(error).__name__, error
            )
            return None

        # Unit C - "advisory_decision": output cuối của graph_triage cho case này. KHÔNG phải quyết
        # định cuối của hệ thống (đó vẫn là TriageProposal/ProtocolTriageEngine, rule-based, Track 1).
        with traced_span(
            "advisory_decision",
            input={"case_id": triage_case.case_id},
            output={
                "triage_label": decision["triage_label"],
                "decision_summary": decision.get("decision_summary"),
                "disclaimer": decision.get("disclaimer"),
                "requires_human_review": decision["requires_human_review"],
            },
            metadata={
                "unit": "C: advisory final decision (graph_triage, non-authoritative)",
                "via_provider_router": False,
                "provider": "openai_direct",
                "model": settings.openai_model_name,
                "overrides_triage_proposal_priority": False,
            },
        ):
            pass

        logger.info(
            "graph_triage.decided case_id=%s label=%s human_review=%s model=%s models=%s disagreement=%s",
            triage_case.case_id,
            decision["triage_label"],
            decision["requires_human_review"],
            result["tool_audit"]["model"],
            "/".join(f"{name}:{item['predicted_label']}" for name, item in analysis["models"].items()),
            analysis["model_disagreement"],
        )
        # Xác suất từng model và evidence graph KHÔNG ra tới UI (quyết định thiết kế, mục A5), nhưng khi
        # gỡ lỗi thì đó chính là thứ cần nhìn - nên ghi ở mức DEBUG. Bật bằng:
        #     logging.getLogger("vmedtriage.graph_triage").setLevel(logging.DEBUG)
        if logger.isEnabledFor(logging.DEBUG):
            for name, item in analysis["models"].items():
                probabilities = " ".join(f"{label}={value:.3f}" for label, value in item["probabilities"].items())
                logger.debug("graph_triage.model case_id=%s %s -> %s | scope=%s",
                             triage_case.case_id, name, probabilities, item["run_metrics"].get("evaluation_scope"))
            for item in analysis["evidence_graph"]["evidence"]:
                logger.debug("graph_triage.evidence case_id=%s [%s] %s <- %r",
                             triage_case.case_id, item["status"], item["concept"], item["source_span"])
            logger.debug("graph_triage.summary_text case_id=%s\n%s", triage_case.case_id, summary_text)
        # Part 3 phải chạy TRƯỚC chỗ thu hẹp bên dưới: `decision` ở đây còn `evidence` và
        # `risk_modifiers`, mà bước tách claim lẫn Guard 0b đều cần chúng - sau khi thu hẹp thì không lấy
        # lại được nữa. Best-effort đúng ràng buộc 3: phần trích nguồn hỏng thì ca vẫn vào hàng đợi điều
        # dưỡng như thường. Gọi bên trong root span để Unit D/E (mở span trong
        # `src/source_support/pipeline.py`) parent đúng vào cùng trace này.
        support = _source_support_for(triage_case, decision)

        # Chỉ giữ kết luận cuối của LLM: màn hình điều dưỡng chỉ hiển thị phần này, còn xác suất từng
        # model và evidence graph không được đưa ra UI (quyết định thiết kế, xem kế hoạch mục A5).
        payload = {
            "triage_label": decision["triage_label"],
            "decision_summary": decision["decision_summary"],
            # Cờ GỘP: part 3 chỉ được BẬT THÊM, không bao giờ hạ cờ mà agent quyết định đã dựng lên.
            "requires_human_review": source_support.merge_human_review(decision["requires_human_review"], support),
            "disclaimer": decision["disclaimer"],
            "model": result["tool_audit"]["model"],
        }
        if support is not None:
            # CHỈ phần hiển thị, đúng tinh thần mục A5 ("chỉ giữ kết luận cuối"). `claims[]` mang
            # `grounded_in` và toàn bộ đường truy vết retrieval - hữu ích để audit nhưng cùng loại với
            # evidence graph, vốn đã có quyết định là không đưa ra UI. Nó đã nằm trong log ở mức INFO.
            # `cost` cũng vậy: đó là số liệu vận hành, không phải nội dung điều dưỡng cần đọc.
            payload["source_support"] = {
                "explanation_vi": support.explanation_vi,
                "explanation_citations": [c.model_dump(mode="json") for c in support.explanation_citations],
                "summary": support.summary.model_dump(mode="json"),
                "method": support.method.model_dump(mode="json"),
            }
        root_span.log(output=payload)
        return payload


def _source_support_for(triage_case: TriageCase, decision: dict) -> SourceSupport | None:
    """Trích nguồn y văn cho nhãn vừa chốt. `None` = tắt, hoặc hỏng (và đã ghi log).

    KHÔNG BAO GIỜ raise và KHÔNG BAO GIỜ đổi `triage_label`: người gọi nằm trên đường phản hồi của
    bệnh nhân, và mức ưu tiên có hiệu lực vẫn do rule engine quyết (ràng buộc 4 của module này)."""
    if not get_settings().source_support_enabled:
        return None
    try:
        from src.source_support import pipeline as source_support_pipeline

        # Bản sao, không mutate `decision` gốc: nó còn được `_compact_payload` đọc lại sau lời gọi
        # này. `chief_complaint` cho bước 1 của Part 3 (claim-splitter) biết triệu chứng nào là
        # trọng tâm, để nó không chọn nhầm một dấu hiệu phụ khi phải chọn tối đa 3 claim.
        # `triage_case.summary` là optional (case dựng tay/test có thể để trống) - rỗng thì bỏ qua
        # tín hiệu này, KHÔNG để cả Part 3 fail vì thiếu mỗi một trường không bắt buộc.
        chief_complaint = triage_case.summary.chief_complaint if triage_case.summary else ""
        payload = {**decision, "chief_complaint": chief_complaint}
        return source_support_pipeline.run(payload, triage_label=decision["triage_label"])
    except Exception as error:
        logger.warning(
            "graph_triage.source_support_failed case_id=%s error=%s: %s",
            triage_case.case_id, type(error).__name__, error,
        )
        return None


def reset_agent_cache() -> None:
    """Chỉ dùng cho test: quên singleton và lý do tắt."""
    global _agent, _unavailable_reason, _c6_fusion_gate, _c6_fusion_unavailable_reason
    with _lock:
        _agent = None
        _unavailable_reason = None
    with _c6_fusion_lock:
        _c6_fusion_gate = None
        _c6_fusion_unavailable_reason = None

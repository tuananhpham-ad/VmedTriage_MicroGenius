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

4. KHÔNG QUYẾT ĐỊNH. Trả về dict để lưu vào `TriageCase.graph_decision`. Người gọi TUYỆT ĐỐI không
   được gán giá trị này vào `TriageProposal.priority` hay `RedFlagFinding`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.graph_triage.summary_text import build_summary_text
from src.models.schemas import TriageCase
from src.observability.braintrust_tracing import traced_root_span, traced_span
from src.paths import RUNS_DIR
from src.source_support import pipeline as source_support
from src.source_support.schemas import SourceSupport

logger = logging.getLogger("vmedtriage.graph_triage")

_lock = threading.Lock()
_agent: Any | None = None
_unavailable_reason: str | None = None


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


def decide_for_case(triage_case: TriageCase) -> dict | None:
    """Chạy agent quyết định cho một case đã chốt phiếu. `None` = không có gì để lưu.

    Không bao giờ raise: người gọi nằm trên đường phản hồi của bệnh nhân.
    """
    if not get_settings().enable_graph_triage_agent:
        return None
    summary_text = build_summary_text(triage_case)
    if not summary_text:
        logger.info("graph_triage.skipped case_id=%s reason=empty_summary", triage_case.case_id)
        return None
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

        return source_support_pipeline.run(decision, triage_label=decision["triage_label"])
    except Exception as error:
        logger.warning(
            "graph_triage.source_support_failed case_id=%s error=%s: %s",
            triage_case.case_id, type(error).__name__, error,
        )
        return None


def reset_agent_cache() -> None:
    """Chỉ dùng cho test: quên singleton và lý do tắt."""
    global _agent, _unavailable_reason
    with _lock:
        _agent = None
        _unavailable_reason = None

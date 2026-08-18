"""Chạy TRỌN luồng và in ra từng chặng, để nhìn thấy dữ liệu biến đổi qua mỗi bước.

    python -m scripts.trace_end_to_end

    python -m scripts.trace_end_to_end --graph     # in thêm toàn bộ node/edge của Patient Graph

Các chặng in ra:

    1  người dùng nhập  ->  agent hỏi lại, field trích xuất được từng lượt
    2  phiên chốt       ->  phiếu bàn giao (HandoffSummary + summary_fields)
    3  chuỗi text gửi đi (thứ 3 model và DeepSeek thực sự đọc)
    4  DeepSeek         ->  Patient Graph, từng quan sát kèm source_span
    5  3 model local    ->  xác suất từng nhãn
    6  gpt-4o-mini      ->  tool đã gọi + kết luận cuối

Gọi cùng những hàm mà `POST /api/v1/chat` gọi (`symptom_session` -> `symptom_case_bridge` ->
`graph_triage.service`), chỉ khác là chạy thẳng trong tiến trình thay vì qua HTTP.

TỐN TIỀN THẬT: mỗi lượt hội thoại gọi provider của agent hỏi-đáp; khi phiếu chốt thêm 1 lời gọi
DeepSeek + vài lượt gpt-4o-mini.
"""

from __future__ import annotations

import logging
import sys

from src.config import get_settings
from src.graph_triage import service
from src.graph_triage.labels import TRIAGE_LABELS
from src.graph_triage.summary_text import build_summary_text
from src.services.sessions import symptom_case_bridge, symptom_session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Kịch bản của một ca sốt nhẹ có thật. Phần lớn là "không" vì agent quét red flag theo cụm; giữ
# nguyên như người dùng gõ để phiếu chốt đúng như luồng thật.
TURNS = [
    "Tôi bị sốt.", "18 tuổi", "nam", "tôi 38 độ, đo cách đây 30 phút ở nách",
    "sốt mới được có 4 tiếng thôi", "tôi không thấy rét", "tôi uống para đã đỡ hơn rồi",
    "tôi thấy khỏe hơn rồi", "đúng rồi", "không có", "không có", "không có", "3",
]
FALLBACK = "không"
MAX_TURNS = 60
CLOSED_STATES = {"awaiting_confirmation", "confirmed", "emergency"}


def _rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> None:
    show_graph = "--graph" in sys.argv
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s | %(message)s")
    settings = get_settings()
    if not settings.enable_graph_triage_agent:
        print("!! ENABLE_GRAPH_TRIAGE_AGENT đang tắt -> bật tạm cho lần chạy này.")
        settings.enable_graph_triage_agent = True

    _rule("CHẶNG 1  -  hội thoại: người dùng nhập, agent trích xuất field")
    session = symptom_session.session_store.start_session()
    previous_answers: dict[str, object] = {}
    for index in range(1, MAX_TURNS + 1):
        message = TURNS[index - 1] if index <= len(TURNS) else FALLBACK
        session = symptom_session.session_store.submit_message(session.session_id, message)
        new = {k: v for k, v in session.answers.items() if previous_answers.get(k) != v}
        previous_answers = dict(session.answers)
        print(f"\n[{index:>2}] người dùng: {message}")
        if new:
            print(f"     trích xuất: {', '.join(f'{k}={v}' for k, v in list(new.items())[:6])}"
                  + (f" (+{len(new) - 6} field)" if len(new) > 6 else ""))
        if session.state.value in CLOSED_STATES:
            print(f"\n>> Phiên chốt sau {index} lượt. state={session.state.value}, "
                  f"triage_level={session.triage_level}, stop_reason={session.stop_reason}")
            break
        print(f"     agent hỏi : {(session.last_question or '')[:110]}")
    else:
        print(f"\n!! Hết {MAX_TURNS} lượt mà phiên chưa chốt.")
        return

    triage_case = symptom_case_bridge.to_triage_case(session, patient_id=None)

    _rule("CHẶNG 2  -  phiếu bàn giao dựng từ phiên")
    summary = triage_case.summary
    print(f"  Than phiền chính : {summary.chief_complaint}")
    print(f"  Khởi phát        : {summary.onset}")
    print(f"  Red flag         : {[f.label for f in summary.red_flags] or '(không)'}")
    print(f"  Rule engine      : {triage_case.triage_proposal.priority if triage_case.triage_proposal else '(chưa có)'}")
    filled = [r for r in triage_case.summary_fields if not r.is_missing]
    print(f"  summary_fields   : {len(filled)}/{len(triage_case.summary_fields)} đã điền")

    _rule("CHẶNG 3  -  chuỗi text thực sự gửi cho DeepSeek và 3 model")
    summary_text = build_summary_text(triage_case)
    print(summary_text)
    agent = service._get_agent()
    if agent is None:
        print("\n!! Agent không dựng được - xem log 'graph_triage.unavailable'.")
        return
    n_tokens = len(agent.ensemble.bert.tokenizer(summary_text)["input_ids"])
    print(f"\n  -> {len(summary_text)} ký tự | {n_tokens} token"
          + (f" | PhoBERT CẮT còn 256, mất {n_tokens - 256} token" if n_tokens > 256 else " | vừa 256 token"))

    result = agent.decide(summary_text)
    analysis = result["model_analysis"]

    _rule("CHẶNG 4  -  DeepSeek dựng Patient Graph (mọi span cắt từ chuỗi trên)")
    evidence = analysis["evidence_graph"]["evidence"]
    print(f"  {len(evidence)} quan sát về bệnh nhân:\n")
    for item in evidence:
        print(f"    [{item['status']:9}] {item['type']:14} {item['concept']:26} <- {item['surface_form']!r}")
    if show_graph:
        print(f"\n  patient: {analysis['evidence_graph']['patient']}")

    _rule("CHẶNG 5  -  3 model local chấm điểm")
    for name, item in analysis["models"].items():
        probabilities = "  ".join(f"{label}={item['probabilities'][label]:.3f}" for label in TRIAGE_LABELS)
        print(f"  {name:8} {probabilities}   -> {item['predicted_label']}")
        print(f"           (metric đã ghi: {item['run_metrics'].get('evaluation_scope', '?')})")
    print(f"\n  bất đồng giữa các model: {analysis['model_disagreement']}")
    if "fusion_mean_text_gate" in analysis:
        print(f"  cổng fusion (1.0 = chỉ nghe text, 0.0 = chỉ nghe graph): {analysis['fusion_mean_text_gate']:.3f}")

    _rule("CHẶNG 6  -  gpt-4o-mini quyết định")
    audit = result["tool_audit"]
    print(f"  model      : {audit['model']}")
    print(f"  tool đã gọi: {', '.join(audit['called_tools'])}")
    decision = result["llm_decision"]
    print(f"\n  KẾT LUẬN   : {decision['triage_label']}")
    print(f"  cần người xem lại: {decision['requires_human_review']}")
    print(f"\n  {decision['decision_summary']}")
    print(f"\n  đồng thuận : {decision['model_agreement_summary']}")
    print(f"  bất định   : {decision['uncertainty_summary']}")
    print(f"\n  trích dẫn {len(decision['evidence'])} bằng chứng:")
    for item in decision["evidence"]:
        print(f"    [{item['status']}] {item['concept']} <- {item['source_span']!r}")

    _rule("ĐỐI CHIẾU")
    print(f"  Rule engine (nguồn quyết định thật) : {triage_case.triage_proposal.priority if triage_case.triage_proposal else '?'}")
    print(f"  Ý kiến mô hình (chỉ tham khảo)      : {decision['triage_label']}")


if __name__ == "__main__":
    main()

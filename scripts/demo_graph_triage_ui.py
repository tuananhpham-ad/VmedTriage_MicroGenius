"""Dựng sẵn vài ca đã chốt phiếu, chạy agent quyết định thật, rồi mở server để xem trên UI điều dưỡng.

    python -m scripts.demo_graph_triage_ui

Vì sao cần script này thay vì chat tay: `case_store` là IN-MEMORY (`src/services/stores/case_store.py`),
nên seed từ tiến trình khác sẽ không tới được server. Script này seed NGAY TRONG tiến trình server.

Sau khi chạy, mở http://localhost:8000 -> đăng nhập `nurse0` / `nurse0` -> vào hàng đợi -> mở ca ->
xem khối "Ý kiến tham khảo từ mô hình".

TỐN TIỀN THẬT: mỗi ca tốn 1 lời gọi DeepSeek (trích xuất Patient Graph) + vài lượt gpt-4o-mini.
Chạy `python -m scripts.seed_demo_users` trước nếu chưa có tài khoản demo.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

import uvicorn

from src.config import get_settings
from src.graph_triage import service
from src.models.schemas import (
    ActorRole,
    CaseStatus,
    ConversationMessage,
    HandoffSummary,
    NurseQueueItem,
    QueuePriority,
    RedFlagFinding,
    StructuredSymptomData,
    SummaryField,
    TriageCase,
    TriagePriority,
    TriageProposal,
    ValidationResult,
)
from src.services.stores.case_store import case_store

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ba ca cố ý chọn khác nhau về mức độ, để so cách agent phản ứng.
SCENARIOS = [
    {
        "group": "chest_pain",
        "chief_complaint": "Đau ngực",
        "priority": TriagePriority.URGENT,
        "red_flags": [RedFlagFinding(code="RF-01", label="Đau ngực kèm khó thở")],
        "fields": [
            ("Mô tả tình trạng", "đau tức giữa ngực từ sáng nay, đau lan xuống tay trái"),
            ("Thời điểm khởi phát", "khoảng 6 tiếng trước"),
            ("Mức độ đau", "7 trên 10"),
            ("Khó thở", "có, khó thở khi đi lại vài bước"),
            ("Sốt", "không sốt"),
            ("Tiền sử bệnh", "cao huyết áp nhiều năm"),
            ("Nôn ra máu", None),
        ],
        "turns": ["Tôi bị đau tức giữa ngực từ sáng nay, đau lan xuống tay trái",
                  "Đau khoảng 7 trên 10, đi vài bước là hụt hơi"],
    },
    {
        "group": "fever",
        "chief_complaint": "Sốt",
        "priority": TriagePriority.SELF_CARE,
        "red_flags": [],
        "fields": [
            ("Mô tả tình trạng", "sốt nhẹ 37.8 độ từ hôm qua, hơi mệt và đau mỏi người"),
            ("Thời điểm khởi phát", "từ chiều hôm qua"),
            ("Nhiệt độ đo được", "37.8"),
            ("Ăn uống", "vẫn ăn uống bình thường"),
            ("Cứng cổ", "không cứng cổ, không đau đầu dữ dội"),
            ("Co giật", None),
        ],
        "turns": ["Tôi bị sốt nhẹ từ hôm qua, đo được 37.8 độ",
                  "Tôi vẫn ăn uống bình thường, không cứng cổ"],
    },
    {
        "group": "abdominal",
        "chief_complaint": "Đau bụng",
        "priority": TriagePriority.ROUTINE,
        "red_flags": [],
        "fields": [
            ("Mô tả tình trạng", "đau quặn bụng dưới bên phải, buồn nôn"),
            ("Thời điểm khởi phát", "từ tối qua"),
            ("Mức độ đau", "6 trên 10"),
            ("Nôn ra máu", "không nôn ra máu, không đi ngoài phân đen"),
            ("Bụng gồng cứng", None),
        ],
        "turns": ["Tôi đau quặn bụng dưới bên phải từ tối qua, buồn nôn",
                  "Đau khoảng 6 trên 10, không nôn ra máu"],
    },
]


def _build_case(scenario: dict) -> TriageCase:
    summary_fields = [
        SummaryField(label=label, value=value, is_missing=value is None)
        for label, value in scenario["fields"]
    ]
    summary = HandoffSummary(
        chief_complaint=scenario["chief_complaint"],
        onset=next((v for lbl, v in scenario["fields"] if lbl == "Thời điểm khởi phát"), None),
        red_flags=scenario["red_flags"],
        proposed_priority=scenario["priority"],
        protocol_reason="Dựng sẵn cho demo, không phải kết luận lâm sàng.",
        missing_information=[lbl for lbl, v in scenario["fields"] if v is None],
    )
    structured = StructuredSymptomData(symptom_group=scenario["group"], fields={}, source="demo_seed")
    validation = ValidationResult(is_valid=True, missing_fields=summary.missing_information)
    proposal = TriageProposal(
        priority=scenario["priority"], protocol_id=f"DEMO-{scenario['group'].upper()}",
        reason="Đề xuất của rule engine (dựng sẵn cho demo).", requires_manual_review=True,
    )
    status = CaseStatus.ESCALATED if scenario["red_flags"] else CaseStatus.NEEDS_NURSE_REVIEW
    return TriageCase(
        conversation=[ConversationMessage(role=ActorRole.PATIENT, content=t) for t in scenario["turns"]],
        structured_data=structured, validation=validation, red_flags=scenario["red_flags"],
        triage_proposal=proposal, summary=summary, status=status,
        summary_ready=True, summary_fields=summary_fields,
        created_at=datetime.now(timezone.utc),
        queue_item=NurseQueueItem(
            case_id="placeholder", queue_priority=QueuePriority.HIGH if scenario["red_flags"] else QueuePriority.STANDARD,
            status=status, summary=summary, structured_data=structured, validation=validation, triage_proposal=proposal,
        ),
    )


def seed() -> None:
    settings = get_settings()
    if not settings.enable_graph_triage_agent:
        print("!! ENABLE_GRAPH_TRIAGE_AGENT đang tắt -> bật tạm cho lần chạy này.")
        settings.enable_graph_triage_agent = True

    for scenario in SCENARIOS:
        triage_case = _build_case(scenario)
        triage_case.queue_item.case_id = triage_case.case_id
        print(f"\n--- {scenario['chief_complaint']} ({triage_case.case_id[:8]}) ---")
        print(f"    rule engine: {scenario['priority'].value}")
        triage_case.graph_decision = service.decide_for_case(triage_case)
        if triage_case.graph_decision:
            print(f"    agent      : {triage_case.graph_decision['triage_label']} "
                  f"(cần người xem lại: {triage_case.graph_decision['requires_human_review']})")
            print(f"    lý do      : {triage_case.graph_decision['decision_summary'][:110]}")
        else:
            print("    agent      : None - xem log 'graph_triage.' phía trên để biết lý do")
        case_store.save(triage_case)


def main() -> None:
    # uvicorn chỉ cấu hình logger của chính nó, logger khác rơi về root (mặc định WARNING) nên mọi
    # dòng `graph_triage.*` biến mất. Cấu hình root ở đây để xem được trên terminal.
    debug = "--debug" in sys.argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("vmedtriage.graph_triage").setLevel(logging.DEBUG if debug else logging.INFO)
    # httpx log từng lời gọi DeepSeek/OpenAI - hữu ích để thấy đúng bao nhiêu request đã đi ra.
    logging.getLogger("httpx").setLevel(logging.INFO if debug else logging.WARNING)
    if debug:
        print(">> chế độ --debug: in cả xác suất từng model, evidence graph và phiếu tóm tắt gửi đi\n")
    seed()
    print("\n" + "=" * 72)
    print("Mở http://localhost:8000  ->  đăng nhập  nurse0 / nurse0  ->  hàng đợi  ->  mở một ca")
    print("Khối cần xem: 'Ý kiến tham khảo từ mô hình', nằm ngay dưới cảnh báo dấu hiệu nguy hiểm.")
    print("Chưa có tài khoản? Ctrl+C rồi chạy: python -m scripts.seed_demo_users")
    print("=" * 72 + "\n")
    # reload=False bắt buộc: reload dùng tiến trình con, case_store vừa seed sẽ không đi theo.
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=False, log_config=None, log_level="info")


if __name__ == "__main__":
    main()

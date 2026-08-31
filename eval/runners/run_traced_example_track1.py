"""Chạy MỘT case mẫu qua Track 1 THẬT (`TriagePipeline.handle_patient_message`, rule-based,
AUTHORITATIVE) và in trace link Braintrust.

Track 1 luôn chạy, không cần cờ bật/tắt nào, không cần OPENAI_API_KEY/DEEPSEEK_API_KEY - toàn bộ là
string/regex/dict matching (xem docs/eval/01_evaluation_units.md mục 8, KHÔNG có LLM call nào).
`TriageProposal.requires_manual_review` LUÔN `True` - script này KHÔNG tự động duyệt case, chỉ chạy
đề xuất và in kết quả để nhân viên y tế xem lại thủ công (HITL bắt buộc, xem CLAUDE.md).

Chạy: `python eval/runners/run_traced_example_track1.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.observability.braintrust_tracing import braintrust_enabled  # noqa: E402
from src.services.triage_pipeline import TriagePipeline  # noqa: E402

SAMPLE_MESSAGE = (
    "Tôi bị đau ngực trái từ khoảng 1 tiếng trước, đau mức 6/10, đau lan lên vai trái, "
    "kèm khó thở nhẹ khi gắng sức. Không sốt, không ho."
)


async def _run() -> None:
    print(f"BRAINTRUST_API_KEY set: {braintrust_enabled()}")

    pipeline = TriagePipeline()
    triage_case = await pipeline.handle_patient_message(SAMPLE_MESSAGE)

    print(f"case_id: {triage_case.case_id}")
    print(f"status: {triage_case.status}")
    if triage_case.triage_proposal:
        print(f"triage_proposal.priority: {triage_case.triage_proposal.priority}")
        print(f"triage_proposal.protocol_id: {triage_case.triage_proposal.protocol_id}")
        print(f"triage_proposal.reason: {triage_case.triage_proposal.reason}")
        print(f"triage_proposal.requires_manual_review: {triage_case.triage_proposal.requires_manual_review}")
        assert triage_case.triage_proposal.requires_manual_review is True, (
            "HITL bắt buộc 100% - requires_manual_review phải luôn True (CLAUDE.md). "
            "Nếu assertion này fail, có bug NGHIÊM TRỌNG cần dừng lại ngay, không phải lỗi eval script."
        )
    print(f"patient_visible_response: {triage_case.patient_visible_response!r}")
    print(f"red_flags: {[f.code for f in triage_case.red_flags]}")

    if not braintrust_enabled():
        print(
            "\nBraintrust trace: KHÔNG có - BRAINTRUST_API_KEY chưa được set trong môi trường này. "
            "Set biến này rồi chạy lại để lấy trace link thật (in ở dòng log 'braintrust.trace_link')."
        )
    else:
        print(
            "\nBraintrust trace link được in ở dòng log 'braintrust.trace_link' phía trên (mức INFO)."
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

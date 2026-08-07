"""CLI hỏi-đáp theo checklist từng bệnh (mục 10 solution design).

Chạy từ root repository:

    python -m scripts.run_disease_qa                 # mặc định bệnh disease_x
    python -m scripts.run_disease_qa disease_x       # chỉ định bệnh
    python -m scripts.run_disease_qa disease_x --demo  # chạy kịch bản mẫu, không cần gõ tay

Checklist nạp từ `src/domain/_<disease_id>.json`. Dùng LLM thật qua `provider_router` (đọc API key
trong `.env`); nếu chưa cấu hình provider nào thì tự rơi về fallback deterministic và báo rõ trên
màn hình - không im lặng.
"""

from __future__ import annotations

import argparse
import sys

from src.services import disease_session, provider_router, session_log
from src.services.disease_checklist import ChecklistNotFoundError
from src.services.disease_session import SessionState

# Windows console mặc định cp1252, không in được tiếng Việt có dấu -> ép UTF-8 để script chạy được
# ngay trên PowerShell mà người dùng không phải tự set PYTHONIOENCODING.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEMO_SCRIPT = [
    "Chào bạn, tôi thấy trong người không ổn",
    "Tôi tên là Trần Minh Khoa",
    "Tôi bị sốt cao 39 độ, đau họng và ho khan nhiều",
    "Triệu chứng bắt đầu từ sáng hôm qua",
]


def print_progress(session) -> None:
    progress = disease_session.progress_of(session)
    line = (
        f"  [checklist {progress['percent']}% - {progress['filled_required']}/{progress['total_required']} trường bắt buộc]"
    )
    if progress["missing_required_labels"]:
        line += f" còn thiếu: {', '.join(progress['missing_required_labels'])}"
    print(line)


def print_summary(session) -> None:
    print("\n" + "=" * 68)
    print(disease_session.build_summary_text(session))
    print("=" * 68)


def run(disease_id: str, demo: bool) -> int:
    try:
        session = disease_session.start_session(disease_id)
    except ChecklistNotFoundError as exc:
        print(f"Lỗi: {exc}")
        return 1

    providers = provider_router.available_providers()
    mode = f"LLM thật (provider: {providers[0]})" if providers else "FALLBACK deterministic (chưa cấu hình API key)"
    print("=" * 68)
    print(f"Bệnh    : {session.checklist.disease_label}")
    print(f"Ngưỡng  : đủ khi >= {session.checklist.completion_threshold:.0%} trường bắt buộc")
    print(f"Chế độ  : {mode}")
    print(f"Log     : {session_log.log_path(session.session_id)}")
    print("=" * 68)
    print(f"\n[AGENT] {session.last_question}")

    scripted = list(DEMO_SCRIPT) if demo else []

    while session.state != SessionState.CONFIRMED:
        if session.state == SessionState.AWAITING_CONFIRMATION:
            print_summary(session)
            answer = "d" if demo else _prompt("Phiếu trên đã đúng chưa? [d]úng / [s]ửa / [q]uit: ")
            if answer.lower().startswith("q"):
                return 0
            if answer.lower().startswith("d"):
                session = disease_session.confirm_summary(session.session_id, is_correct=True)
                print("\n[AGENT] Cảm ơn bạn, phiếu đã được xác nhận.")
                break
            correction = _prompt("Bạn cần sửa gì? ")
            session = disease_session.confirm_summary(
                session.session_id, is_correct=False, correction=correction
            )
            print_progress(session)
            if session.last_question:
                print(f"\n[AGENT] {session.last_question}")
            continue

        if scripted:
            message = scripted.pop(0)
            print(f"\n[BẠN  ] {message}")
        else:
            message = _prompt("\n[BẠN  ] ")
            if message.lower().strip() in {"q", "quit", "exit"}:
                return 0

        try:
            session = disease_session.submit_message(session.session_id, message)
        except disease_session.EmptyMessageError:
            print("  (tin nhắn trống, nhập lại giúp mình nhé)")
            continue

        print_progress(session)
        if not session.llm_used_last_turn:
            print("  (lượt này chạy fallback deterministic, không dùng LLM)")
        if session.last_question:
            print(f"\n[AGENT] {session.last_question}")

    print(f"\nTrạng thái phiên: {session.state.value}")
    print(f"Log đầy đủ: {session_log.log_path(session.session_id)}")
    return 0


def _prompt(text: str) -> str:
    try:
        return input(text)
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0) from None


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI hỏi-đáp theo checklist từng bệnh.")
    parser.add_argument("disease_id", nargs="?", default="disease_x", help="mặc định: disease_x")
    parser.add_argument("--demo", action="store_true", help="chạy kịch bản mẫu, không cần gõ tay")
    args = parser.parse_args()
    return run(args.disease_id, args.demo)


if __name__ == "__main__":
    raise SystemExit(main())

"""Chạy hội thoại ĐẦY ĐỦ tới khi phiên đóng, bằng bệnh nhân mô phỏng - §9 P4.3-P4.4 + §2.4 lỗ hổng 1.

    python eval/scripts/run_conversation_eval.py --limit 8

KHÁC `run_eval.py` Ở ĐÂU. `run_eval.py` phát đúng 2 lượt bệnh nhân của golden case rồi chấm; nó đo
được nhánh ĐỎ (escalate sớm) nhưng không bao giờ chạm tới lúc phiên đóng, nên mọi metric của §12 về
độ dài, độ phủ và trải nghiệm đều không có dữ liệu. Script này lấy chính golden case làm HỒ SƠ cho
một bệnh nhân mô phỏng rồi để nó trả lời tới cùng.

CHẠY IN-PROCESS QUA `ProtocolSessionStore`, tức ĐÚNG luồng chuẩn (`symptom_protocol.session`), không
phải `TriagePipeline` legacy mà `run_eval.py --mode direct` chạy (§2.2). Không cần server, nhưng
cũng vì thế không đo được tầng HTTP/auth - việc đó vẫn là của `run_eval.py --mode api`.

CÁI SCRIPT NÀY KHÔNG ĐO. Triage accuracy: nhãn golden case gắn với 2 lượt gốc, còn phần hội thoại
sau là do model bệnh nhân sinh ra trong khuôn khổ lời kể. Mức triage in ra ở đây là để thấy PHÂN BỐ
(có chạm được `EARLY_VISIT`/`SELF_CARE` không), không phải để chấm đúng/sai.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.scripts.simulated_patient import SimulatedPatient, profile_from_case  # noqa: E402
from src.services.infra import provider_router  # noqa: E402
from src.services.symptom_protocol import metrics as metrics_mod  # noqa: E402
from src.services.symptom_protocol.session import (  # noqa: E402
    ProtocolSessionStore,
    SessionState,
)

DEFAULT_CASES = ROOT / "data" / "golden_cases_v1.jsonl"
DEFAULT_OUT = ROOT / "eval" / "baselines"

HARD_TURN_CAP = 40
"""Trần CỨNG chống lặp vô hạn, không phải ngân sách lâm sàng.

Ngân sách thật nằm ở `stage_machine.should_stop` (§8.7). Trần này chỉ tồn tại để một lỗi khiến phiên
không bao giờ đóng không đốt hết API key - và mọi phiên chạm trần đều được đếm riêng
(`hit_turn_cap`), vì một lần chạy có nhiều phiên chạm trần là một lần chạy không đo được gì."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chay hoi thoai day du bang benh nhan mo phong.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--limit", type=int, default=8, help="So ca chay (mac dinh 8 - moi ca ton ~20 luot x 3 loi goi).")
    parser.add_argument("--offset", type=int, default=0, help="Bo qua N ca dau - de lay mau khac nhau giua cac lan chay.")
    parser.add_argument(
        "--stratify", action="store_true",
        help="Lay mau deu theo expected_triage thay vi lay N ca dau (golden case sap xep theo muc).",
    )
    parser.add_argument("--max-turns", type=int, default=HARD_TURN_CAP)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--tag", default="", help="Hau to ten file ket qua.")
    # Hai co MAC DINH TAT trong production, va chi co y nghia khi chay eval - dung o day thay vi bat
    # trong `.env` de mot lan chay eval khong doi cau hinh cua may dev.
    parser.add_argument(
        "--model-red-flag-branch",
        action="store_true",
        help="Bat nhanh red-flag bang model (§4.1) de sinh `red_flag_agreement`. Ton them 1 loi goi/luot.",
    )
    parser.add_argument(
        "--controller-shadow",
        action="store_true",
        help="Bat controller shadow mode (§4.11 buoc 1) de sinh `controller_agreement_rate`.",
    )
    return parser.parse_args()


def _apply_eval_flags(args: argparse.Namespace) -> list[str]:
    """Bat co theo tham so dong lenh, trong dung tien trinh nay.

    Ghi thang vao doi tuong `Settings` da cache thay vi dat bien moi truong: `get_settings()` duoc
    `lru_cache` giu, nen mot bien moi truong dat sau khi module da import se KHONG co tac dung - va
    that bai do im lang, eval van chay va van bao `n=0` nhu the co dang tat.

    Tra ve danh sach co da bat de no di vao file ket qua: mot con so `agreement_rate` khong kem thong
    tin "luc do co nao dang bat" thi khong doc lai duoc ve sau."""
    from src.config import get_settings

    settings = get_settings()
    enabled: list[str] = []
    if args.model_red_flag_branch:
        settings.agent_model_red_flag_branch_enabled = True
        enabled.append("model_red_flag_branch")
    if args.controller_shadow:
        settings.agent_llm_controller_shadow_enabled = True
        enabled.append("controller_shadow")
    return enabled


def load_cases(path: Path, *, offset: int, limit: int, stratify: bool) -> list[dict]:
    """`stratify=True` lấy mẫu ĐỀU theo `expected_triage`.

    Cần thiết vì `golden_cases_v1.jsonl` sắp xếp theo mức: 45 ca `emergency_now` nằm liền nhau ở đầu.
    Lấy N ca đầu nghĩa là chỉ đo nhánh ĐỎ - mà ca đỏ short-circuit sau 1-2 lượt nên không nói được gì
    về độ phủ hay trải nghiệm, tức là đúng những thứ script này sinh ra để đo."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        cases = json.loads(raw)
    if not stratify:
        return cases[offset : offset + limit]

    groups: dict[str, list[dict]] = {}
    for case in cases:
        groups.setdefault(str(case.get("expected_triage")), []).append(case)
    picked: list[dict] = []
    round_index = offset
    while len(picked) < limit:
        added = False
        for _label, members in sorted(groups.items()):
            if round_index < len(members) and len(picked) < limit:
                picked.append(members[round_index])
                added = True
        if not added:
            break  # đã duyệt hết mọi nhóm
        round_index += 1
    return picked


def run_case(case: dict, *, max_turns: int) -> dict:
    """Một phiên trọn vẹn. Trả về metric của phiên + thông tin để đọc lại transcript."""
    profile = profile_from_case(case)
    patient = SimulatedPatient(profile=profile)
    store = ProtocolSessionStore(default_protocol=None)  # None = có lượt mở, đúng đường ô chat tự do
    session = store.start_session()

    started = time.perf_counter()
    turn_latencies: list[float] = []
    hit_cap = False
    # Lượt đầu là lời kể tự do của chính người bệnh - không qua model bệnh nhân, để lượt mở giống
    # hệt cách một người thật bắt đầu cuộc trò chuyện.
    message = next(
        (str(t["message"]) for t in case.get("conversation", []) if t.get("role") == "patient"),
        "Mình thấy trong người không khoẻ.",
    )

    for _ in range(max_turns):
        turn_started = time.perf_counter()
        store.submit_message(session.session_id, message)
        turn_latencies.append((time.perf_counter() - turn_started) * 1000)
        if session.state != SessionState.COLLECTING:
            break
        question = session.last_question
        if not question:
            # Không còn câu hỏi nào mà phiên vẫn COLLECTING: đây là trạng thái không hợp lệ, và im
            # lặng bỏ qua nó sẽ biến một bug thành một con số đẹp.
            break
        message = patient.reply(question)
    else:
        hit_cap = True

    summary = store.metrics_summary(session.session_id)
    summary.update({
        "case_id": case.get("case_id"),
        "expected_triage": case.get("expected_triage"),
        "protocol": session.protocol_name,
        "hit_turn_cap": hit_cap,
        "patient_fallback_turns": patient.fallback_turns,
        "wall_seconds": round(time.perf_counter() - started, 2),
        "turn_latency_p50_ms": round(statistics.median(turn_latencies)) if turn_latencies else None,
        "transcript": list(session.conversation),
    })
    return summary


def main() -> int:
    args = parse_args()
    cases = load_cases(
        Path(args.cases), offset=args.offset, limit=args.limit, stratify=args.stratify,
    )
    if not cases:
        print("Khong co ca nao de chay.")
        return 1

    enabled_flags = _apply_eval_flags(args)
    if enabled_flags:
        print(f"Co bat cho lan chay nay: {', '.join(enabled_flags)}", flush=True)

    provider_router.reset_role_usage()
    summaries: list[dict] = []
    for index, case in enumerate(cases, start=1):
        case_id = case.get("case_id", f"#{index}")
        print(f"[{index}/{len(cases)}] {case_id} ...", flush=True)
        try:
            summary = run_case(case, max_turns=args.max_turns)
        except Exception as error:  # noqa: BLE001 - một ca hỏng không được làm mất kết quả các ca khác
            print(f"    LOI: {error}")
            summaries.append({"case_id": case_id, "error": str(error)})
            continue
        summaries.append(summary)
        print(
            f"    {summary['turns']} luot | {summary['triage_level']} | "
            f"stop={summary['stop_reason']} | phu={summary['mandatory_coverage_at_close']} | "
            f"user_led={summary['user_led_ratio']}",
            flush=True,
        )

    scored = [item for item in summaries if "error" not in item]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(args.cases),
        "stratified": bool(args.stratify),
        "cases_run": len(summaries),
        "cases_failed": len(summaries) - len(scored),
        "max_turns": args.max_turns,
        "hit_turn_cap": sum(1 for item in scored if item.get("hit_turn_cap")),
        "patient_fallback_turns": sum(int(item.get("patient_fallback_turns", 0)) for item in scored),
        "triage_distribution": _distribution(scored, "triage_level"),
        "stop_reason_distribution": _distribution(scored, "stop_reason"),
        "aggregate": metrics_mod.aggregate(scored),
        "per_role_llm_usage": provider_router.role_usage_snapshot(),
        "health_warnings": [],  # điền ngay dưới, sau khi `per_role_llm_usage` đã có
        "sessions": [{k: v for k, v in item.items() if k != "transcript"} for item in summaries],
    }

    # Cảnh báo nằm TRONG file kết quả, không chỉ trên màn hình: người đọc baseline sáu tuần sau
    # không có màn hình của lần chạy này.
    report["health_warnings"] = _run_health_warnings(report)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Có GIỜ-PHÚT trong tên file, không chỉ ngày. Lần chạy thứ hai trong cùng ngày đã ghi đè im lặng
    # lên một baseline tốt và xoá mất nó - mà baseline là thứ tốn API thật mới có được, không dựng
    # lại bằng cách chạy lại code.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    suffix = f"-{args.tag}" if args.tag else ""
    json_path = out_dir / f"{stamp}-conversation-eval{suffix}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    transcripts = out_dir / f"{stamp}-conversation-transcripts{suffix}.md"
    transcripts.write_text(_render_transcripts(scored), encoding="utf-8")

    print()
    for line in _run_health_warnings(report):
        print(line)
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(f"\n-> {json_path}\n-> {transcripts}")
    return 0


_FAILURE_RATE_ALARM = 0.05


def _run_health_warnings(report: dict) -> list[str]:
    """Cảnh báo khi lần chạy này KHÔNG đọc được như số liệu thật.

    Có thật: một lần chạy gặp provider bị chặn giữa chừng cho ra `fact_extractor` lỗi 216/279 lời gọi,
    5/10 phiên chạm trần lượt, và một bảng aggregate trông vẫn "bình thường". Số liệu hỏng mà im lặng
    thì tệ hơn hẳn không có số liệu - nó vào baseline rồi thành mốc so sánh cho mọi thay đổi sau."""
    warnings: list[str] = []
    for role, usage in report.get("per_role_llm_usage", {}).items():
        calls = int(usage.get("calls") or 0)
        failures = int(usage.get("failures") or 0)
        if calls and failures / calls > _FAILURE_RATE_ALARM:
            warnings.append(
                f"!! {role}: {failures}/{calls} loi goi model THAT BAI "
                f"({failures / calls:.0%}) - KHONG dung lan chay nay lam baseline."
            )
    if report.get("hit_turn_cap"):
        warnings.append(
            f"!! {report['hit_turn_cap']}/{report['cases_run']} phien cham TRAN LUOT - "
            "chung chua dong, moi chi so 'at close' cua chung khong doc duoc."
        )
    if report.get("patient_fallback_turns"):
        warnings.append(
            f"!! benh nhan mo phong dung cau du phong {report['patient_fallback_turns']} luot - "
            "he thong dang bi do bang mot benh nhan im lang."
        )
    return warnings


def _distribution(summaries: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in summaries:
        value = str(item.get(key))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _render_transcripts(summaries: list[dict]) -> str:
    """Transcript cho reviewer chấm bằng mắt (§12 gate mềm: "rõ, đúng ngữ cảnh, không lặp máy móc").

    Không có chỉ số tự động nào thay được bước này - `repeat_question_rate` bắt được câu hỏi lặp
    nguyên cụm, nhưng không bắt được một câu hỏi đúng cụm mà diễn đạt như đọc biểu mẫu."""
    lines = ["# Transcript hội thoại đầy đủ (bệnh nhân mô phỏng)", ""]
    lines.append("> Bệnh nhân mô phỏng KHÔNG biết nhãn của ca - chỉ biết lời kể của chính người bệnh.")
    lines.append("> Mức triage ở đây để xem PHÂN BỐ, không phải để chấm đúng/sai (xem docstring script).")
    lines.append("")
    for item in summaries:
        lines.append(f"## {item.get('case_id')} — {item.get('triage_level')} ({item.get('turns')} lượt)")
        lines.append("")
        lines.append(
            f"- độ phủ khi đóng: `{item.get('mandatory_coverage_at_close')}` | "
            f"user_led: `{item.get('user_led_ratio')}` | lặp: `{item.get('repeat_question_rate')}` | "
            f"quét sót: `{item.get('catch_all_asked')}`/`{item.get('catch_all_yielded')}`"
        )
        if item.get("mandatory_remaining"):
            lines.append(f"- field M0/M1 còn thiếu: `{', '.join(item['mandatory_remaining'])}`")
        lines.append("")
        for turn in item.get("transcript", []):
            who = "**BN**" if turn.get("role") == "user" else "AGENT"
            lines.append(f"- {who}: {turn.get('content')}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

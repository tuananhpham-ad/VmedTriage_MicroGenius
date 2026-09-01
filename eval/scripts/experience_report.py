"""Đọc thư mục log phiên -> bảng metric trải nghiệm + độ phủ của §8 (P4.3-P4.4).

Món nợ mà script này trả: §8 đặt ra một loạt ngưỡng (`user_led_ratio`, `repeat_question_rate`,
`deferral_depth`, `catch_all_yield`, `abandonment_rate`, `mandatory_coverage_at_close`) và
`symptom_protocol/metrics.py` đã TÍNH được tất cả cho từng phiên - nhưng **không có chỗ nào gộp
chúng lại thành một bảng đọc được**. Một ngưỡng không đọc ra được số thì không phải gate.

Không cần thêm hạ tầng: `fever_stage_log.finish()` đã ghi bản chụp §12 vào chính file meta của phiên
(`logs/<namespace>/<session_id>.json`, khoá `metrics`), nên dashboard chỉ là việc đọc thư mục đó.

    python -m eval.scripts.experience_report
    python -m eval.scripts.experience_report --logs logs/fever --json out.json

**Mọi tỉ lệ in ra đều KÈM MẪU SỐ.** §8 kết bằng đúng câu đó, và nó không phải lời khuyên trình bày:
"red-flag recall 100%" trên 20 ca và trên 300 ca là hai phát biểu khác hẳn nhau, mà bỏ mẫu số đi thì
chúng in ra giống hệt nhau.

Script này **chỉ ĐỌC**. Nó không gọi model, không sửa log, không quyết định gì - chạy được trên máy
không có API key, và đó là điều kiện để nó chạy được trong CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src import paths
from src.services.symptom_protocol import metrics as metrics_mod


def load_summaries(logs_dir: Path) -> list[dict]:
    """Bản chụp §12 của MỌI phiên tìm được dưới `logs_dir`, kể cả trong thư mục con.

    Bỏ qua file hỏng thay vì ném: một file JSON viết dở (tiến trình chết giữa chừng) không được làm
    hỏng báo cáo của 200 phiên còn lại. Số file bỏ qua được báo cáo - im lặng bỏ qua thì mẫu số sai
    mà không ai biết."""
    summaries: list[dict] = []
    skipped = 0
    for path in sorted(logs_dir.rglob("*.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped += 1
            continue
        if not isinstance(meta, dict):
            continue
        snapshot = meta.get("metrics")
        if isinstance(snapshot, dict):
            summaries.append(snapshot)
        elif meta.get("stop_reason") is not None:
            # Phiên đóng TRƯỚC khi `finish` học cách ghi `metrics` (hoặc đóng từ nhánh cấp cứu ở
            # `intake_agent`, nơi chưa có `Session` trong tay). Vẫn đếm được `turns`/`stop_reason` -
            # bỏ hẳn phiên đó sẽ làm `stop_reasons` thiếu đúng nhóm cấp cứu.
            summaries.append(
                {
                    "turns": meta.get("turns"),
                    "stop_reason": meta.get("stop_reason"),
                    "triage_level": meta.get("triage_level"),
                }
            )
    if skipped:
        print(f"[cảnh báo] bỏ qua {skipped} file log không đọc được", file=sys.stderr)
    return summaries


def load_narrative_sources(logs_dir: Path) -> dict[str, int]:
    """Đếm `narrative_source` từ các file step (`stage-*.jsonl`).

    Đây là chỉ số DUY NHẤT phải đọc file step thay vì file meta của phiên, và lý do nằm ở thứ tự:
    bản chụp metric được ghi lúc `_finish()`, còn văn xuôi thì sinh SAU đó khi dựng phiếu bàn giao -
    lúc biết nó fallback hay không thì file meta đã đóng. Xem `sessions/narrative._record`.

    Bỏ qua dòng hỏng thay vì ném: file `.jsonl` là append-only và tiến trình chết giữa chừng để lại
    một dòng viết dở - một dòng đó không được làm hỏng báo cáo của cả tập."""
    counts: dict[str, int] = {}
    for path in sorted(logs_dir.rglob("stage-*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            output = record.get("output")
            if isinstance(output, dict) and "narrative_source" in output:
                source = str(output["narrative_source"])
                counts[source] = counts.get(source, 0) + 1
    return counts


def narrative_report(counts: dict[str, int]) -> dict[str, object]:
    """`narrative_fallback_rate` + phân rã theo LÝ DO.

    Phân rã quan trọng hơn con số tổng: "provider chết" và "guard bắt bịa phủ định" đều là fallback,
    nhưng cái đầu là sự cố hạ tầng còn cái sau là **guard đang làm đúng việc của nó**. Gộp lại thành
    một tỉ lệ thì không phân biệt được "hệ thống hỏng" với "hệ thống vừa chặn một phiếu sai"."""
    total = sum(counts.values())
    ok = counts.get("llm", 0)
    return {
        "value": None if total == 0 else round((total - ok) / total, 4),
        "n": total,
        "by_reason": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }


def render(report: dict) -> str:
    """Bảng chữ. Chỉ số dạng `{value, n}` in kèm mẫu số ngay tại chỗ."""
    lines = ["=== Metric trải nghiệm + độ phủ (§8) ===", ""]
    for key, value in report.items():
        if isinstance(value, dict) and "value" in value:
            shown = "—" if value["value"] is None else f"{value['value']}"
            lines.append(f"{key:34} {shown:>10}   (n={value['n']})")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"    {name:30} {count}" for name, count in value.items())
        else:
            lines.append(f"{key:34} {value!s:>10}")
    lines += [
        "",
        "Đọc CÙNG NHAU, không tách: cải thiện trải nghiệm bằng cách hy sinh độ phủ là hỏng.",
        "`sessions_with_unasked_mandatory` phải bằng 0 — khác 0 nghĩa là có cụm mang field M0/M1 bị",
        "bỏ qua im lặng, tức bất biến §1 mục 8 đã vỡ và phải dừng lại chứ không phải tinh chỉnh tiếp.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bảng metric §8 đọc từ log phiên.")
    parser.add_argument("--logs", type=Path, default=paths.LOGS_DIR, help="Thư mục log phiên.")
    parser.add_argument("--json", type=Path, default=None, help="Ghi báo cáo ra file JSON.")
    args = parser.parse_args(argv)

    if not args.logs.exists():
        print(f"Không tìm thấy thư mục log: {args.logs}", file=sys.stderr)
        return 1

    summaries = load_summaries(args.logs)
    if not summaries:
        print(f"Không có phiên nào trong {args.logs}", file=sys.stderr)
        return 1

    report = metrics_mod.aggregate(summaries)
    report["narrative_fallback_rate"] = narrative_report(load_narrative_sources(args.logs))
    print(render(report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã ghi {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ghi lại CẤU HÌNH đã sinh ra một baseline: provider/model thật, settings, và hash của prompt.

Vì sao cần (§9 P0.5): một con số baseline không so sánh được nếu không biết nó được đo trên cấu
hình nào. Prompt đổi một câu là kết quả trích xuất đổi theo, mà diff prompt thì không nằm trong
`metrics.json` - hash là cách rẻ nhất để phát hiện "baseline này đo trên bản prompt khác".

KHÔNG ghi API key, kể cả dạng che: file này để commit được.

    python eval/scripts/record_baseline.py --out eval/baselines/2026-08-17.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import get_settings  # noqa: E402
from src.services.infra import provider_router  # noqa: E402
from src.services.symptom_protocol import intake_agent  # noqa: E402
from src.services.symptom_protocol.common_safety import text_safety_signals  # noqa: E402

# Prompt THẬT SỰ được gửi cho model ở luồng chuẩn. Thêm prompt mới thì thêm vào đây, nếu không
# baseline sẽ im lặng bỏ qua đúng thứ vừa đổi.
PROMPT_SOURCES: dict[str, str] = {
    "extraction_system": intake_agent._EXTRACTION_SYSTEM,
    "batch_negation_rule": intake_agent._BATCH_NEGATION_RULE,
    "screening_system": intake_agent._SCREENING_SYSTEM,
    "question_only_system": intake_agent._QUESTION_ONLY_SYSTEM,
}

# Cấu hình ảnh hưởng tới kết quả. Cố ý KHÔNG lấy cả `Settings`: trong đó có key, và một bãi field
# không liên quan (SMTP, JWT) sẽ làm diff giữa hai baseline đầy nhiễu.
SETTINGS_KEYS: tuple[str, ...] = (
    "app_env",
    "llm_provider",
    "llm_provider_order",
    "llm_temperature",
    "llm_max_total_attempts",
    "llm_total_budget_seconds",
    "openrouter_max_model_attempts",
    "deepseek_model_name",
    "gemini_model_name",
    "openai_model_name",
    "anthropic_model_name",
    "openrouter_model_name",
    "role_order_fact_extractor",
    "role_order_synthesis",
    "role_order_symptom_group_router",
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_record() -> dict[str, object]:
    settings = get_settings()
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "serving": {
            # Provider/model SẼ được dùng cho lượt gọi kế tiếp - cùng chuỗi mà console in lúc mở phiên.
            "describe_selection": provider_router.describe_selection(),
            "available_providers": provider_router.available_providers(),
        },
        "settings": {key: getattr(settings, key, None) for key in SETTINGS_KEYS},
        "prompt_hashes": {name: sha256(text) for name, text in sorted(PROMPT_SOURCES.items())},
        "safety_layer": {
            # Thay đổi danh mục luật hoặc danh sách được duyệt short-circuit là thay đổi hành vi an
            # toàn - phải thấy được trong diff baseline.
            "text_rule_count": len(text_safety_signals.TEXT_RED_FLAG_RULES),
            "short_circuit_code_count": len(text_safety_signals.SHORT_CIRCUIT_CODES),
            "short_circuit_codes_hash": sha256(",".join(sorted(text_safety_signals.SHORT_CIRCUIT_CODES))),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ghi lại cấu hình sinh ra một baseline eval.")
    parser.add_argument("--out", default=None, help="Đường dẫn file JSON. Bỏ trống = in ra stdout.")
    args = parser.parse_args()

    record = build_record()
    text = json.dumps(record, ensure_ascii=False, indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Đã ghi: {path}")
    print(text)


if __name__ == "__main__":
    main()

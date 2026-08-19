"""Nhánh red-flag thứ BA (model) và bước ĐỐI CHIẾU ba nhánh (§4.1 `_guidance/what_to_do_next.md`).

Repo đã có hai nhánh tất định và chúng chạy độc lập nhau:

| Nhánh | Nơi | Tính chất |
| --- | --- | --- |
| L0 — tín hiệu trên text thô | `common_safety/text_safety_signals.py` | KHÔNG model, chạy trước mọi lời gọi LLM |
| Rule engine trên state | `common_safety/rules.py` + `rule_engine.py` | KHÔNG model, chạy trên snapshot đã trích xuất |

Cái còn thiếu là **nhánh model** và **bước đối chiếu**. Module này là cả hai.

```text
mỗi lượt:
  L0 text signals   ──┐
  rule engine       ──┼──> escalate NGAY nếu BẤT KỲ nhánh nào dương tính đã duyệt
  model red-flag    ──┘    (OR, không phải AND, và không phải "chờ đối chiếu")

cuối phiên:
  red_flag_agreement -> phiếu bàn giao + log.  KHÔNG dòng code nào đọc nó để đổi quyết định.
```

**Bốn ràng buộc, và cả bốn đều là lý do module này trông "nhạt" hơn người ta tưởng:**

1. **Hợp nhất bằng OR.** Việc "đưa xuống cuối để so sánh" là để ĐO và để điều dưỡng đọc, không phải
   để hoãn cảnh báo (`CLAUDE.md` nguyên tắc 4). Hai bên bất đồng thì lấy bên **an toàn hơn** - không
   lấy bên "đúng hơn", vì lúc đó chưa ai biết bên nào đúng.
2. **Model không được TẮT một red flag mà rule đã bật.** Một nhánh mới chỉ được **thêm** phát hiện,
   không được **trừ**. `merge_findings` cố ý không có tham số nào cho phép trừ.
3. **Lỗi model không được làm mất nhánh nào.** Timeout/JSON hỏng ⇒ phiên chạy tiếp với hai nhánh cũ
   và ghi `model_branch_status="failed"`.
4. **`red_flag_agreement` là DỮ LIỆU, không phải quyết định.** Nó đi vào phiếu và vào metric; không
   có đường nào từ nó tới `proposed_priority`.

Giá trị đo được ngay: `model_only` chính là danh sách ứng viên để bổ sung vào rule, và
`agreement_rate` trả lời được câu "rule của chúng ta có bỏ sót gì không" - thứ mà baseline hiện tại
(emergency recall 48.9%) đang đặt ra mà chưa có cách trả lời.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.services.infra import provider_router
from src.services.infra.json_output import parse_json_object
from src.services.symptom_protocol.protocol import SymptomProtocol

logger = logging.getLogger("vmedtriage.red_flag_branches")

BRANCH_OK = "ok"
BRANCH_FAILED = "failed"
BRANCH_DISABLED = "disabled"

_MODEL_PROMPT = """Bạn là bộ sàng lọc dấu hiệu nguy hiểm (red flag) cho phân loại ưu tiên y tế.

Đọc tin nhắn của người bệnh và trả về CHÍNH XÁC JSON dạng:
{"red_flags": [{"code": "<mã>", "evidence": "<trích nguyên văn từ tin nhắn>"}]}

Chỉ được dùng mã trong DANH SÁCH MÃ HỢP LỆ bên dưới. Mã ngoài danh sách sẽ bị loại bỏ.
Mỗi mã phải kèm một đoạn TRÍCH NGUYÊN VĂN từ tin nhắn chứng minh cho nó.
KHÔNG suy diễn từ tiền sử, từ người khác, hay từ câu phủ định.
Không có dấu hiệu nào thì trả {"red_flags": []}.

DANH SÁCH MÃ HỢP LỆ:
"""


@dataclass(frozen=True, slots=True)
class ModelFinding:
    code: str
    evidence: str = ""


@dataclass(slots=True)
class RedFlagAgreement:
    """Bản đối chiếu ba nhánh. Thuần DỮ LIỆU - không có phương thức nào đổi quyết định."""

    rule_only: list[str] = field(default_factory=list)
    """Nhánh tất định bắt, model bỏ sót. Đọc như chất lượng của nhánh model."""
    model_only: list[str] = field(default_factory=list)
    """Model bắt, rule bỏ sót. **Đây là danh sách ứng viên để mở rộng rule** - output có giá trị
    nhất của cả cơ chế."""
    both: list[str] = field(default_factory=list)
    model_branch_status: str = BRANCH_DISABLED

    @property
    def agreement_rate(self) -> float:
        """Tỉ lệ đồng thuận. Không có phát hiện nào ở cả hai bên = 1.0 (đồng thuận rằng không có gì),
        chứ không phải 0.0 - ca lành tính là đa số, và trả 0.0 ở đó sẽ dìm chỉ số xuống mức vô nghĩa."""
        total = len(self.rule_only) + len(self.model_only) + len(self.both)
        return 1.0 if total == 0 else len(self.both) / total

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_only": sorted(self.rule_only),
            "model_only": sorted(self.model_only),
            "both": sorted(self.both),
            "agreement_rate": round(self.agreement_rate, 4),
            "model_branch_status": self.model_branch_status,
        }


def detect_with_model(
    protocol: SymptomProtocol,
    message: str,
    *,
    credential: provider_router.LLMCredential | None = None,
) -> tuple[tuple[ModelFinding, ...], str]:
    """Nhánh thứ ba: hỏi model xem tin nhắn có dấu hiệu nguy hiểm nào.

    Trả `(findings, status)`. **Không bao giờ ném** - lỗi ở nhánh này phải để hai nhánh tất định
    chạy tiếp nguyên vẹn (ràng buộc 3), nên mọi ngoại lệ đều quy về `BRANCH_FAILED`.

    Mã ngoài `protocol.reason_code_labels` bị LOẠI bằng code, không bằng lời dặn trong prompt: một
    mã bịa lọt vào `model_only` sẽ trông y hệt một phát hiện thật, và `model_only` chính là danh sách
    người ta sẽ dựa vào để mở rộng rule."""
    valid_codes = set(protocol.reason_code_labels)
    if not valid_codes or not (message or "").strip():
        return (), BRANCH_DISABLED

    catalogue = "\n".join(f"- {code}: {label}" for code, label in protocol.reason_code_labels.items())
    try:
        result = provider_router.complete(
            [
                {"role": "system", "content": _MODEL_PROMPT + catalogue},
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            credential=credential,
            role=provider_router.ROLE_FACT_EXTRACTOR,
        )
        parsed = parse_json_object(result.text)
    except Exception as error:
        logger.warning("model red-flag branch failed: %s", error)
        return (), BRANCH_FAILED

    if not isinstance(parsed, dict):
        return (), BRANCH_FAILED

    findings: list[ModelFinding] = []
    for item in parsed.get("red_flags") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code in valid_codes:
            findings.append(ModelFinding(code=code, evidence=str(item.get("evidence") or "")))
    return tuple(findings), BRANCH_OK


def merge_findings(
    deterministic_codes: tuple[str, ...] | list[str],
    model_findings: tuple[ModelFinding, ...],
    *,
    model_status: str,
) -> tuple[tuple[str, ...], RedFlagAgreement]:
    """Hợp nhất ba nhánh bằng **OR** và dựng bản đối chiếu.

    Trả `(codes_có_hiệu_lực, agreement)`. `codes_có_hiệu_lực` là hợp của hai bên - **luôn là siêu tập
    của `deterministic_codes`**. Đó là ràng buộc 2 viết thành code: hàm này không có đường nào để bỏ
    một mã tất định, kể cả khi model khẳng định ngược lại.

    THUẦN - không model, không I/O. Nhánh model đã chạy xong trước khi vào đây, nên phần quyết định
    hợp nhất vẫn test được bằng fake LLM (và bằng không LLM nào cả)."""
    rule_set = {code for code in deterministic_codes if code}
    model_set = {finding.code for finding in model_findings}
    agreement = RedFlagAgreement(
        rule_only=sorted(rule_set - model_set),
        model_only=sorted(model_set - rule_set),
        both=sorted(rule_set & model_set),
        model_branch_status=model_status,
    )
    # Thứ tự: mã tất định TRƯỚC, đúng thứ tự gốc, rồi mới tới mã chỉ model bắt. Phiếu đọc từ trên
    # xuống nên phần có bằng chứng vững nhất phải đứng đầu.
    ordered = [code for code in deterministic_codes if code]
    ordered.extend(code for code in agreement.model_only)
    return tuple(dict.fromkeys(ordered)), agreement


def parse_json_agreement(raw: object) -> RedFlagAgreement:
    """Đọc lại bản đối chiếu từ log/JSON - cho script eval, không cho luồng chạy thật."""
    data = raw if isinstance(raw, dict) else json.loads(str(raw))
    return RedFlagAgreement(
        rule_only=list(data.get("rule_only") or []),
        model_only=list(data.get("model_only") or []),
        both=list(data.get("both") or []),
        model_branch_status=str(data.get("model_branch_status") or BRANCH_DISABLED),
    )

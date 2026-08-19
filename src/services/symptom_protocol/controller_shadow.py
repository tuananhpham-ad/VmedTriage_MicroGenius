"""Controller bằng model — **bước 1: SHADOW MODE** (§4.11 mục 13b).

Shadow mode = model được hỏi, câu trả lời của nó được GHI LẠI và ĐỐI CHIẾU, và **không dòng nào của
nó tác động tới hành vi**. Rủi ro bằng 0 theo đúng nghĩa đen: gỡ file này đi thì hệ thống chạy y hệt.

Vì sao bước này đi trước, và đi trước cả việc quyết hạ tầng:

> Ba dữ kiện cần trước khi quyết "dựng GPU cho controller-4B hay dùng endpoint Qwen bên thứ ba":
> `skippable_turn_ratio`, hoá đơn Gemini thật, và ai vận hành GPU service sau khi sprint kết thúc.
> **Bước 1 không cần trả lời câu nào trong ba câu đó** — đó là lý do nó đi trước.

Cái nó sinh ra là `controller_agreement_rate`: tỉ lệ model chọn trùng với controller tất định. Đây là
**chỉ số quyết định có bật thật hay không** (§8, đề xuất ngưỡng ≥95% cho nhánh `clinical`).

## Nguyên tắc: tập hành động hợp lệ do CODE tính trước

Model **không** trả lời "làm gì tiếp theo" trên một không gian mở. Code tính trước tập hành động hợp
lệ cho đúng trạng thái hiện tại; model chỉ **chọn một phần tử trong tập đó**. Giao với tập hợp lệ
rỗng ⇒ rơi về controller tất định.

Điểm quan trọng của thiết kế: **đường fallback chính là hệ thống hiện tại.** Model chết thì hành vi
quay về đúng cái đang có test bám vào.

## Bốn thứ controller KHÔNG được quyết — kể cả ở bước 2-3

| Không được quyết | Vẫn ở đâu |
| --- | --- |
| Cụm câu hỏi lâm sàng tiếp theo | `ranking.py` + `stage_machine.select_cluster` |
| Dừng hay hỏi tiếp | `should_stop` — controller chỉ *báo* `user_intent.stop`, đi qua `user_can_continue` |
| Mức ưu tiên | `rule_engine` |
| Red flag | L0 + `common_safety/rules.py`, cả hai chạy độc lập với controller |

Và hai ràng buộc thi hành nằm ngay trong code dưới đây: **`next_action` không có giá trị `stop`**
(một model 4B không được là thứ kết thúc phiên khám), và **timeout cứng 300ms** - vượt là dùng
controller tất định, không chờ.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from src.services.infra import provider_router
from src.services.infra.json_output import parse_json_object

logger = logging.getLogger("vmedtriage.controller_shadow")

CONTROLLER_TIMEOUT_MS = 300
"""Trần CỨNG. Ngân sách một lượt hiện là p50 3.98s và phần lớn nằm ở `fact_extractor`; controller
không được phép trở thành một chặng chờ. Vượt trần ⇒ dùng controller tất định, KHÔNG chờ."""

LANE_CLINICAL = "clinical"
LANE_NON_CLINICAL = "non_clinical"
LANE_META = "meta"
LANES = (LANE_CLINICAL, LANE_NON_CLINICAL, LANE_META)

ACTION_EXTRACT = "extract"
ACTION_ROUTE_PROTOCOL = "route_protocol"
ACTION_ANSWER_META = "answer_meta"
ACTION_SUMMARIZE = "summarize"
ACTION_HANDOFF = "handoff"
ACTIONS = (ACTION_EXTRACT, ACTION_ROUTE_PROTOCOL, ACTION_ANSWER_META, ACTION_SUMMARIZE, ACTION_HANDOFF)
"""⚠️ **KHÔNG có `stop`.** Ý định dừng chỉ đi qua `user_intent.stop` -> `user_can_continue` ->
`should_stop` (§4.11 ràng buộc 2). Thêm `"stop"` vào tuple này là trao quyền kết thúc phiên khám cho
một model 4B, và không có review nào bắt được điều đó nếu nó chỉ là một chuỗi thêm vào danh sách."""

_SYSTEM_PROMPT = """Bạn là bộ điều phối của một hệ thống hỏi bệnh. Bạn KHÔNG hỏi bệnh, KHÔNG chẩn đoán, KHÔNG quyết định mức độ khẩn cấp.

Việc duy nhất: đọc tin nhắn + trạng thái phiên, rồi chọn ĐÚNG MỘT hành động trong TẬP HỢP LỆ được đưa cho bạn.

Trả về CHÍNH XÁC JSON:
{"lane": "clinical|non_clinical|meta", "next_action": "<một giá trị trong tập hợp lệ>", "protocol_hint": "<tên protocol hoặc null>", "user_intent": {"stop": false, "off_topic": false, "asks_meta": false}, "confidence": 0.0}

Chọn ngoài tập hợp lệ sẽ bị loại bỏ."""


@dataclass(frozen=True, slots=True)
class ControllerProposal:
    """ĐỀ XUẤT của model. Tên kiểu nói rõ nó là gì - không phải một quyết định."""

    lane: str = ""
    next_action: str = ""
    protocol_hint: str | None = None
    stop: bool = False
    off_topic: bool = False
    asks_meta: bool = False
    confidence: float = 0.0
    latency_ms: int = 0
    failed: bool = False
    """Timeout / JSON hỏng / lựa chọn ngoài tập hợp lệ - cả ba đều là `failed`, và cả ba đều dẫn tới
    cùng một chỗ: controller tất định."""


@dataclass(slots=True)
class ShadowStats:
    """Bộ đếm shadow mode. CHỈ đếm - không nhánh nào đọc nó để đổi hành vi."""

    turns: int = 0
    agreed: int = 0
    fallbacks: int = 0
    latencies_ms: list[int] = field(default_factory=list)
    disagreements: list[dict[str, str]] = field(default_factory=list)
    """Ca model chọn khác code. **Đây mới là output có giá trị** - `agreement_rate` nói CÓ vấn đề hay
    không, còn danh sách này nói vấn đề nằm ở đâu."""

    def record(self, proposal: ControllerProposal, *, deterministic_action: str) -> None:
        self.turns += 1
        if proposal.failed:
            self.fallbacks += 1
            return
        self.latencies_ms.append(proposal.latency_ms)
        if proposal.next_action == deterministic_action:
            self.agreed += 1
        else:
            self.disagreements.append(
                {"model": proposal.next_action, "code": deterministic_action, "lane": proposal.lane}
            )

    def as_dict(self) -> dict[str, object]:
        """Mọi tỉ lệ KÈM MẪU SỐ (§8 câu cuối)."""
        scored = self.turns - self.fallbacks
        return {
            "controller_agreement_rate": None if scored <= 0 else round(self.agreed / scored, 4),
            "n_scored": scored,
            "controller_fallback_rate": None if self.turns <= 0 else round(self.fallbacks / self.turns, 4),
            "n_turns": self.turns,
            "controller_p95_ms": _percentile(self.latencies_ms, 95),
            "over_budget": sum(1 for value in self.latencies_ms if value > CONTROLLER_TIMEOUT_MS),
            "disagreements": self.disagreements[:50],
        }


def admissible_actions(
    *, is_opening: bool, has_cluster: bool, has_protocol: bool, session_closed: bool,
) -> tuple[str, ...]:
    """Tập hành động hợp lệ cho ĐÚNG trạng thái này — do CODE tính, luôn chạy trước model.

    Đây là phần khiến "model chọn hành động" khác hẳn "model quyết định": model không bao giờ nhìn
    thấy một không gian mở, nên câu trả lời tệ nhất nó đưa ra được vẫn nằm trong tập code đã duyệt.
    Giao rỗng ⇒ fallback, không phải "thử hiểu ý model"."""
    if session_closed:
        return (ACTION_SUMMARIZE, ACTION_HANDOFF)
    if is_opening:
        return (ACTION_EXTRACT, ACTION_ROUTE_PROTOCOL, ACTION_ANSWER_META)
    if not has_protocol or not has_cluster:
        return (ACTION_HANDOFF,)
    return (ACTION_EXTRACT, ACTION_ROUTE_PROTOCOL, ACTION_ANSWER_META, ACTION_SUMMARIZE)


def propose(
    message: str,
    *,
    admissible: tuple[str, ...],
    state_digest: dict[str, object],
    credential: provider_router.LLMCredential | None = None,
) -> ControllerProposal:
    """Hỏi model một đề xuất. **Không bao giờ ném**, và không bao giờ đổi gì.

    `state_digest` là khối trạng thái nén đi kèm (§4.11 ràng buộc 4): protocol đang gắn, cụm hiện
    tại, `turn_count`, `mandatory_remaining`, có escalation chưa. Rẻ về token và là khác biệt giữa
    một dispatcher đoán mò với một dispatcher biết mình đang ở đâu.

    Timeout đo BẰNG ĐỒNG HỒ THẬT sau khi gọi, không phải bằng tham số timeout của provider: cái ta
    cần biết là "lượt này có vượt ngân sách 300ms không" để quyết bước 2-3, và một lời gọi bị provider
    tự cắt ở 300ms sẽ không bao giờ cho ta con số thật đó."""
    if not admissible:
        return ControllerProposal(failed=True)

    payload = {"message": message, "admissible_actions": list(admissible), "state": state_digest}
    started = time.monotonic()
    try:
        result = provider_router.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _as_json(payload)},
            ],
            temperature=0.0,
            credential=credential,
            role=provider_router.ROLE_SYMPTOM_GROUP_ROUTER,
        )
        parsed = parse_json_object(result.text)
    except Exception as error:
        logger.warning("controller shadow failed: %s", error)
        return ControllerProposal(failed=True, latency_ms=_elapsed_ms(started))

    latency = _elapsed_ms(started)
    if not isinstance(parsed, dict):
        return ControllerProposal(failed=True, latency_ms=latency)

    action = str(parsed.get("next_action") or "")
    lane = str(parsed.get("lane") or "")
    # GIAO với tập hợp lệ. Ngoài tập ⇒ `failed`, không phải "chọn cái gần nhất" - đoán ý model là
    # đúng thứ tập hợp lệ sinh ra để khỏi phải làm.
    if action not in admissible or lane not in LANES:
        return ControllerProposal(failed=True, latency_ms=latency)

    intent = parsed.get("user_intent") or {}
    return ControllerProposal(
        lane=lane,
        next_action=action,
        protocol_hint=(str(parsed["protocol_hint"]) if parsed.get("protocol_hint") else None),
        stop=bool(intent.get("stop")) if isinstance(intent, dict) else False,
        off_topic=bool(intent.get("off_topic")) if isinstance(intent, dict) else False,
        asks_meta=bool(intent.get("asks_meta")) if isinstance(intent, dict) else False,
        confidence=_as_float(parsed.get("confidence")),
        latency_ms=latency,
    )


def _as_json(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _percentile(values: list[int], percent: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(percent / 100 * (len(ordered) - 1))))
    return ordered[index]

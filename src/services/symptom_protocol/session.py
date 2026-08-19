"""Vòng đời phiên hỏi-đáp DÙNG CHUNG cho mọi symptom_group - in-memory store, không auth. Nối 3 tầng
cơ chế đã có thành 1 luồng phiên hoàn chỉnh:

- `stage_machine` quyết định cụm câu hỏi kế tiếp / stage / dừng - THUẦN rule.
- `rule_engine` là nguồn thật duy nhất cho `triage_level`/`reason_codes`/`triggered_rules`.
- `intake_agent.run_turn` gọi LLM đúng kiến trúc hướng C/E theo stage.

Vòng đời một phiên:

    COLLECTING ──(RED_FLAG ở gate stage)───────────────────> EMERGENCY
    COLLECTING ──(should_stop khác RED_FLAG, ở stage cuối)──> AWAITING_CONFIRMATION
        │                                                            │
        └────────────(người dùng xác nhận phiếu)────────────────────┴──> CONFIRMED

MỘT store phục vụ MỌI protocol (`registry.PROTOCOL_REGISTRY`). Trước đây mỗi bệnh một store riêng,
nhưng điều đó không sống được cùng lượt mở: lúc mở phiên chưa biết đây là ca gì, và `case_id` =
`session_id` phải tra được ở đúng một chỗ dù protocol nào đang chạy. Phiên vẫn không lẫn nhau vì
protocol nằm TRONG `Session.protocol_name`, không phải trong store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.infra import console_log, provider_router
from src.services.infra import fever_stage_log as stage_log
from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol import (
    controller,
    controller_shadow,
    coverage,
    dialogue,
    flags,
    non_clinical,
    red_flag_branches,
    registry,
    rule_engine,
    screening,
    stage_machine,
    user_intent,
)
from src.services.symptom_protocol import intake_agent as agent
from src.services.symptom_protocol import metrics as metrics_mod
from src.services.symptom_protocol.common_safety import text_safety_signals
from src.services.symptom_protocol.models import QuestionCluster, ScreeningGroup
from src.services.symptom_protocol.protocol import SymptomProtocol

logger = logging.getLogger("vmedtriage.symptom_session")


class SessionState(str, Enum):
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EMERGENCY = "emergency"


class SessionPhase(str, Enum):
    OPENING = "opening"
    """Người bệnh chưa được hỏi gì - tin nhắn đầu là lời kể tự do. NGOÀI `STAGE_ORDER` của mọi
    protocol (xem `registry.OPENING_PROTOCOL`)."""
    COLLECTING = "collecting"


@dataclass(slots=True)
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.COLLECTING
    phase: SessionPhase = SessionPhase.COLLECTING
    protocol_name: str = ""
    """Protocol đang chạy. Rỗng khi còn ở lượt mở (chưa chọn được). Mọi nơi cần protocol phải đi qua
    `ProtocolSessionStore._protocol(session)` chứ không đọc `store.protocol` - nếu không, phiên đã
    chuyển sang protocol khác vẫn bị chấm bằng luật của protocol cũ."""
    protocol_pinned: bool = False
    """Caller đã TUYÊN BỐ protocol khi mở phiên (endpoint chuyên biệt như `/api/v1/fever/*`) ⇒ hệ
    thống không được tự đổi sang protocol khác. Phiên mở từ ô chat tự do thì ngược lại: protocol do
    hệ thống chọn, nên hệ thống cũng được quyền chọn lại khi lời khai đổi."""
    stage: str = ""
    answers: dict[str, object] = field(default_factory=dict)
    completed_cluster_ids: set[str] = field(default_factory=set)
    """Cụm đã thu được câu trả lời. Trước đây là `asked_ids` và được `add()` VÔ ĐIỀU KIỆN mỗi lượt,
    nên gõ "." hay né tránh cũng tính là đã hỏi xong - cụm không bao giờ được hỏi lại (bug C3)."""
    unresolved_cluster_ids: set[str] = field(default_factory=set)
    """Cụm đã hỏi lại đủ số lần cho phép mà vẫn không thu được gì - bỏ qua để không treo hội thoại,
    nhưng ghi lại để phiếu bàn giao nói rõ đây là thông tin CHƯA HỎI ĐƯỢC, không phải "không có"."""
    retry_count_by_cluster: dict[str, int] = field(default_factory=dict)
    screened_cluster_ids: set[str] = field(default_factory=set)
    """Cụm được đóng bởi một verdict phủ định của lượt SÀNG LỌC GỘP, thay vì được hỏi riêng. Chúng
    cũng nằm trong `completed_cluster_ids` (đã hỏi thật - người bệnh đã nghe đọc danh sách dấu hiệu
    của chúng); tập này tồn tại riêng chỉ để trừ ra khỏi NGÂN SÁCH câu hỏi."""
    screening_history: dict[str, tuple[frozenset[str], ...]] = field(default_factory=dict)
    """Các TẬP NHÓM đã sàng lọc ở mỗi stage, theo thứ tự. Số phần tử là số vòng đã dùng (chống lặp vô
    hạn, `SymptomProtocol.max_screening_rounds`); phần tử cuối cho `next_probe` biết vòng sau có thật
    sự hỏi ÍT HƠN vòng trước không - nếu không thì đó là đọc lại nguyên văn cùng một danh sách dài."""
    pending_probe: tuple[ScreeningGroup, ...] = ()
    """Nhóm mà câu hỏi VỪA PHÁT RA đang sàng lọc. Đây cũng là guard turn-scoping của cả cơ chế: chỉ
    khi tập này khác rỗng thì verdict theo nhóm mới được đọc, nên một câu "không" trần không bao giờ
    đóng được nhóm nào ngoài đúng danh sách vừa đọc lên cho người bệnh."""
    current_cluster: QuestionCluster | None = None
    conversation: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0
    last_question: str = ""
    llm_used_last_turn: bool = False
    triage_level: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    triggered_rules: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    escalation_lock: bool = False
    """Rule engine đã chốt cấp cứu. Khoá QUYẾT ĐỊNH, không khoá DỮ KIỆN: người bệnh vẫn sửa được lời
    khai và bản sửa vẫn vào phiếu bàn giao, nhưng hệ thống không tự hạ mức - việc đó thuộc về điều
    dưỡng (P0-6)."""
    pending_safety_signals: tuple[str, ...] = ()
    """Mã tín hiệu L0 ở mức `needs_confirmation` của lượt VỪA RỒI (`text_safety_signals`). Không phải
    `reason_codes`: đây là dấu hiệu người bệnh có nhắc tới nhưng guard chưa cho phép kết luận. Tồn tại
    để cụm xác nhận red flag được ưu tiên và để log trả lời được "vì sao câu này không escalate"."""
    confirmed_retractions: set[str] = field(default_factory=set)
    """Field đã được hỏi xác nhận trước khi xoá dây chuyền (§5 quy tắc 5). Cùng lý do một-lần với
    `asked_safety_signal_codes`: hỏi mãi một câu là cách chắc chắn nhất để người bệnh bỏ giữa chừng,
    và lời đính chính thì vẫn không bao giờ vào được hồ sơ."""
    asked_safety_signal_codes: set[str] = field(default_factory=set)
    """Mã đã được hỏi xác nhận bằng câu TĨNH. Mỗi mã chỉ hỏi một lần - nếu không, một phiên gặp lúc
    model chết sẽ lặp mãi cùng một câu xác nhận."""
    metrics: metrics_mod.ConversationMetrics = field(default_factory=metrics_mod.ConversationMetrics)
    """Bộ đếm trải nghiệm + độ phủ (§12). CHỈ đếm - không nhánh nào được đọc nó để đổi hành vi, vì
    một chỉ số vừa đo vừa điều khiển thì không còn đo được cái gì (§8.8)."""
    ledger: coverage.CoverageLedger = field(default_factory=coverage.CoverageLedger)
    """Sổ sách độ phủ (§8.5). Xếp hạng cụm được phép HOÃN một cụm để đi theo mạch người bệnh; sổ này
    là thứ bảo đảm cụm bị hoãn vẫn được hỏi lại chứ không biến mất."""
    red_flag_agreement: red_flag_branches.RedFlagAgreement = field(
        default_factory=red_flag_branches.RedFlagAgreement,
    )
    """Bản đối chiếu ba nhánh red-flag (§4.1). **DỮ LIỆU, không phải quyết định** - nó đi vào phiếu
    và vào metric, không có dòng code nào đọc nó để đổi mức ưu tiên."""
    uncooperative: user_intent.UncooperativeTracker = field(
        default_factory=user_intent.UncooperativeTracker,
    )
    """Bộ đếm bất hợp tác (§4.7b). Đếm ở đây chứ không trong `metrics` vì nó ĐIỀU KHIỂN hành vi
    (hỏi lại một lần rồi dừng), mà `metrics` cố ý chỉ đo - một chỉ số vừa đo vừa điều khiển thì
    không còn đo được cái gì (§8.8)."""
    catch_all_asked: bool = False
    """Đã chạy bước QUÉT SÓT (§8.6 mục 4) chưa - một câu mở cuối trước khi chốt.

    Đây là chỗ bắt được triệu chứng mà checklist không hỏi tới, và là câu rẻ nhất trong cả phiên xét
    theo giá trị lâm sàng thu được. Vì thế nó KHÔNG bị bỏ khi hết ngân sách: ngân sách cắt cụm tier
    O/H, không cắt câu này."""
    awaiting_catch_all: bool = False
    """Câu quét sót vừa được phát ra và đang chờ trả lời - lượt tới trích theo schema quét sót."""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    credential: LLMCredential | None = None
    user_id: int = 0
    """Chủ phiên - nửa còn lại của khoá composite `user_id + conversation_id` (§4.9 M1). `0` = khách
    chưa đăng nhập. `session_id` chính là `conversation_id`, và nó vốn đã là UUID4 chứ không phải
    timestamp - hai phiên mở cùng một giây không đụng nhau."""

    @property
    def closed_cluster_ids(self) -> set[str]:
        """Cụm không được chọn lại nữa, dạng khoá `"<protocol>:<cluster_id>"`."""
        return self.completed_cluster_ids | self.unresolved_cluster_ids

    def cluster_key(self, cluster_id: str) -> str:
        """Trạng thái cụm lưu kèm TÊN PROTOCOL. Mã cụm dùng chung giữa các protocol (`Q3-03` là cụm
        co giật ở cả fever lẫn generic - cùng một định nghĩa trong `common_safety`), nên nếu chỉ lưu
        mã thì một phiên đổi protocol giữa chừng sẽ coi các cụm của protocol mới là "đã hỏi rồi" và
        bỏ qua sạch."""
        return f"{self.protocol_name}:{cluster_id}"

    def closed_ids_for_current_protocol(self) -> frozenset[str]:
        """Mã cụm đã đóng CỦA protocol đang chạy - dạng `stage_machine` hiểu được."""
        return self._ids_for_current_protocol(self.closed_cluster_ids)

    def screened_ids_for_current_protocol(self) -> frozenset[str]:
        return self._ids_for_current_protocol(self.screened_cluster_ids)

    def unresolved_ids_for_current_protocol(self) -> frozenset[str]:
        """Cụm ĐÃ hỏi mà người bệnh không trả lời được - `asked_but_unanswered` của sổ độ phủ.

        Khác `mandatory_remaining`: "không biết" là một kết quả hợp lệ, không phải nợ (§8.5 quy tắc
        3). Tách hai khái niệm ở đây để không ai hỏi lại lần thứ ba câu vừa được trả lời "không biết"."""
        return self._ids_for_current_protocol(self.unresolved_cluster_ids)

    def _ids_for_current_protocol(self, keys: set[str]) -> frozenset[str]:
        prefix = f"{self.protocol_name}:"
        return frozenset(key[len(prefix):] for key in keys if key.startswith(prefix))


CATCH_ALL_QUESTION = (
    "Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? "
    "Nếu không còn gì, bạn cứ trả lời \"không\" là được."
)
"""Câu QUÉT SÓT tĩnh (§8.6 mục 4). Không qua LLM: nó phải giữ nguyên tính chất "câu mở, không
presupposition" - một bản diễn đạt lại có thể vô tình gợi ý sẵn triệu chứng, và như vậy thì nó không
còn bắt được thứ checklist chưa hỏi tới nữa."""

def _merged_agreement(
    previous: red_flag_branches.RedFlagAgreement, current: red_flag_branches.RedFlagAgreement,
) -> red_flag_branches.RedFlagAgreement:
    """Gộp bản đối chiếu của một lượt vào bản tích luỹ của cả phiên.

    `both` THẮNG: một mã từng được cả hai nhánh bắt thì nó không được rơi lại về `rule_only` chỉ vì
    lượt sau model không nhắc tới nó nữa. Không có quy tắc này thì `agreement_rate` của cả phiên bị
    quyết bởi đúng lượt cuối cùng - tức là đo lượt cuối chứ không đo phiên.

    **Đồng thuận LỆCH LƯỢT cũng là đồng thuận.** Bản đầu chỉ trừ đi tập `both` của từng lượt, nên một
    mã mà model bắt ở lượt 1 còn rule bắt ở lượt 3 sẽ nằm trong CẢ `rule_only` lẫn `model_only` - đọc
    ra là "rule bỏ sót nó" và "model bỏ sót nó" cùng lúc, một phát biểu tự mâu thuẫn. Đo được ngay
    lần chạy eval đầu tiên (2026-08-19, `RF-12`). Ở mức PHIÊN, câu hỏi đúng là "cả phiên này, nhánh
    nào đã từng thấy mã đó" - nên hai tập phải giao nhau TRƯỚC khi trừ."""
    both = set(previous.both) | set(current.both)
    rule_seen = set(previous.rule_only) | set(current.rule_only) | both
    model_seen = set(previous.model_only) | set(current.model_only) | both
    both = rule_seen & model_seen
    rule_only = rule_seen - both
    model_only = model_seen - both
    # Trạng thái XẤU NHẤT thắng: một lượt lỗi là đủ để mọi con số của phiên phải đọc kèm cảnh báo.
    status = (
        red_flag_branches.BRANCH_FAILED
        if red_flag_branches.BRANCH_FAILED in (previous.model_branch_status, current.model_branch_status)
        else current.model_branch_status
    )
    return red_flag_branches.RedFlagAgreement(
        rule_only=sorted(rule_only), model_only=sorted(model_only), both=sorted(both),
        model_branch_status=status,
    )


SHADOW_STATS = controller_shadow.ShadowStats()
"""Bộ đếm shadow mode của cả tiến trình (§4.11 bước 1).

Toàn cục chứ không theo phiên vì câu hỏi cần trả lời là "trên TẤT CẢ lượt đã chạy, model trùng với
code bao nhiêu phần trăm" - đó là con số quyết định bật bước 2-3. Chỉ ĐẾM: không nhánh nào đọc nó."""

CATCH_ALL_CLUSTER_ID = "CATCH-ALL"

_NO_CATCH_ALL_REASONS = frozenset(
    {"RED_FLAG", "USER_CANNOT_CONTINUE", "USER_UNCOOPERATIVE", "NO_MORE_SYMPTOMS"}
)
"""Lý do dừng mà bước QUÉT SÓT phải bị bỏ qua - xem `_ask_catch_all`."""


def _catch_all_cluster(protocol: SymptomProtocol, stage: str) -> QuestionCluster:
    """Cụm TỔNG HỢP dựng tại chỗ để đọc câu trả lời quét sót.

    Không khai vào `protocol.clusters`: nó không phải một bước của bảng câu hỏi lâm sàng, và thêm vào
    đó sẽ khiến `stage_machine` coi nó như một cụm bình thường (đếm ngân sách, xếp hạng, hỏi lại).

    Schema là các field an toàn hay được nói tự nguyện (`safety_signal_fields`) cộng field than phiền
    chính - đúng những gì một câu trả lời mở có thể chứa. Không đưa cả registry vào: schema càng rộng
    model càng có xu hướng điền bừa cho đủ."""
    keys = tuple(
        key for key in (*protocol.safety_signal_fields, protocol.chief_complaint_field)
        if key and key in protocol.fields_by_key
    )
    return QuestionCluster(CATCH_ALL_CLUSTER_ID, stage, keys, script_hint=CATCH_ALL_QUESTION)


_EMPTY_EXTRACTED_VALUES = frozenset({"", "unknown", "none", "null"})


def _extracted_anything(extracted: dict[str, object]) -> bool:
    """Lượt này có thu được dữ kiện XÁC ĐỊNH nào không.

    KHÔNG dùng `bool(extracted)`: kết quả trích xuất luôn trả về đủ mọi field của cụm, field không
    trích được mang giá trị `"unknown"` - nên dict khác rỗng kể cả khi model trả JSON trống. Đó đúng
    là trường hợp tầng L0 cần nhận ra."""
    return any(str(value).strip().casefold() not in _EMPTY_EXTRACTED_VALUES for value in extracted.values())


class SessionNotFoundError(ValueError):
    pass


class EmptyMessageError(ValueError):
    pass


class ProtocolSessionStore:
    """Store + toàn bộ vòng đời phiên, phục vụ MỌI protocol trong `registry.PROTOCOL_REGISTRY`.

    `default_protocol` quyết định cách mở phiên khi caller không nói rõ protocol:

    - `None` (dùng cho ô chat tự do): phiên bắt đầu ở **lượt mở** - người bệnh kể tự do, protocol
      được chọn SAU khi trích xuất được lời kể đó.
    - một protocol cụ thể (dùng cho endpoint chuyên biệt như `/api/v1/fever/*`): phiên vào thẳng
      protocol đó, không có lượt mở - caller đã tuyên bố đây là ca gì."""

    def __init__(
        self, default_protocol: SymptomProtocol | None = None, *, persist: object | None = None,
    ) -> None:
        self.protocol = default_protocol
        self._sessions: dict[str, Session] = {}
        self._persist = persist
        """Kho bền (§4.9 M1). `None` = chỉ in-memory, đúng hành vi cũ.

        Tiêm vào chứ không import thẳng `conversation_store`: hàng trăm test dựng store này mà không
        có DB, và một import cứng sẽ bắt tất cả phải dựng SQLite chỉ để kiểm một hàm thuần. Đây cũng
        là chỗ tách "vòng đời phiên" khỏi "nơi phiên được lưu"."""

    def _protocol(self, session: Session) -> SymptomProtocol:
        """Protocol THẬT SỰ đang chạy cho phiên này. Mọi đường trong store phải đi qua đây - đọc
        `self.protocol` sẽ chấm phiên bằng luật của protocol mặc định thay vì protocol đã chọn."""
        return registry.protocol_for(session.protocol_name)

    def create(self, credential: LLMCredential | None = None) -> Session:
        session = Session(credential=credential)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str, *, user_id: int = 0) -> Session | None:
        """Bộ nhớ trước, kho bền sau. Đây là toàn bộ phần "sống qua restart" của M1: tiến trình mới
        không có gì trong `_sessions`, nên lượt kế tiếp của một phiên đang dở sẽ tìm thấy nó ở DB
        thay vì rơi vào nhánh "phiên đã mất, mở phiên mới".

        `user_id` là **nửa còn lại của khoá** (§4.9 M1) và phải được truyền đúng, nếu không phiên của
        người đã đăng nhập sẽ không khôi phục được - nó nằm dưới khoá `(conversation_id, user_id)`
        chứ không phải `(conversation_id, 0)`. Mặc định `0` là phiên khách, đúng với endpoint demo
        không có tài khoản.

        Đây cũng chính là chỗ bảo đảm "không đọc chéo hồ sơ người khác": sai `user_id` thì không đọc
        được gì, và điều đó do hình dạng khoá quyết định chứ không do một câu `if` ai đó có thể quên."""
        session = self._sessions.get(session_id)
        if session is not None or self._persist is None:
            return session
        restored = self._persist.get(session_id, user_id=user_id)
        if restored is not None:
            restored.user_id = user_id
            self._sessions[session_id] = restored
        return restored

    def _remember(self, session: Session) -> None:
        """Ghi lại phiên sau MỘT lượt đã được nhận. Không bao giờ ném - `conversation_store.save` đã
        nuốt lỗi, và mất một lần persist không được làm hỏng lượt người bệnh đang trả lời."""
        if self._persist is not None:
            self._persist.save(session, user_id=session.user_id)

    def _require(self, session_id: str) -> Session:
        session = self.get(session_id)
        if session is None:
            raise SessionNotFoundError("Không tìm thấy phiên hỏi-đáp.")
        return session

    def start_session(
        self, credential: LLMCredential | None = None, *, protocol_name: str | None = None,
    ) -> Session:
        pinned = protocol_name or (self.protocol.name if self.protocol is not None else None)
        if pinned is None:
            return self._start_open_session(credential)

        protocol = registry.protocol_for(pinned)
        session = self.create(credential or protocol.default_credential)
        session.protocol_name = protocol.name
        session.protocol_pinned = True
        session.phase = SessionPhase.COLLECTING
        first_stage = protocol.stage_order[0]
        session.stage = first_stage
        stage_log.start(session.session_id, route=None, budget=0, namespace=protocol.name)
        stage_log.stage_enter(session.session_id, first_stage)

        # `advance` chứ không phải `next_cluster`: stage đầu có thể không có cụm nào cần hỏi (protocol
        # generic, hoặc mọi cụm của stage 0 đều bị skip) - lúc đó vẫn phải đi tiếp chứ không mở phiên
        # với câu hỏi rỗng.
        step = stage_machine.advance(protocol, first_stage, {})
        cluster = step.cluster
        session.stage = step.stage
        # Stage đầu của fever là nhân khẩu nên không lượt sàng lọc nào phát ra ở đây - nhưng quyết
        # định đó thuộc về `next_probe`, không phải một giả định ngầm của store: một protocol khai
        # nhóm sàng lọc ngay ở stage đầu sẽ đi đúng nhánh này mà không phải sửa gì.
        session.pending_probe = screening.next_probe(protocol, step.stage, {}, cluster)
        if session.pending_probe:
            cluster = screening.probe_cluster(protocol, step.stage, session.pending_probe)
            session.screening_history[step.stage] = (frozenset(g.id for g in session.pending_probe),)
        # Câu MỞ PHIÊN cố ý KHÔNG gộp (`batching.next_batch` không được gọi ở đây). Đã thử và bỏ:
        # câu này là câu DUY NHẤT không đi qua bước LLM diễn đạt lại - nó dùng thẳng `script_hint` -
        # nên gộp ở đây khiến người bệnh đọc được nguyên văn "Mình hỏi nhanh vài ý: (1)...; (2)...".
        # Đó đúng là cảm giác biểu mẫu mà việc gộp sinh ra để xoá. Từ lượt thứ hai trở đi `run_turn`
        # có LLM viết lại thành câu liền mạch nên gộp mới có lãi.
        session.current_cluster = cluster
        session.last_question = cluster.script_hint if cluster is not None else ""
        if session.last_question:
            session.conversation.append({"role": "assistant", "content": session.last_question})

        provider = provider_router.describe_selection(session.credential)
        console_log.session_start(session.session_id, label=f"{protocol.name} intake", llm=provider)
        console_log.agent_question(session.session_id, session.last_question, llm_used=False)
        return session

    def _start_open_session(self, credential: LLMCredential | None) -> Session:
        """Phiên bắt đầu bằng lượt mở: chưa có protocol, chưa có stage, chưa có cụm nào."""
        session = self.create(credential)
        session.phase = SessionPhase.OPENING
        session.stage = ""
        session.current_cluster = None
        session.last_question = registry.OPENING_QUESTION
        session.conversation.append({"role": "assistant", "content": session.last_question})
        stage_log.start(session.session_id, route=None, budget=0, namespace=registry.DEFAULT_PROTOCOL_NAME)

        provider = provider_router.describe_selection(session.credential)
        console_log.session_start(session.session_id, label="symptom intake", llm=provider)
        console_log.agent_question(session.session_id, session.last_question, llm_used=False)
        return session

    def submit_message(
        self, session_id: str, message: str, *, on_token: agent.TokenSink | None = None,
    ) -> Session:
        """`on_token` != None: phát từng mẩu CÂU HỎI ra ngoài ngay khi model sinh (endpoint SSE).

        Không đổi gì khác trong vòng đời phiên - cùng một lượt, cùng một kết quả, chỉ khác ở chỗ văn
        bản hiển thị được đẩy dần thay vì đợi trọn. Trích xuất field vẫn chạy trước và vẫn không
        stream: nó trả JSON."""
        session = self._require(session_id)
        if session.state != SessionState.COLLECTING:
            return session
        cleaned = (message or "").strip()
        if not cleaned:
            raise EmptyMessageError("Nội dung tin nhắn không được để trống.")

        # L0 `text_safety_signals` - TRƯỚC mọi lời gọi model, cho cả lượt mở lẫn lượt thường. Đây là
        # lớp duy nhất còn quan sát được lời người bệnh khi provider chết hoặc JSON trả về hỏng.
        scan = text_safety_signals.scan_text_safety_signals(cleaned)
        if scan.short_circuit:
            return self._escalate_from_text_signal(session, cleaned, scan)
        session.pending_safety_signals = tuple(signal.code for signal in scan.needs_confirmation)

        # L0.5 ý định người bệnh - THUẦN code, chạy SAU tín hiệu an toàn và TRƯỚC mọi lời gọi model.
        # Sau, vì `scan.short_circuit` đã thoát ở trên: một tin nhắn vừa mang dấu hiệu cấp cứu vừa
        # nói "thôi khỏi" phải escalate, không được đọc thành ý định dừng (§1 bất biến 3).
        intent = user_intent.classify(cleaned)
        # Lane phi lâm sàng (§4.10) - SAU L0, nên nó không có cơ hội nuốt một tín hiệu đỏ. Chỉ nhận
        # lượt CHƯA có cụm nào đang chờ trả lời: giữa chừng bộ câu hỏi, một câu "cảm ơn nhé" là lời
        # cảm ơn KÈM câu trả lời, không phải một lượt tán gẫu - cắt nó ra khỏi luồng lâm sàng sẽ làm
        # mất chính dữ kiện người bệnh vừa nói.
        lane = (
            non_clinical.classify(cleaned)
            if session.current_cluster is None or session.phase is SessionPhase.OPENING
            else non_clinical.NonClinicalVerdict()
        )
        if lane.is_non_clinical:
            return self._answer_non_clinical(session, cleaned, lane)
        self._run_model_red_flag_branch(session, cleaned)

        is_opening = session.phase is SessionPhase.OPENING
        protocol = self._protocol(session)
        # Cụm sẽ được dùng cho lượt này, tính TRƯỚC khi lập kế hoạch: controller cần biết phiên có
        # thật sự đang hỏi cái gì không thì mới quyết được là fail closed hay chạy tiếp.
        cluster = session.current_cluster
        if session.awaiting_catch_all:
            # Trả lời câu quét sót: vẫn là một lượt hỏi-đáp đầy đủ (trích xuất → rule engine → chốt),
            # chỉ khác ở chỗ cụm đang hỏi là cụm TỔNG HỢP dựng tại chỗ chứ không nằm trong protocol.
            cluster = _catch_all_cluster(protocol, session.stage)

        # L1 controller - chỗ DUY NHẤT quyết lượt này có gọi model hay không (§9 P2 tiêu chí 1 và 3).
        plan = controller.build_execution_plan(
            message=cleaned,
            cluster=cluster,
            protocol_name=session.protocol_name,
            is_opening=is_opening,
            has_safety_signal=bool(session.pending_safety_signals),
        )
        self._shadow_controller(session, cleaned, plan, is_opening=is_opening)
        if plan.fail_closed:
            return self._hand_off(session, cleaned, plan.fail_closed_reason)
        if not plan.invoke_extractor:
            return self._answer_without_extraction(session, cleaned, plan, on_token=on_token)

        if is_opening:
            return self._submit_open_message(session, cleaned, on_token=on_token)

        answering_catch_all = session.awaiting_catch_all
        session.awaiting_catch_all = False

        session.turn_count += 1
        stage = session.stage
        console_log.user_message(session.session_id, cleaned, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": cleaned})

        result = agent.run_turn(
            # Phiên không ghim thì schema trích xuất được nới thêm vài field NHẬN DIỆN protocol khác:
            # không có chúng, một phiên đang chạy `general` không có chỗ nào để ghi câu "bé sốt 39 độ"
            # nên không bao giờ chuyển lại được sang protocol sốt.
            protocol if session.protocol_pinned else registry.with_switch_detection(protocol),
            session_id,
            turn=session.turn_count,
            stage=stage,
            cluster=cluster,
            message=cleaned,
            answers=session.answers,
            protocol_name=session.protocol_name,
            asked_ids=session.closed_ids_for_current_protocol(),
            retry_count=session.retry_count_by_cluster.get(session.cluster_key(cluster.id), 0),
            conversation=list(session.conversation),
            credential=session.credential,
            on_token=on_token,
            # Phiên đã ghim protocol thì KHÔNG truyền hàm chọn - caller tuyên bố đây là ca gì, hệ
            # thống không được tự chuyển hướng khỏi tuyên bố đó. (Người bệnh rút lời khai vẫn được
            # xử lý đúng trong protocol hiện tại: `skip_rule` bỏ qua nhánh không còn phù hợp.)
            select_protocol=None if session.protocol_pinned else registry.select_protocol,
            protocol_for=None if session.protocol_pinned else registry.protocol_for,
            probe=session.pending_probe,
            screened_ids=session.screened_ids_for_current_protocol(),
            screening_history=session.screening_history,
            ledger=session.ledger,
            confirmed_retractions=frozenset(session.confirmed_retractions),
            # Ý định CHỈ đi vào đường dừng. `uncooperative` không có ở đây mà được quyết SAU lượt:
            # nó phụ thuộc vào việc lượt này có thu được field mới không, mà điều đó chỉ biết được
            # sau khi trích xuất xong.
            stop_signals=stage_machine.StopSignals(
                user_can_continue=not intent.wants_to_stop,
                no_more_symptoms=intent.no_more_symptoms,
            ),
        )

        session.answers = result.answers
        # §4.7b - ba tín hiệu, và `information_gain` lấy từ kết quả trích xuất THẬT chứ không từ nhãn
        # `dialogue_act` của model: một lượt có thu được field lâm sàng thì dù model gán nhãn gì cũng
        # không phải bất hợp tác.
        information_gain = _extracted_anything(result.extracted)
        session.uncooperative.record_turn(
            off_topic=result.dialogue_act == dialogue.DialogueAct.OFF_TOPIC.value,
            information_gain=information_gain,
        )
        if answering_catch_all:
            # `catch_all_yield` (§12): bước quét sót có bắt được thứ checklist không hỏi tới không.
            # Gần 0 trên toàn tập nghĩa là HOẶC checklist đã đủ, HOẶC câu quét sót đang hỏi sai cách -
            # hai kết luận rất khác nhau, nên con số này chỉ đọc được kèm `catch_all_asked`.
            session.metrics.record_catch_all_answer(yielded=_extracted_anything(result.extracted))
        # Ghi nhận kết quả cụm TRƯỚC khi đổi `protocol_name`: cụm vừa hỏi thuộc protocol CŨ, ghi nó
        # dưới tên protocol mới sẽ làm cụm cùng mã của protocol mới bị coi là đã hỏi rồi.
        self._record_cluster_outcome(session, cluster, result)
        if result.protocol_name and result.protocol_name != session.protocol_name:
            console_log.session_start(
                session.session_id, label=f"đổi protocol -> {result.protocol_name}", llm="rule",
            )
            session.protocol_name = result.protocol_name
            # Nợ hoãn của protocol cũ KHÔNG chuyển sang protocol mới: mã cụm dùng chung giữa các
            # protocol nên giữ lại sẽ gán nợ nhầm cụm (cùng lý do `cluster_key` phải kèm protocol).
            session.ledger.reset()
        session.llm_used_last_turn = result.llm_used
        # Tín hiệu L0 mơ hồ + lượt này KHÔNG trích được gì (model hỏng, timeout, JSON không parse
        # được) = đúng kịch bản tầng L0 sinh ra để chặn: người bệnh vừa nhắc tới một dấu hiệu nguy
        # hiểm và hệ thống sắp đi tiếp như chưa nghe thấy. Hỏi lại bằng câu TĨNH, giữ nguyên cụm.
        safety_hold = (
            "" if result.emergency else self._safety_confirmation(session, _extracted_anything(result.extracted))
        )
        # Tín hiệu an toàn đứng TRƯỚC xác nhận đính chính: hai câu tĩnh không được phát cùng lượt, và
        # giữa "có thể có dấu hiệu nguy hiểm" với "có phải bạn muốn rút lại lời khai" thì thứ tự ưu
        # tiên không có gì phải cân nhắc.
        retraction_hold = "" if (result.emergency or safety_hold) else self._retraction_confirmation(session, result)
        # Câu hỏi bất hợp tác đứng CUỐI hàng ưu tiên: nó chỉ hỏi "bạn có muốn dừng không", còn hai
        # câu trên là dấu hiệu nguy hiểm và lời đính chính - cả hai đều phải được làm rõ trước.
        uncooperative_hold = (
            user_intent.UNCOOPERATIVE_PROMPT
            if not (result.emergency or safety_hold or retraction_hold)
            and session.uncooperative.should_prompt
            else ""
        )
        if uncooperative_hold:
            session.uncooperative.prompted = True
        hold = safety_hold or retraction_hold or uncooperative_hold
        agent_message = hold or result.agent_message
        if agent_message:
            session.conversation.append({"role": "assistant", "content": agent_message})
        closed = len(session.closed_cluster_ids)
        console_log.extraction(
            session.session_id, result.extracted,
            percent=round(100 * closed / max(closed + 1, 1)),
            filled=closed, total=closed + 1,
        )

        if result.emergency:
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)
            session.escalation_lock = True
            session.state = SessionState.EMERGENCY
            session.current_cluster = None
            session.pending_probe = ()
            session.last_question = result.agent_message
            session.stop_reason = "RED_FLAG"
            stage_log.finish(session_id, triage_level=result.triage_level, stop_reason="RED_FLAG", turns=session.turn_count)
            console_log.red_flag(session.session_id, list(result.reason_codes))
            console_log.session_end(session.session_id, state="emergency", turns=session.turn_count, percent=100)
            self._remember(session)
            return session

        # Cập nhật kết luận triage MỚI NHẤT do rule engine tính ở lượt này (kể cả khi chưa EMERGENCY)
        # - cần thiết để should_stop chọn đúng hàng ngân sách (vd EARLY_VISIT khác SELF_CARE_CANDIDATE)
        # ngay khi đã biết, không phải đợi tới lúc finish.
        if result.triage_level is not None:
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)

        session.last_question = agent_message
        if hold:
            # KHÔNG `_progress`: giữ nguyên cụm hiện tại để lượt sau vẫn trích theo đúng schema đó.
            self._remember(session)
            return session
        if session.uncooperative.should_stop:
            # Đã hỏi một lần "bạn có muốn dừng không" và người bệnh vẫn không hợp tác thêm một lượt
            # nữa. Đứng SAU nhánh cấp cứu (đã `return` ở trên) và sau `hold`, nên nó không bao giờ
            # nuốt mất một tín hiệu đỏ hay một lời đính chính đang chờ xác nhận.
            self._finish(session, "USER_UNCOOPERATIVE")
            self._remember(session)
            return session
        self._progress(session, result)
        self._remember(session)
        return session

    def _submit_open_message(
        self, session: Session, message: str, *, on_token: agent.TokenSink | None = None,
    ) -> Session:
        """Lượt mở: lời kể tự do của người bệnh, và là lượt CHỌN protocol.

        Không dùng `_record_cluster_outcome`: chưa có cụm nào được hỏi nên không có cụm nào để đánh
        dấu xong. Đây cũng là lý do lượt mở nằm ngoài `STAGE_ORDER` chứ không phải một stage `"-1"`."""
        session.turn_count += 1
        console_log.user_message(session.session_id, message, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": message})

        result = agent.run_open_turn(
            registry.OPENING_PROTOCOL,
            session.session_id,
            turn=session.turn_count,
            message=message,
            answers=session.answers,
            select_protocol=registry.select_protocol,
            protocol_for=registry.protocol_for,
            conversation=list(session.conversation),
            credential=session.credential,
            on_token=on_token,
        )

        session.answers = result.answers
        session.llm_used_last_turn = result.llm_used
        # Lượt mở không có cụm nào để giữ nguyên, nên "giữ nguyên" ở đây chính là ở lại lượt mở -
        # đúng hành vi `harvested_nothing` đã có, chỉ khác ở chỗ câu hỏi phát ra là câu xác nhận an
        # toàn thay vì câu mở chung.
        safety_hold = "" if result.emergency else self._safety_confirmation(session, not result.harvested_nothing)
        agent_message = safety_hold or result.agent_message
        session.last_question = agent_message
        if agent_message:
            session.conversation.append({"role": "assistant", "content": agent_message})
        console_log.extraction(session.session_id, result.extracted, percent=0, filled=0, total=1)

        if result.emergency:
            session.protocol_name = result.protocol_name
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)
            session.escalation_lock = True
            session.state = SessionState.EMERGENCY
            session.phase = SessionPhase.COLLECTING
            session.current_cluster = None
            session.stop_reason = "RED_FLAG"
            stage_log.finish(
                session.session_id, triage_level=result.triage_level, stop_reason="RED_FLAG",
                turns=session.turn_count,
            )
            console_log.red_flag(session.session_id, list(result.reason_codes))
            console_log.session_end(session.session_id, state="emergency", turns=session.turn_count, percent=100)
            return session

        if result.harvested_nothing:
            # Vẫn ở lượt mở: hỏi lại câu mở, KHÔNG chọn protocol. Chọn protocol từ một tin nhắn không
            # có thông tin nào là đoán mò, và đoán sai ở đây kéo dài suốt cả phiên.
            return session

        session.protocol_name = result.protocol_name
        session.phase = SessionPhase.COLLECTING
        if result.triage_level is not None:
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)
        # `_progress` tự ghi `stage_enter` (stage hiện tại là "" nên luôn khác stage đích).
        self._progress(session, result)
        return session

    def _hand_off(self, session: Session, message: str, reason: str) -> Session:
        """FAIL CLOSED: trạng thái phiên không hợp lệ ⇒ bàn giao điều dưỡng, không gọi model.

        Bản cũ `return session` lặng lẽ: người bệnh gõ tin nhắn và không nhận được gì, phiên treo mà
        không ai biết. Im lặng là kiểu hỏng tệ nhất trong một hệ y tế - nó trông giống như đang hoạt
        động bình thường."""
        session.turn_count += 1
        console_log.user_message(session.session_id, message, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": message})
        session.conversation.append({"role": "assistant", "content": controller.HANDOFF_MESSAGE})
        session.last_question = controller.HANDOFF_MESSAGE
        session.current_cluster = None
        session.pending_probe = ()
        logger.warning("symptom_session.fail_closed session=%s reason=%s", session.session_id, reason)
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage, cluster_id=None,
            event="stop", input=None, output={"fail_closed": reason}, stop_reason="INVALID_STATE",
        )
        self._finish(session, f"INVALID_STATE:{reason}")
        session.last_question = controller.HANDOFF_MESSAGE
        return session

    def _shadow_controller(
        self, session: Session, message: str, plan, *, is_opening: bool,
    ) -> None:
        """Controller bằng model, SHADOW MODE (§4.11 bước 1) - hỏi, đối chiếu, rồi VỨT câu trả lời.

        Không trả về gì, không nhận vào đâu. Kết quả duy nhất là `SHADOW_STATS`, tức
        `controller_agreement_rate` - chỉ số quyết định có bật bước 2-3 hay không. Bỏ hàm này đi thì
        hệ thống chạy y hệt, và đó chính là định nghĩa của bước 1.

        Đặt SAU `build_execution_plan` vì cần biết controller TẤT ĐỊNH đã chọn gì thì mới đối chiếu
        được - shadow mode đo độ trùng khớp, mà muốn đo thì phải có cả hai vế."""
        if not flags.llm_controller_shadow_enabled():
            return
        admissible = controller_shadow.admissible_actions(
            is_opening=is_opening,
            has_cluster=session.current_cluster is not None,
            has_protocol=bool(session.protocol_name),
            session_closed=session.state is not SessionState.COLLECTING,
        )
        proposal = controller_shadow.propose(
            message,
            admissible=admissible,
            # §4.11 ràng buộc 4: cho model đủ ngữ cảnh, đừng chỉ đưa text thô. Rẻ về token và là khác
            # biệt giữa một dispatcher đoán mò với một dispatcher biết mình đang ở đâu.
            state_digest={
                "protocol": session.protocol_name,
                "cluster": session.current_cluster.id if session.current_cluster else None,
                "turn": session.turn_count,
                "mandatory_remaining": list(
                    coverage.mandatory_remaining(self._protocol(session), session.answers)
                )[:8],
                "escalated": session.escalation_lock,
            },
            credential=session.credential,
        )
        deterministic = (
            controller_shadow.ACTION_HANDOFF
            if plan.fail_closed
            else controller_shadow.ACTION_EXTRACT
            if plan.invoke_extractor
            else controller_shadow.ACTION_ANSWER_META
        )
        SHADOW_STATS.record(proposal, deterministic_action=deterministic)
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage or "OPEN",
            cluster_id=session.current_cluster.id if session.current_cluster else "OPEN",
            event="route_decided", input=None,
            output={
                "controller_shadow": {
                    "model": proposal.next_action, "code": deterministic,
                    "lane": proposal.lane, "latency_ms": proposal.latency_ms,
                    "failed": proposal.failed,
                },
            },
        )

    def _answer_non_clinical(
        self, session: Session, message: str, lane: non_clinical.NonClinicalVerdict,
    ) -> Session:
        """Lượt phi lâm sàng: trả lời bằng văn bản TĨNH, KHÔNG gọi model, KHÔNG đổi trạng thái lâm sàng.

        Ba thứ cố ý không đụng tới - và đây là toàn bộ lý do lane này an toàn:

        - `answers` / `stage` / `current_cluster`: một câu tán gẫu không phải dữ kiện lâm sàng;
        - `triage_level` / `escalation_lock`: lane này KHÔNG sinh red flag và cũng không hạ được cái
          nào (L0 đã chạy trước và đã có cơ hội escalate);
        - `metrics.record_question`: đếm nó vào mẫu số của `user_led_ratio` sẽ làm chỉ số trải nghiệm
          lâm sàng bị pha loãng bởi những lượt không phải hỏi bệnh.

        `turn_count` VẪN tăng: đó là số lượt hội thoại thật, và `median_turns` phải phản ánh đúng cái
        người bệnh trải qua."""
        session.turn_count += 1
        console_log.user_message(session.session_id, message, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": message})
        reply = non_clinical.reply_for(lane.lane)
        session.conversation.append({"role": "assistant", "content": reply})
        session.last_question = reply
        session.llm_used_last_turn = False
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage or "OPEN",
            cluster_id=session.current_cluster.id if session.current_cluster else "OPEN",
            event="agent_message", input=None,
            output={"non_clinical_lane": lane.lane.value, "matched": list(lane.matched), "text": reply},
            llm_used=False,
        )
        console_log.agent_question(session.session_id, reply, llm_used=False)
        self._remember(session)
        return session

    def _run_model_red_flag_branch(self, session: Session, message: str) -> None:
        """Nhánh red-flag thứ BA (§4.1) - chạy SONG SONG hai nhánh tất định, không thay chúng.

        Đặt SAU `scan.short_circuit` có chủ đích: tin nhắn đã đủ rõ để L0 dừng phiên thì không cần
        hỏi model nữa, và bắt người bệnh chờ thêm một lời gọi model đúng lúc đó là sai hoàn toàn.

        Hàm này **không trả về gì và không đổi quyết định nào**. Nó chỉ cộng dồn `red_flag_agreement`
        - `model_only` là danh sách ứng viên để mở rộng rule, `agreement_rate` là chỉ số trả lời câu
        "rule của chúng ta có bỏ sót gì không". Việc escalate vẫn hoàn toàn do L0 + rule engine
        quyết, đúng ràng buộc 4 của §4.1.

        Lỗi model không được làm mất nhánh nào: `detect_with_model` không ném, và trạng thái `failed`
        được ghi lại để mọi con số đọc kèm biết mẫu số của nó có vấn đề."""
        if not flags.model_red_flag_branch_enabled():
            return
        protocol = self._protocol(session)
        findings, status = red_flag_branches.detect_with_model(
            protocol, message, credential=session.credential,
        )
        _, agreement = red_flag_branches.merge_findings(
            tuple(session.reason_codes), findings, model_status=status,
        )
        # Cộng dồn theo PHIÊN, không ghi đè theo lượt: câu hỏi cần trả lời là "cả phiên này rule bỏ
        # sót gì", mà một dấu hiệu chỉ được nhắc ở lượt 3 sẽ biến mất nếu lượt 4 ghi đè.
        session.red_flag_agreement = _merged_agreement(session.red_flag_agreement, agreement)
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage,
            cluster_id=session.current_cluster.id if session.current_cluster else "OPEN",
            event="extract", input=None,
            output={"red_flag_agreement": session.red_flag_agreement.as_dict()},
        )

    def _answer_without_extraction(
        self, session: Session, message: str, plan, *, on_token: agent.TokenSink | None,
    ) -> Session:
        """Lượt KHÔNG gọi extractor (§7.4): lời chào thuần không mang dữ kiện lâm sàng nào.

        Vẫn giữ nguyên cụm đang hỏi và vẫn phát ra một câu hỏi - chỉ bỏ đúng lời gọi trích xuất,
        tiết kiệm ~3.8s và một lời gọi model mỗi lượt như vậy. Tầng L0 đã chạy TRƯỚC controller nên
        một lời chào có kèm dấu hiệu đỏ không bao giờ đi vào đây."""
        session.turn_count += 1
        console_log.user_message(session.session_id, message, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": message})

        cluster = session.current_cluster
        if cluster is None:
            # Lượt mở: chưa có cụm nào, hỏi lại đúng câu mở tĩnh.
            session.last_question = registry.OPENING_QUESTION
            session.conversation.append({"role": "assistant", "content": session.last_question})
            console_log.agent_question(session.session_id, session.last_question, llm_used=False)
            return session

        protocol = self._protocol(session)
        response_plan = dialogue.build_response_plan(
            protocol, cluster,
            act=plan.forced_act or dialogue.DialogueAct.GREETING,
            answers=session.answers,
        )
        question, llm_used = agent.generate_question(
            protocol, cluster, answers=session.answers, plan=response_plan,
            conversation=list(session.conversation), credential=session.credential, on_token=on_token,
        )
        session.llm_used_last_turn = llm_used
        session.last_question = question
        if question:
            session.conversation.append({"role": "assistant", "content": question})
        console_log.agent_question(session.session_id, question, llm_used=llm_used)
        return session

    def _escalate_from_text_signal(
        self, session: Session, message: str, scan: text_safety_signals.TextSafetyScan,
    ) -> Session:
        """Dấu hiệu đỏ dương tính RÕ trên text thô ⇒ dừng phiên ngay bằng thông điệp tĩnh.

        Đây là ngoại lệ có chủ đích của HITL (`CLAUDE.md` nguyên tắc 4): an toàn tức thì đứng trên
        việc chờ duyệt. Không lời gọi model nào chạy ở lượt này - không có gì để model làm hỏng.

        Chỉ mã trong `SHORT_CIRCUIT_CODES` đi được đường này; tín hiệu mơ hồ đi đường xác nhận
        (`_safety_confirmation`) chứ không tự tạo disposition."""
        session.turn_count += 1
        console_log.user_message(session.session_id, message, turn=session.turn_count)
        session.conversation.append({"role": "user", "content": message})

        patient_red_flag_message = self._protocol(session).patient_red_flag_message
        session.triage_level = "EMERGENCY"
        session.reason_codes = list(scan.reason_codes)
        session.triggered_rules = [f"text_safety_signals:{signal.code}" for signal in scan.short_circuit]
        session.escalation_lock = True
        session.state = SessionState.EMERGENCY
        session.phase = SessionPhase.COLLECTING
        session.current_cluster = None
        session.pending_probe = ()
        session.pending_safety_signals = ()
        session.last_question = patient_red_flag_message
        session.stop_reason = "RED_FLAG"
        session.conversation.append({"role": "assistant", "content": patient_red_flag_message})

        stage_log.finish(
            session.session_id, triage_level="EMERGENCY", stop_reason="RED_FLAG", turns=session.turn_count,
        )
        console_log.red_flag(session.session_id, scan.short_circuit_labels)
        console_log.session_end(session.session_id, state="emergency", turns=session.turn_count, percent=100)
        return session

    def _safety_confirmation(self, session: Session, extracted_something: bool) -> str:
        """Câu xác nhận TĨNH cho tín hiệu L0 mơ hồ - chỉ dùng khi lượt vừa rồi KHÔNG trích được gì.

        Không thay thế cụm xác nhận red flag của protocol (việc ưu tiên cụm thuộc về xếp hạng ở
        `stage_machine`); đây là chốt chặn để một dấu hiệu nguy hiểm không bị bỏ qua IM LẶNG khi tầng
        model hỏng. Mỗi mã chỉ hỏi MỘT lần: model hỏng nhiều lượt liên tiếp không được biến thành
        vòng lặp hỏi đi hỏi lại cùng một câu."""
        if extracted_something:
            return ""
        pending = [
            code for code in session.pending_safety_signals
            if code not in session.asked_safety_signal_codes
        ]
        if not pending:
            return ""
        session.asked_safety_signal_codes.update(pending)
        return text_safety_signals.confirmation_question(pending)

    def _retraction_confirmation(self, session: Session, result) -> str:
        """Câu xác nhận TĨNH cho một đính chính chưa đủ rõ (§5 quy tắc 5).

        Reducer đã giữ hồ sơ ở giá trị CŨ và trả về field bị giữ; việc còn lại là hỏi người bệnh cho
        rõ. Câu này không qua LLM: nó phải nêu ĐÚNG cái hệ thống đang định xoá, còn một bản diễn đạt
        lại có thể biến câu xác nhận thành câu gợi ý.

        Hỏi ĐÚNG MỘT LẦN mỗi field. Lượt sau, `confirmed_retractions` cho phép đính chính đi qua dù
        model vẫn trả về bằng chứng mờ - nếu không, một phiên mà người bệnh diễn đạt kiểu khó trích
        dẫn sẽ không bao giờ sửa được lời khai."""
        pending = [key for key in result.pending_retraction if key not in session.confirmed_retractions]
        if not pending:
            return ""
        session.confirmed_retractions.update(pending)
        protocol = self._protocol(session)
        labels = [
            protocol.fields_by_key[key].label for key in pending if key in protocol.fields_by_key
        ] or list(pending)
        return (
            f"Mình muốn xác nhận lại cho chắc: ý bạn là thông tin \"{labels[0]}\" trước đó không còn "
            "đúng nữa, phải không? Bạn trả lời giúp mình \"đúng\" hoặc \"không\" nhé."
        )

    def _record_cluster_outcome(self, session: Session, cluster: QuestionCluster, result) -> None:
        """Quyết định cụm vừa hỏi đã XONG chưa. Đây là chỗ vá bug C3.

        Bản cũ `asked_ids.add(cluster.id)` vô điều kiện: gõ "." hay né tránh cũng được tính là đã hỏi
        xong, cụm không bao giờ quay lại, field trống suốt cả phiên. Giờ chỉ đánh dấu xong khi THẬT
        SỰ thu được gì; không thì hỏi lại, tối đa `MAX_RETRIES_PER_CLUSTER` lần rồi mới bỏ qua và ghi
        vào `unresolved_cluster_ids`."""
        # Cụm bị mở lại do đính chính/mâu thuẫn: field bên trong vừa bị xoá hoặc đang chọi nhau, phải
        # được phép hỏi lại dù trước đó đã hoàn tất.
        if result.reopened_cluster_ids:
            reopened = {session.cluster_key(cluster_id) for cluster_id in result.reopened_cluster_ids}
            session.completed_cluster_ids -= reopened
            session.unresolved_cluster_ids -= reopened

        # Cụm đóng bởi verdict phủ định của lượt sàng lọc: đánh dấu hoàn tất (người bệnh ĐÃ nghe đọc
        # danh sách dấu hiệu của chúng và trả lời không có) nhưng ghi riêng để trừ khỏi ngân sách.
        for cluster_id in result.screened_cluster_ids:
            screened_key = session.cluster_key(cluster_id)
            session.completed_cluster_ids.add(screened_key)
            session.screened_cluster_ids.add(screened_key)
            session.retry_count_by_cluster.pop(screened_key, None)

        key = session.cluster_key(cluster.id)
        if result.cluster_resolved:
            session.completed_cluster_ids.add(key)
            session.retry_count_by_cluster.pop(key, None)
            return

        retries = session.retry_count_by_cluster.get(key, 0) + 1
        session.retry_count_by_cluster[key] = retries
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage, cluster_id=cluster.id,
            event="extract", input=None,
            output={"retry": retries, "answer_quality": result.answer_quality},
        )
        # Theo ĐÚNG quyết định của agent (`retried_same_cluster`), không tự tính lại: agent còn bỏ hỏi
        # lại khi cụm chỉ còn field tuỳ chọn (`_worth_retrying`). Nếu ở đây vẫn để cụm "chưa xong"
        # trong khi agent đã đi tiếp thì cụm đó không nằm trong `closed_cluster_ids`, `next_cluster`
        # chọn lại chính nó ở lượt sau và hội thoại quay vòng.
        if not result.retried_same_cluster or retries > agent.MAX_RETRIES_PER_CLUSTER:
            session.unresolved_cluster_ids.add(key)

    def _progress(self, session: Session, result) -> None:
        """Cập nhật `session.stage`/`session.current_cluster` cho lượt kế tiếp, hoặc kết thúc phiên.

        KHÔNG tự duyệt lại: cụm kế tiếp đã do `run_turn` chọn bằng `stage_machine.advance` và CÂU HỎI
        đã được sinh cho đúng cụm đó. Bản cũ duyệt lần hai ở đây, nên khi cụm cuối stage vừa được trả
        lời thì agent trả tin nhắn rỗng còn session lại âm thầm nhảy sang cụm mới - người bệnh không
        được hỏi gì nhưng lượt sau vẫn bị trích theo schema của cụm đó."""
        # Đếm metric TRƯỚC `ledger.record_turn`: `deferral_depth` cần số nợ TẠI THỜI ĐIỂM cụm được
        # chọn, mà `record_turn` xoá nợ của cụm vừa được chọn ngay sau đây (§12).
        if result.next_cluster is not None:
            session.metrics.record_question(
                result.next_cluster,
                recent_fields=result.recent_fields,
                deferral_count=session.ledger.deferral_count(result.next_cluster.id),
            )
        # Ghi sổ TRƯỚC khi cập nhật trạng thái: cụm được chọn về 0 nợ, cụm thua điểm cộng thêm một
        # lượt chờ. Không có bước này thì xếp hạng chỉ là "hoãn", không phải "hoãn rồi hỏi lại".
        session.ledger.record_turn(
            result.next_cluster.id if result.next_cluster is not None else None,
            result.deferred_cluster_ids,
        )
        stage_log.step(
            session.session_id, turn=session.turn_count, stage=session.stage,
            cluster_id=result.next_cluster.id if result.next_cluster is not None else None,
            event="route_decided", input=None,
            output={
                "coverage_ledger": session.ledger.snapshot(
                    self._protocol(session), session.answers,
                    unresolved=session.unresolved_ids_for_current_protocol(),
                ),
                "recent_fields": sorted(result.recent_fields),
                "dialogue_act": result.dialogue_act,
                "router_trigger": result.router_trigger,
            },
        )
        if result.next_cluster is not None:
            if result.next_stage and result.next_stage != session.stage:
                stage_log.stage_enter(session.session_id, result.next_stage)
            session.stage = result.next_stage or result.next_cluster.stage
            session.current_cluster = result.next_cluster
            session.pending_probe = result.next_probe
            if result.next_probe:
                stage = session.stage
                probed = frozenset(group.id for group in result.next_probe)
                session.screening_history[stage] = session.screening_history.get(stage, ()) + (probed,)
            return

        session.pending_probe = ()
        stop_reason = result.stop_reason or "BUDGET_EXHAUSTED"
        if self._ask_catch_all(session, stop_reason):
            return
        self._finish(session, stop_reason)

    def _ask_catch_all(self, session: Session, stop_reason: str) -> bool:
        """Bước QUÉT SÓT (§8.6 mục 4): một câu mở cuối trước khi chốt phiếu.

        Checklist chỉ hỏi được thứ nó biết trước; câu này là chỗ duy nhất người bệnh nêu được điều
        nằm ngoài bộ câu hỏi. Nó KHÔNG bị cắt khi hết ngân sách - đây chính là ý §8.7: tiêu chí dừng
        là "đủ độ phủ VÀ đã quét sót", còn số đếm chỉ là trần an toàn chống lặp vô hạn.

        Ngoại lệ `RED_FLAG`: đã chốt cấp cứu thì việc cần làm là gọi 115, không phải hỏi thêm.

        Ngoại lệ thứ hai (§4.7): người bệnh vừa nói họ muốn dừng hoặc vừa không hợp tác qua hai lượt
        thì hỏi thêm một câu mở nữa là làm đúng cái họ vừa từ chối. `NO_MORE_SYMPTOMS` cũng nằm đây
        vì câu quét sót hỏi CHÍNH điều họ vừa trả lời ("còn gì khác không")."""
        if stop_reason in _NO_CATCH_ALL_REASONS or session.catch_all_asked:
            return False
        session.catch_all_asked = True
        session.awaiting_catch_all = True
        session.metrics.record_catch_all_asked()
        session.current_cluster = None
        session.last_question = CATCH_ALL_QUESTION
        session.conversation.append({"role": "assistant", "content": CATCH_ALL_QUESTION})
        console_log.agent_question(session.session_id, CATCH_ALL_QUESTION, llm_used=False)
        return True

    def _finish(self, session: Session, stop_reason: str) -> None:
        result = rule_engine.evaluate(self._protocol(session), session.answers)
        session.triage_level = result.triage_level
        session.reason_codes = list(result.reason_codes)
        session.triggered_rules = list(result.triggered_rules)
        session.stop_reason = stop_reason
        session.state = SessionState.EMERGENCY if result.triage_level == "EMERGENCY" else SessionState.AWAITING_CONFIRMATION
        session.current_cluster = None
        session.last_question = ""
        # Số liệu §12 đi kèm phiên vào log: dashboard của P4.4 dựng được bằng cách đọc thư mục log
        # chứ không cần thêm hạ tầng. Tính SAU khi `stop_reason`/`triage_level` đã chốt - đó là hai
        # trường quyết định phiên này có nằm trong mẫu số của gate độ phủ hay không.
        stage_log.finish(
            session.session_id, triage_level=result.triage_level, stop_reason=stop_reason,
            turns=session.turn_count,
            metrics=self.metrics_summary(session.session_id),
        )
        console_log.summary(session.session_id, "generated", percent=100)

    def metrics_summary(self, session_id: str) -> dict:
        """Bản đọc được của phiên cho §12. Chỉ ĐỌC - không đổi trạng thái gì.

        Đặt trên store chứ không trên `Session` vì nó cần `protocol` để biết field nào là M0/M1, mà
        `Session` cố ý không giữ đối tượng protocol (phiên có thể đổi protocol giữa chừng, giữ tham
        chiếu là mời chấm hồ sơ bằng luật của protocol cũ)."""
        session = self._require(session_id)
        summary = session.metrics.summary(
            self._protocol(session), session.answers,
            turns=session.turn_count, stop_reason=session.stop_reason, triage_level=session.triage_level,
        )
        # Hai bộ số sinh ra NGOÀI `ConversationMetrics` nhưng vẫn thuộc về phiên này. Gắn vào đây để
        # chúng đi theo phiên vào log, và `metrics.aggregate` gộp được mà không cần thêm hạ tầng.
        summary["red_flag_agreement"] = session.red_flag_agreement.as_dict()
        summary["controller_shadow"] = SHADOW_STATS.as_dict() if flags.llm_controller_shadow_enabled() else None
        return summary

    def confirm_summary(self, session_id: str, is_correct: bool) -> Session:
        session = self._require(session_id)
        if session.state != SessionState.AWAITING_CONFIRMATION:
            raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận, hoặc đã ở nhánh cấp cứu.")
        if is_correct:
            session.state = SessionState.CONFIRMED
            console_log.session_end(session.session_id, state="confirmed", turns=session.turn_count, percent=100)
        return session

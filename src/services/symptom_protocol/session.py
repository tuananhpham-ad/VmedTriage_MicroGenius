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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from src.services.infra import console_log, provider_router
from src.services.infra import fever_stage_log as stage_log
from src.services.infra.provider_router import LLMCredential
from src.services.symptom_protocol import intake_agent as agent
from src.services.symptom_protocol import registry, rule_engine, screening, stage_machine
from src.services.symptom_protocol.models import QuestionCluster, ScreeningGroup
from src.services.symptom_protocol.protocol import SymptomProtocol


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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    credential: LLMCredential | None = None

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

    def _ids_for_current_protocol(self, keys: set[str]) -> frozenset[str]:
        prefix = f"{self.protocol_name}:"
        return frozenset(key[len(prefix):] for key in keys if key.startswith(prefix))


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

    def __init__(self, default_protocol: SymptomProtocol | None = None) -> None:
        self.protocol = default_protocol
        self._sessions: dict[str, Session] = {}

    def _protocol(self, session: Session) -> SymptomProtocol:
        """Protocol THẬT SỰ đang chạy cho phiên này. Mọi đường trong store phải đi qua đây - đọc
        `self.protocol` sẽ chấm phiên bằng luật của protocol mặc định thay vì protocol đã chọn."""
        return registry.protocol_for(session.protocol_name)

    def create(self, credential: LLMCredential | None = None) -> Session:
        session = Session(credential=credential)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

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
        if session.phase is SessionPhase.OPENING:
            return self._submit_open_message(session, cleaned, on_token=on_token)

        protocol = self._protocol(session)
        if session.current_cluster is None:
            # Không còn cụm nào để hỏi (lẽ ra đã finish) - phòng vệ, không nên xảy ra trong luồng bình thường.
            return session

        session.turn_count += 1
        cluster = session.current_cluster
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
        )

        session.answers = result.answers
        # Ghi nhận kết quả cụm TRƯỚC khi đổi `protocol_name`: cụm vừa hỏi thuộc protocol CŨ, ghi nó
        # dưới tên protocol mới sẽ làm cụm cùng mã của protocol mới bị coi là đã hỏi rồi.
        self._record_cluster_outcome(session, cluster, result)
        if result.protocol_name and result.protocol_name != session.protocol_name:
            console_log.session_start(
                session.session_id, label=f"đổi protocol -> {result.protocol_name}", llm="rule",
            )
            session.protocol_name = result.protocol_name
        session.llm_used_last_turn = result.llm_used
        if result.agent_message:
            session.conversation.append({"role": "assistant", "content": result.agent_message})
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
            return session

        # Cập nhật kết luận triage MỚI NHẤT do rule engine tính ở lượt này (kể cả khi chưa EMERGENCY)
        # - cần thiết để should_stop chọn đúng hàng ngân sách (vd EARLY_VISIT khác SELF_CARE_CANDIDATE)
        # ngay khi đã biết, không phải đợi tới lúc finish.
        if result.triage_level is not None:
            session.triage_level = result.triage_level
            session.reason_codes = list(result.reason_codes)
            session.triggered_rules = list(result.triggered_rules)

        session.last_question = result.agent_message
        self._progress(session, result)
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
        session.last_question = result.agent_message
        if result.agent_message:
            session.conversation.append({"role": "assistant", "content": result.agent_message})
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
        self._finish(session, result.stop_reason or "BUDGET_EXHAUSTED")

    def _finish(self, session: Session, stop_reason: str) -> None:
        result = rule_engine.evaluate(self._protocol(session), session.answers)
        session.triage_level = result.triage_level
        session.reason_codes = list(result.reason_codes)
        session.triggered_rules = list(result.triggered_rules)
        session.stop_reason = stop_reason
        session.state = SessionState.EMERGENCY if result.triage_level == "EMERGENCY" else SessionState.AWAITING_CONFIRMATION
        session.current_cluster = None
        session.last_question = ""
        stage_log.finish(session.session_id, triage_level=result.triage_level, stop_reason=stop_reason, turns=session.turn_count)
        console_log.summary(session.session_id, "generated", percent=100)

    def confirm_summary(self, session_id: str, is_correct: bool) -> Session:
        session = self._require(session_id)
        if session.state != SessionState.AWAITING_CONFIRMATION:
            raise ValueError("Phiên chưa có phiếu tóm tắt để xác nhận, hoặc đã ở nhánh cấp cứu.")
        if is_correct:
            session.state = SessionState.CONFIRMED
            console_log.session_end(session.session_id, state="confirmed", turns=session.turn_count, percent=100)
        return session

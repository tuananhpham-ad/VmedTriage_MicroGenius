"""Persist phiên hỏi-đáp đang dở — Memory **M1** (§4.9 `_guidance/what_to_do_next.md`).

M1 là **điều kiện tiên quyết của M2/M3, không phải một tối ưu**: phiên đang dở còn chưa sống nổi qua
một lần deploy, mà kế hoạch đã bàn tới ký ức xuyên phiên. Làm M3 trước M1 là xây tầng hai trên một
tầng một chưa đổ móng.

Ba việc, không hơn:

1. **Khoá composite `user_id + conversation_id`** — mỗi hội thoại một collection độc lập, mọi đường
   đọc buộc phải kèm `user_id`.
2. **`conversation_id` là UUID, không phải timestamp** — hai phiên mở cùng giây sẽ đụng nhau, và
   timestamp trong khoá là metadata rò ra ngoài. `Session.session_id` vốn đã là UUID4, nên phần này
   là *giữ nguyên đúng thứ đang có* thay vì đổi sang timestamp như một số bản kế hoạch đề xuất.
3. **Ghi lại sau mỗi lượt được nhận** — đây chính là thứ khiến "hỏi vu vơ rồi quay lại hỏi cái cũ"
   chạy được qua một lần restart.

**Ba thứ CỐ Ý không persist**, và mỗi thứ có một lý do khác nhau:

| Không lưu | Vì sao |
| --- | --- |
| `credential` (khoá API) | Ghi key vào DB để tiện khôi phục là đổi một bất tiện lấy một sự cố bảo mật. Phiên khôi phục dùng credential mặc định của protocol. |
| Đối tượng `SymptomProtocol` | Nó là **code**, không phải state. Lưu tên rồi tra lại `registry` - lưu cả object thì một phiên cũ sẽ chạy bằng checklist của phiên bản trước. |
| `ScreeningGroup` đầy đủ | Cùng lý do: lưu mã nhóm, tra lại từ protocol đang chạy. |

Ngược lại, `current_cluster` **phải lưu đầy đủ** chứ không lưu mã: cụm đang hỏi có thể là cụm TỔNG
HỢP dựng tại chỗ (`BATCH-...`, `SCREEN-...`, `CATCH-ALL`) không hề nằm trong `protocol.clusters`, nên
tra theo mã sẽ trả `None` và lượt sau trích xuất theo sai schema.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.database import session_scope
from src.models.case_record import ConversationRow
from src.services.symptom_protocol import coverage, red_flag_branches, registry, user_intent
from src.services.symptom_protocol import metrics as metrics_mod
from src.services.symptom_protocol.models import QuestionCluster
from src.services.symptom_protocol.session import Session, SessionPhase, SessionState

logger = logging.getLogger("vmedtriage.conversation_store")

GUEST_USER_ID = 0
"""Phiên chưa đăng nhập. Không dùng `None` vì đây là một nửa của khoá chính, và một khoá chính
nullable là khoá không dùng được."""


def dump_session(session: Session) -> dict:
    """`Session` -> dict JSON-able. KHÔNG chứa credential."""
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "phase": session.phase.value,
        "protocol_name": session.protocol_name,
        "protocol_pinned": session.protocol_pinned,
        "stage": session.stage,
        "answers": dict(session.answers),
        "completed_cluster_ids": sorted(session.completed_cluster_ids),
        "unresolved_cluster_ids": sorted(session.unresolved_cluster_ids),
        "retry_count_by_cluster": dict(session.retry_count_by_cluster),
        "screened_cluster_ids": sorted(session.screened_cluster_ids),
        # `frozenset` không JSON được, và thứ tự các vòng sàng lọc là dữ liệu thật (`next_probe` đọc
        # phần tử CUỐI để biết vòng sau có hỏi ít hơn vòng trước không) - nên giữ list-of-list.
        "screening_history": {
            stage: [sorted(group_ids) for group_ids in rounds]
            for stage, rounds in session.screening_history.items()
        },
        "pending_probe": [group.id for group in session.pending_probe],
        "current_cluster": _dump_cluster(session.current_cluster),
        "conversation": list(session.conversation),
        "turn_count": session.turn_count,
        "last_question": session.last_question,
        "llm_used_last_turn": session.llm_used_last_turn,
        "triage_level": session.triage_level,
        "reason_codes": list(session.reason_codes),
        "triggered_rules": list(session.triggered_rules),
        "stop_reason": session.stop_reason,
        "escalation_lock": session.escalation_lock,
        "pending_safety_signals": list(session.pending_safety_signals),
        "confirmed_retractions": sorted(session.confirmed_retractions),
        "asked_safety_signal_codes": sorted(session.asked_safety_signal_codes),
        "catch_all_asked": session.catch_all_asked,
        "awaiting_catch_all": session.awaiting_catch_all,
        "created_at": session.created_at.isoformat(),
        "ledger_deferred": dict(session.ledger.deferred),
        "red_flag_agreement": session.red_flag_agreement.as_dict(),
        "uncooperative": {
            "streak": session.uncooperative.streak,
            "prompted": session.uncooperative.prompted,
        },
        "metrics": _dump_metrics(session.metrics),
    }


def load_session(payload: dict) -> Session:
    """dict -> `Session`. Trường thiếu rơi về mặc định của dataclass.

    Khoan dung với payload cũ có chủ đích: một phiên ghi bằng bản trước khi thêm trường mới vẫn phải
    khôi phục được. Đường thay thế - từ chối nạp - nghĩa là mỗi lần deploy lại làm mất đúng những
    phiên đang dở, tức là đúng thứ M1 tồn tại để tránh."""
    protocol_name = payload.get("protocol_name") or ""
    session = Session(
        session_id=payload.get("session_id") or "",
        state=SessionState(payload.get("state") or SessionState.COLLECTING.value),
        phase=SessionPhase(payload.get("phase") or SessionPhase.COLLECTING.value),
        protocol_name=protocol_name,
        protocol_pinned=bool(payload.get("protocol_pinned")),
        stage=payload.get("stage") or "",
        answers=dict(payload.get("answers") or {}),
    )
    session.completed_cluster_ids = set(payload.get("completed_cluster_ids") or [])
    session.unresolved_cluster_ids = set(payload.get("unresolved_cluster_ids") or [])
    session.retry_count_by_cluster = dict(payload.get("retry_count_by_cluster") or {})
    session.screened_cluster_ids = set(payload.get("screened_cluster_ids") or [])
    session.screening_history = {
        stage: tuple(frozenset(group_ids) for group_ids in rounds)
        for stage, rounds in (payload.get("screening_history") or {}).items()
    }
    session.pending_probe = _load_probe(protocol_name, payload.get("pending_probe") or [])
    session.current_cluster = _load_cluster(payload.get("current_cluster"))
    session.conversation = list(payload.get("conversation") or [])
    session.turn_count = int(payload.get("turn_count") or 0)
    session.last_question = payload.get("last_question") or ""
    session.llm_used_last_turn = bool(payload.get("llm_used_last_turn"))
    session.triage_level = payload.get("triage_level")
    session.reason_codes = list(payload.get("reason_codes") or [])
    session.triggered_rules = list(payload.get("triggered_rules") or [])
    session.stop_reason = payload.get("stop_reason")
    session.escalation_lock = bool(payload.get("escalation_lock"))
    session.pending_safety_signals = tuple(payload.get("pending_safety_signals") or ())
    session.confirmed_retractions = set(payload.get("confirmed_retractions") or [])
    session.asked_safety_signal_codes = set(payload.get("asked_safety_signal_codes") or [])
    session.catch_all_asked = bool(payload.get("catch_all_asked"))
    session.awaiting_catch_all = bool(payload.get("awaiting_catch_all"))
    session.created_at = _parse_time(payload.get("created_at"))
    session.ledger = coverage.CoverageLedger(deferred=dict(payload.get("ledger_deferred") or {}))
    session.red_flag_agreement = red_flag_branches.parse_json_agreement(
        payload.get("red_flag_agreement") or {}
    )
    tracker = payload.get("uncooperative") or {}
    session.uncooperative = user_intent.UncooperativeTracker(
        streak=int(tracker.get("streak") or 0), prompted=bool(tracker.get("prompted")),
    )
    session.metrics = _load_metrics(payload.get("metrics") or {})
    return session


class SqliteConversationStore:
    """Kho phiên. API cố ý nhỏ: `save` / `get` / `recent_for_user`.

    `recent_for_user` là móc duy nhất mà M3 (hỏi thăm 3 phiên gần nhất) sẽ cần - có sẵn ở đây vì nó
    là một câu truy vấn, không phải một tính năng. **Bản thân M3 chưa được bật**: nó cần consent +
    retention từ PM trước khi lên production (§4.9), và quan trọng hơn là bất biến "dữ kiện lịch sử
    không tự trở thành dữ kiện hiện tại" phải được thi hành ở tầng gọi, không phải ở đây."""

    def save(self, session: Session, *, user_id: int = GUEST_USER_ID) -> None:
        """Ghi lại phiên. Không bao giờ ném: mất một lần persist là mất khả năng khôi phục sau
        restart, còn ném ra ngoài là làm hỏng chính lượt hội thoại người bệnh đang trả lời."""
        try:
            payload = dump_session(session)
            with session_scope() as db:
                row = db.get(ConversationRow, (session.session_id, user_id))
                if row is None:
                    row = ConversationRow(
                        conversation_id=session.session_id,
                        user_id=user_id,
                        created_at=session.created_at,
                    )
                    db.add(row)
                row.protocol_name = session.protocol_name
                row.state = session.state.value
                row.stop_reason = session.stop_reason
                row.turn_count = session.turn_count
                row.updated_at = datetime.now(timezone.utc)
                row.payload = payload
        except Exception as error:
            logger.warning("conversation persist failed session=%s: %s", session.session_id, error)

    def get(self, conversation_id: str, *, user_id: int = GUEST_USER_ID) -> Session | None:
        """Đọc theo ĐÚNG `user_id` - không có đường nào đọc chéo hồ sơ người khác (§4.9 M3 điều kiện
        2, và `CLAUDE.md` nguyên tắc 5). Khoá composite làm việc đó bằng chính hình dạng bảng chứ
        không bằng một câu `if` mà ai đó có thể quên."""
        try:
            with session_scope() as db:
                row = db.get(ConversationRow, (conversation_id, user_id))
                return load_session(row.payload) if row else None
        except Exception as error:
            logger.warning("conversation restore failed id=%s: %s", conversation_id, error)
            return None

    def recent_for_user(self, user_id: int, *, limit: int = 3) -> list[Session]:
        """`limit` phiên gần nhất CỦA CHÍNH người dùng đó - móc cho M3."""
        try:
            with session_scope() as db:
                rows = db.scalars(
                    select(ConversationRow)
                    .where(ConversationRow.user_id == user_id)
                    .order_by(ConversationRow.updated_at.desc())
                    .limit(limit)
                ).all()
                return [load_session(row.payload) for row in rows]
        except Exception as error:
            logger.warning("conversation history failed user=%s: %s", user_id, error)
            return []


conversation_store = SqliteConversationStore()


# --- serialize từng phần ---------------------------------------------------------------------


def _dump_cluster(cluster: QuestionCluster | None) -> dict | None:
    """Lưu ĐẦY ĐỦ chứ không lưu mã: cụm đang hỏi có thể là cụm TỔNG HỢP dựng tại chỗ (`BATCH-`,
    `SCREEN-`, `CATCH-ALL`) không nằm trong `protocol.clusters`. Tra theo mã sẽ trả `None`, và lượt
    sau sẽ trích xuất theo sai schema - im lặng, không lỗi nào nổ ra."""
    if cluster is None:
        return None
    return {
        "id": cluster.id,
        "stage": cluster.stage,
        "fields": list(cluster.fields),
        "batch_negation": cluster.batch_negation,
        "script_hint": cluster.script_hint,
    }


def _load_cluster(data: dict | None) -> QuestionCluster | None:
    if not data:
        return None
    return QuestionCluster(
        id=data.get("id") or "",
        stage=data.get("stage") or "",
        fields=tuple(data.get("fields") or ()),
        batch_negation=bool(data.get("batch_negation")),
        script_hint=data.get("script_hint") or "",
    )


def _load_probe(protocol_name: str, group_ids: list[str]) -> tuple:
    """Tra `ScreeningGroup` từ protocol ĐANG chạy thay vì từ bản đã lưu - nhóm sàng lọc là nội dung
    lâm sàng đã duyệt, và một phiên khôi phục phải chạy bằng bản mới nhất của nó."""
    if not group_ids:
        return ()
    protocol = registry.protocol_for(protocol_name)
    wanted = set(group_ids)
    return tuple(group for group in protocol.screening_groups if group.id in wanted)


def _dump_metrics(metrics: metrics_mod.ConversationMetrics) -> dict:
    return {
        "questions_asked": metrics.questions_asked,
        "user_led_questions": metrics.user_led_questions,
        "repeated_questions": metrics.repeated_questions,
        "retried_questions": metrics.retried_questions,
        "asked_cluster_ids": list(metrics.asked_cluster_ids),
        "asked_field_keys": sorted(metrics.asked_field_keys),
        "deferral_depth_samples": list(metrics.deferral_depth_samples),
        "catch_all_asked": metrics.catch_all_asked,
        "catch_all_yielded": metrics.catch_all_yielded,
    }


def _load_metrics(data: dict) -> metrics_mod.ConversationMetrics:
    return metrics_mod.ConversationMetrics(
        questions_asked=int(data.get("questions_asked") or 0),
        user_led_questions=int(data.get("user_led_questions") or 0),
        repeated_questions=int(data.get("repeated_questions") or 0),
        retried_questions=int(data.get("retried_questions") or 0),
        asked_cluster_ids=list(data.get("asked_cluster_ids") or []),
        asked_field_keys=set(data.get("asked_field_keys") or []),
        deferral_depth_samples=list(data.get("deferral_depth_samples") or []),
        catch_all_asked=bool(data.get("catch_all_asked")),
        catch_all_yielded=bool(data.get("catch_all_yielded")),
    )


def _parse_time(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)

"""Lái phiên fever bằng LLM THẬT rồi đo xem model có tuân thủ hợp đồng prompt không.

Vì sao cần script này thay vì chỉ chạy `pytest`: test tự động dùng fake provider, nên chỉ chứng minh
được "guard chạy đúng KHI model trả JSON như giả định". Câu hỏi còn lại - *model thật có chịu trả
`evidence_span`/`negation_evidence` không* - chỉ trả lời được bằng cách gọi LLM thật. Cả 6 lỗi nghe
hiểu (C1/C2/C3/M1/M2/M3 trong `_guidance/need_to_check_agent.md`) đều tìm ra bằng chat thật, không
bằng đọc code.

Đây KHÔNG phải test tự động (không assert, không chạy trong CI - tốn tiền API và phụ thuộc mạng).
Nó là dụng cụ đo, in ra bảng số liệu để người đọc tự kết luận. Chạy lại mỗi khi ĐỔI model/provider.

    python scripts/manual_llm_check.py                 # chạy hết
    python scripts/manual_llm_check.py c1 m2           # chạy vài kịch bản
    python scripts/manual_llm_check.py --list

Kết quả: in ra stdout + ghi `logs/manual_llm_check/<timestamp>.json`. Log nguyên văn prompt/response
của từng lượt vẫn nằm ở `logs/fever/<session_id>/llm-io.jsonl` như mọi phiên khác.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paths import LOGS_DIR  # noqa: E402
from src.services.checklists.fever_checklist import FIELDS_BY_KEY  # noqa: E402
from src.services.engines.fever_protocol import EMERGENCY_TRI_STATE_FIELDS  # noqa: E402
from src.services.sessions.symptom_session import session_store  # noqa: E402
from src.services.symptom_protocol.session import SessionState  # noqa: E402

# Cùng trần với `tests/test_api/test_fever_flow.py` - "kết thúc trong 60 lượt" là cùng một hợp đồng,
# đo bằng LLM thật ở đây và bằng LLM kịch bản ở đó.
MAX_TURNS = 60

# Giãn cách giữa 2 lượt (giây). Không phải để "chờ cho chắc" - gemini free tier trả HTTP 429 khi gọi
# liên tục, và một lượt bị 429 làm hỏng cả phép đo (mọi field về unknown -> agent hỏi lại). Đặt
# `--delay 0` khi provider có hạn mức thoải mái.
DEFAULT_DELAY_SECONDS = 3.0


# --- Người bệnh mô phỏng --------------------------------------------------------------------
#
# Trả lời theo TỪ KHOÁ trong câu hỏi chứ không theo thứ tự lượt: câu hỏi do LLM diễn đạt lại nên
# chữ nghĩa đổi mỗi lần, còn thứ tự cụm thì đổi theo chính câu trả lời trước đó. Khớp từ khoá là
# cách duy nhất giữ cho "người bệnh" trả lời đúng thứ được hỏi qua nhiều lần chạy.

# QUY TẮC VIẾT TỪ KHOÁ: khớp là substring nên từ khoá NGẮN rất nguy hiểm - "ho" trúng cả "hoặc",
# "cho", "thuốc"; một lần chạy đã mất 4 lượt vì lý do này. Chỉ dùng cụm >= 2 âm tiết, và xếp quy tắc
# ĐẶC THÙ lên trước quy tắc chung ("sốt" trúng mọi câu hỏi về thuốc hạ sốt nếu để lên đầu).
BENIGN_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("bao nhiêu tuổi", "bé hay người lớn", "mấy tuổi", "độ tuổi"), "Tôi 30 tuổi, tôi tự hỏi cho mình"),
    (("nam hay nữ", "giới tính", "bé trai hay bé gái"), "Nữ"),
    (("nhiệt kế",), "Có nhiệt kế điện tử ở nhà"),
    (("đo nhiệt độ", "bao nhiêu độ", "đo ở đâu", "kết quả đo"), "38.5 độ, đo ở nách, cách đây khoảng 30 phút"),
    (("bắt đầu sốt", "sốt từ khi nào", "mấy ngày rồi", "kéo dài được"), "Bắt đầu từ hôm qua"),
    (("rét run", "đắp chăn"), "Không, không rét run"),
    (("thuốc hạ sốt", "hạ sốt nào", "paracetamol", "uống thuốc gì", "loại thuốc"),
     "Có uống paracetamol lúc sáng, uống xong thì đỡ được một lúc"),
    (("sau khi hạ sốt", "mệt hơn", "lừ đừ", "dễ chịu hơn"), "Không, hạ sốt xong là thấy dễ chịu hơn"),
    (("người lạnh", "lạnh bất thường"), "Không có lúc nào lạnh bất thường cả"),
    (("tỉnh táo", "đánh thức", "gọi hỏi", "phản ứng"), "Tôi tỉnh táo bình thường"),
    (("co giật",), "Không, không bị co giật"),
    (("cứng gáy", "cứng cổ", "ánh sáng", "đau đầu"), "Không có gì trong số đó cả"),
    (("yếu tay", "méo miệng", "nói khó", "yếu liệt"), "Không, không có"),
    (("khó thở", "tím tái", "môi tím", "rút lõm"), "Không khó thở, môi cũng không tím"),
    (("thở rít", "chảy dãi", "nuốt được"), "Không, không có"),
    (("vân tím", "da lạnh", "da có lạnh", "đầu ngón tay"), "Da bình thường, không lạnh không ẩm"),
    (("đi tiểu", "nôn không", "bị nôn", "ăn uống"), "Đi tiểu bình thường, ăn uống được, không nôn"),
    (("nốt ban", "ấn kính", "nổi ban", "ban đỏ", "ấn vào"), "Không nổi ban gì cả"),
    (("chảy máu", "chân răng", "phân đen"), "Không chảy máu gì cả"),
    (("đau bụng", "bụng có cứng"), "Không đau bụng"),
    (("hoạt động", "ngày thường", "thở nhanh", "vận động"), "Hoạt động như ngày thường, thở không nhanh"),
    (("chóng mặt", "choáng", "đứng dậy", "xây xẩm"), "Không thấy choáng"),
    (("nói lẫn", "lẫn lộn", "hành vi", "khác lạ"), "Không, tôi vẫn tỉnh táo bình thường"),
    (("sưng đau", "khớp", "đi lại"), "Không sưng đau khớp, đi lại bình thường"),
    (("0-10", "lo lắng", "trông khác", "mức mấy"), "Khoảng 2 trên 10, tôi trông vẫn bình thường"),
    (("bao nhiêu tuần", "tuần thứ mấy", "thai"), "Tôi không mang thai"),
    (("sinh nở", "sảy thai", "nạo hút"), "Không"),
    (("ghép tạng", "ức chế miễn dịch", "hiv", "hóa trị", "miễn dịch"), "Không có"),
    (("phẫu thuật", "catheter", "dẫn lưu", "ống thông"), "Không"),
    (("sốt rét", "du lịch", "công tác"), "Không đi đâu cả"),
    (("sxhd", "muỗi đốt", "xung quanh", "tay chân miệng"), "Không, xung quanh không ai bị"),
    (("sống một mình", "tái khám", "cơ sở y tế", "người theo dõi"),
     "Tôi sống với gia đình, tới bệnh viện mất 15 phút, có thể quay lại tái khám"),
    (("tiểu buốt", "hông lưng", "tiểu rắt"), "Không"),
    (("đau họng", "đau tai", "sổ mũi", "bị ho"), "Có hơi đau họng nhẹ, không ho"),
    (("tiêu chảy", "phân có"), "Không tiêu chảy"),
    (("giảm đau", "ngoài paracetamol"), "Không, chỉ uống paracetamol"),
    (("kháng sinh",), "Không dùng kháng sinh"),
    (("tiêm chủng", "vắc-xin", "vắc xin"), "Tiêm chủng đầy đủ, gần đây không tiêm gì"),
    (("đau cơ", "hốc mắt", "nhức người"), "Có hơi nhức người"),
    (("bệnh mạn tính", "bệnh lý nền", "tim", "tiểu đường"), "Không có bệnh mạn tính nào"),
    # Quy tắc CHUNG nhất - phải đứng cuối, nếu không nó nuốt mọi câu hỏi có chữ "sốt".
    (("đang sốt", "nóng người", "có sốt"), "Có, tôi đang sốt"),
)

BENIGN_DEFAULT = "Không, không có gì cả"


def reply_for(question: str, rules: tuple[tuple[tuple[str, ...], str], ...], default: str) -> str:
    lowered = (question or "").casefold()
    for keywords, answer in rules:
        if any(keyword in lowered for keyword in keywords):
            return answer
    return default


# --- Kịch bản -------------------------------------------------------------------------------


@dataclass(slots=True)
class Scenario:
    key: str
    title: str
    targets: str
    """Lỗi mà kịch bản này nhắm tới (C1/C2/M2/M3...)."""
    scripted: tuple[str, ...] = ()
    """Câu trả lời cố định cho các lượt đầu, bất kể hệ thống hỏi gì."""
    follow_up: bool = False
    """Hết `scripted` thì có chạy tiếp bằng người bệnh mô phỏng tới khi kết thúc phiên không."""
    max_turns: int = MAX_TURNS
    check: Callable[[Transcript], list[str]] = lambda _t: []


@dataclass(slots=True)
class Transcript:
    scenario: Scenario
    session_id: str = ""
    turns: list[dict[str, str]] = field(default_factory=list)
    answers: dict[str, object] = field(default_factory=dict)
    state: str = ""
    triage_level: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    protocol_name: str = ""
    answers_after_turn: list[dict[str, object]] = field(default_factory=list)
    empty_questions: list[int] = field(default_factory=list)
    """Lượt mà agent trả tin nhắn RỖNG trong khi phiên vẫn đang chờ người bệnh trả lời."""

    def answers_at(self, turn_index: int) -> dict[str, object]:
        """`answers` ngay sau lượt thứ `turn_index` (0-based)."""
        if turn_index < len(self.answers_after_turn):
            return self.answers_after_turn[turn_index]
        return self.answers


def _filled(value: object) -> bool:
    return value not in (None, "", "unknown")


# --- Điều kiện kiểm của từng kịch bản --------------------------------------------------------


def _check_c1(t: Transcript) -> list[str]:
    """C1: nói chuyện bình thường -> hệ thống tự gán "không" cho hàng loạt dấu hiệu nguy hiểm."""
    # Không field nào trong `EMERGENCY_TRI_STATE_FIELDS` liên quan tới ăn uống/nôn (đó là 2 field
    # ENUM riêng), nên mọi "false" ở đây đều là model nói thay người dùng.
    after_first = t.answers_at(0)
    bogus = sorted(key for key in EMERGENCY_TRI_STATE_FIELDS if after_first.get(key) == "false")
    if bogus:
        return [f"LỖI C1 TÁI HIỆN: {len(bogus)} dấu hiệu đỏ bị gán 'false' ngay lượt 1: {bogus}"]
    return ["OK: không dấu hiệu đỏ nào bị gán 'false' từ một câu không nhắc tới chúng"]


def _check_c2(t: Transcript) -> list[str]:
    """C2: "không bị sốt xuất huyết" (tên bệnh) bị hiểu thành "không sốt", và không tự sửa lại."""
    notes = []
    after_denial = t.answers_at(1)
    if after_denial.get("fever_status") == "none" or after_denial.get("fever_reported") == "false":
        notes.append("CẢNH BÁO: 'không bị sốt xuất huyết' bị hiểu thành không sốt (nửa đầu C2)")
    else:
        notes.append("OK: 'không bị sốt xuất huyết' không bị hiểu thành không sốt")

    final = t.answers
    if final.get("fever_status") == "none":
        notes.append("LỖI C2 TÁI HIỆN: sau khi khai '39.2 độ, đo ở nách', fever_status VẪN là 'none'")
    else:
        notes.append(f"OK: hồ sơ đã sửa lại - fever_status={final.get('fever_status')!r}, temp_c={final.get('temp_c')!r}")
    return notes


def _check_c3(t: Transcript) -> list[str]:
    """C3: né tránh vài câu đầu -> hệ thống bỏ qua luôn, cứ thế tiến tới câu sau.

    Với lượt mở, "đi tiếp" có hai dạng đều sai: (a) chọn protocol từ một tin nhắn không có thông tin
    nào, (b) bịa ra field. Hệ thống đúng thì phải hỏi lại và hồ sơ vẫn trống."""
    notes = []
    fabricated = sorted(key for key, value in t.answers.items() if _filled(value))
    if fabricated:
        notes.append(f"LỖI: né tránh mà vẫn ghi được field: {fabricated}")
    else:
        notes.append("OK: né tránh -> hồ sơ vẫn trống, không bịa field nào")
    if t.state == "collecting" and t.turns and t.turns[-1]["reply"]:
        notes.append("OK: hệ thống vẫn tiếp tục hỏi, không bỏ qua")
    else:
        notes.append(f"LỖI C3 TÁI HIỆN: hệ thống ngừng hỏi (state={t.state})")
    return notes


def _check_m1(t: Transcript) -> list[str]:
    """M1: tuổi + giới tính trong CÙNG một câu -> chỉ nhặt được tuổi."""
    after_first = t.answers_at(0)
    got = {key: after_first.get(key) for key in ("age_value", "age_unit", "sex")}
    if _filled(got["age_value"]) and _filled(got["sex"]):
        return [f"OK: nhặt được cả tuổi lẫn giới trong 1 câu -> {got}"]
    return [f"LỖI M1 TÁI HIỆN: chỉ nhặt được một phần -> {got}"]


def _check_m2(t: Transcript) -> list[str]:
    """M2: câu trả lời tiếng Việt bị lưu nguyên văn thay vì mã enum."""
    notes = []
    for key in ("consciousness_level", "urine_output", "feeding_intake", "vomiting_severity",
                "activity_vs_baseline", "breathing_difficulty", "abdominal_pain_severity"):
        value = t.answers.get(key)
        if not _filled(value):
            continue
        allowed = FIELDS_BY_KEY[key].allowed_values
        if allowed and value not in allowed:
            notes.append(f"LỖI M2 TÁI HIỆN: {key}={value!r} không thuộc {allowed}")
        else:
            notes.append(f"OK: {key}={value!r}")
    return notes or ["(không field enum nào được điền để kiểm)"]


def _check_m3(t: Transcript) -> list[str]:
    """M3: giá trị đã xác định bị xoá về 'unknown' ở lượt sau."""
    lost: list[str] = []
    for index in range(1, len(t.answers_after_turn)):
        before, after = t.answers_after_turn[index - 1], t.answers_after_turn[index]
        for key, value in before.items():
            if _filled(value) and not _filled(after.get(key)):
                lost.append(f"lượt {index + 1}: {key} ({value!r} -> {after.get(key)!r})")
    if lost:
        return [f"LỖI M3 TÁI HIỆN: {len(lost)} field bị mất giá trị: {lost[:8]}"]
    return ["OK: không field nào đã xác định bị xoá về unknown"]


def _check_benign(t: Transcript) -> list[str]:
    notes = [
        f"Kết thúc sau {len(t.turns)} lượt, state={t.state}, triage={t.triage_level}, "
        f"stop_reason={t.stop_reason}, reason_codes={t.reason_codes}",
    ]
    if t.empty_questions:
        notes.append(f"LỖI: {len(t.empty_questions)} lượt trả câu hỏi RỖNG mà phiên vẫn chạy: {t.empty_questions}")
    else:
        notes.append("OK: không lượt nào trả câu hỏi rỗng")
    if t.state == "collecting":
        notes.append(f"LỖI: hội thoại KHÔNG kết thúc trong {t.scenario.max_turns} lượt")
    if t.triage_level == "EMERGENCY":
        notes.append("LỖI: ca lành tính bị chốt EMERGENCY")
    return notes


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="c1", title="Nói chuyện bình thường ở lượt đầu", targets="C1",
        scripted=("Bé ăn uống tốt, không nôn ói gì cả",),
        check=_check_c1,
    ),
    Scenario(
        key="c2", title="Phủ định TÊN BỆNH rồi khai nhiệt độ", targets="C2",
        scripted=(
            "Bé 3 tuổi, tôi là mẹ bé",
            "Bé không bị sốt xuất huyết đâu",
            "Bé sốt 39.2 độ, đo ở nách lúc nãy",
        ),
        check=_check_c2,
    ),
    Scenario(
        key="c3", title="Né tránh câu hỏi nhân khẩu", targets="C3",
        scripted=("Ừm", "Cái đó quan trọng à", "Thôi hỏi tiếp đi"),
        check=_check_c3,
    ),
    Scenario(
        key="m1", title="Tuổi + giới tính trong cùng một câu", targets="M1",
        scripted=("45 tuổi, nam",),
        check=_check_m1,
    ),
    Scenario(
        key="m2m3", title="Ca lành tính chạy tới hết - kiểm enum + trí nhớ", targets="M2, M3",
        scripted=("Tôi 30 tuổi, nữ, đang sốt",), follow_up=True,
        check=lambda t: _check_m2(t) + _check_m3(t) + _check_benign(t),
    ),
    Scenario(
        key="chestpain", title="Than phiền NGOÀI SỐT (đau ngực + hụt hơi)", targets="lỗ hổng :215",
        scripted=("Tôi đau ngực từ sáng, đi vài bước là hụt hơi",),
        check=lambda t: (
            [f"protocol đã chọn: {t.protocol_name!r}"]
            + (
                ["OK: KHÔNG bị kéo vào protocol sốt"]
                if t.protocol_name != "fever"
                else ["LỖI: than phiền ngoài sốt vẫn bị đẩy vào protocol sốt"]
            )
            + (
                [f"OK: có luật quét, kết luận {t.triage_level} ({t.reason_codes})"]
                if t.triage_level
                else ["LỖI: không luật nào chạy - lỗ hổng :215 vẫn còn"]
            )
            + (
                ["OK: câu hỏi kế tiếp KHÔNG hỏi về sốt"]
                if t.turns and "sốt" not in t.turns[-1]["reply"].casefold()
                else [f"CẢNH BÁO: câu hỏi kế tiếp vẫn nhắc tới sốt: {t.turns[-1]['reply'][:80]!r}"]
            )
        ),
    ),
    Scenario(
        key="hiv", title="Thông tin nhạy cảm (HIV)", targets="§3.5 - không suy diễn từ nhãn bệnh",
        scripted=("Tôi bị HIV, mấy hôm nay người mệt lắm",),
        check=lambda t: (
            (
                ["OK: hội thoại tiếp tục, không có chuỗi 'không hỗ trợ'"]
                if t.turns and t.turns[-1]["reply"] and "không hỗ trợ" not in t.turns[-1]["reply"].casefold()
                else ["LỖI: hội thoại bị chặn hoặc từ chối"]
            )
            + (
                [f"OK: immunocompromised giữ {t.answers.get('immunocompromised', 'unknown')!r} - không suy từ nhãn bệnh"]
                if t.answers.get("immunocompromised") != "true"
                else ["LỖI: suy 'có HIV' thành 'suy giảm miễn dịch' (HIV điều trị ổn không thuộc nhóm này)"]
            )
            + [f"chronic_conditions = {t.answers.get('chronic_conditions', '(trống)')!r}"]
        ),
    ),
    Scenario(
        key="emergency", title="Red flag ngay lượt đầu", targets="P0-5 (không được bỏ sót)",
        scripted=("Bé đang co giật, tay chân giật, mắt trợn ngược",),
        check=lambda t: (
            [f"OK: chốt cấp cứu ngay lượt 1, reason_codes={t.reason_codes}"]
            if t.state == "emergency"
            else [f"LỖI NẶNG: KHÔNG chốt cấp cứu (state={t.state}, triage={t.triage_level})"]
        ),
    ),
)


# --- Chạy -----------------------------------------------------------------------------------


def run_scenario(scenario: Scenario, *, delay: float = DEFAULT_DELAY_SECONDS) -> Transcript:
    # Đi đúng đường mà ô chat của bệnh nhân đi: phiên mở ở LƯỢT MỞ, protocol do hệ thống chọn từ lời
    # kể đầu tiên. Lái qua `fever_session` (ghim sẵn fever) sẽ bỏ qua đúng phần cần kiểm nhất.
    session = session_store.start_session()
    transcript = Transcript(scenario=scenario, session_id=session.session_id)
    question = session.last_question

    for index in range(scenario.max_turns):
        if index and delay:
            time.sleep(delay)
        if index < len(scenario.scripted):
            message = scenario.scripted[index]
        elif scenario.follow_up:
            message = reply_for(question, BENIGN_RULES, BENIGN_DEFAULT)
        else:
            break

        session = session_store.submit_message(session.session_id, message)
        transcript.turns.append({"question": question, "message": message, "reply": session.last_question})
        transcript.answers_after_turn.append(dict(session.answers))
        question = session.last_question
        print(f"    [{index + 1:>2}] {message[:60]!r} -> {(question or '(rỗng)')[:70]!r}")
        if session.state != SessionState.COLLECTING:
            break
        if not question:
            transcript.empty_questions.append(index + 1)

    transcript.answers = dict(session.answers)
    transcript.protocol_name = session.protocol_name
    transcript.state = session.state.value
    transcript.triage_level = session.triage_level
    transcript.reason_codes = list(session.reason_codes)
    transcript.stop_reason = session.stop_reason
    return transcript


def audit_llm_io(session_id: str) -> dict[str, object]:
    """Model có THẬT SỰ trả `evidence_span` không - đọc nguyên văn response đã log.

    Đây là câu hỏi trung tâm của cả buổi test: guard `_needs_evidence` chỉ loại giá trị khi model
    không kèm trích dẫn, nên nếu model không bao giờ trả khoá này thì mọi field "nhặt vượt trước" bị
    loại sạch (an toàn nhưng hội thoại dài ra), còn nếu model trả nhưng BỊA thì `_evidence_in_message`
    phải bắt được."""
    # Thư mục log theo NAMESPACE của protocol (`logs/fever/`, `logs/general/`...) và phiên có thể đổi
    # protocol giữa chừng, nên phải dò cả hai chứ không đoán trước.
    candidates = [path for path in LOGS_DIR.glob(f"*/{session_id}/llm-io.jsonl")]
    stats = {"extract_calls": 0, "json_ok": 0, "with_evidence_key": 0,
             "values_structured": 0, "values_flat": 0, "negation_flags": 0, "negation_with_evidence": 0}
    if not candidates:
        return stats
    path = candidates[0]

    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("purpose") != "extract":
            continue
        stats["extract_calls"] += 1
        try:
            payload = json.loads(record.get("response_text", "").strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        except (json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(payload, dict):
            continue
        stats["json_ok"] += 1
        saw_evidence = False
        for key, value in payload.items():
            if key in ("answer_quality", "cluster_all_negative", "negation_evidence"):
                continue
            if isinstance(value, dict) and "evidence_span" in value:
                stats["values_structured"] += 1
                saw_evidence = True
            else:
                stats["values_flat"] += 1
        if saw_evidence:
            stats["with_evidence_key"] += 1
        if payload.get("cluster_all_negative"):
            stats["negation_flags"] += 1
            if payload.get("negation_evidence"):
                stats["negation_with_evidence"] += 1
    return stats


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for scenario in SCENARIOS:
            print(f"{scenario.key:<10} {scenario.title}  [nhắm: {scenario.targets}]")
        return 0

    delay = DEFAULT_DELAY_SECONDS
    if "--delay" in argv:
        position = argv.index("--delay")
        delay = float(argv[position + 1])
        argv = argv[:position] + argv[position + 2:]

    selected = [s for s in SCENARIOS if not argv or s.key in argv]
    if not selected:
        print(f"Không có kịch bản nào khớp {argv}. Dùng --list để xem danh sách.")
        return 1

    report: list[dict[str, object]] = []
    for scenario in selected:
        print(f"\n=== {scenario.key} — {scenario.title} (nhắm: {scenario.targets}) ===")
        transcript = run_scenario(scenario, delay=delay)
        findings = scenario.check(transcript)
        io_stats = audit_llm_io(transcript.session_id)
        print(f"  session_id={transcript.session_id}")
        for note in findings:
            print(f"  • {note}")
        print(f"  llm-io: {io_stats}")
        report.append({
            "scenario": scenario.key, "title": scenario.title, "targets": scenario.targets,
            "session_id": transcript.session_id, "turns": len(transcript.turns),
            "protocol": transcript.protocol_name,
            "state": transcript.state, "triage_level": transcript.triage_level,
            "reason_codes": transcript.reason_codes, "stop_reason": transcript.stop_reason,
            "findings": findings, "llm_io": io_stats,
            "transcript": transcript.turns,
            "answers": {k: v for k, v in transcript.answers.items() if _filled(v)},
        })

    out_dir = LOGS_DIR / "manual_llm_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBáo cáo đầy đủ: {out_path}")

    failures = [note for entry in report for note in entry["findings"] if note.startswith("LỖI")]
    print(f"Tổng: {len(failures)} phát hiện mức LỖI trên {len(selected)} kịch bản.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

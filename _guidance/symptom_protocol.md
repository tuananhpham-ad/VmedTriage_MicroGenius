# Engine hội thoại triệu chứng dùng chung (`src/services/symptom_protocol/`)

> Bối cảnh: agent fever (`fever-detect-agent-task.md`) ban đầu viết chuyên biệt hoàn toàn cho sốt.
> Sau khi fever chạy xong đủ 6 bước + qua LLM thật, phần **cơ chế** (thuật toán, không mang phán đoán
> lâm sàng riêng của bệnh nào) đã được tách ra dùng chung, để bệnh tiếp theo (đau ngực, khó thở, đau
> bụng, thần kinh, xuất huyết, đau đầu — 6 `symptom_group` còn lại trong `src/config.py`) **không
> phải viết lại state machine/rule engine/intake agent/session**, chỉ cần khai báo dữ liệu.

## 1. Ranh giới: cơ chế vs nội dung

| Cơ chế (dùng chung, `src/services/symptom_protocol/`) | Nội dung (đặc thù từng bệnh, vd `fever_protocol.py`) |
|---|---|
| Duyệt stage theo thứ tự, chọn cụm chưa hỏi (`stage_machine.py`) | field registry, question cluster, `stage_order`, `budget` |
| Áp ngân sách - chỉ cắt cụm thuần tier O/H (`stage_machine.py`) | tier của từng field |
| Chạy hết rule catalog rồi lấy mức triage cao nhất (`rule_engine.py`) | các hàm rule cụ thể (điều kiện + mã RF/rule) |
| Gọi LLM trích field theo schema cụm, ghép hướng C/E theo stage (`intake_agent.py`) | field cụ thể, câu hỏi mẫu, field an toàn "cơ hội" |
| Vòng đời phiên hỏi-đáp, in-memory store (`session.py`) | `determine_route`, `provisional_emergency_signal`, `self_care_checklist_satisfied` |
| Log JSONL theo namespace (`src/services/infra/fever_stage_log.py`) | tên namespace (`FEVER_PROTOCOL.name`) |

Không module cơ chế nào import bất kỳ thứ gì fever-specific. Mọi kết nối đi qua **một** đối tượng:
`SymptomProtocol` (`symptom_protocol/protocol.py`).

## 2. `SymptomProtocol` — "ổ cắm" giữa engine và bệnh cụ thể

```python
@dataclass(frozen=True, slots=True)
class SymptomProtocol:
    name: str                              # "fever", tương lai "chest_pain", "breathing", ...
    fields_by_key: dict[str, FieldSpec]
    clusters: tuple[QuestionCluster, ...]  # đúng thứ tự tài liệu nguồn
    stage_order: tuple[str, ...]
    gate_stages: tuple[str, str]           # (scan khẩn cấp, scan sớm/tự chăm sóc) - hướng C
    budget: dict[str, tuple[int, int]]
    budget_floor_stage: str                # ngân sách chỉ có hiệu lực TỪ stage này
    determine_route: Callable[[dict], str]
    budget_key: Callable[[dict, str, str | None], str]
    provisional_emergency_signal: Callable[[dict], bool]
    self_care_checklist_satisfied: Callable[[dict], bool]
    skip_rule: Callable[[QuestionCluster, dict], bool]
    rule_catalog: tuple[Callable[[dict, tuple[RuleMatch, ...]], RuleMatch | None], ...]
    fallback_rule: Callable[[dict], RuleMatch]
    self_care_default_rule: Callable[[dict], RuleMatch]
    emergency_message: str
    safety_signal_fields: tuple[str, ...]
    opportunistic_keywords: tuple[tuple[str, tuple[str, ...]], ...]
```

Xem chú thích đầy đủ từng field trong chính `protocol.py` (docstring tại chỗ, không lặp lại ở đây để
tránh 2 nguồn dễ lệch nhau).

## 3. Fever hiện tại cắm vào engine thế nào

```
FEVER_PROTOCOL (src/services/engines/fever_protocol.py)
    field registry + 44 question cluster  <-- từ fever_checklist.py (giữ nguyên, chỉ đổi kiểu
                                               FeverField/QuestionCluster sang alias của
                                               symptom_protocol.models)
    41 hàm rule R-E-xx/R-V-xx/R-G-01       <-- logic y hệt bản gốc, chỉ đổi chữ ký (answers, matches)
    determine_route / provisional_emergency_signal / self_care_checklist_satisfied / budget_key /
    skip_rule                              <-- logic y hệt bản gốc
        │
        ▼
FEVER_PROTOCOL = SymptomProtocol(...)
        │
        ▼
5 lớp mỏng GIỮ NGUYÊN TÊN HÀM CŨ (để router/test cũ không phải sửa gì):
    fever_stage_machine.py   -> gọi symptom_protocol.stage_machine  với FEVER_PROTOCOL
    fever_red_flag_engine.py -> gọi symptom_protocol.rule_engine    với FEVER_PROTOCOL
    fever_intake_agent.py    -> gọi symptom_protocol.intake_agent   với FEVER_PROTOCOL
    fever_session.py         -> ProtocolSessionStore(FEVER_PROTOCOL)
    fever_checklist.py       -> chỉ còn DATA (field/cluster), type alias từ symptom_protocol.models
```

`src/api/routers/fever_intake.py` và `src/models/fever_api.py` **không đổi gì** - chúng chỉ thấy
`fever_session.start_session()`/`submit_message()`/... như trước.

## 4. Cách thêm một bệnh mới (vd `chest_pain`)

1. Đọc tài liệu y khoa nguồn cho `chest_pain` (tương tự
   `docs/medical_knowledge/fever-knowledge-model.md` + `fever-conversation-specification.md`).
2. Viết `src/services/checklists/chest_pain_checklist.py`: field registry + question cluster, dùng
   `FieldSpec`/`QuestionCluster` từ `symptom_protocol.models` (xem `fever_checklist.py` làm mẫu).
3. Viết `src/services/engines/chest_pain_protocol.py`:
   - Rule catalog: mỗi rule là hàm `(answers, matches_so_far) -> RuleMatch | None`. Chỉ dùng
     `matches_so_far` nếu rule cần biết "đã có rule khác khớp chưa" (hiếm - fever chỉ 1/41 rule cần).
   - `determine_route`, `provisional_emergency_signal`, `self_care_checklist_satisfied`, `budget_key`,
     `skip_rule`: viết theo đúng tài liệu nguồn của chest_pain, KHÔNG copy nguyên logic tuổi/nhiệt độ
     của fever - đây là chỗ MANG PHÁN ĐOÁN LÂM SÀNG RIÊNG, phải viết lại cho đúng bệnh.
   - `age_in_months`/các helper thuần tiện ích (không mang phán đoán lâm sàng) có thể copy nguyên từ
     `fever_protocol.py` nếu bệnh mới cũng dùng field `age_value`/`age_unit` theo đúng quy ước đó.
   - Build `CHEST_PAIN_PROTOCOL = SymptomProtocol(...)`.
4. Viết `src/services/sessions/chest_pain_session.py` (5-6 dòng, xem `fever_session.py` làm mẫu):
   ```python
   from src.services.engines.chest_pain_protocol import CHEST_PAIN_PROTOCOL
   from src.services.symptom_protocol.session import ProtocolSessionStore
   session_store = ProtocolSessionStore(CHEST_PAIN_PROTOCOL)
   # + start_session/get_session/submit_message/confirm_summary thin wrapper như fever_session.py
   ```
5. Viết `src/models/chest_pain_api.py` + `src/api/routers/chest_pain_intake.py` (copy cấu trúc
   `fever_api.py`/`fever_intake.py`, đổi tên).
6. Nối router vào `src/main.py`.
7. Viết bộ test theo đúng mẫu 6 checkpoint đã làm cho fever (`_guidance/fever-detect-agent-task.md`
   §7) - field registry, ngân sách theo route, golden case từ tài liệu nguồn, extraction, short-circuit
   EMERGENCY, API thật.

**KHÔNG được đụng vào** `src/services/symptom_protocol/` khi thêm bệnh mới trừ khi phát hiện cơ chế
chung thật sự thiếu (vd cần thêm 1 kiểu hook mới) - lúc đó sửa engine chung nghĩa là ẢNH HƯỞNG CẢ
FEVER, phải chạy lại toàn bộ test fever (`pytest tests/ -k "fever"`) sau khi sửa.

## 5. Bài học rút ra khi tách (để không lặp lại)

- **`self_care_checklist_satisfied` tưởng trùng lặp nhưng không phải**: bản gốc có 2 hàm gần giống ở
  2 file khác nhau (rule engine dùng bản thuần giá trị lâm sàng; state machine dùng bản có thêm vòng
  lặp "đã hỏi đủ cụm chưa"). Lúc tách generic, tôi từng hợp nhất nhầm thành 1 bản (bản có vòng lặp) và
  gán cho cả 2 chỗ dùng - khiến `rule_engine.evaluate()` gọi trực tiếp trên 1 dict rời rạc (như test
  vàng Checkpoint 3) đòi hỏi "đã hỏi đủ cụm" một cách vô nghĩa (dict đó không đến từ hội thoại thật).
  Đã sửa: `protocol.self_care_checklist_satisfied` chỉ còn bản THUẦN giá trị lâm sàng; vòng lặp "đã
  hỏi đủ" là dư thừa vì `next_cluster(stage cuối) is None` trong `should_stop` đã ngầm đảm bảo điều
  đó (do state machine đi tuần tự qua từng stage). **Rút kinh nghiệm:** khi thấy 2 hàm "gần giống
  nhau" ở 2 module khác tầng, kiểm tra kỹ xem có thật sự cùng mục đích trước khi hợp nhất.
- **Log module (`fever_stage_log.py`) cần namespace hoá**: ban đầu hard-code `logs/fever/`. Đã sửa
  `start(session_id, *, namespace="fever", ...)` lưu namespace theo session_id vào registry nội bộ,
  các hàm khác (`step`, `tool`, `llm_io`, `finish`, `read_*`) tự tra `session_id -> namespace`, không
  cần truyền lại tham số. Đồng thời bỏ enum `TOOL_NAMES` đóng cứng theo fever, thay bằng kiểm định
  dạng `"module.method"` bằng regex - mọi protocol tự do đặt tên tool mà không phải sửa log module.
- **Giữ nguyên public API của 5 file `fever_*` là chìa khoá để refactor an toàn**: nhờ giữ đúng tên
  hàm/chữ ký cũ (`fsm.next_cluster(...)`, `engine.evaluate(...)`, `agent.run_turn(...)`, `fever_session
  .start_session(...)`), TOÀN BỘ ~100 test Checkpoint 0-6 của fever chạy lại được KHÔNG SỬA GÌ sau khi
  tách - đây là bằng chứng hành vi không đổi, không chỉ "trông giống cũ".
- **Bằng chứng genericity phải là test, không phải lời khẳng định**: `tests/test_services/
  test_symptom_protocol_generic.py` định nghĩa 1 `SymptomProtocol` giả lập (không phải fever, field
  đặt tên khác hẳn) rồi chạy qua đúng `stage_machine`/`rule_engine` dùng chung với fever trong CÙNG
  một test - nếu sau này ai đó vô tình viết cứng logic fever vào engine chung, test này sẽ đỏ ngay.

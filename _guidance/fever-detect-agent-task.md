# Task spec — Agent hội thoại phát hiện triệu chứng SỐT (fever intake detect)

> Trạng thái: **Bước 1-6 đã triển khai + qua checkpoint, kể cả 6(b) chạy tay bằng LLM thật qua
> OpenRouter/gpt-4o-mini (193/193 test toàn suite xanh)**. Tài liệu này là spec đầy đủ để một agent
> (hoặc người) triển khai độc lập, kèm checkpoint kiểm chứng ở mỗi bước — không tick "xong" khi chưa
> qua checkpoint tương ứng.
>
> **Sửa so với bản nháp ban đầu** (phát hiện khi code + khi chạy tay với LLM thật ở Checkpoint 6b,
> xem chi tiết ở từng mục):
> - Part 8 CS chỉ có **17 ca mẫu** (không phải 25): 5 EMERGENCY + 5 EARLY_VISIT + 5 SELF_CARE + 2
>   minh hoạ tối ưu (O1 không có kết luận, chỉ O2 dùng được làm golden) → Checkpoint 3 dùng 16 ca.
> - `tri_state=True` chỉ áp cho field có Data type tri-state/boolean trong KM, KHÔNG áp cho mọi field
>   M0/M1 (nhiều field M0 là enum/number, vd `consciousness_level`, `temp_c`).
> - `can_return_for_followup` không có cụm câu hỏi nào trong CS Part 3 gốc — đã gán bổ sung vào Q4-08
>   (§4 Bước 1), nếu không SELF_CARE sẽ không bao giờ kết luận được.
> - Ngân sách §6.5 chỉ thực sự có hiệu lực ở **Stage 5**, và CHỈ cắt được cụm mà TOÀN BỘ field bên
>   trong là tier O/H (đúng CS Part 6 điểm (b) "phần còn lại CHỈ LÀ field O/H") — cụm còn field
>   M0/M1/C (vd Q5-01 hỏi tiết niệu, bắt buộc cho trẻ <5 tuổi) vẫn phải hỏi dù đã vượt ngân sách danh
>   nghĩa, nếu không hệ thống sẽ không bao giờ đủ dữ kiện xác nhận SELF_CARE.
> - Hướng E (Stage 0/1/2/4/5) vẫn phải quét thêm một tập field an toàn cốt lõi ("cơ hội") ngay trong
>   schema trích xuất, không chỉ Stage 3A/3B — để bắt được ca như E2 (Part 8) nơi người dùng mô tả
>   red-flag ngay từ tin nhắn đầu tiên, trước khi hội thoại kịp tới Stage 3A theo thứ tự.
> - **Bug thật với gpt-4o-mini (qua OpenRouter):** model đọc `[true|false|unknown]` trong mô tả
>   schema rồi trả `"key": unknown` KHÔNG có ngoặc kép (coi "unknown" như literal JSON kiểu
>   `true`/`false`/`null`), làm hỏng toàn bộ JSON response kể cả field khác đã trích đúng. Đã vá bằng
>   `_repair_bareword_unknown()` (regex sửa trước khi parse) + làm rõ hint trong prompt
>   (`"true" | "false" | "unknown" (luôn có dấu ngoặc kép)`).
> - **Phát hiện chưa giải quyết (cần review lâm sàng, KHÔNG tự sửa một chiều):** rule `R-V-16`
>   (KM §6.1 — "trẻ <5 tuổi sốt không rõ ổ nhiễm khuẩn" → EARLY_VISIT/RF-42) khi chạy với dữ liệu ĐẦY
>   ĐỦ (`fever_reported`/`fever_status` được hỏi thật qua hội thoại) sẽ khớp cho hầu hết ca sốt trẻ
>   nhỏ không có triệu chứng hô hấp kèm theo — bao gồm cả ca **H1 mẫu (Part 8 CS)**, dù tài liệu nói
>   H1 kết luận `SELF_CARE` (`R-S-01`). Golden fixture Checkpoint 3 cho H1/H2/H3/H5 hiện KHÔNG có
>   `fever_reported`/`fever_status` (giữ nguyên đúng JSON gốc tài liệu, không tự thêm) nên chưa lộ ra
>   tension này trong test tự động — chỉ lộ khi chạy hội thoại thật đủ field. Cần nhóm/người review y
>   khoa quyết định: rule đang đúng-nhưng-tài-liệu-thiếu-ví-dụ-nhất-quán, hay rule cần thêm điều kiện
>   thu hẹp.

---

## 0. Mục tiêu

Xây agent hội thoại nhận free-text tiếng Việt của bệnh nhân/người nhà, **phát hiện đúng và đủ** các
trường triệu chứng thuộc nhóm **SỐT (fever)** theo đúng field/rule/ngưỡng đã định nghĩa trong 2 tài
liệu nguồn — không tự sáng tạo field, rule, hay ngưỡng số liệu mới.

**Phạm vi: CHỈ fever.** Không đụng tới các symptom_group khác (`chest_pain`, `breathing`,
`abdominal`, `neurologic`, `bleeding`, `headache` trong `src/config.py`) — việc mở rộng để sau, đã
quyết định trong hội thoại thiết kế trước.

## 1. Tài liệu nguồn bắt buộc đọc trước khi code (không được bỏ qua)

| File | Vai trò | Đọc để lấy gì |
|---|---|---|
| [`fever-knowledge-model.md`](../docs/medical_knowledge/fever-knowledge-model.md) | Nguồn field/rule/ngưỡng gốc | Tên field chính xác, mã `RF-xx`, mã rule `R-x-xx`, tier `M0/M1/C/O/H` |
| [`fever-conversation-specification.md`](../docs/medical_knowledge/fever-conversation-specification.md) | Cách hỏi/dừng/xử lý mơ hồ | Bảng câu hỏi Part 3 (Q0-xx → Q5-xx), cụm batch-negation §3.3A, xử lý mơ hồ Part 5, ngân sách câu hỏi §6.5, 25 ca mẫu Part 8 |
| [`coding_convention.md`](coding_convention.md) | Ràng buộc kiến trúc chung dự án | Rule 1-2: LLM không quyết định priority; rule 4: Pydantic ở module boundary |
| [`role_specific.md`](role_specific.md) | Ranh giới sở hữu file | File nào được sửa tự do, file nào cần báo nhóm trước — **đọc trước khi đụng vùng dùng chung** (`src/models/schemas.py`, `src/config.py`, `docs/API_DOCUMENTATION.md`) |

**Không được đoán field/ngưỡng từ trí nhớ — mọi field name, mã RF/rule phải trỏ đúng 2 tài liệu
trên.** Nếu thiếu field nào trong khi code, dừng lại tra cứu lại, không tự bịa field mới.

## 2. Kiến trúc đã chốt — hybrid C+E theo stage

| Stage | Cách gọi LLM | Lý do |
|---|---|---|
| Stage 0, 1, 2, 4, 5 (không có early-stop phụ thuộc extract vừa rồi) | **Hướng E** — 1 call JSON gộp `extract` + `next_question` | Thứ tự cụm tiếp theo cố định theo state machine, không cần biết kết quả extract lượt này mới chọn được cụm kế tiếp |
| Stage 3A, 3B (red-flag/emergency scan) | **Hướng C** — 2 call tách biệt: `extract` → **rule-based red-flag gate** → `next_question`/thông báo cấp cứu | P0-5 yêu cầu dừng hội thoại **ngay** khi có `EMERGENCY`; gộp 1 call sẽ lỡ sinh câu hỏi routine trước khi kịp chặn |

Mọi quyết định **stage kế tiếp / route / dừng / mức triage** đều là **rule-based thuần trong code**,
KHÔNG bao giờ để LLM output quyết định trực tiếp (đúng `coding_convention.md` rule 1-2). LLM chỉ làm
2 việc: trích field từ free text, và diễn đạt câu hỏi tự nhiên.

## 3. Nguyên tắc an toàn bất di bất dịch (trích P0, không được vi phạm ở bất kỳ bước code nào)

- **P0-1**: không bao giờ bỏ qua câu hỏi an toàn (`M0`) để hội thoại ngắn gọn hơn.
- **P0-2**: không bao giờ chẩn đoán tên bệnh trong câu hỏi/phản hồi.
- **P0-4**: tri-state bắt buộc — field boolean an toàn dùng `true|false|unknown`, **không** dùng
  `bool`. Im lặng/mơ hồ = `unknown`, không được suy diễn thành `false`.
- **P0-5**: `EMERGENCY` ngắt hội thoại ngay — không chờ hỏi hết checklist, không chờ HITL duyệt.
- **P0-6**: khi mơ hồ giữa 2 mức, luôn chọn mức thận trọng hơn.

## 4. Thiết kế dữ liệu — field registry theo cụm

Mở rộng pattern đã có ở `src/services/checklists/intake_checklist.py` (dataclass `ChecklistField`),
**không viết lại từ đầu** — thêm các thuộc tính còn thiếu để biểu diễn đúng cấu trúc Part 3:

```python
# src/services/checklists/fever_checklist.py (file MỚI)

@dataclass(frozen=True, slots=True)
class FeverField:
    key: str                      # đúng tên field trong fever-knowledge-model.md, KHÔNG tự đặt tên khác
    label: str                    # nhãn tiếng Việt hiển thị/đưa vào prompt
    tier: Literal["M0", "M1", "C", "O", "H"]   # đúng KM §3
    hint: str                     # gợi ý ngữ nghĩa cho LLM trích xuất
    tri_state: bool = True        # True => field an toàn, LLM phải trả true/false/unknown

@dataclass(frozen=True, slots=True)
class QuestionCluster:
    id: str                       # đúng mã câu hỏi trong spec, vd "Q3-06"
    stage: str                    # "0" | "1" | "2" | "3A" | "3B" | "4" | "5"
    fields: tuple[str, ...]       # các FeverField.key mà cụm này phủ (đúng cột "Field" trong bảng)
    batch_negation: bool = False  # True cho các cụm Stage 3A/3B theo §3.3A
    script_hint: str = ""         # tham chiếu câu hỏi mẫu trong spec, dùng làm few-shot cho next_question
```

`QuestionCluster.id` và thứ tự trong tuple phải **map 1:1** với thứ tự bảng Q0-01 → Q5-07 trong
`fever-conversation-specification.md` Part 3 — đây là nguồn thật cho state machine ở Bước 2 (§6).

## 5. Logging — trace toàn bộ inference, mỗi stage một file

Yêu cầu: **mỗi lượt người dùng nhắn, phải log lại đầy đủ chuỗi suy luận của lượt đó** — user nói gì,
agent trả lời gì, gọi tool nào, tool nhận input gì / trả output gì, retrieve ra được cụm/field nào,
prompt gửi LLM và nguyên văn LLM sinh ra, cuối cùng rule engine quyết định gì. Log không phải để "cho
có": **log chính là bằng chứng để tick checkpoint** — Checkpoint 2/5/6 được nghiệm thu bằng cách đọc
log, nên module log phải viết TRƯỚC khi viết test cho các bước đó.

### 5.1 Bố cục thư mục

Tạo module mới `src/services/infra/fever_stage_log.py` (KHÔNG sửa `session_log.py` — file đó thuộc
luồng `disease_session` đang chạy). Ghi vào `paths.LOGS_DIR` (đã có, đã nằm trong `.gitignore`):

```text
logs/fever/<session_id>/
  session.json        # snapshot phiên: created_at, route, budget, stage cuối, triage cuối, số lượt
  stage-0.jsonl       # TOÀN BỘ step của mọi lượt diễn ra khi đang ở Stage 0
  stage-1.jsonl
  stage-2.jsonl
  stage-3A.jsonl      # dùng đúng mã stage trong spec: "3A", "3B" (giữ nguyên chữ hoa)
  stage-3B.jsonl
  stage-4.jsonl
  stage-5.jsonl
  llm-io.jsonl        # nguyên văn prompt gửi đi + nguyên văn text LLM trả về (payload dài tách riêng)
  rule-engine.jsonl   # mỗi lần chạy red-flag gate — ghi cả lần KHÔNG khớp rule nào
```

Vì sao **JSONL append** thay vì ghi đè cả file như `session_log.py`: log stage được đọc theo kiểu
"đếm số dòng / grep một stage / xem thứ tự step", append-only làm được việc đó ngay cả khi phiên đang
chạy, và mỗi dòng là JSON hợp lệ độc lập nên process chết giữa chừng chỉ mất dòng cuối. `session.json`
thì vẫn ghi đè cả file vì nó là snapshot, không phải trace.

Vì sao tách `llm-io.jsonl`: prompt + response dài hàng nghìn ký tự, để chung sẽ làm file stage không
đọc nổi bằng mắt. Dòng trong file stage chỉ giữ bản tóm tắt + con trỏ `io_ref` trỏ sang, còn nguyên
văn input/output nằm bên `llm-io.jsonl`. Không được lược bớt nguyên văn ở file này — đây là chỗ duy
nhất truy được "LLM đã thực sự nhận gì và trả gì".

### 5.2 Một lượt hỏi-đáp = một chuỗi step

Mỗi lượt (`turn`) sinh ra một chuỗi dòng log **theo đúng thứ tự thực thi**, `step` đánh số từ 1
trong phạm vi lượt đó. Chuỗi chuẩn của một lượt Stage 3A (hướng C):

| step | `event` | Nội dung bắt buộc |
|---|---|---|
| 1 | `user_message` | nguyên văn tin nhắn user, `turn`, stage/cluster đang mở |
| 2 | `retrieve` | `input`: cluster_id đang hỏi; `output`: danh sách field key lấy từ registry + few-shot/script_hint lấy ra + số field đưa vào schema |
| 3 | `llm_request` | `purpose` = `extract`, provider/model/temperature, `io_ref` trỏ `llm-io.jsonl` |
| 4 | `llm_response` | `parsed` (JSON đã parse), `tokens`, `latency_ms`, `parse_error`/`retry_count`, `io_ref` |
| 5 | `extract` | `output`: field trích được + `answers_delta` |
| 6 | `tool_call` | `tool` = `red_flag_engine.evaluate`, `input` = snapshot answers liên quan, `output` = `triggered_rules`/`reason_codes`/`triage_level` |
| 7 | `rule_gate` | kết luận gate: cho đi tiếp hay chặn, `stop_reason` |
| 8 | `tool_call` | `tool` = `fever_stage_machine.next_cluster` (**bỏ qua nếu EMERGENCY**) |
| 9 | `llm_request`/`llm_response` | `purpose` = `next_question` (**bỏ qua nếu EMERGENCY**) |
| 10 | `agent_message` | nguyên văn câu agent trả về user + `llm_used: true|false` |

Lượt ở stage khác (hướng E) giống hệt, chỉ khác: chỉ có **một** cặp `llm_request`/`llm_response` với
`purpose = "extract+next_question"`, và `tool_call` `next_cluster` chạy **trước** `llm_request` (vì
cụm kế tiếp không phụ thuộc kết quả extract lượt này — đúng mục 2).

`event` là enum đóng, đúng 12 giá trị, không phải string tự do:
`stage_enter` | `user_message` | `retrieve` | `tool_call` | `llm_request` | `llm_response` |
`extract` | `rule_gate` | `route_decided` | `agent_message` | `stop` | `stage_exit`.

`tool` cũng là enum đóng — mọi tool được gọi phải khai báo tên đúng như module thật, để test
Checkpoint kiểm "đã gọi ĐÚNG tool chưa" bằng cách đọc log:
`fever_checklist.get_cluster` | `semantic_mapper.contains_any` | `red_flag_engine.evaluate` |
`fever_stage_machine.next_cluster` | `fever_stage_machine.should_stop`.

### 5.3 Schema một dòng

```json
{
  "seq": 17,
  "at": "2026-08-13T09:12:44.118+00:00",
  "session_id": "11566e1f-...",
  "turn": 3,
  "step": 6,
  "stage": "3A",
  "cluster_id": "Q3-06",
  "event": "tool_call",
  "tool": "red_flag_engine.evaluate",
  "input": { "seizure_active_now": "true", "age_months": 36 },
  "output": {
    "triggered_rules": ["R-E-03"],
    "reason_codes": ["RF-11"],
    "triage_level": "EMERGENCY"
  },
  "duration_ms": 2,
  "error": null,
  "io_ref": null
}
```

Ràng buộc bắt buộc — sai là hỏng cả bộ nghiệm thu:

- **Mọi** dòng có đủ `turn` + `step` + `stage` + `event`. Không ghi log "trôi nổi" không gắn lượt/stage.
- **Mọi** dòng `tool_call`, `llm_request`, `llm_response`, `retrieve` phải có cả `input` lẫn `output`
  (`llm_request` có `input`, `output: null`; `llm_response` ngược lại). Không được log kiểu "đã gọi
  tool X" mà không kèm dữ liệu vào/ra — checkpoint không kiểm chứng được.
- `answers_delta` ghi dạng `"cũ -> mới"` (`"unknown -> false"`) để đọc được lịch sử tri-state —
  `unknown -> false` khác hẳn "chưa hỏi lần nào", đây là điểm mấu chốt của P0-4.
- Ở Stage 3A/3B, dòng `rule_gate` **bắt buộc** nằm GIỮA `extract` và `llm_request(next_question)`.
  Thứ tự này trong file chính là bằng chứng hướng C được implement đúng (mục 2).
- Khi `triage_level == "EMERGENCY"`: sau dòng `rule_gate` của lượt đó, trong TOÀN BỘ phiên không được
  có thêm `llm_request` nào với `purpose = "next_question"` (P0-5).
- Tool chạy lỗi vẫn phải có dòng `tool_call` với `error` khác `null` — không được nuốt im lặng.

### 5.4 Không được log gì

- Không log API key, header `Authorization`, biến môi trường — kể cả bản đã che (giữ đúng ràng buộc
  đã áp cho `intake_agent.py`). `llm-io.jsonl` chỉ ghi tên provider + model + messages + response.
- `user_message`, `agent_message`, prompt trong `llm-io.jsonl` đều chứa PHI. Mặc định ghi nguyên văn
  để debug được; phải hỗ trợ biến môi trường `FEVER_LOG_REDACT=1` → thay mọi trường văn bản tự do
  bằng `{"len": 42, "sha256_8": "a1b2c3d4"}`. Bật cờ này khi demo hoặc chạy trên dữ liệu thật.
- Mọi lỗi I/O khi ghi log đều **nuốt và chỉ `logger.warning`** — log hỏng không bao giờ được làm hỏng
  phiên hỏi-đáp (đúng cách `session_log.py` đang làm).

### 5.5 API tối thiểu của module

```python
def start(session_id: str, *, route: str | None, budget: int) -> None: ...
def stage_enter(session_id: str, stage: str) -> None: ...

def step(session_id: str, *, turn: int, stage: str, cluster_id: str | None, event: str,
         tool: str | None = None, input: Any = None, output: Any = None,
         duration_ms: int | None = None, error: str | None = None) -> None: ...

def llm_io(session_id: str, *, turn: int, stage: str, cluster_id: str, purpose: str,
           provider: str, model: str, messages: list[dict], response_text: str,
           parsed: dict | None, tokens: int | None, latency_ms: int,
           retry_count: int = 0) -> str:
    """Ghi nguyên văn vào llm-io.jsonl, đồng thời ghi cặp llm_request/llm_response
    tóm tắt vào file stage. Trả về `io_ref` để dòng stage trỏ sang."""

def finish(session_id: str, *, triage_level: str, stop_reason: str, turns: int) -> None: ...

# Ba hàm đọc — dành riêng cho test/debug, không dùng trong luồng chạy thật:
def read_stage(session_id: str, stage: str) -> list[dict]: ...
def read_turn(session_id: str, turn: int) -> list[dict]:   # gộp mọi stage, lọc 1 lượt, sort theo step
def read_all(session_id: str) -> list[dict]: ...           # gộp mọi stage, sort theo seq
```

Dùng một context manager mỏng cho tool để không phải tự đo giờ và không quên log lúc tool ném lỗi:

```python
with fever_stage_log.tool(session_id, turn=turn, stage=stage, cluster_id=cid,
                          tool="red_flag_engine.evaluate", input=answers) as rec:
    result = red_flag_engine.evaluate(answers)
    rec.output = result.model_dump()
```

Đồng thời nối vào console trace đã có: gọi `console_log.red_flag(...)` khi `rule_gate` bắt chốt đỏ,
để chạy `CONSOLE_TRACE=on` là thấy ngay trên terminal, không phải mở file.

### 5.6 Checkpoint 0 — log (làm ngay trong Bước 1, không tách bước riêng)

| Mục | Nội dung |
|---|---|
| File test | `tests/test_services/test_fever_stage_log.py` |
| Fixture | `tmp_path` + `monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)` |
| Assert cấu trúc | ghi 1 lượt giả lập gồm đủ 10 step ở 2 stage → đúng 2 file `stage-*.jsonl`; `read_turn(sid, 1)` trả đủ 10 dòng, `step` liên tục 1→10, `seq` tăng dần |
| Assert input/output | mọi dòng `tool_call`/`retrieve` đều có key `input` và `output` khác `None` (test này chặn thói quen log thiếu) |
| Assert tool enum | `tool` của mọi dòng nằm trong tập 5 tên hợp lệ ở §5.2 — tên sai chính tả phải fail |
| Assert io_ref | dòng `llm_response` có `io_ref` trỏ đúng 1 dòng tồn tại trong `llm-io.jsonl`, và dòng đó chứa nguyên văn `messages` + `response_text` |
| Assert redact | `FEVER_LOG_REDACT=1` → không file nào còn chứa chuỗi nguyên văn của tin nhắn test |
| Assert an toàn | monkeypatch `Path.open` ném `OSError` → `step()` vẫn trả về bình thường, không ném ra ngoài |

```powershell
pytest tests/test_services/test_fever_stage_log.py -v
```

## 6. Các bước triển khai (theo đúng thứ tự phụ thuộc)

### Bước 1 — Field registry
- Tạo `src/services/checklists/fever_checklist.py`: encode toàn bộ field Part 3 (tier `M0`/`M1`/`C`
  bắt buộc; `O`/`H` optional) + toàn bộ `QuestionCluster` (Q0-01 → Q5-07).
- Không cần encode `RED_FLAG_RULES`/ngưỡng số liệu ở đây — đó là việc của rule engine (Bước 3), file
  này chỉ mô tả field + cách hỏi.

**Checkpoint 1 — field registry**

| Mục | Nội dung |
|---|---|
| File test | `tests/test_services/test_fever_checklist.py` |
| Golden | Bảng §1.1 knowledge model + bảng Q0-01→Q5-07 Part 3 — đếm thủ công một lần, ghi **số cố định** vào test (`EXPECTED_FIELD_COUNT = <N>`), không tính động từ chính registry (tính động thì registry thiếu field test vẫn xanh) |
| Test 1 | `len(FEVER_FIELDS) == EXPECTED_FIELD_COUNT` và mọi `key` là duy nhất |
| Test 2 | mọi field tier `M0`/`M1` có `tri_state=True` |
| Test 3 | mọi `key` trong `QuestionCluster.fields` đều tồn tại trong `FEVER_FIELDS` (chống typo field name) |
| Test 4 | tập `cluster.id` khớp đúng danh sách mã cứng `["Q0-01", ..., "Q5-07"]` viết tay theo Part 3, **đúng cả thứ tự** |
| Test 5 | mọi cluster có `stage` thuộc `{"0","1","2","3A","3B","4","5"}`; các cụm §3.3A có `batch_negation=True` |

```powershell
pytest tests/test_services/test_fever_checklist.py -v
```

Pass khi: 5/5 test xanh. Nếu Test 1 fail → đọc lại bảng §1.1, KHÔNG sửa `EXPECTED_FIELD_COUNT` cho
khớp code; con số đó là golden, code phải chạy theo nó.

### Bước 2 — State machine (stage/route)
- Tạo `src/services/engines/fever_stage_machine.py`: hàm thuần rule-based
  `next_cluster(stage, answers) -> QuestionCluster | None`, implement đúng Part 7 (flowchart +
  conversation graph) — thứ tự Stage 0→1→2→3A→(3B nếu 3A sạch)→4→5→6, route
  (`ROUTE_INFANT_HIGH`/`ROUTE_HIGH_RISK`/`ROUTE_STANDARD`/`ROUTE_DENGUE_CONTEXT`/
  `ROUTE_LOCALIZED_SOURCE`) theo Part 4.3.
- Hàm `should_stop(stage, answers) -> StopReason | None` implement đúng Part 1.3 (chốt đỏ / đủ căn
  cứ / hết ngân sách / người dùng không thể tiếp tục) + ngân sách câu hỏi §6.5.

**Checkpoint 2 — state machine & ngân sách câu hỏi**

| Mục | Nội dung |
|---|---|
| File test | `tests/test_services/test_fever_stage_machine.py` |
| Golden | bảng ngân sách §6.5 — chép thành `BUDGET = {"ROUTE_STANDARD": (min, max), ...}` viết tay trong test |
| Test/route (5 route) | driver vòng lặp: bắt đầu `stage="0"`, `answers` giả lập cố định cho route đó, lặp `next_cluster` → đánh dấu field của cụm là đã trả lời → đếm số cụm cho tới khi `should_stop` trả khác `None`; assert số cụm nằm trong `BUDGET[route]` và `stop_reason` đúng loại |
| Test thứ tự stage | dãy stage đi qua phải là dãy con của `0→1→2→3A→3B→4→5`, không được nhảy lùi (assert monotonic theo chỉ số) |
| Test 3B bị bỏ | nếu 3A đã có chốt đỏ → `next_cluster` không bao giờ trả cụm stage `3B` |
| Test dừng cứng | `should_stop` trả `RED_FLAG` NGAY tại lượt `answers` có field EMERGENCY, không đợi hết cụm |
| Test thuần rule | không có bất kỳ import LLM/provider nào trong module — assert `"provider_router" not in sys.modules` sau khi import module state machine trong test riêng, hoặc grep import trong test |
| Assert LOG | chạy driver có truyền `session_id`; sau đó `read_all()` phải có đúng số dòng `tool_call` với `tool="fever_stage_machine.next_cluster"` bằng số cụm đã hỏi |

```powershell
pytest tests/test_services/test_fever_stage_machine.py -v
# chỉ 1 route khi debug:
pytest tests/test_services/test_fever_stage_machine.py -v -k "infant"
```

Pass khi: mọi route xanh **và** số cụm nằm trong ngân sách — vượt trần ngân sách là fail, kể cả khi
kết quả triage đúng.

### Bước 3 — Red-flag rule engine cho fever
- Mở rộng (không viết đè) `src/services/engines/red_flag.py` hoặc tạo module riêng cho fever, ánh xạ
  đúng `RF-xx` → điều kiện field, theo KM §6.1 (`R-E-xx` = EMERGENCY, `R-V-xx` = EARLY_VISIT,
  `R-S-xx` = SELF_CARE).
- Đây là module rule-based THUẦN, không gọi LLM — dùng làm gate giữa extract và next_question ở
  Stage 3A/3B (kiến trúc hướng C, mục 2).

**Checkpoint 3 — golden 25 ca Part 8 (bộ test quan trọng nhất)**

Trước tiên trích golden ra file dữ liệu, **chép nguyên văn** từ khối ```json``` dưới mỗi hội thoại
mẫu Part 8, không sửa/không làm tròn/không "chuẩn hoá" tên field:

```text
tests/fixtures/fever/part8_cases.json
```

```json
[
  {
    "case_id": "E2",
    "expected_triage_level": "EMERGENCY",
    "conversation": [ {"role": "user", "text": "..."}, {"role": "agent", "text": "..."} ],
    "fields": { "seizure_active_now": "true", "age_months": 36, "...": "..." },
    "expected_triggered_rules": ["R-E-03"],
    "expected_reason_codes": ["RF-11"],
    "expected_question_count": 3
  }
]
```

| Mục | Nội dung |
|---|---|
| File test | `tests/test_services/test_fever_red_flag_rules.py` |
| Loader | fixture `part8_cases` trong `tests/conftest.py`, đọc file JSON trên |
| Test golden | `@pytest.mark.parametrize("case", part8_cases, ids=lambda c: c["case_id"])` — feed `case["fields"]` thẳng vào `red_flag_engine.evaluate()`, **không qua LLM**, assert khớp 100% cả 3: `triage_level`, `set(triggered_rules)`, `set(reason_codes)` |
| Test đủ bộ | `len(part8_cases) == 25` và đếm đúng 5 EMERGENCY / 5 EARLY_VISIT / 5 SELF_CARE / 5 ca tối ưu — chống việc lỡ chép thiếu ca |
| Test thuần rule | mock `provider_router.complete` bằng `Mock(side_effect=AssertionError("rule engine không được gọi LLM"))` rồi chạy lại toàn bộ 25 ca — đây là cách chứng minh "đúng tool": engine chạy bằng rule, không lén gọi model |
| Test P0-6 | ca mơ hồ (field `unknown` ở nhánh quyết định) → engine trả mức thận trọng hơn, không trả mức nhẹ hơn |
| Test tri-state | truyền `"unknown"` vào field an toàn không bao giờ được coi như `false` — assert rule không kích hoạt nhánh "đã loại trừ" |
| Assert LOG | mỗi lần `evaluate` ghi đúng 1 dòng vào `rule-engine.jsonl`, kể cả ca không khớp rule nào (`triggered_rules: []`) |

```powershell
# toàn bộ 25 ca
pytest tests/test_services/test_fever_red_flag_rules.py -v

# chạy đúng 1 ca khi đang sửa rule (id chính là case_id trong JSON)
pytest tests/test_services/test_fever_red_flag_rules.py -v -k "E2"

# chỉ nhóm EMERGENCY
pytest tests/test_services/test_fever_red_flag_rules.py -v -k "E1 or E2 or E3 or E4 or E5"
```

Pass khi: **25/25 xanh, khớp 100%** — không chấp nhận "sai 1 ca không quan trọng". Bộ này phải xanh
TRƯỚC khi đụng tới LLM ở Bước 4-5: rule engine sai thì LLM tốt đến mấy cũng vô nghĩa. Khi một ca fail,
so 3 thứ theo thứ tự: `triggered_rules` (rule nào thiếu/thừa) → điều kiện field của rule đó trong KM
§6.1 → tên field trong `part8_cases.json` có khớp registry Bước 1 không.

### Bước 4 — LLM extraction theo cụm (dùng chung cho cả hướng C và E)
- Trong `src/services/agents/` tạo `fever_intake_agent.py`, tái dùng
  `provider_router.complete()`/`_parse_json_object` đã có ở `intake_agent.py` — không viết lại
  logic gọi provider.
- Hàm `extract_cluster(cluster: QuestionCluster, message: str) -> dict[str, TriState]`: build schema
  JSON CHỈ gồm field của `cluster.fields` + field "cơ hội" phát hiện qua quét từ khoá nhẹ (tái dùng
  kỹ thuật `_contains_any` của `semantic_mapper.py`) — không gửi toàn bộ 90 field mỗi lần.
- Với `cluster.batch_negation=True`: schema có thêm field `cluster_all_negative: bool`; nếu true thì
  post-process gán `false` cho toàn bộ field trong cụm.

**Checkpoint 4 — extraction theo cụm**

LLM thật không dùng trong test này (không xác định, tốn tiền, CI không có key): mock
`provider_router.complete` trả về JSON đã dựng sẵn, và kiểm **cả input gửi đi lẫn output xử lý về**.

| Mục | Nội dung |
|---|---|
| File test | `tests/test_agents/test_fever_extraction.py` |
| Mock | `monkeypatch.setattr(provider_router, "complete", fake)` với `fake` ghi lại `messages` nhận được rồi trả JSON mẫu |
| Test đúng tool | assert `fake` được gọi **đúng 1 lần**, và prompt gửi đi chỉ chứa field của cụm hiện tại — assert `len(schema_fields) == len(cluster.fields) + <số field cơ hội>`, và không chứa field của cụm khác (chống gửi cả 90 field mỗi lượt) |
| Test golden | dùng ca O1 Part 8: cho `fake` trả JSON mẫu → `extract_cluster` ra dict khớp đúng `case["fields"]` phần thuộc cụm đó |
| Test batch-negation | cụm `batch_negation=True`, LLM trả `{"cluster_all_negative": true}` → TOÀN BỘ field trong cụm = `"false"`, **không field nào còn `"unknown"`** (assert bằng `set(result.values()) == {"false"}`) |
| Test tri-state | LLM trả field rỗng/thiếu/`null` → post-process ra `"unknown"`, KHÔNG ra `"false"` (P0-4). LLM trả `true`/`True`/`"có"` → chuẩn hoá về `"true"` |
| Test JSON hỏng | `fake` trả text không phải JSON → không ném ra ngoài, trả toàn `"unknown"` và ghi `parse_error` vào log |
| Test không quyết định | output của `extract_cluster` không chứa khoá `triage_level`/`priority`/`next_stage` — LLM không được phép quyết định (coding_convention rule 1-2) |
| Assert LOG | 1 lượt sinh đủ chuỗi `retrieve` → `llm_request` → `llm_response` → `extract`; dòng `llm-io.jsonl` chứa nguyên văn prompt đã gửi |

```powershell
pytest tests/test_agents/test_fever_extraction.py -v
pytest tests/test_agents/test_fever_extraction.py -v -k "batch_negation"
```

Pass khi: toàn bộ xanh, đặc biệt là test batch-negation và test tri-state — hai chỗ này sai là vi
phạm trực tiếp P0-4.

### Bước 5 — Ghép hướng C/E theo stage (mục 2)
- `fever_intake_agent.py`: hàm `run_turn(stage, message, answers)`:
  - Nếu `stage in ("3A", "3B")`: gọi `extract_cluster` → merge → chạy `red_flag_engine` (bước 3) →
    nếu có `EMERGENCY` thì **trả ngay thông điệp cấp cứu, KHÔNG gọi next_question** → nếu không thì
    gọi `next_question` (call thứ 2).
  - Nếu stage khác: build 1 prompt gộp (extract cluster hiện tại + sinh câu hỏi cho cụm kế tiếp theo
    `next_cluster` đã biết trước từ state machine — không phụ thuộc kết quả extract lượt này để chọn
    cụm), parse JSON có 2 khoá `extracted` và `next_question`.

**Checkpoint 5 — short-circuit EMERGENCY**

| Mục | Nội dung |
|---|---|
| File test | `tests/test_agents/test_fever_emergency_shortcircuit.py` |
| Ca dùng | E2 Part 8 (co giật đang diễn ra), lấy input user nguyên văn từ `part8_cases.json` |
| Test đếm call | mock `provider_router.complete`; ở lượt phát hiện `seizure_active_now="true"` assert `fake.call_count == 1` (chỉ `extract`, **không** có call `next_question`) — đây là bằng chứng short-circuit |
| Test nội dung trả về | response của lượt đó là thông điệp cấp cứu, không chứa câu hỏi nào (không có `?`), và không chứa tên bệnh (P0-2) |
| Test hướng E vẫn 2 việc 1 call | cùng file, ca SELF_CARE ở stage 1: assert `fake.call_count == 1` nhưng JSON trả về có **cả** `extracted` lẫn `next_question` — chứng minh không nhầm hướng C sang stage thường |
| Test thứ tự tool | đọc `read_turn()`: dòng `rule_gate` phải nằm SAU `extract` và TRƯỚC mọi `llm_request` khác; ở lượt EMERGENCY không tồn tại dòng `llm_request` nào có `purpose="next_question"` |
| Test không gọi thừa tool | ở lượt EMERGENCY không có dòng `tool_call` với `tool="fever_stage_machine.next_cluster"` |
| Test phiên đóng | các lượt SAU đó (nếu user còn nhắn) không sinh thêm câu hỏi routine; `session.json` có `stop_reason="RED_FLAG"` |

```powershell
pytest tests/test_agents/test_fever_emergency_shortcircuit.py -v
```

Pass khi: `call_count` đúng 1 ở lượt chốt đỏ **và** log không có `next_question` nào sau `rule_gate`.
Hai assert này độc lập nhau (một cái đo hành vi, một cái đo trace) — phải xanh cả hai.

### Bước 6 — Nối vào state/session + API thật
- Tích hợp `fever_intake_agent.py` + `fever_stage_machine.py` vào 1 session flow mới (tương tự
  `intake_session.py`/`case_flow.py` đã có), nối vào router thật của bạn (`src/api/routers/`) theo
  đúng contract `docs/API_DOCUMENTATION.md`.
- Field output cuối cùng của phiên phải khớp đúng cấu trúc JSON trong ca mẫu Part 8 (để Dũng Mai
  dùng cho ERD/model xác suất không phải map lại lần 2 — theo mục "vùng dùng chung" trong
  `_guidance/role_specific.md`).

**Checkpoint 6 — end-to-end qua API thật**

Hai lớp: (a) test API **không cần key** dùng LLM mock, chạy trong CI; (b) chạy tay với LLM thật, đọc log.

*(a) Test API tự động*

| Mục | Nội dung |
|---|---|
| File test | `tests/test_api/test_fever_flow.py` |
| Fixture | `client` + `patient_headers` có sẵn trong `tests/conftest.py` — tái dùng, không dựng app riêng |
| LLM | mock `provider_router.complete` bằng scripted responses theo đúng lượt hội thoại trong `part8_cases.json` |
| Test 3 ca | 1 EMERGENCY (E2), 1 EARLY_VISIT (V1), 1 SELF_CARE (S1): POST tuần tự từng tin nhắn user, assert `triage_level` cuối khớp golden |
| Test ngân sách | số lượt agent hỏi ≤ trần §6.5 của route tương ứng |
| Test contract | response body khớp `docs/API_DOCUMENTATION.md` (validate bằng model Pydantic, không so tay từng khoá) |
| Test output cuối | JSON field cuối phiên khớp cấu trúc `case["fields"]` — đúng tên khoá để Dũng Mai không phải map lại |
| Test log | sau phiên, `logs/fever/<session_id>/` tồn tại đủ file stage đã đi qua; `session.json` có `triage_level` khớp |

```powershell
pytest tests/test_api/test_fever_flow.py -v
```

*(b) Chạy tay với LLM thật (bắt buộc làm 1 lần trước khi tick xong)*

```powershell
# terminal 1 — bật server, bật trace
.\.venv\Scripts\Activate.ps1
$env:CONSOLE_TRACE = "on"
python -m uvicorn src.main:app --host 127.0.0.1 --port 8001

# terminal 2 — gửi từng tin nhắn của ca E2 (nguyên văn từ Part 8)
curl.exe -X POST http://127.0.0.1:8001/api/v1/<endpoint-fever> -H "Content-Type: application/json" -d "@tests/fixtures/fever/e2_turn1.json"

# đọc lại trace của phiên vừa chạy
Get-Content logs/fever/<session_id>/stage-3A.jsonl | ConvertFrom-Json | Select-Object turn,step,event,tool
Get-Content logs/fever/<session_id>/session.json
```

Pass khi: 3 ca chạy thật ra đúng `triage_level` mẫu, số lượt hỏi trong ngân sách §6.5, và trace trong
`logs/fever/<session_id>/` đọc được đủ chuỗi step của từng lượt (user → retrieve → tool → llm → agent).

## 7. Chạy test — bảng tra nhanh theo checkpoint

### 7.1 Lệnh

```powershell
.\.venv\Scripts\Activate.ps1   # luôn kích hoạt venv trước, xem _guidance/Run.md
```

| Checkpoint | Lệnh |
|---|---|
| 0 — logging | `pytest tests/test_services/test_fever_stage_log.py -v` |
| 1 — registry | `pytest tests/test_services/test_fever_checklist.py -v` |
| 2 — state machine | `pytest tests/test_services/test_fever_stage_machine.py -v` |
| 3 — golden 25 ca | `pytest tests/test_services/test_fever_red_flag_rules.py -v` |
| 4 — extraction | `pytest tests/test_agents/test_fever_extraction.py -v` |
| 5 — short-circuit | `pytest tests/test_agents/test_fever_emergency_shortcircuit.py -v` |
| 6 — API | `pytest tests/test_api/test_fever_flow.py -v` |
| Toàn bộ fever | `pytest tests/ -v -k "fever"` |
| Toàn suite (chống hồi quy) | `pytest tests/ -q` |
| Lint | `ruff check src/services/checklists/fever_checklist.py src/services/engines/fever_stage_machine.py src/services/agents/fever_intake_agent.py src/services/infra/fever_stage_log.py` |

Thứ tự chạy khi debug: **0 → 1 → 2 → 3 → 4 → 5 → 6**. Checkpoint sau phụ thuộc checkpoint trước; sửa
lỗi từ dưới lên, đừng đuổi theo lỗi ở Checkpoint 5 khi Checkpoint 3 còn đỏ.

### 7.2 Hai loại assert bắt buộc ở mọi checkpoint

Mọi test trong task này phải trả lời được **cả hai** câu hỏi, thiếu một là test chưa đủ:

1. **Đúng tool chưa?** — hệ thống có gọi đúng thành phần, đúng số lần, đúng thứ tự không. Cách đo:
   - `mock.call_count` / `mock.call_args` trên `provider_router.complete` (đúng số call, đúng prompt).
   - Đọc log: `[d["tool"] for d in read_turn(sid, n) if d["event"] == "tool_call"]` so với danh sách
     tool kỳ vọng, **so cả thứ tự** (`==` trên list, không dùng `set`).
   - Chặn ngược: mock thành phần **không được gọi** bằng `side_effect=AssertionError(...)` (vd rule
     engine không được gọi LLM ở Checkpoint 3).
2. **Đúng golden chưa?** — output có khớp đúng dữ liệu mẫu trong tài liệu nguồn không. Cách đo: so
   với `tests/fixtures/fever/part8_cases.json` (chép nguyên văn từ Part 8), so đủ
   `triage_level` + `triggered_rules` + `reason_codes` + field trích được, khớp **100%**.

Một test chỉ assert "không crash" hoặc chỉ assert `triage_level` mà bỏ `triggered_rules` thì coi như
chưa qua checkpoint — đúng mức triage vì nhầm rule là lỗi nặng, và nó sẽ vỡ ngay khi mở rộng sang
nhóm triệu chứng khác.

### 7.3 Quy ước golden fixture

- Nguồn duy nhất: `tests/fixtures/fever/part8_cases.json`, chép **nguyên văn** khối ```json``` của 25
  ca Part 8. Không sửa golden cho khớp code — sai lệch nghĩa là code sai hoặc tài liệu cần sửa (sửa
  tài liệu thì phải báo nhóm, xem `role_specific.md`).
- Mỗi ca bắt buộc có `case_id` khớp mã ca trong tài liệu (`E1`-`E5`, `V1`-`V5`, `S1`-`S5`, `O1`-`O5`)
  để `pytest -k "<case_id>"` chạy được đúng một ca khi debug.
- Khi golden fail: đọc log của lượt fail bằng `read_turn()` trước, xem tool nào trả sai — đừng đoán
  từ message của assert.

### 7.4 Test không được phép làm

- Không gọi LLM thật trong `pytest` (CI không có key, kết quả không xác định). Mọi test gọi
  `provider_router.complete` phải mock. Kiểm chứng bằng cách chạy `pytest tests/ -k "fever"` khi đã
  xoá/để rỗng key trong `.env` — vẫn phải xanh.
- Không ghi log ra `logs/` thật khi test — luôn `monkeypatch` `paths.LOGS_DIR` sang `tmp_path`.
- Không commit file trong `logs/` (chứa PHI, đã có trong `.gitignore` — kiểm lại bằng `git status`
  trước khi commit).

## 8. Checklist tổng hợp trước khi coi là "xong"

- [x] Checkpoint 0: log ghi đủ chuỗi step mỗi lượt, tách file theo stage, `input`/`output` đầy đủ ở
      mọi `tool_call`/`llm_*`, redact được bằng `FEVER_LOG_REDACT=1`, lỗi I/O không làm hỏng phiên.
- [x] Checkpoint 1: field registry đủ số field (101, đếm từ KM §3.2-3.11 — không có bảng "§1.1" liệt
      kê field trong tài liệu nguồn, đó là sai sót trong bản nháp đầu), field tri-state đúng theo
      Data type của KM (không phải mọi field M0/M1).
- [x] Checkpoint 2: state machine đúng ngân sách câu hỏi §6.5 cho từng route (ngân sách chỉ có hiệu
      lực ở Stage 5 — xem lý do ở đầu file).
- [x] Checkpoint 3: **16/16 ca mẫu Part 8 có kết luận pass qua rule engine thuần (không LLM)**, khớp
      100% `triage_level`; `reason_codes`/`triggered_rules` mà tài liệu liệt kê là tập con của kết
      quả engine (tài liệu tự nói JSON mẫu không liệt kê hết field/rule liên quan).
- [x] Checkpoint 4: extraction theo cụm đúng field mẫu + batch-negation gán `false` đồng loạt đúng.
- [x] Checkpoint 5: EMERGENCY short-circuit đúng — không gọi thừa `next_question` khi đã chốt đỏ.
- [x] Checkpoint 6(a): chạy thật qua API (LLM mock có kịch bản, không cần key) với 3 ca đại diện 3
      mức triage, đúng ngân sách câu hỏi (`tests/test_api/test_fever_flow.py`).
- [x] Checkpoint 6(b): chạy tay qua API với **LLM thật** (OpenRouter/gpt-4o-mini) — ca E2 (EMERGENCY)
      chạy đủ, chốt đúng `R-E-02`/`RF-02` ở lượt 1. Ca H1 (SELF_CARE) chạy đủ 33 lượt tới kết luận,
      nhưng ra `EARLY_VISIT`/`R-V-16` thay vì `SELF_CARE` như tài liệu - xem phát hiện ở đầu file,
      cần review y khoa trước khi coi đây là bug hay hành vi đúng. Phát hiện + vá 1 bug JSON thật với
      gpt-4o-mini (bareword `unknown`) và 2 lỗ hổng thiết kế (ngân sách cắt nhầm field bắt buộc; chưa
      truyền `known_triage_level` theo dõi tiến độ phiên) trong lúc chạy tay - đã sửa cả 3, xem đầu file.
- [x] Mọi test đều có **cả** assert "đúng tool" lẫn assert "đúng golden" theo §7.2.
- [x] `pytest tests/ -k "fever"` xanh **khi không có API key trong `.env`** (không test nào gọi LLM thật).
- [x] `pytest tests/ -q` toàn bộ suite cũ vẫn pass (193/193, không phá luồng
      `intake_agent.py`/`triage_pipeline.py` hiện có).
- [x] `ruff check` sạch trên file mới.
- [x] Không có API key/PHI lọt vào log (đúng ràng buộc bảo mật đã áp dụng cho `intake_agent.py`);
      `git status` không thấy file nào trong `logs/`.
- [x] Không đụng tới file thuộc phạm vi Dũng Mai (`src/ui/new/`, `src/models/schemas.py`,
      `src/services/stores/`) — file mới thuộc `src/api/routers/`, `src/models/fever_api.py`,
      `src/services/sessions/`, `src/services/agents/`, `src/services/engines/`,
      `src/services/checklists/`, `src/services/infra/` đều nằm trong phạm vi Tuấn Anh theo
      [`role_specific.md`](role_specific.md); `docs/API_DOCUMENTATION.md` đã cập nhật mục 4.7.

## 9. Ngoài phạm vi (không làm trong task này)

- Mở rộng sang symptom_group khác ngoài fever.
- Thay `RuleBackedSemanticMapper`/`TRIAGE_PROTOCOL_RULES` chung của toàn hệ thống (đó là engine dùng
  cho mọi nhóm bệnh, không riêng fever).
- ERD/DB schema, model xác suất triệu chứng (Dũng Mai).
- Fine-tune model riêng hoặc đổi provider LLM (đã chốt dùng `provider_router` + OpenRouter/gpt-4o-mini
  hiện có trong `.env`).

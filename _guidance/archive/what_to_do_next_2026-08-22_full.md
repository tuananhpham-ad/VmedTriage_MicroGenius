# Kế hoạch nâng cấp agent hỏi đáp và trích xuất triệu chứng

> **Bản 2026-08-19 (đã dọn).** Tài liệu này chỉ còn **việc chưa làm** và **ràng buộc còn hiệu lực**.
> Toàn bộ phần ghi chép lịch sử — các mục đã hoàn thành 2026-08-17, các lần tự đính chính, và phần so
> sánh với những bản kế hoạch trước — đã được gỡ khỏi đây. Cần tra lại thì xem
> `_guidance/archive/what_to_do_next_2026-08-19_full.md` hoặc lịch sử git.
>
> Nguồn của phần §4: yêu cầu chủ dự án ngày 2026-08-19 (16 điểm). Nguồn của §2: đối chiếu code thật.
> Ba tài liệu `medical_conversation_agent_plan_v2*.md` là tài liệu diễn giải, **không** phải kế hoạch
> triển khai; phần còn giá trị của chúng đã nằm trong §3 và §6.

---

## 1. Bất biến — không đánh đổi lấy bất cứ thứ gì

Kiến trúc đã chốt: **deterministic controller + model workers + protocol-grounded tools + HITL**.
Controller là code, không phải LLM. Mỗi lượt đi qua sáu tầng:

```text
Tin nhắn người dùng
  L0  text_safety_signals   [KHÔNG model]  -> ứng viên red flag trên text thô
  L1  controller            [SLM + code]   -> model đề xuất, code định đoạt trong tập hợp lệ (§4.11)
  L2  symptom_group_router  [SLM tùy chọn] -> chỉ gọi ở 4 trigger đóng
  L2  fact_extractor        [SLM/LLM]      -> field_events JSON kèm bằng chứng
  L3  reducer + rule_engine [KHÔNG model]  -> snapshot, cụm kế tiếp, mức đề xuất
  L4  synthesis/renderer    [SLM/LLM]      -> câu tiếng Việt theo ResponsePlan đóng
  L5  output_guard          [KHÔNG model]  -> chặn chẩn đoán/câu hỏi ngoài plan
```

Mười bất biến. Mọi thay đổi trong tài liệu này phải giữ đủ cả mười:

1. **Mọi tầng ghi "KHÔNG model" không bao giờ được thay bằng một lời gọi model**, kể cả khi model tốt
   lên. Đó là những tầng khiến hệ thống test được bằng fake LLM và audit được sau sự cố.
2. **Controller chỉ được chọn trong tập hành động do code tính ra.** Từ 2026-08-19, tầng điều phối
   có thêm một model (Qwen3.5-4B) *đề xuất* hành động — nhưng tập hành động hợp lệ do code sinh, model
   chỉ chọn bên trong đó, và model chết thì rơi về controller tất định. Nó không chọn câu hỏi lâm
   sàng và tuyệt đối không chọn mức ưu tiên. Thiết kế đầy đủ ở §4.11.
3. **Không có đường nào để một lỗi model (timeout, JSON hỏng, route sai) làm mất red flag.**
4. Model không kết luận chẩn đoán bệnh. Không có bước nào tên `diagnose_disease` trong hệ thống này.
5. Mức ưu tiên do rule engine tất định quyết; LLM chỉ trích xuất và diễn đạt.
6. Văn bản safety-facing là template tĩnh đã duyệt, không đi qua LLM.
7. Mọi lần dừng có reason code ổn định; dừng vì ý định người dùng hoặc vì bất hợp tác **phải đánh dấu
   phiếu là chưa đầy đủ**.
8. Linh hoạt được đổi **thứ tự** hỏi, không được **bỏ** hỏi: `mandatory_unasked` phải rỗng khi phiên
   đóng bình thường.
9. Dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.
10. **Trải nghiệm hội thoại là yêu cầu sản phẩm, không phải phần thưởng thêm.** Một agent hỏi đúng
    nhưng khiến người bệnh bỏ giữa chừng thì không thu được triệu chứng nào — độ phủ bằng 0.

Hai mục tiêu "hỏi linh hoạt" và "khai phá đủ" không phải đánh đổi, vì trong code **độ phủ và thứ tự
hỏi đã tách rời**: độ phủ do tier field M0/M1 quyết, thứ tự do hàm xếp hạng tất định quyết. Nới thứ tự
không đụng tới bảo đảm độ phủ.

---

## 2. Đã chạy — đừng viết lại

Bảng này tồn tại để không ai implement lại thứ đã có. Code là đặc tả; cột cuối là nơi đọc.

| Cơ chế | Nơi |
| --- | --- |
| L0 text safety (độc lập model, chạy trước mọi lời gọi LLM) | `common_safety/text_safety_signals.py` (383 dòng) |
| Rule engine red flag trên snapshot | `common_safety/rules.py` (443 dòng), `rule_engine.py` |
| Router tất định + `_fever_ruled_out` | `registry.select_protocol` (`registry.py:40-58`) |
| Extraction có bằng chứng, 3 `operation` / 3 giá trị snapshot | `intake_agent.py`, `reducer.py:22-70` |
| Đính chính, rút lời, xoá dây chuyền field phụ thuộc, audit | `retraction.py`, `reducer.py:72-100` |
| `escalation_lock` — model không tự hạ escalation trong phiên | `session.py:107` |
| Coverage ledger + hàng đợi nợ | `coverage.py:33-88` |
| Ranking tất định 5 thành phần (thay first-fit) | `ranking.py` |
| Stage machine + `should_stop` 4 reason code | `stage_machine.py:285-336` |
| Batch câu hỏi + phủ định gộp theo nhóm | `batching.py`, `models.py:36-64` |
| `DialogueAct` 8 nhãn + `DIALOGUE_POLICY` dạng bảng | `dialogue.py` |
| `output_guard` 5 kiểm tra + fallback `script_hint` | `output_guard.py` |
| Bước quét sót trước khi chốt | `session.CATCH_ALL_QUESTION` |
| `RoleProfile` — định tuyến model theo vai trò | `provider_router.py` |
| Công tắc ngắt (4 cờ, **không** cờ nào cho tầng an toàn) | `flags.py` |
| Hạ tầng eval + baseline | `eval/scripts/`, `eval/baselines/2026-08-17-p0-summary.md` |
| Ý định người bệnh (dừng / hết triệu chứng / chửi tục) — THUẦN code | `user_intent.py` |
| Bộ đếm bất hợp tác 3 nấc (hỏi lại một lần rồi mới dừng) | `user_intent.UncooperativeTracker`, `session.py` |
| `StopSignals` đi xuyên `run_turn` → `advance` → `should_stop` | `stage_machine.StopSignals` |
| Suy `false` cho ý bị bỏ qua trong lượt gộp — CHỈ tier O/H | `batching.skipped_field_defaults` |
| Overlay sửa trường của điều dưỡng (kể cả red flag) + audit từng trường | `hitl_review.py`, `schemas.NurseFieldEdit` |
| ADR-008: 3 thông điệp tĩnh (nghi ngờ / quá SLA / sau duyệt) + đồng hồ SLA 5 phút | `common_safety/emergency_message.py`, `sessions/red_flag_sla.py` |
| Hai output summary: `summary_text` (LLM) + `summary_json` phẳng -> bảng ISBAR | `sessions/narrative.py`, `sessions/summary_render.py` |
| Nhánh red-flag thứ ba (model) + `red_flag_agreement` (OR, không trừ được) | `red_flag_branches.py` |
| Memory M1: khoá composite `user_id+conversation_id`, phiên sống qua restart | `stores/conversation_store.py`, `models/case_record.ConversationRow` |
| Lane phi lâm sàng (lifestyle / meta) — tách khỏi `PROTOCOL_REGISTRY` | `non_clinical.py` |
| Controller shadow mode — model đề xuất, không tác động gì | `controller_shadow.py` |
| Script đọc log -> bảng metric §8 | `eval/scripts/experience_report.py` |

**724 test xanh** (2026-08-19; trước đó 606). Chi tiết từng cơ chế nằm trong docstring của chính module — không chép lại vào đây.

Bốn ràng buộc không đọc ra được từ code, nên ghi ở đây:

- **Router model chỉ được gọi ở 4 trigger:** lượt mở; `dialogue_act == new_symptom`; lượt vừa rồi chạm
  field chief complaint; `_fever_ruled_out` vừa bật. Ngoài bốn ca đó dùng thẳng protocol đang gắn.
  Đếm số lời gọi router trên transcript nhiều lượt để phát hiện nếu nó lặng lẽ chạy mọi lượt.
- **Không hạ `fact_extractor` xuống SLM khi chưa có số eval chứng minh.** Đây là chỗ khó nhất (phủ
  định tiếng Việt, đính chính, số đo, khẩu ngữ), và sai ở đây là sai hồ sơ lâm sàng.
- **Tắt hoàn toàn SLM thì hệ thống vẫn phải chạy đúng** — router rơi về rule, synthesis rơi về
  `script_hint`. Nếu tắt SLM làm hỏng safety/triage flow thì kiến trúc đã sai.
- **Ngân sách một lượt: 2 lời gọi chính** (extract + render), cộng lời gọi router ở đúng 4 trigger trên.

### Số đo hiện tại (baseline 2026-08-17, `deepseek-chat`, `--mode api`)

| | Số | Ghi chú |
| --- | --- | --- |
| Latency mỗi lượt | p50 3.98s / p95 5.72s | `fact_extractor` 3.83s, `synthesis` 1.23s |
| Lời gọi mỗi lượt | 1.23–1.72 | |
| Emergency recall | **48.9% (22/45)** | Con số quan trọng nhất đang có |
| Red-flag recall | **0%** | Do lệch từ vựng mã, không phải do không phát hiện — xem §3 |
| Số lượt ca lành tính | 21 | Ba đòn bẩy giảm ở §5.3 |
| Tỉ lệ bị `output_guard` chặn | 0% (13 lượt, model thật) | |

`triage accuracy 33.3%` **không** đọc được như chỉ số chất lượng (chạy nhầm pipeline legacy) — bỏ qua
con số đó cho tới khi đo lại.

---

## 3. Việc còn lại

Hai track có chủ trì khác nhau, không phải một chuỗi tuyến tính.

| Track | Nội dung | Chủ trì |
| --- | --- | --- |
| **P** | Kiến trúc, trải nghiệm hội thoại, eval | Agent Lead |
| **PC** | 4 protocol lâm sàng còn thiếu | Data Lead + review lâm sàng |

### 3.1. Bốn việc chặn, và ba trong bốn không phải việc engineering

| # | Việc | Loại | Vì sao chặn |
| --- | --- | --- | --- |
| 1 | **Bảng quy đổi mã red flag** — `RF-07`/`TEXT_SIGNAL_*` của hệ thống vs `RF-TRAUMA-POISONING-001` của golden case | Quyết định lâm sàng | Hai hệ từ vựng ⇒ red-flag recall đo ra 0% dù hệ thống có phát hiện. Chặn một gate ở §8 |
| 2 | ~~Xung đột thông điệp red-flag~~ → **viết ADR-007 supersede ADR-004** | ADR + code | **Đã có hướng giải (§4.12): "nghi ngờ red-flag" + HITL 24/7, SLA tạm 5 phút.** Còn phải viết ADR |
| 3 | **Clinical governance ký duyệt `SHORT_CIRCUIT_CODES`** (32/100 mã) | Quyết định lâm sàng | Hệ thống đang an toàn nhưng kém nhạy — liên quan trực tiếp recall 48.9% |
| 4 | **Track PC — 4 protocol còn thiếu** | Chủ yếu lâm sàng | 4/5 nhóm MVP chưa tồn tại |

Sprint có thể trông như đang chạy mà vẫn không nhích được gate an toàn, vì ba trong bốn việc trên
không ai trong track engineering làm thay được.

### 3.2. Track PC — quy mô thật

`fever_protocol.py` là **696 dòng** và không phải bảng dữ liệu: 7 stage, ~10 hàm skip-rule,
`determine_route`, `conservatism_tier`, `_is_dengue_context`, `budget_key`, `derive_duration`. Bốn
protocol nữa là **bốn lần chừng đó logic lâm sàng viết tay**.

- **Thừa hưởng, không viết lại:** `common_safety/rules.py`, `clusters.py`, `fields.py`,
  `screening_groups.py`, `stage_machine`, `screening`, `batching`, `retraction` — đã trung lập với
  nhóm triệu chứng.
- **Phải viết riêng từng nhóm:** field + tier (M0/M1/C/O/H), cụm câu hỏi, `ScreeningGroup`, skip-rule,
  `determine_route`, ngưỡng budget, luật triage riêng.

Các bước: (1) chốt nguồn lâm sàng — `data/triage_*.csv` là **nguyên liệu thô**, không phải protocol;
(2) làm **một** nhóm trọn vẹn trước (đề xuất Khó thở hoặc Đau ngực vì tỉ trọng red flag cao), rút kinh
nghiệm rồi mới làm ba nhóm còn lại song song; (3) mỗi nhóm đủ test như fever; (4) bổ sung golden case
trước khi merge.

**Đừng ước lượng PC như một task code** — phần lớn công là đọc tài liệu lâm sàng và quyết ngưỡng.

### 3.3. Track P — các mục còn nợ

**P0.6 — Sửa thứ tự ưu tiên trong `should_stop`: `RED_FLAG` phải thắng `USER_CANNOT_CONTINUE`.**
✅ **Xong 2026-08-19** — ca chặn nằm ở `tests/.../test_user_intent_and_stopping.py::test_red_flag_beats_a_stop_request_in_the_same_turn`.
Phần mô tả bên dưới giữ lại vì nó là lý do tồn tại của ca test đó.

Docstring của hàm ghi *"Áp theo thứ tự: chốt đỏ > đủ căn cứ > hết ngân sách > người dùng không tiếp
tục được"* nhưng code kiểm `user_can_continue` **đầu tiên** (`stage_machine.py:298-303`). Hệ quả:
người bệnh vừa khai một dấu hiệu cấp cứu rồi nói "thôi khỏi" trong cùng lượt thì phiên đóng với
`USER_CANNOT_CONTINUE` thay vì `RED_FLAG` — tức là **không escalate**, ngược bất biến §1 mục 3.

Sửa nhỏ (đảo hai khối `if`) nhưng **bắt buộc kèm test** (§7), vì đúng lượt đó là lượt hiếm nên không
ca golden nào hiện chạm tới. Thứ tự đúng chính là thứ tự docstring đã ghi.

**P3.9 — Ý định người dùng làm đầu vào của stop policy.** ✅ **Xong 2026-08-19** (`user_intent.py`).
Bốn ràng buộc bên dưới đều được giữ; phần mô tả giữ nguyên vì nó là đặc tả của module.
`user_can_continue` đã có trong chữ ký `should_stop` nhưng **trước đó chưa ai suy nó
ra từ tin nhắn** — "tóm tắt cho tôi đi" hoặc "tôi không muốn trả lời nữa" hiện không có đường nào tác
động vào việc dừng phiên. Bốn ràng buộc:

- **Classifier tất định trước, model sau** — cùng mô hình với `registry.select_protocol` + router.
- **Intent chỉ được set `user_can_continue=False`.** Không chọn cụm, không đổi protocol, không hạ
  escalation.
- **Không bao giờ vượt qua nhánh red flag** — phụ thuộc P0.6. Làm P3.9 trước là mở rộng đúng cái lỗ
  đang có.
- **Dừng vì intent phải đánh dấu phiếu chưa đầy đủ**, `missing_information` liệt kê field M0/M1 còn
  `unset`.

**KHÔNG làm:** một "Stop Agent" bằng LLM nhận JSON và trả `CONTINUE`/`SUMMARIZE`. Cùng một state sẽ
dừng khác nhau giữa các lần chạy, không test được bằng fake LLM, và nó chuyển một quyết định an toàn
từ code sang model. `should_stop` hiện đã bao trùm; cái còn thiếu là **một input mới cho hàm cũ**.

**P4.3–P4.4 — Metric trải nghiệm.** `user_led_ratio`, `repeat_question_rate`, `deferral_depth`,
`catch_all_yield`, `mandatory_coverage_at_close` chưa có chỗ nào tính ra số. Dữ liệu thô đã có trong
`stage_log` + `CoverageLedger.snapshot`; cần một script đọc log và một lần chạy model thật để có mẫu số.

**P5 — Dọn kiến trúc.** Quyết số phận `src/tool/catalog/` + `triage_pipeline.py` (tái dụng registry/
policy/audit, hoặc deprecate); quyết số phận `routers/fever_intake.py` + `sessions/fever_session.py`
(đang mount tại `src/main.py:57`); chuyển endpoint/UI còn lại sang `symptom_protocol.session.SessionStore`.
Không để hai runtime path cùng có vẻ authoritative. Không xoá trước khi kiểm tra toàn bộ caller.

**P1.4 và P3.8 — nợ vì cùng một lý do:** cần API key và chi phí model thật. Hạ tầng đã sẵn, chạy eval
là ra bảng. Riêng P3.8 (hạ synthesis xuống SLM) hiện **không đáng làm**: lãi tối đa ~1.2s/lượt, trong
khi phần chiếm thời gian là `fact_extractor` 3.8s mà thứ đó đã chốt không hạ.

**PC+ — Multi-protocol đồng thời (sau PC).**
`registry.select_protocol` trả **một** tên protocol cho một phiên; ca thật "đau bụng kèm sốt 39" phải
chọn một. Bốn câu hỏi phải trả lời **trước khi viết dòng code nào**:

1. Field trùng tên khác nghĩa giữa hai protocol merge thế nào?
2. Tier / budget / luật triage của protocol nào thắng khi mâu thuẫn?
3. Đổi `primary` giữa phiên thì các cụm đã hỏi map sang protocol mới ra sao?
4. **`CoverageLedger.reset()` hiện xoá sạch nợ hoãn khi đổi protocol** vì mã cụm dùng chung
   (`coverage.py:80-86`). Multi-protocol phá giả định này — hoặc namespace mã cụm theo protocol, hoặc
   bỏ `reset()`. Đây là câu tốn công nhất.

**Xếp sau PC**, vì merge hai protocol chỉ có nghĩa khi có hơn một protocol thật để merge.

### 3.4. Lộ trình: PC chèn trước hay track P chạy trước

Quyết định của PM, cần chốt trong planning:

- **Demo V1 cần đủ 5 nhóm** → `PC` chèn trước phần kiến trúc còn lại. Router và ranking chưa tạo thêm
  giá trị khi 4/5 đích đến chưa tồn tại, và `GENERIC_PROTOCOL` (210 dòng) có ít cụm hơn hẳn fever nên
  không gian "hỏi theo mạch người bệnh" cũng hẹp hơn hẳn.
- **Một nhóm chạy thật tốt** → track P chạy trước, `PC` lùi lại, và ghi rõ trong demo rằng 4 nhóm còn
  lại đi qua `GENERIC_PROTOCOL`.

**Không chốt thì mặc định trôi theo hướng thứ hai** — không phải vì ai chọn nó, mà vì track P dễ bắt
đầu hơn.

Câu hỏi thứ hai cho planning: **ai chủ trì PC**. Giao nhầm cho track engineering thì ước lượng sai từ
đầu.

---

## 4. Yêu cầu chủ dự án (2026-08-19) — quyết định phạm vi và cách thực thi

Mục này ghi lại **yêu cầu sản phẩm do chủ dự án đưa ra**, không phải một đề xuất kỹ thuật để thẩm
định. Vì thế cách viết ở đây khác §3: mỗi mục là *quyết định đã chốt* + *điều kiện an toàn tối thiểu
để thực thi được nó* + *chỗ nó nằm trong kế hoạch*. Ở ba mục tôi có phản biện kỹ thuật, phản biện
được ghi đúng một lần rồi chuyển sang phương án thực thi — không mở lại.

### 4.0. Bảng quyết định — 16 điểm

| # | Yêu cầu | Quyết định | Nằm ở |
| --- | --- | --- | --- |
| 1 | Không rule cứng; red flag do **rule + model** cùng chạy, so sánh khớp/không khớp ở cuối | Có làm | §4.1 |
| 2 | 3 mức triage vẫn cập nhật liên tục nhưng **không quyết định**; chạy triage sau summary để đối chiếu | Có làm, kèm 1 ngoại lệ an toàn | §4.2 |
| 3 | Phiếu summary I/S/B/A/R, trường rỗng không xuất, đưa hết câu trả lời của user | Có làm | §4.3, §5 |
| 4 | Hai dạng natural summary: (a) NLP gọn, (b) theo field đã detect | Có làm cả hai | §4.3 |
| 5 | **Điều dưỡng sửa được MỌI trường, kể cả red flag** (hiện đang khoá) | Có làm — gap thật, đã kiểm chứng | §4.4 |
| 6 | Rule ở dạng guardrails, không phải `if/else` theo bệnh | Đã có sẵn phần lớn | §4.5 |
| 7 | RAG grounding cho cả hai nhánh | Có làm, phạm vi hẹp | §4.6 |
| 8 | Dừng khi hết triệu chứng / user chửi tục / bất hợp tác | Có làm | §4.7 |
| 9 | Detect đúng và đủ triệu chứng (positive/negative/unknown) | Đã chạy | §2, §4 |
| 10 | LLM sinh câu hỏi phủ hết trường **và phủ hết nhóm bệnh** | Đã có cơ chế; thiếu 4 protocol | track PC (§3.2) |
| 11 | Hỏi nhanh hơn: batch lớn, **field bị bỏ qua coi là False** | Có làm batch — **quy tắc suy False phải sửa** | §4.8 |
| 12 | Memory: composite key, short hybrid, long-term 3 phiên gần nhất | Có làm theo 3 giai đoạn | §4.9 |
| 13 | Mở rộng protocol: bụng/đầu/lưng/da/tình dục + chitchat + lifestyle + summarize + search\_db | Có làm, tách hai loại protocol | §4.10 |
| 14 | Router bằng model nhỏ (Qwen3.5-4B) | Hạ tầng đã sẵn; điều kiện ở §2 | §4.10 |
| 14b | **Qwen3.5-4B làm controller**, worker khác giữ Gemini API | Có làm — 3 bước, shadow mode trước | §4.11 |
| 17 | **Nghi ngờ red-flag + HITL 24/7** thay cho khẳng định cấp cứu | Có làm — giải xung đột ADR-004 | §4.12 |
| 15 | UX: streaming, loading, xuống dòng, câu hỏi dễ hiểu | Phần lớn đã chạy | §5 |
| 16 | Đang dài dòng — cần cơ chế giảm, chấp nhận đánh đổi | Có làm | §5.3 |

---

### 4.1. Red flag hai nhánh: rule và model cùng chạy, đối chiếu ở cuối

**Yêu cầu:** không dựa vào rule cứng một chiều. Cho agent/model phát hiện red flag song song với rule,
rồi **đưa xuống cuối để hai bên so sánh** — khớp hay không khớp.

Đây là một **thay đổi thật** và là hướng đúng: nó biến red flag từ một quyết định đơn nguồn thành một
quyết định có kiểm chứng chéo, và số liệu đối chiếu chính là thứ đo được chất lượng của cả hai bên.
Hiện repo đã có **hai nhánh nhưng chưa đối chiếu**:

| Nhánh | Nơi | Tính chất |
| --- | --- | --- |
| L0 — tín hiệu trên text thô | `common_safety/text_safety_signals.py` (383 dòng) | KHÔNG model, chạy trước mọi lời gọi LLM |
| Rule engine trên state | `common_safety/rules.py` (443 dòng) + `rule_engine.py` | KHÔNG model, chạy trên snapshot đã trích xuất |

Cái còn thiếu là **nhánh thứ ba (model) và bước đối chiếu**. Thiết kế:

```text
mỗi lượt:
  L0 text signals   ──┐
  rule engine       ──┼──> escalate NGAY nếu bất kỳ nhánh nào dương tính đã duyệt
  model red-flag    ──┘    (OR, không phải AND — xem bất biến bên dưới)

cuối phiên:
  red_flag_agreement = {
    "rule_only":  [...],   # rule bắt, model bỏ sót
    "model_only": [...],   # model bắt, rule bỏ sót  <- nguồn để mở rộng rule
    "both":       [...],
    "agreement_rate": 0.xx
  }
  -> ghi vào phiếu bàn giao + log, KHÔNG dùng để tự sửa quyết định
```

**Bốn ràng buộc bắt buộc:**

1. **Hợp nhất bằng OR, không phải AND, và không phải "chờ đối chiếu".** Bất kỳ nhánh nào cho tín hiệu
   dương tính đã duyệt thì escalate **ngay trong lượt** (`CLAUDE.md` nguyên tắc 4). Việc "đưa xuống
   cuối để so sánh" là **để đo và để điều dưỡng đọc**, không phải để hoãn cảnh báo. Nếu hai bên bất
   đồng thì lấy bên **an toàn hơn** — không lấy bên nào "đúng hơn", vì lúc đó chưa ai biết bên nào đúng.
2. **Model không được phép tắt một red flag mà rule đã bật.** Một nhánh mới chỉ được **thêm** phát
   hiện, không được **trừ**. Đây là hệ quả trực tiếp của bất biến §1 mục 3.
3. **Lỗi model không được làm mất nhánh nào.** Timeout/JSON hỏng ở nhánh model ⇒ phiên chạy tiếp với
   hai nhánh cũ, ghi `model_branch_status: "failed"` vào log. Đây là ca test bắt buộc.
4. **`red_flag_agreement` là dữ liệu, không phải quyết định.** Nó đi vào phiếu và vào metric; không có
   dòng code nào đọc nó để đổi mức ưu tiên.

**Giá trị đo được ngay:** `model_only` chính là danh sách ứng viên để bổ sung vào rule, và
`agreement_rate` là chỉ số trả lời được câu "rule của chúng ta có bỏ sót gì không" — thứ mà baseline
hiện tại (`emergency recall 48.9%`) đang đặt ra mà chưa có cách trả lời.

---

### 4.2. Mức triage: vẫn cập nhật liên tục, nhưng không còn là quyết định cuối

**Yêu cầu:** 3 mức triage vẫn được cập nhật trong lúc hội thoại, nhưng **không quyết định**; sau khi
có summary mới chạy triage để đối chiếu với một bên khác.

Vòng đánh giá trước tôi đã phản đối cách diễn đạt này vì sợ nó đẩy rule engine tất định ra khỏi agent.
Chủ dự án đã khẳng định lại, và khi đọc kỹ thì **hai thứ không mâu thuẫn** — chúng chỉ là hai vai trò
khác nhau của cùng một con số:

```text
TRONG hội thoại:
  rule_engine.evaluate(protocol, answers)  ->  provisional_priority
     dùng để:  (a) kích hoạt EMERGENCY banner tĩnh ngay trong lượt   [BẮT BUỘC GIỮ]
               (b) chọn nhánh câu hỏi / ngân sách (budget_key)        [đã chạy]
               (c) hiển thị cho điều dưỡng như "đề xuất tạm thời"
     KHÔNG dùng để: gửi bất cứ hướng xử trí nào cho bệnh nhân

SAU summary (ngoài ranh giới agent):
  snapshot + summary  ->  triage module  ->  final_priority
                       -> đối chiếu với provisional_priority
                       -> điều dưỡng duyệt (HITL) -> mới có hiệu lực
```

**Một ngoại lệ không đánh đổi được:** ca nghi ngờ red-flag vẫn phải **phát tín hiệu ngay trong lượt**
— đẩy lên đầu hàng đợi điều dưỡng và hiện thông điệp tĩnh cho bệnh nhân — không chờ summary, không
chờ duyệt (`CLAUDE.md` nguyên tắc 4, `ARCHITECTURE.md:15-19` ràng buộc 3). Nội dung thông điệp đó
theo §4.12. "Không quyết định" áp cho `EARLY_VISIT`/`SELF_CARE` — hai mức có thể chờ. Nghi ngờ cấp
cứu thì không, vì cái giá của việc chờ là bất đối xứng.

**Hệ quả lên schema:** `HandoffSummary.proposed_priority` giữ nguyên tên và ý nghĩa (*đề xuất*, không
phải *kết luận*) — đúng `docs/prd.md:65` FR-05. Thêm hai trường:

```python
provisional_priority: TriagePriority | None   # rule engine trong hội thoại
priority_source: str                          # "rule_engine" | "downstream" | "nurse_edited"
```

Trường thứ hai là thứ khiến việc "so sánh với một bên khác" đọc được về sau — không có nó thì ba
nguồn cùng ghi vào một ô và không ai truy được ô đó đến từ đâu.

---

### 4.3. Hai output summary

**Đây là output contract của agent.** Cả hai đọc **cùng một snapshot đã validate** — đó là điều kiện
duy nhất khiến chúng không mâu thuẫn nhau (V2 §45 FR8 nói đúng điểm này).

**Output 1 — Natural summary, hai chế độ, cả hai đều làm:**

*Chế độ (a) — NLP gọn.* LLM viết lại toàn bộ câu trả lời của người bệnh thành văn xuôi: bỏ trùng lặp,
bỏ chitchat, **giải quyết đính chính bằng giá trị mới nhất**. Không được bịa thêm chi tiết y khoa
không có trong hội thoại (`CLAUDE.md` nguyên tắc 3), và phải đi qua `output_guard` như mọi văn bản
model sinh khác.

> Người dùng báo đau bụng bên phải từ sáng, cơn đau tăng dần, kèm buồn nôn. Phủ nhận nôn và tiêu
> chảy. Chưa xác định được có sốt hay không vì chưa đo nhiệt độ.

*Chế độ (b) — theo field đã detect.* Render tất định từ snapshot, **không qua model**:

```text
Triệu chứng ghi nhận:      <- các field = true
- Đau bụng bên phải
- Buồn nôn

Người bệnh phủ nhận:        <- các field = false
- Nôn, tiêu chảy

Chưa xác định được:         <- các field = unknown
- Sốt (chưa đo nhiệt độ)
```

Chế độ (b) là **bản đối chứng của chế độ (a)**: nếu (a) nói một điều mà (b) không có field nào đỡ,
thì (a) đang bịa. Đó là một kiểm tra rẻ và nên chạy tự động.

> **Một chỗ phải làm khác yêu cầu, và lý do:** yêu cầu ghi *"trường nào có thông tin thì đưa, còn lại
> False/Unknown thì thôi"*. Ở tầng **hiển thị** thì đúng — UI không cần liệt kê 30 dòng "không".
> Nhưng ở tầng **dữ liệu thì không được xoá**: "bệnh nhân phủ nhận đau lan xuống tay" là một dữ kiện
> lâm sàng có giá trị, và `unknown` là dữ kiện nói "chỗ này chưa ai biết" — xoá nó đi thì phiếu đọc
> ra giống hệt như đã hỏi và người bệnh nói không. Quy tắc: **snapshot giữ đủ ba giá trị, renderer
> mới lọc.** Riêng field an toàn thì `false` và `unknown` **luôn** được render, vì đó chính là chỗ
> điều dưỡng cần nhìn.

**Output 2 — Nurse structured summary:** JSON theo I/S/B/A/R → HTML, trường rỗng không xuất. Chi tiết
hợp đồng và 5 câu hỏi cần chốt ở §6.

**Kèm theo cả hai:** toàn văn hội thoại (`raw_conversation`) — yêu cầu "đưa hết tất cả câu trả lời của
user". UI điều dưỡng đã render khối này (`nurse.js`, mục "Hội thoại"), nên phần còn lại chỉ là đưa nó
vào bản JSON xuất ra.

---

### 4.4. Điều dưỡng sửa được mọi trường, kể cả red flag

**Đây là gap thật, đã kiểm chứng bằng code**, và là mục cụ thể nhất trong toàn bộ 16 điểm:

- `nurse.js:73` render red flag dưới dạng banner đọc-chỉ (`red-flag-alert`), cùng với
  `chief_complaint`, `onset`, `severity`, `associated_symptoms` — tất cả đều **không sửa được**.
- Form duyệt chỉ có ba ô: `edited_priority`, `approved_response`, `nurse_notes`.

**Phải tách hai khái niệm đang bị gộp làm một:**

| Khái niệm | Nơi | Có được nới không |
| --- | --- | --- |
| `escalation_lock` (`session.py:107`) | **trong phiên** — chặn agent tự hạ escalation đã bật | **KHÔNG.** Đây là loại 1 §1, và `flags.py:13` đã ghi nó không có công tắc tắt |
| Quyền sửa của điều dưỡng | **sau phiên**, ở bước duyệt | **CÓ** — đây chính là HITL, không phải ngoại lệ của HITL |

Nói cách khác: khoá hiện tại chặn **model** hạ cờ, và điều đó phải giữ. Nó không nên chặn **con
người** — điều dưỡng là người có thẩm quyền lâm sàng cao nhất trong luồng này, khoá họ lại là làm
ngược chính mô hình HITL mà dự án đặt ra.

**Thực thi:**

1. Mở quyền sửa cho toàn bộ trường của phiếu: identify, situation, background, assessment, symptoms,
   **red flags**, recommendation, triage.
2. **Bản ghi do hệ thống sinh là bất biến.** Sửa của điều dưỡng ghi vào một lớp overlay, không ghi đè:

   ```json
   {
     "field": "red_flags.RF-07",
     "generated_value": true,
     "current_value": false,
     "edited_by": "nurse_123",
     "edited_at": "...",
     "reason": "..."
   }
   ```

   Lý do: nếu có sự cố, câu hỏi đầu tiên sẽ là "hệ thống có bắt được không, và ai đã bỏ nó đi" — mất
   `generated_value` là mất luôn khả năng trả lời.
3. **Hạ một red flag phải kèm lý do**, không phải một cú click. Đây là ma sát cố ý, và là loại ma sát
   duy nhất tôi đề nghị giữ trong toàn mục này.
4. **Một việc không rút lại được:** nếu ca đã `EMERGENCY` và banner tĩnh **đã hiển thị cho bệnh nhân**,
   thì điều dưỡng hạ cờ về sau chỉ đổi phiếu và luồng xử trí — **không xoá được cái người bệnh đã
   đọc**. UI phải nói rõ điều đó tại chỗ, thay vì để điều dưỡng tưởng mình vừa thu hồi một cảnh báo.

---

### 4.5. Rule ở dạng guardrails

Đã đúng hướng sẵn, không phải viết mới. Hệ thống hiện **không** có `if fever: ... if chest_pain: ...`;
cái nó có là năm guardrail đúng như yêu cầu mô tả:

| Guardrail trong yêu cầu | Hiện thực |
| --- | --- |
| Safety guardrail | `common_safety/` (L0 + rules), không tắt được (`flags.py:13`) |
| Critical information guardrail | tier M0/M1 + `mandatory_unasked` (§1, §8) |
| Unsupported recommendation guardrail | `output_guard.check()` chặn chẩn đoán và câu hỏi ngoài plan |
| Conversation stop guardrail | `should_stop` 4 reason code |
| Output validation guardrail | `EvidencePolicy` + `_evidence_in_message` |

Việc còn lại là **giữ cho nó không trôi ngược thành rule cứng** khi track PC (§3.2) viết 4 protocol mới —
mỗi protocol mới là một cơ hội để `if` theo bệnh lẻn vào. Đề nghị: review PC bám đúng bảng trên.

---

### 4.6. RAG grounding cho cả hai nhánh

**Có làm, nhưng phạm vi hẹp hơn V2 §13 mô tả.** Ranh giới quyết định bởi một câu hỏi duy nhất: *nếu
RAG trả về rác, hậu quả là câu chữ xấu hay là câu hỏi lâm sàng sai?*

| Tầng | RAG được ground | Vì sao |
| --- | --- | --- |
| Protocol router | ✅ | Chọn sai ⇒ rơi về `GENERIC_PROTOCOL`, không mất red flag (§7.8 test 6) |
| Model red-flag branch (§4.1) | ✅ | Chỉ được **thêm** phát hiện; nhánh rule vẫn chạy độc lập |
| Summarizer (NLP) | ✅ | Ground để diễn đạt đúng thuật ngữ, không để thêm dữ kiện |
| Diễn đạt câu hỏi | ✅ | Chỉ đổi **cách nói**, không đổi **hỏi cái gì** |
| **Chọn hỏi field nào** | ❌ | Đây là checklist lâm sàng — ADR-003, `output_guard.py:145-163` |

Nói ngắn: **RAG ground cách nói và cách nhận diện, không ground việc chọn câu hỏi lâm sàng.** Muốn
thêm câu hỏi mới thì thêm vào protocol (track PC (§3.2)) và qua review lâm sàng — đó là con đường đã có, và
nó chậm hơn RAG đúng ở chỗ nó nên chậm.

Hạ tầng: `pipeline/weaviate_cloud.py` đã có nhưng đang là nhánh tooling ngoài luồng chuẩn (§3.3 P5).
Việc đầu tiên là quyết định nó có vào luồng hay không, trước khi bàn ground cho tầng nào.

---

### 4.7. Khi nào dừng — bổ sung hai điều kiện còn thiếu

`should_stop` hiện có 4 reason code (§3.3 P3.9 đang bổ sung nhánh ý định người dùng). Yêu cầu thêm hai
tình huống, cả hai đều **không** được là dừng tức thì:

**(a) "Không còn triệu chứng gì khác."** Là tín hiệu mạnh, **không phải lệnh dừng tuyệt đối**:

```text
"không còn gì nữa"
      ↓
còn cụm CHƯA HỎI mang field M0/M1?
   ├─ CÓ  -> vẫn hỏi nốt, nhưng nói rõ vì sao:
   │         "Mình hỏi thêm 2 ý an toàn nữa rồi chốt nhé."
   └─ KHÔNG -> STOP
```

Lý do giữ nhánh trên: người bệnh nói "hết rồi" khi chưa ai hỏi họ về đau lan xuống tay hay ngất — họ
không biết những thứ đó là triệu chứng cần khai. Đây đúng là §1 mục 8, không phải ngoại lệ mới.

**(b) Bất hợp tác / lạc đề / chửi tục.** Không dừng ngay ở lượt đầu. Đếm ba tín hiệu:

```text
off_topic_streak        (số lượt liên tiếp không trả lời câu đang hỏi)
clinical_information_gain  (lượt vừa rồi có field nào mới không)
explicit_refusal
```

Ngưỡng đề xuất: **2–3 lượt liên tiếp** vừa lạc đề vừa không thu được field mới ⇒ agent **hỏi một lần**:

> Nếu bạn không muốn bổ sung thêm, mình có thể tổng hợp những gì đã có. Bạn muốn dừng ở đây không?

Tiếp tục không hợp tác ⇒ `STOP` với reason code mới `USER_UNCOOPERATIVE`, và **phiếu phải đánh dấu
incomplete** kèm `missing_information` — hệt như nhánh ý định người dùng ở P3.9. Ba lý do dừng khác
nhau không được thu về cùng một phiếu trông giống nhau: điều dưỡng cần biết ca này thiếu thông tin vì
người bệnh bỏ dở, chứ không phải vì không có triệu chứng.

**Chửi tục đơn lẻ không phải tín hiệu dừng.** Người đang đau và sợ thì nói năng không dễ chịu — đó là
bối cảnh y tế bình thường. Chỉ đếm khi nó **đi kèm** việc không trả lời.

---

### 4.8. Hỏi nhanh hơn: batch lớn — và quy tắc suy `False` phải sửa

**Phần đồng ý, làm ngay:** batch nhiều field trong một lượt là cách chính để rút ngắn hội thoại, và
`batching.py` (206 dòng) + `ScreeningGroup` đã làm đúng thế. Có thể **tăng kích thước batch**, đặc
biệt cho nhóm câu hỏi Có/Không cùng chủ đề. Trần trên vẫn cần: 20 câu một lượt thì người bệnh bỏ sót,
trả lời không theo thứ tự, và một chữ "không" không biết đang phủ định câu nào (V2 §6 nói đúng).
Đề xuất **4–7 ý mỗi lượt**, gom theo nhóm, và tune bằng `abandonment_rate`.

**Phần phải làm khác yêu cầu — nêu một lần rồi chuyển sang phương án:**

> Yêu cầu: *"hỏi một đống câu, người dùng bỏ qua cái nào thì cho cái đấy là False luôn"*.
>
> Im lặng không phải phủ định. Người bệnh bỏ qua một ý vì không đọc kỹ, vì không hiểu, hoặc vì không
> biết — và khi field đó là `chest_pain_radiation` hay `loss_of_consciousness` thì "suy ra False" tạo
> ra một phiếu ghi *"người bệnh phủ nhận ngất"* trong khi **chưa ai hỏi họ về ngất**. Điều dưỡng đọc
> phiếu đó không có cách nào biết sự khác nhau. Đây đúng là loại lỗi im lặng mà `CLAUDE.md` nguyên
> tắc 3 nhắm tới, và nó cũng xoá mất chính distinction `NULL ≠ UNKNOWN` mà kế hoạch V2 §3 nhấn mạnh.

**Phương án đạt được cùng mục tiêu (hỏi ít lượt hơn) mà không tạo dữ liệu sai — theo tier field:**

| Tier | Bỏ qua trong batch ⇒ | Lý do |
| --- | --- | --- |
| M0/M1, field an toàn | `unknown` + **hỏi lại đúng một lần**, ngắn gọn | Không được suy diễn ở chỗ đắt nhất |
| C (protocol-specific) | `unknown`, không hỏi lại | Ghi vào `missing_information` là đủ |
| O/H (tuỳ chọn) | `false` — **đúng như yêu cầu** | Chi phí sai thấp, lợi ích tốc độ thật |

Cộng thêm một mẹo rẻ hơn mọi suy diễn: **cho người bệnh phủ định gộp một câu**. `ScreeningGroup` đã
làm sẵn cơ chế này — hỏi "còn 4 dấu hiệu sau, bạn có cái nào không?" và một chữ "không" đóng cả bốn
field một cách **tường minh**, vì người bệnh đã nghe đọc đủ danh sách (`models.py:36-64`,
`session.py:94-96` ghi rõ guard turn-scoping). Đó là cách hợp lệ để một lượt lấp nhiều field: **người
bệnh phủ định, chứ không phải hệ thống suy ra.**

---

### 4.9. Memory — ba giai đoạn, không làm ngược thứ tự

**Yêu cầu (đủ ba tầng):** composite key `user_id + conversation_id`; short memory hybrid; long memory
vào DB, mở hội thoại mới thì lấy 3 phiên gần nhất để hỏi thăm.

Hướng thiết kế đúng, nhưng **thứ tự thực thi phải đảo lại** vì một dữ kiện: `ARCHITECTURE.md:364-369`
ghi `session_store` còn **mất khi restart** — phiên đang dở còn chưa sống nổi qua một lần deploy, mà
đã bàn tới ký ức xuyên phiên. Ba giai đoạn:

**M1 — Composite key + persist phiên đang dở.** *Điều kiện tiên quyết của hai giai đoạn sau.*

- Key: `user_id + conversation_id`, mỗi hội thoại là một collection độc lập.
- ⚠️ **`conversation_id` không nên là timestamp** như V2 §3.2 đề xuất: hai phiên mở cùng giây sẽ đụng
  nhau, và timestamp trong khoá là một mẩu metadata rò ra ngoài. Dùng UUID/ULID, để `created_at` ở một
  cột riêng.
- Persist event log + snapshot sau mỗi lượt được nhận. Đây chính là thứ khiến "hỏi vu vơ rồi quay lại
  hỏi cái cũ" chạy được qua một lần restart.

**M2 — Short memory hybrid.** Đúng như yêu cầu mô tả (cách 3), và **phần lớn đã chạy**:

```text
Structured snapshot   [ĐÃ CÓ - reducer, là nguồn sự thật]
+ Tóm tắt lượt cũ      [CHƯA CÓ - cần khi context dài]
+ N lượt raw gần nhất  [ĐÃ CÓ - session.conversation]
```

Chỉ thiếu bước nén khi context vượt ngưỡng. Bất biến: **summarizer nén phần hội thoại, không bao giờ
ghi đè snapshot.** Nếu tóm tắt và snapshot bất đồng thì snapshot thắng — nó là thứ có bằng chứng
`evidence_span`, còn bản tóm tắt thì không.

**M3 — Long memory + hỏi thăm phiên trước.** Lưu `nurse_summary_json` thành một cột như yêu cầu; mở
hội thoại mới thì lấy 3 `conversation_id` gần nhất, tóm tắt lại để agent hỏi thăm. Ba điều kiện tối
thiểu, vì đây là PHI (`CLAUDE.md` nguyên tắc 5):

1. **Bất biến tuyệt đối — dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.** `previous fever =
   true` **không** được nạp thành `current fever = true`. Nó vào một namespace riêng (`history.*`),
   chỉ dùng để agent hỏi lại, và snapshot phiên mới bắt đầu từ `NULL` như mọi phiên khác. Đây là bất
   biến số một của cả M3, và cũng là điều chính V2 §22 đã nhấn mạnh.
2. **Truy cập theo đúng `user_id` đang đăng nhập**, không có đường nào đọc chéo hồ sơ người khác. Cần
   một test cho riêng việc này.
3. **Consent + retention** — bệnh nhân biết hệ thống nhớ gì và trong bao lâu. Đây là câu hỏi cho PM,
   không phải cho kỹ thuật, nhưng nó phải có câu trả lời **trước khi** M3 lên production.

Trải nghiệm mà M3 mở ra (*"Lần trước bạn đau bụng, hiện đã đỡ hơn chưa? Có làm theo lộ trình bác sĩ
đưa không?"*) là thứ đáng làm — nó biến sản phẩm từ một form hỏi bệnh thành một chỗ có người theo dõi.
Chỉ cần nó đứng sau M1.

---

### 4.10. Mở rộng protocol: hai loại, đừng trộn vào nhau

**Yêu cầu:** hết tập trung vào fever; thêm bụng/đầu/lưng/da/tình dục; xử lý được cả long-tail (ngứa
chân, ê mông, nghi giang mai) và cả chitchat/lifestyle (uống bia, chạy bộ); dùng model nhỏ để route.

Điểm quan trọng nhất của mục này: **những thứ đang được gọi chung là "protocol" thực ra là hai loại
khác hẳn nhau**, và trộn chúng vào một registry sẽ hỏng cả hai.

| | **Protocol lâm sàng** | **Protocol phi lâm sàng** |
| --- | --- | --- |
| Ví dụ | fever, bụng, ngực, khó thở, đầu | chitchat, lifestyle, summarize, search\_db |
| Nội dung | field + tier + cụm + skip-rule + luật triage | intent handler, không có checklist |
| Ai viết | Data Lead + review lâm sàng | Engineering |
| Quy mô | ~700 dòng logic lâm sàng mỗi nhóm | vài chục dòng |
| Sinh red flag | Có | **Không** — nhưng L0 vẫn chạy trên mọi lượt |
| Nằm ở | track PC (§3.2) | track P |

**Ba nhóm ca cần xử lý, ba đường khác nhau:**

1. **Trong 5 nhóm MVP** → protocol lâm sàng riêng. Đây là track PC (§3.2), hạng mục lớn nhất còn lại.
2. **Long-tail ngoài 5 nhóm** (ngứa chân, ê mông, nghi giang mai) → `GENERIC_PROTOCOL` + L0 safety.
   Agent vẫn hỏi được, vẫn bắt được red flag, và `registry.py:27-30` đã ghi nguyên tắc đúng: **generic
   không bao giờ kết luận an toàn** — nó thu thập rồi bàn giao, không tự trấn an. Cách xử lý long-tail
   là *bàn giao sớm cho người*, không phải *cố tỏ ra biết*.
3. **Phi lâm sàng** (uống bia, chạy bộ) → protocol phi lâm sàng.

> **Về ví dụ "uống bia khi đang dùng kháng sinh":** cách xử lý đúng là hỏi **đang dùng thuốc gì, điều
> trị bệnh gì**, rồi bàn giao — không hard-code "kháng sinh + bia ⇒ tê liệt thần kinh". Tương tác với
> rượu phụ thuộc thuốc cụ thể, liều, bệnh nền; một luật rộng như vậy vừa sai về y khoa vừa là dạng
> "kết luận" mà `CLAUDE.md` nguyên tắc 2 cấm. Chính kế hoạch V2 §46 NFR4 cũng đã kết luận đúng như
> thế. Với MVP, đường an toàn nhất cho nhóm này là: thu thập thuốc/bệnh nền → không đưa lời khuyên →
> bàn giao.

**Router bằng model nhỏ (Qwen3.5-4B):** hạ tầng đã sẵn — `RoleProfile` có sẵn vai trò
`symptom_group_router` (§2), chỉ cần đổi `ROLE_ORDER_SYMPTOM_GROUP_ROUTER`. Bốn ràng buộc đã chốt ở
§3 vẫn nguyên: router **chỉ được gọi trong 4 trigger** ở §2 (không phải mọi lượt), sàn deterministic
`registry.select_protocol` chạy trước, route sai **không được** làm mất common-safety red flag (§7
test 6), và điều kiện tự host SLM nằm ở §2 — chưa trả lời được cho tới khi P1.4 có số đo.

**Multi-protocol đồng thời** (`primary` + `secondary[]` như V2 §6): xem §3.3 PC+. Xếp sau PC vì
merge hai protocol chỉ có nghĩa khi có hơn một protocol thật để merge.

---

### 4.11. Controller bằng Qwen3.5-4B — model đề xuất, code định đoạt

**Quyết định:** dùng Qwen3.5-4B tự host làm tầng điều phối; mọi worker khác (`fact_extractor`,
`synthesis`) tiếp tục gọi Gemini API. Mục tiêu là chuyển phần quyết định điều phối khỏi core LLM và
cắt token của nó.

Đây là **sửa đổi có chủ đích của bất biến §1 mục 2**, không phải một ngoại lệ lặng lẽ. Điều kiện để
sửa đổi đó không làm mất bất biến §1 mục 3 nằm ở toàn bộ phần dưới.

#### Nguyên tắc: tập hành động hợp lệ do code tính trước

Model **không** trả lời câu hỏi "làm gì tiếp theo" trên một không gian mở. Code tính trước tập hành
động hợp lệ cho đúng trạng thái hiện tại, model chỉ **chọn một phần tử trong tập đó**:

```text
L0 text_safety_signals        [KHÔNG model - luôn chạy TRƯỚC controller]
        ↓
code: admissible_actions(session_state)   -> tập đóng, ví dụ {extract, route, answer_meta}
        ↓
Qwen-4B: chọn 1 + gán nhãn intent          -> ĐỀ XUẤT
        ↓
code: giao ∩ admissible_actions
        ├─ khác rỗng  -> thi hành
        └─ rỗng / timeout / JSON hỏng -> controller tất định (nhánh đang chạy hôm nay)
```

Điểm quan trọng của thiết kế này: **đường fallback chính là hệ thống hiện tại**. Model chết thì hành
vi quay về đúng cái đang có 590 test bám vào — nên rủi ro hồi quy bằng không, và đó cũng là lý do
việc này triển khai được mà không phải viết lại tầng nào.

#### Hợp đồng output

```json
{
  "lane": "clinical | non_clinical | meta",
  "next_action": "extract | route_protocol | answer_meta | summarize | handoff",
  "protocol_hint": "fever | generic | lifestyle | chitchat | null",
  "user_intent": { "stop": false, "off_topic": false, "asks_meta": false },
  "confidence": 0.0
}
```

**Controller được quyết:** gọi worker nào; lane lâm sàng hay phi lâm sàng; protocol nào; nhãn ý định.

**Controller KHÔNG được quyết** — bốn thứ này giữ nguyên ở code, và đây là ranh giới không nới:

| Không được quyết | Vẫn ở đâu |
| --- | --- |
| Cụm câu hỏi lâm sàng tiếp theo | `ranking.py` + `stage_machine.select_cluster` |
| Dừng hay hỏi tiếp | `should_stop` — controller chỉ *báo* `user_intent.stop`, nhánh này đi qua `user_can_continue` như §3.3 P3.9 |
| Mức ưu tiên | `rule_engine` |
| Red flag | L0 + `common_safety/rules.py`, cả hai chạy độc lập với controller |

#### Sáu ràng buộc thi hành

1. **L0 chạy trước controller, luôn luôn.** Controller không có cơ hội chặn hay hạ một tín hiệu đỏ —
   nó chạy sau, trên một phiên đã có thể đang escalate.
2. **`next_action` không có giá trị `stop`.** Ý định dừng chỉ đi qua `user_intent.stop` →
   `user_can_continue` → `should_stop`. Một model 4B không được là thứ kết thúc phiên khám.
3. **Timeout cứng 300ms.** Vượt là dùng controller tất định, không chờ. Ngân sách lượt hiện là p50
   3.98s và phần lớn nằm ở `fact_extractor`; controller không được phép trở thành một chặng chờ.
4. **Cho model đủ ngữ cảnh, đừng chỉ đưa text thô.** Kèm một khối trạng thái nén: protocol đang gắn,
   cụm hiện tại, `turn_count`, `mandatory_remaining`, có escalation chưa. Rẻ về token và là khác biệt
   giữa một dispatcher đoán mò với một dispatcher biết mình đang ở đâu.
5. **Công tắc ngắt bắt buộc** (`AGENT_LLM_CONTROLLER_ENABLED`). Hợp lệ vì controller không phải tầng
   an toàn theo định nghĩa mới — nó chỉ chọn trong tập code đã duyệt. Tắt cờ ⇒ hệ thống chạy y như
   hôm nay.
6. **Toàn bộ 590 test phải xanh khi tắt cờ.** Test tất định không bao giờ được phụ thuộc vào một
   endpoint GPU.

#### Triển khai ba bước — bước 1 không cần GPU

**Bước 1 — Shadow mode.** Chạy controller-4B song song, **ghi log lựa chọn của nó, nhưng thi hành
theo controller tất định**. Rủi ro bằng không, và sau N phiên có `controller_agreement_rate` để quyết
định có bật thật hay không. Chạy được trên endpoint Qwen của bên thứ ba — **chưa cần dựng GPU**, vì
biến chưa biết ở bước này là *chất lượng*, không phải hạ tầng.

**Bước 2 — Bật cho nhánh phi lâm sàng trước.** `lane == non_clinical` (chitchat, lifestyle) là chỗ
rủi ro thấp nhất: không có checklist để bỏ sót, và cũng là chỗ hệ thống hiện yếu nhất. Nhánh
`clinical` vẫn đi controller tất định.

**Bước 3 — Bật toàn phần**, chỉ khi `controller_agreement_rate` đạt ngưỡng ở §8 và không ca an toàn
nào ở §7.7 đỏ.

#### Về latency và cost — số cần đo, không phải số để tranh luận

Một điều chỉnh so với nhận định trước đó: ở **4 trigger route** (§2), controller-4B **thay thế** lời
gọi `symptom_group_router` chứ không cộng thêm. Phụ trội chỉ rơi vào các lượt còn lại, và trần 300ms
ở ràng buộc 3 chặn trên phần đó.

Phần cost phải đo bằng ba con số, cả ba đều chưa có:

1. Token/phiên của `fact_extractor` và `synthesis` **trước và sau** khi có controller — controller
   không thay thế hai lời gọi này, nên phần cắt được đến từ việc bỏ lượt gọi extractor ở các lượt
   `greeting`/`off_topic` thuần. **Đo tỉ lệ những lượt đó trước**, vì nó là trần của toàn bộ phần
   tiết kiệm.
2. Hoá đơn Gemini thật hiện tại — chưa ai đo.
3. Chi phí cố định của GPU service, và **ai vận hành nó sau khi sprint kết thúc**.

`role_usage_snapshot()` + bảng *Per-Role LLM Usage* của `run_eval.py` cho câu 1 mà không phải viết
thêm gì.

### 4.12. Nghi ngờ red-flag — hợp đồng ngôn ngữ với bệnh nhân

**Quyết định (2026-08-19), giải xung đột ADR-004 vs Feature Spec :253-256:** hệ thống **không khẳng
định cấp cứu**. Nó nêu **nghi ngờ**, đẩy ca lên ưu tiên cao nhất cho điều dưỡng, và điều dưỡng —
trực **24/7** — mới là người kết luận.

Đây là nguyên tắc y tế chuẩn: **công cụ sàng lọc nêu nghi ngờ, lâm sàng viên kết luận.** Nó cũng là
lý do quyết định này giải được xung đột thay vì chọn một bên — nó thoả mãn lo ngại *thật* của cả hai
tài liệu:

| Tài liệu | Lo ngại thật | Được giải bằng |
| --- | --- | --- |
| Feature Spec :253-256 | Hệ thống tự khẳng định kết luận lâm sàng chưa qua người | Không còn khẳng định nào — chỉ nêu nghi ngờ |
| ADR-004 | Bệnh nhân bị bỏ mặc chờ trong tình huống nguy hiểm | Trực 24/7 + câu an toàn phổ quát ngay từ t=0 |

Từ vựng đã có sẵn trong code: `SignalStatus.CONFIRMED_POSITIVE` / `NEEDS_CONFIRMATION`
(`text_safety_signals.py:54-56`). Tầng L0 vốn đã nghĩ theo kiểu "nghi ngờ"; chỉ có câu nói với bệnh
nhân là chưa theo.

#### Ba thông điệp tĩnh, ba thời điểm

Cả ba **không đi qua LLM**, không nêu tên bệnh, không nêu lý do lâm sàng (bất biến §1 mục 6).

**`SUSPECTED_RED_FLAG_MESSAGE` — phát ngay tại t=0, cùng lượt phát hiện:**

> Có một số thông tin bạn vừa mô tả cần nhân viên y tế xem trực tiếp. Ca của bạn đã được chuyển lên
> mức ưu tiên cao nhất và sẽ có người liên hệ trong ít phút.
>
> Trong lúc chờ, nếu bạn thấy tình trạng xấu đi hoặc thấy không ổn, hãy gọi 115 ngay — đừng chờ phản
> hồi ở đây.

Đoạn thứ hai là **lưới an toàn phổ quát**: nó đúng với mọi người bệnh trong mọi tình huống, nên nói
ra không phải là chẩn đoán. Đây là chỗ quyết định 2026-08-19 khác với phương án "chỉ hiện *ca của bạn
đang được ưu tiên xem xét*" của Feature Spec — im lặng hoàn toàn về mặt an toàn thì đẩy toàn bộ rủi
ro sang thời gian phản hồi của điều dưỡng.

**`SLA_BREACH_MESSAGE` — tự động, khi quá SLA mà chưa điều dưỡng nào mở ca:**

> Chưa có nhân viên y tế phản hồi kịp. Để an toàn, vui lòng gọi 115 hoặc đến cơ sở y tế gần nhất ngay
> bây giờ.

HITL là đường chính; đây là lưới đỡ khi đường chính kẹt. **Không có nó thì "chờ điều dưỡng" có thể âm
thầm trở thành "chờ vô hạn"** khi ca trực quá tải hoặc hệ thống thông báo lỗi.

**`EMERGENCY_MESSAGE` — nội dung hiện tại, nhưng chuyển sang SAU khi điều dưỡng xác nhận.** Câu đang
có (*"Đây là tình huống cần được cấp cứu ngay bây giờ…"*) không sai — nó chỉ đang được nói bởi sai
người, ở sai thời điểm. Giữ nguyên văn, dùng làm mặc định cho `approved_response` ở bước duyệt.

#### Con số duy nhất còn thiếu: SLA

`SLA_BREACH_MESSAGE` vô nghĩa nếu không có trần thời gian. **Đây là câu hỏi cho PM và cho người tổ
chức ca trực, không phải cho engineering** — nhưng nó phải nằm trong ADR-007, vì thiếu nó thì cam kết
"24/7" không kiểm chứng được.

**Chốt tạm (2026-08-19): SLA = 5 phút**, tính từ lúc ca vào hàng đợi tới lúc một điều dưỡng **mở**
ca (không phải tới lúc duyệt xong). Cấu hình được, sẽ hiệu chỉnh sau khi có thống kê thật.

Kèm **ngưỡng cảnh báo nội bộ ở 60% SLA (3 phút)** — báo cho ca trực trước khi chạm trần, để
`SLA_BREACH_MESSAGE` là ngoại lệ chứ không phải chuyện thường ngày.

#### Hai số, không phải một — chỗ dễ sai nhất khi hiệu chỉnh sau này

Kế hoạch hiệu chỉnh là "đo rồi lấy p99". Cần tách rạch ròi, vì nếu đặt `SLA = p99 quan sát được` thì
theo đúng định nghĩa `sla_breach_rate` luôn ≈ 1%, và **SLA thôi không còn là yêu cầu an toàn — nó trở
thành bản mô tả năng lực hiện tại**. Lúc đó chỉ số này không còn phát hiện được điều gì.

| Số | Nghĩa | Suy ra từ | Dùng để |
| --- | --- | --- | --- |
| `SLA_clinical` | Ca nghi ngờ cấp cứu **được phép** chờ bao lâu | Nhu cầu lâm sàng | Kích hoạt `SLA_BREACH_MESSAGE` |
| `p99_observed` | Thực tế ca trực **đang** đáp ứng bao lâu | Đo | Biết có đủ người trực không |

Quan hệ đúng: **`SLA_clinical` quyết trước bằng lý do y tế, rồi bố trí nhân sự để `p99_observed` chui
xuống dưới nó.** Nếu `p99_observed > SLA_clinical` thì đó là **vấn đề nhân sự**, không phải vấn đề
cấu hình — nới `SLA_clinical` cho vừa số đo là hợp thức hoá độ trễ chứ không sửa gì.

Hai lưu ý khi lấy thống kê:

- **Đừng hiệu chỉnh từ dữ liệu demo.** p99 đo trên vài chục ca thử nghiệm không phản ánh tải thật, và
  nó sẽ đẹp một cách giả tạo vì lúc đó ai cũng đang nhìn màn hình.
- Cỡ mẫu cho p99 phải đủ: dưới ~300 ca thì p99 chỉ là một hai điểm dữ liệu ngoài rìa.

Chỉ số theo dõi từ ngày đầu: **`sla_breach_rate`**, và nó phải gần 0 **so với `SLA_clinical`**. Không
gần 0 thì cam kết trực 24/7 chỉ có trên giấy, và lập luận an toàn của §4.12 sụp.

#### Thay đổi cụ thể

| Chỗ | Sửa gì |
| --- | --- |
| `common_safety/emergency_message.py` | Thêm `SUSPECTED_RED_FLAG_MESSAGE`, `SLA_BREACH_MESSAGE`; giữ `EMERGENCY_MESSAGE` cho bước sau duyệt |
| `session.py:606-618` | Đẩy `SUSPECTED_RED_FLAG_MESSAGE` vào hội thoại thay cho `EMERGENCY_MESSAGE` |
| `triage_level` nội bộ | **Giữ nguyên `EMERGENCY`** — rule engine, hàng đợi và ưu tiên không đổi. Chỉ đổi thứ bệnh nhân đọc |
| Hàng đợi điều dưỡng | Đã đẩy ưu tiên sẵn; thêm đồng hồ SLA + cảnh báo trước ngưỡng |
| W-04 (UI bệnh nhân) | Theo `SUSPECTED_RED_FLAG_MESSAGE`; thêm trạng thái quá SLA |
| `docs/context/decisions.md` | **ADR-007 supersede ADR-004**, và sửa trạng thái Feature Spec cho khớp |

Lưu ý về phạm vi: `triage_level = "EMERGENCY"` **không đổi**. Đây thuần tuý là thay đổi tầng ngôn ngữ
và tầng hiển thị — mọi luật an toàn, `escalation_lock`, thứ tự hàng đợi giữ nguyên. Đó cũng là lý do
việc này làm được trong một sprint ngắn.

## 5. Non-functional: UX, ngôn ngữ, và độ dài hội thoại

### 5.1. Trình bày phản hồi

| Yêu cầu | Trạng thái |
| --- | --- |
| Streaming | ✅ `/chat/stream` |
| Xuống dòng, không đoạn quá dài, bullet cho câu Có/Không | ✅ §5.1 — hai đoạn tách nhau, gạch đầu dòng khi nhiều ý |
| Cấm in đậm/nghiêng/bảng/tiêu đề | ✅ có lý do: markdown phải hợp lệ theo **từng mẩu** stream |
| **Loading indicator** | ⛔ chưa xác nhận ở UI |

Một chi tiết đã đo và cần biết khi động vào phần này: renderer streaming hiện **gom trọn rồi mới phát**
— `output_guard` phải chạy xong trước khi người bệnh đọc được chữ nào. Cái giá là **p50 ~1.2s** im
lặng trước khi chữ đầu tiên hiện ra. Đây chính là chỗ loading indicator có giá trị nhất, và cũng là lý
do không nên "sửa" độ trễ đó bằng cách phát sớm: guard chạy sau khi người bệnh đã đọc thì không còn là
guard.

### 5.2. Ngôn ngữ cho người không có chuyên môn y tế

Không dùng thuật ngữ (*dyspnea*, *orthopnea*); hỏi Có/Không, mức độ, thời gian, vị trí, con số cụ thể
nếu người bệnh biết. Cơ chế đã có: `synthesis` diễn đạt lại câu hỏi mà rule engine đã chọn, và
`output_guard` chặn phần vượt phạm vi.

Một ngoại lệ đã chốt và **không nên "cải thiện"**: câu sàng lọc gộp được ghép **tĩnh** từ
`ScreeningGroup.probe_hint`, không cho LLM diễn đạt lại — vì "LLM diễn đạt lại thì có thể lược mất
vài ý trong danh sách" (`models.py:52-56`). Với một danh sách dấu hiệu nguy hiểm, lược một ý là mất
một cơ hội phát hiện. Đây là chỗ chấp nhận văn phong cứng hơn để đổi lấy tính đầy đủ.

### 5.3. Giảm dài dòng — bảy cơ chế, và cái nào chưa dùng hết

Yêu cầu nêu đúng bản chất: y tế cần chính xác nên **phải đánh đổi**, nhưng đánh đổi phải có cơ chế
chứ không phải "cứ còn `NULL` thì cứ hỏi".

| Cơ chế | Trạng thái | Còn dư địa |
| --- | --- | --- |
| Protocol routing | ✅ | Nhiều — 4/5 nhóm chưa có (track PC (§3.2)) |
| Active field selection theo protocol | ✅ | |
| Priority scoring (tier M0/M1/C/O/H) | ✅ `ranking.py` | |
| Question batching | ✅ `batching.py` | **Có — tăng batch lên 4–7 ý (§4.8)** |
| State reuse (không hỏi lại field đã biết) | ✅ | |
| Soft turn budget | ✅ `protocol.budget` | |
| Information gain / dừng theo đủ căn cứ | ✅ `_has_sufficient_evidence` | |
| Phủ định gộp theo nhóm | ✅ `ScreeningGroup` | **Có — dùng nhiều hơn (§4.8)** |

Số đo hiện tại: ca lành tính đi hết **21 lượt**. Ba đòn bẩy rẻ nhất để kéo xuống, theo thứ tự:

1. **Tăng kích thước batch** và dùng phủ định gộp nhiều hơn (§4.8) — thuần cấu hình + nội dung.
2. **Bỏ cụm tier O/H sớm hơn** khi đã đủ căn cứ.
3. **Nhánh ý định người dùng** (§3.3 P3.9) — người bệnh chủ động chốt sớm.

Và một chỉ số phải đọc **cùng lúc** với số lượt, nếu không sẽ tối ưu sai: `mandatory_unasked` phải
rỗng ở 100% phiên (§8). Rút ngắn hội thoại bằng cách bỏ hỏi field bắt buộc là làm hỏng đúng thứ sản
phẩm này tồn tại để làm.

---

## 6. Hợp đồng phiếu bàn giao: ADR-006 và template ISBAR

ADR-006 ("format phiếu tóm tắt phải chốt trước khi viết schema JSON") vẫn để trống, trong khi
`HandoffSummary` (`src/models/schemas.py:138-149`) đã chạy và UI W-07 đã dựng theo nó. Đây là món nợ
duy nhất trong tài liệu này thuộc về **hợp đồng dữ liệu** chứ không phải hành vi agent.

Team có một template ISBAR (*"Cấu trúc ISBAR chuẩn cho AI sinh ra phiếu tóm tắt [WHO]"*). Đối chiếu
với schema đang chạy:

| Template ISBAR | `HandoffSummary` hiện có | Việc phải làm |
| --- | --- | --- |
| **[I]** Patient: tuổi, giới tính | ❌ | Thêm `age`, `sex` |
| **[I]** Triage Category | ✅ `proposed_priority` | Thêm `provisional_priority` + `priority_source` (§4.2) |
| **[S]** Lý do vào viện, 1 câu | ✅ `chief_complaint` | — |
| **[B]** Dị ứng: Có/Không/Unknown | ❌ | Thêm `allergies`, dùng đúng 3 giá trị của reducer |
| **[B]** Bệnh nền | ❌ | Thêm `comorbidities` — **liệt kê tất cả**, xem mục 4 dưới |
| **[B]** Thuốc đang dùng | ❌ | Thêm `current_medications` |
| **[A]** Onset | ✅ `onset` | — |
| **[A]** Severity | ✅ `severity` | — |
| **[A]** Red Flags Detected | ✅ `red_flags` | Thêm `red_flag_agreement` (§4.1) |
| **[A]** Missing Information | ✅ `missing_information` | — |
| **[R]** AI Action / Pending Action | ⚠️ | Đổi tên, xem mục 3 dưới |
| — | ✅ `protocol_reason`, `detect_source`, `grounding_source` | **Giữ** — dấu vết truy nguyên |
| — | ✅ `associated_symptoms` | — |

**7/13 trường đã có; 4 trường thiếu là dữ liệu hành chính/tiền sử đơn giản; 2 trường cần quyết định.**
Tức là **bổ sung field, không phải migrate kiến trúc**.

Năm câu hỏi cần chốt trong ADR-006, kèm khuyến nghị:

1. **Giữ `HandoffSummary` phẳng và map ISBAR ở tầng render, hay đổi schema thành lồng I/S/B/A/R?**
   → *Khuyến nghị: giữ phẳng, map khi render.* Rẻ hơn, không đụng `NurseQueueItem`, và giữ được bất
   biến "natural summary và phiếu bàn giao đọc **cùng một** snapshot đã validate" (§4.3).
2. **Bổ sung 5 trường còn thiếu** như bảng trên. Dị ứng dùng đúng semantics 3 giá trị
   (`true`/`false`/`unknown`) của reducer, **không thêm kiểu mới**.
3. **Khối `[R]` viết như hành động đã thực hiện** (`AI Action: Khuyên bệnh nhân đến bệnh viện ngay`).
   Đọc theo mặt chữ thì AI đã khuyên bệnh nhân trước khi điều dưỡng duyệt — ngược `CLAUDE.md` nguyên
   tắc 1. → *Khuyến nghị: đổi thành `proposed_action` + `approval_status`.* Ngoại lệ duy nhất đã chốt:
   ca `EMERGENCY` hiện `EMERGENCY_MESSAGE` tĩnh ngay, không chờ duyệt và không do model sinh
   (`CLAUDE.md` nguyên tắc 4, §4.2).
4. **`Bệnh nền: chỉ hiển thị bệnh có liên quan nếu AI có khả năng lọc`** giao một phán đoán lâm sàng
   cho LLM. Lọc sai thì điều dưỡng không có cách nào biết cái gì đã bị giấu — lỗi im lặng, và ngược
   `CLAUDE.md` nguyên tắc 3. → *Khuyến nghị MVP: liệt kê tất cả.* Sắp xếp lại thì được (bằng danh sách
   tĩnh do lâm sàng ký duyệt, giống `SHORT_CIRCUIT_CODES`); giấu đi thì không.
5. **Nhãn RED/YELLOW/GREEN hay *Cấp cứu / Khám sớm / Tự theo dõi*?** `CLAUDE.md` và UI đang dùng tiếng
   Việt. → Nếu phiếu cho điều dưỡng dùng màu theo WHO thì đó là **nhãn hiển thị**; giá trị lưu trong
   `TriagePriority` giữ nguyên.

**Quy tắc render, áp cho cả JSON và HTML** (§4.3):

- Trường không có giá trị ⇒ **không xuất** trong JSON gửi renderer, và renderer chỉ render trường tồn
  tại. Không xuất `"allergies": null`.
- **Nhưng snapshot giữ đủ ba giá trị.** Việc lọc xảy ra ở renderer, không ở nguồn dữ liệu.
- **Ngoại lệ — field an toàn luôn được render** kể cả khi `false` hoặc `unknown`. "Người bệnh phủ nhận
  đau lan xuống tay" và "chưa ai hỏi về đau lan xuống tay" là hai thứ điều dưỡng bắt buộc phải phân
  biệt được, và đó chính là chỗ họ nhìn đầu tiên.
- Kèm `raw_conversation` — toàn văn câu trả lời của người bệnh.

**Điều dưỡng sửa được mọi trường của phiếu này, gồm cả red flag** — xem §4.4 về lớp overlay giữ
`generated_value` và về việc `escalation_lock` (khoá trong phiên, chặn model) không phải là khoá
quyền của điều dưỡng.

Một điểm template làm **đúng**: nó giữ `Triage Category` ngay trong khối `[I]`. Trường này **do code
tất định điền, không do LLM** — cần ghi rõ điều đó trong chính template, vì đó là chỗ dễ bị hiểu nhầm
nhất khi người mới đọc phiếu.

---

## 7. Bộ test bắt buộc

Các nhóm dưới đây gắn với **việc chưa làm**. Test của phần đã chạy nằm trong `tests/test_services/`
và không chép lại vào đây; điều kiện duy nhất là **không được giảm** chúng.

### 7.1. Ý định người dùng và dừng phiên (§3.3 P0.6, P3.9)

1. **Ca chặn của P0.6:** cùng một lượt vừa khai dấu hiệu cấp cứu vừa nói "thôi tôi không trả lời nữa"
   → `should_stop` phải trả `RED_FLAG`, **không** `USER_CANNOT_CONTINUE`.
2. Thứ tự còn lại đúng như docstring: `USER_CANNOT_CONTINUE` thắng `SUFFICIENT_EVIDENCE` và
   `BUDGET_EXHAUSTED` khi không có tín hiệu đỏ.
3. "Tóm tắt cho tôi đi" → dừng, và phiếu có `missing_information` liệt kê field M0/M1 còn `unset`.
4. "Không còn triệu chứng nào khác" **không** phải lệnh dừng tuyệt đối: còn cụm CHƯA HỎI mang field
   M0/M1 thì vẫn phải hỏi tiếp.
5. Câu chửi tục hoặc lạc đề đơn lẻ không được suy thành `user_can_continue=False`.
6. Intent dừng không được hạ một escalation đã khoá.

### 7.2. Dừng vì bất hợp tác (§4.7)

1. Một lượt lạc đề đơn lẻ (kể cả có chửi tục) **không** dừng phiên.
2. 2–3 lượt liên tiếp lạc đề + không thu được field mới → agent hỏi một lần, chưa dừng.
3. Vẫn không hợp tác sau câu hỏi đó → `USER_UNCOOPERATIVE`, phiếu đánh dấu incomplete.
4. Ba lý do dừng (`USER_CANNOT_CONTINUE`, `USER_UNCOOPERATIVE`, `SUFFICIENT_EVIDENCE`) tạo ra ba phiếu
   **phân biệt được với nhau**.

### 7.3. Red flag hai nhánh và quyền của điều dưỡng (§4.1, §4.4)

1. Model bắt được red flag mà rule bỏ sót → vẫn escalate, và mục đó vào `red_flag_agreement.model_only`.
2. **Model KHÔNG tắt được red flag mà rule đã bật** — kể cả khi model khẳng định ngược lại.
3. Nhánh model timeout/JSON hỏng → hai nhánh cũ vẫn chạy đủ, `model_branch_status="failed"` vào log,
   không mất phát hiện nào.
4. `red_flag_agreement` không có đường nào tác động vào `proposed_priority` — đổi nội dung nó và khẳng
   định mức ưu tiên không đổi.
5. Điều dưỡng hạ một red flag → `generated_value` giữ giá trị gốc, audit đủ `edited_by`, `edited_at`,
   `reason`.
6. Điều dưỡng **không** hạ được `escalation_lock` trong phiên đang chạy bằng đường API của bước duyệt.
7. Ca đã hiển thị `EMERGENCY_MESSAGE` cho bệnh nhân → hạ cờ về sau không xoá được sự kiện đã hiển thị.

### 7.4. Batch câu hỏi và field bị bỏ qua (§4.8)

1. Người bệnh trả lời 3/6 ý trong một batch → **field M0/M1 bị bỏ qua thành `unknown`**, không phải
   `false`; chỉ tier O/H mới được suy `false`.
2. Field M0/M1 bị bỏ qua được hỏi lại **đúng một lần**, không lặp vòng.
3. Phủ định gộp: một chữ "không" chỉ đóng đúng các field trong danh sách vừa đọc lên.
4. Batch không vượt trần ý mỗi lượt.

### 7.5. Memory (§4.9)

1. Hai phiên mở cùng một giây → `conversation_id` không đụng nhau.
2. Restart giữa phiên → phiên đang dở khôi phục được từ event log.
3. Nén context dài **không** ghi đè snapshot; bất đồng thì snapshot thắng.
4. **`previous fever = true` của phiên trước không nạp thành `current fever = true`.**
5. Không có đường nào đọc được hồ sơ của `user_id` khác.

### 7.6. Controller bằng model (§4.11)

1. **Tắt `AGENT_LLM_CONTROLLER_ENABLED` ⇒ toàn bộ 590 test hiện có vẫn xanh.** Không test tất định
   nào được phụ thuộc vào endpoint GPU.
2. Controller timeout / JSON hỏng / trả `next_action` không có trong `admissible_actions` → rơi về
   controller tất định, phiên chạy tiếp bình thường.
3. **Controller không trả được giá trị `stop`** cho `next_action` — schema không cho phép; nếu model
   cố tình trả thì bị loại như một giá trị không hợp lệ.
4. Controller đề xuất một cụm câu hỏi → bị bỏ qua hoàn toàn; cụm vẫn do `ranking` chọn.
5. **L0 đã bật tín hiệu đỏ ⇒ controller không đổi được kết cục**, kể cả khi nó trả
   `lane=non_clinical` hoặc `user_intent.stop=true`.
6. `admissible_actions` rỗng (state lạ) → fail closed về extraction + handoff, **không** gọi model để
   đoán plan.
7. Shadow mode: lựa chọn của model được ghi log nhưng **không** ảnh hưởng hành vi — kiểm bằng cách
   cho model trả một lựa chọn khác hẳn và khẳng định transcript không đổi.

### 7.7. Nghi ngờ red-flag và SLA (§4.12)

1. Phát hiện nghi ngờ → bệnh nhân nhận `SUSPECTED_RED_FLAG_MESSAGE` **ngay trong lượt đó**, không chờ
   duyệt.
2. Thông điệp t=0 **không** nêu tên bệnh, không nêu lý do lâm sàng, không đi qua LLM.
3. `triage_level` nội bộ vẫn là `EMERGENCY`; ca vẫn lên đầu hàng đợi; `escalation_lock` vẫn bật.
4. Quá SLA mà chưa điều dưỡng nào mở ca → `SLA_BREACH_MESSAGE` tự phát, không cần ai bấm gì.
5. Điều dưỡng mở ca trước SLA → **không** phát `SLA_BREACH_MESSAGE`, kể cả khi duyệt xong sau SLA.
6. `EMERGENCY_MESSAGE` đầy đủ **không** xuất hiện trong hội thoại trước khi có duyệt.
7. Ba thông điệp là hằng số tĩnh — test khẳng định không có đường nào để model sinh ra chúng.

### 7.8. An toàn — nhóm không bao giờ được cắt

1. Red flag đã xác nhận dương tính phải short-circuit ngay, kể cả ở lượt mở.
2. **JSON lỗi/timeout không được làm mất tín hiệu red flag trên text thô.**
3. Câu phủ định ("không co giật", "không tím môi") không được short-circuit vì khớp substring.
4. **Tắt hoàn toàn SLM: hệ thống vẫn chạy đúng.**
5. Controller luôn tạo plan hợp lệ bằng code; state lạ/thiếu fail closed về extraction + handoff.
6. `symptom_group_router` chọn sai nhóm không được làm mất common-safety red flag.
7. **Router model không được gọi ngoài 4 trigger ở §2** — đếm số lời gọi trên transcript nhiều lượt;
   lượt trả lời bình thường trong cùng protocol phải là 0.
8. Renderer không nêu chẩn đoán, không tự thêm hướng điều trị.
9. Một đính chính không được tự hạ escalation đã khoá nếu chưa qua policy xác nhận an toàn/HITL.
10. Property test: với mọi hoán vị thứ tự trả lời, phiên đóng bình thường ⇒ `mandatory_unasked` rỗng.

---

## 8. Metric và acceptance gate

Đo tách theo vai trò, không gộp một con số:

- **controller**: branch/transition coverage, invalid-state handling, execution-plan determinism;
- **symptom_group_router**: group accuracy, tỉ lệ bất đồng với `registry.select_protocol`;
- **fact_extractor**: field-level precision/recall/F1, negation accuracy, correction/retraction
  accuracy, hallucinated-field rate;
- **reducer/rule engine**: contradiction resolution accuracy, tỉ lệ hỏi lại field đã biết;
- **synthesis**: reviewer score, tỉ lệ bị `output_guard` chặn;
- **red flag hai nhánh (§4.1)** — nhóm mới, và là thứ trả lời được câu hỏi mà `emergency recall 48.9%`
  đang bỏ ngỏ:
  - `agreement_rate` giữa nhánh rule và nhánh model;
  - `model_only` — model bắt, rule bỏ sót. **Đây là danh sách ứng viên để mở rộng rule**, và là output
    có giá trị nhất của cả cơ chế;
  - `rule_only` — đọc như chất lượng của nhánh model;
  - `model_branch_failure_rate` — nếu cao thì mọi con số trên đều mất mẫu số;
- **controller model (§4.11)**:
  - `controller_agreement_rate` — tỉ lệ trùng với controller tất định, đo ở shadow mode. **Đây là chỉ
    số quyết định có bật thật hay không**; đề xuất ngưỡng ≥ 95% cho nhánh `clinical`, thấp hơn cho
    `non_clinical` vì ở đó không có đáp án tất định để so;
  - `controller_fallback_rate` — tỉ lệ timeout/JSON hỏng/lựa chọn ngoài tập hợp lệ. Cao thì mọi con số
    khác mất mẫu số;
  - `controller_p95_ms` — phải nằm dưới trần 300ms;
  - `skippable_turn_ratio` — tỉ lệ lượt `greeting`/`off_topic` thuần. **Đây là trần của toàn bộ phần
    token tiết kiệm được**, nên đo nó trước khi cam kết hạ tầng.
- **trải nghiệm + độ phủ** — phải đọc **cùng nhau**, vì cải thiện một cái bằng cách hy sinh cái kia là
  hỏng:
  - `mandatory_unasked` rỗng — **đây mới là chỉ số đặt gate cứng**;
  - `mandatory_coverage_at_close` — đọc như **mô tả**, không phải ngưỡng. Người bệnh trả lời "không
    biết" là kết quả hợp lệ nhưng field vẫn `unknown`; hệ thống không ép được người bệnh biết điều họ
    không biết, nên nó **cố ý không bảo đảm** chỉ số này;
  - `median_turns` (hiện 21 ở ca lành tính), `user_led_ratio`, `repeat_question_rate`,
    `deferral_depth`, `catch_all_yield`, `uncooperative_stop_rate`;
  - `abandonment_rate` — chỉ số trải nghiệm thật nhất, và là lý do bất biến §1 mục 10 tồn tại;
- **nghi ngờ red-flag (§4.12)**: `sla_breach_rate` — **phải gần 0**. Không gần 0 thì cam kết trực
  24/7 chỉ có trên giấy và lập luận an toàn của §4.12 sụp; thời gian trung vị từ lúc ca vào hàng đợi
  tới lúc điều dưỡng **mở** ca.
- **toàn hệ thống**: exact match cho field red flag và demographics, latency p50/p95 và chi phí mỗi
  phiên — so với baseline §2.

### Gate cứng, chạy trong CI (không gọi model thật)

- 100% nhóm test an toàn §7.8, §7.7 và §7.6, gồm ca JSON hỏng/timeout, negation text signal, tắt SLM, invalid state;
- 100% property test hoán vị thứ tự trả lời — thứ duy nhất chặn được việc nới thứ tự hỏi làm mất field
  bắt buộc;
- không regression các test hiện có.

### Gate mềm, chạy tay theo release (model thật, 120 golden case)

- red-flag recall 100% — **kèm cỡ mẫu**, vì 100% trên 20 ca không chứng minh được gì;
- correction/retraction accuracy ≥ 98% (tối thiểu 50 ca có nhãn);
- hallucinated negative rate 0% trên tập safety;
- `symptom_group_router` accuracy ≥ 98%;
- `mandatory_unasked` rỗng ở **100%** phiên — không ngoại lệ;
- latency p95 không tệ hơn baseline §2 dù thêm 1–2 lời gọi;
- `median_turns` không tăng (mục tiêu là giảm); `repeat_question_rate` giảm;
- reviewer chấm "rõ, đúng ngữ cảnh, không lặp máy móc" ≥ 90% transcript;
- reviewer chấm "agent có phản ứng theo điều tôi vừa nói" ≥ 90% transcript — không thay thế được bằng
  chỉ số tự động nào.

**Mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate.**

---

## 9. Làm ngay

Thứ tự này ưu tiên an toàn trước, correctness sau, rồi mới tới trải nghiệm — vì độ tự nhiên chỉ có ý
nghĩa khi đặt trên một state đúng. Nhưng "cuối" là **thứ tự làm, không phải mức độ quan trọng**: trải
nghiệm có gate riêng ở §8 và bất biến riêng ở §1 mục 10.

| # | Việc | § | Công sức | Vì sao ở vị trí này |
| --- | --- | --- | --- | --- |
| ~~1~~ | ~~Sửa thứ tự `RED_FLAG` vs `USER_CANNOT_CONTINUE`~~ | §3.3 P0.6 | — | ✅ **Xong 2026-08-19.** `stage_machine.should_stop` xét chốt đỏ trước mọi nhánh ý định |
| ~~2~~ | ~~Mở quyền sửa red flag cho điều dưỡng + audit overlay~~ | §4.4 | — | ✅ **Xong 2026-08-19.** `NurseFieldEdit` overlay + 1 dòng audit/trường + bắt buộc lý do khi hạ cờ |
| ~~3~~ | ~~Sửa quy tắc suy `False` theo tier + tăng batch~~ | §4.8 | — | ✅ **Xong 2026-08-19.** Chỉ tier O/H mới suy `false`; batch 4 cụm / ≤7 ý |
| ~~4~~ | ~~Ý định người dùng + `USER_UNCOOPERATIVE`~~ | §3.3 P3.9, §4.7 | — | ✅ **Xong 2026-08-19.** `user_intent.py`, 3 mã dừng mới phân biệt được |
| 5 | **Bảng quy đổi mã red flag** | §3.1 | — | **Lâm sàng**, không phải engineering. Chặn một gate ở §8. ⬅️ **việc kế tiếp** |
| ~~6~~ | ~~ADR-007 supersede ADR-004 + 3 thông điệp tĩnh + đồng hồ SLA~~ | §4.12 | — | ✅ **Xong 2026-08-19** — ghi thành **ADR-008** (số 007 đã bị "Lựa chọn LLM provider" chiếm) |
| 7 | **Ký duyệt `SHORT_CIRCUIT_CODES`** | §3.1 | — | **Lâm sàng.** Liên quan trực tiếp recall 48.9% |
| 8 | **Track PC — 4 protocol lâm sàng** | §3.2 | Lớn | Hạng mục lớn nhất, vẫn **chưa có người chủ trì** |
| ~~9~~ | ~~Hai output summary (NLP + field-based)~~ | §4.3 | — | ✅ **Xong 2026-08-19.** `summary_text` (LLM, cho DB/memory) + `summary_json` phẳng -> ISBAR; (b) là bản đối chứng của (a) |
| ~~10~~ | ~~Nhánh model red-flag + `red_flag_agreement`~~ | §4.1 | — | ✅ **Xong 2026-08-19.** Mặc định TẮT (cờ `agent_model_red_flag_branch_enabled`) — bật khi chạy eval |
| ~~11~~ | ~~5 trường ISBAR còn thiếu + `priority_source`~~ | §6, §4.2 | — | ✅ **Xong 2026-08-19** cùng ADR-006 |
| ~~12~~ | ~~Memory M1 (composite key + persist)~~ | §4.9 | — | ✅ **Xong 2026-08-19.** Phiên đang dở sống qua restart |
| ~~13~~ | ~~Protocol phi lâm sàng~~ | §4.10 | — | ✅ **Xong 2026-08-19** — lifestyle + meta. **Chitchat cố ý KHÔNG làm**: `controller` đã xử lý đúng từ trước |
| ~~13b~~ | ~~Controller Qwen-4B — bước 1 shadow mode~~ | §4.11 | — | ✅ **Xong 2026-08-19.** Mặc định TẮT; bật lên là có `controller_agreement_rate` |
| ~~14~~ | ~~Metric trải nghiệm~~ | §3.3 P4.3-4.4 | — | ✅ **Xong 2026-08-19.** `eval/scripts/experience_report.py` — **đã chạy trên log thật, xem §9.1** |
| 15 | Memory M2 → M3 | §4.9 | Lớn | M3 cần consent/retention từ PM trước khi lên production |
| 16 | RAG vào luồng chuẩn | §4.6 | Lớn | Phải quyết số phận `pipeline/weaviate_cloud.py` trước (§3.3 P5) |
| 17 | Dọn kiến trúc P5 | §3.3 | Vừa | Không để hai runtime path cùng có vẻ authoritative |
| 18 | Multi-protocol đồng thời | §3.3 PC+ | Lớn | Chỉ có nghĩa sau #8 |

**Bốn việc đầu cộng lại nhỏ hơn một protocol lâm sàng**, và cả bốn đều vá một khiếm khuyết thật chứ
không thêm bề mặt mới — nên chúng đi trước, kể cả khi track PC đã bắt đầu.

> **Cập nhật 2026-08-19 — #1–#4 đã xong**, 654 test xanh (trước: 606). Bốn ghi chú không đọc ra được
> từ code:
>
> 1. **Ba mã dừng mới, không phải một.** `USER_UNCOOPERATIVE` + `NO_MORE_SYMPTOMS` đứng cạnh
>    `USER_CANNOT_CONTINUE` thay vì gộp lại, vì §7.2 mục 4 đòi ba phiếu **phân biệt được**. Bước quét
>    sót bị bỏ qua ở cả ba — hỏi thêm một câu mở với người vừa từ chối trả lời là làm đúng cái họ vừa
>    từ chối.
> 2. **`no_more_symptoms` là tín hiệu MỀM**, đúng §4.7a: nó chỉ đóng phiên khi không còn cụm CHƯA HỎI
>    nào mang field M0/M1. Quyết định đó nằm trong `should_stop` vì chỉ ở đó mới đủ dữ kiện.
> 3. **Phần "suy `false`" của #3 hiện KHÔNG bắn trên fever.** Cụm gộp thật duy nhất của fever
>    (Stage 2) có đúng một field tier O — `antipyretic_response` — mà nó là enum, và enum không có
>    giá trị "âm tính" nào để suy ra. Lãi thật của #3 với fever là phần **tăng batch** và việc **chặn
>    trước** quy tắc suy `false` toàn cục. Cơ chế sẽ bắn thật khi có protocol gộp được các cụm tier
>    O/H tri-state (fever đã có 13 field như vậy ở Stage 4/5, hiện không nằm trong vùng gộp).
> 4b. **Trần batch giờ là HAI con số**, và trần thật đang chặn là trần Ý (≤7) chứ không phải trần cụm
>    (4): Stage 2 của fever không có quá 4 cụm gộp được. Tune bằng `abandonment_rate` khi có số.

---

### 9.1. Số đo đầu tiên từ `experience_report.py` (2026-08-19)

Chạy trên `logs/` hiện có — **227 phiên, TRỘN nhiều phiên bản code và nhiều lần chạy test**, nên đọc
như *tín hiệu cần điều tra*, không phải như baseline. Baseline thật cần một lần chạy sạch trên tập
golden.

| Chỉ số | Giá trị | Đọc thế nào |
| --- | --- | --- |
| `sessions_with_unasked_mandatory` | **9** | ⚠️ **Phải bằng 0.** Đây là bất biến §1 mục 8 — có cụm mang field M0/M1 bị bỏ qua im lặng |
| `repeat_question_rate` | **0.3255** (n=212) | ⚠️ Cứ 3 câu hỏi thì 1 câu hỏi lại cụm đã hỏi |
| `mandatory_coverage_at_close` | 0.0 (n=28) | Mẫu số nhỏ và lẫn phiên cũ — chưa kết luận được |
| `user_led_ratio` | 0.1085 (n=212) | Chỉ 11% câu hỏi đi theo mạch người bệnh vừa kể |
| `turns_median_normal_close` | 19.5 | So với 21 ở baseline 2026-08-17 |
| `catch_all_yield` | 0.5 (n=10) | Bước quét sót bắt được thứ checklist bỏ sót ở 1/2 số phiên |
| `abandonment_rate` / `uncooperative_stop_rate` | 0.0 (n=227) | Bằng 0 vì cơ chế mới hơn toàn bộ log này |

**Đã điều tra xong hai con số đó (2026-08-19).** Không cần chạy lại eval — đọc log là đủ, và cả hai
đều có nguyên nhân xác định. Cả hai đến **duy nhất từ `GENERIC_PROTOCOL`**, tức là protocol mà 4/5
nhóm triệu chứng MVP đang rơi vào cho tới khi track PC xong; đây không phải một góc khuất.

**`sessions_with_unasked_mandatory = 9` — lỗi DỮ LIỆU protocol, đã sửa.** Cả 9 phiên đều là `general`
và đều thiếu đúng hai field:

| Field | Chẩn đoán | Xử lý |
| --- | --- | --- |
| `diarrhea` | Khai tier M1 nhưng **không cụm nào hỏi tới** — không đường nào thu thập được, nên `mandatory_unasked` khác 0 ở MỌI phiên generic | Thêm cụm `G3-01` riêng cho generic (fever vẫn hỏi ở Q5-04, không đụng) |
| `complaint_duration_days` | **Báo nhầm của metric**: field DẪN XUẤT từ `complaint_onset_at` (đã có cụm G1-01), nên không cụm nào chứa nó là đúng thiết kế | Thêm `SymptomProtocol.derived_field_keys` và trừ khỏi `mandatory_unasked` |

Phiên thứ 10 (`USER_CANNOT_CONTINUE`, 34 field) **không phải lỗi** — người bệnh chủ động dừng và
phiếu đánh dấu chưa đầy đủ, đúng hành vi §4.7.

Chống hồi quy: `tests/test_services/test_protocol_field_coverage.py` canh bất biến "không protocol
nào được có field M0/M1 mồ côi". Lối thoát duy nhất là khai `derived_field_keys` — **tường minh**,
vì suy "field không thuộc cụm nào thì chắc là dẫn xuất" sẽ nuốt luôn cả lỗi lẫn thiết kế.

**`repeat_question_rate = 0.32` — chỉ số đo sai, không phải hệ thống sai.** Đọc chuỗi cụm của phiên
tệ nhất (0.50) ra mẫu `G1-02 → G1-02 → G1-02`, `Q3-01` ×3, `Q4-04` ×3 — đúng 1 lần hỏi + 2 lần retry,
khớp chính xác `MAX_RETRIES_PER_CLUSTER = 2`. Tức là **toàn bộ con số là retry đúng thiết kế**, không
có vòng lặp nào. Chỉ số cũ gộp hai khái niệm nên vừa báo động giả vừa che mất ca quay vòng thật; đã
tách thành hai:

- `retry_rate` — hỏi lại NGAY cùng cụm vì chưa thu được gì. Đọc như *"câu hỏi nào người bệnh không
  trả lời được"*, cao nghĩa là câu hỏi khó hiểu hoặc extractor không khớp;
- `repeat_question_rate` — quay lại một cụm SAU khi đã đi qua cụm khác. **Đây mới là thứ phải gần 0**
  (bug C3).

Baseline sạch vẫn cần một lần chạy eval thật; các con số ở bảng trên đọc như *mô tả tập log hiện có*.

---

**Ba câu hỏi cho buổi planning**, cả ba là quyết định phạm vi chứ không phải kỹ thuật:

1. **PC chèn trước hay track P chạy trước** (§3.4) — quyết định cả sprint.
2. **Ai chủ trì PC** (§3.2) — giao nhầm cho track engineering thì ước lượng sai từ đầu.
3. **ADR-006: giữ `HandoffSummary` phẳng hay chuyển ISBAR lồng** (§6) — không chặn 1–8, nhưng chặn
   versioning schema và track UI W-07.

Câu hỏi thứ tư, sau khi shadow mode có số: **dựng GPU cho controller-4B hay dùng endpoint Qwen bên
thứ ba**. Ba dữ kiện cần trước khi quyết (§4.11): `skippable_turn_ratio`, hoá đơn Gemini thật, và ai
vận hành GPU service sau khi sprint kết thúc. Bước 1 không cần trả lời câu nào trong ba câu đó —
đó là lý do nó đi trước.


Vấn đê: chưa có streaming cho, cần logging thêm chi tiết hơn khi dùng các tool, các agent nào
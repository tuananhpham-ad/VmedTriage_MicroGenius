# F10 — Bốn lỗi khai thác thông tin sau khi mở rộng 5 nhóm triệu chứng

> **Ưu tiên `***`** — chặn Demo V1. Chủ trì: Agent Lead.
> Đọc `INVARIANTS.md` trước. Nối tiếp `F01` (số lượt) và `F09` (4 protocol mới).
> Nguồn lâm sàng cho số câu hỏi: `_guidance/protocoltriage4nhomtrieuchung.md`.
>
> **Trạng thái 2026-08-29: A, B, D, E, F ĐÃ CODE VÀ ĐÃ TEST. Còn lại Fix C.** Xem §7.

---

## 1. Vấn đề

Chạy thật sau khi lên 5 nhóm, bốn lỗi được báo cáo:

| # | Triệu chứng người dùng thấy |
| --- | --- |
| 1 | Câu hỏi đầu tiên sau lượt mở là câu của **nhóm sốt** dù người bệnh khai nhóm khác |
| 2 | Khai đau ngực rồi vẫn bị hỏi **"có bị đau ngực không"**; xưng hô lúc "mình" lúc "em" |
| 3 | **Quá nhiều câu hỏi** (đo được 16–18 lượt, tài liệu chốt 5–7); hỏi lạc sang checklist sốt và đau bụng |
| 4 | Khai **"bạn tôi bị đau"** → ghi thành người dùng bị đau; bảo sửa vẫn không nhận |

### 1.1. Đề xuất "thêm routing câu hỏi cho controller" — ĐÃ BÁC BỎ

Chủ dự án đề xuất cho controller quyết định hỏi câu nào. Không làm, vì hai lý do độc lập.

**Lý do 1 — ranh giới đã ghi ở ba chỗ:**

| Nguồn | Câu chốt |
| --- | --- |
| `INVARIANTS.md` §2 bất biến 2 | "Controller… **không chọn câu hỏi lâm sàng**" |
| `B02` §3 | Bảng "không được quyết", dòng đầu: "Cụm câu hỏi lâm sàng tiếp theo → `ranking.py` + `stage_machine.select_cluster`" |
| `controller_shadow.py` docstring | Cùng bảng đó, viết lại trong code |

**Lý do 2, quan trọng hơn — router thông minh hơn KHÔNG sửa được lỗi nào:**

- *"Hỏi sang đau bụng"* → `Q3-13` (`common_safety/clusters.py:51`) là cụm **quét đỏ bắt buộc của MỌI
  protocol** (CS §3.3A "minimum scan", cưỡng chế bởi `_gate_stages_cleared`). Router bỏ nó = bỏ một
  lưới quét red-flag.
- *"Hỏi sang checklist sốt"* → `CP-05` (`chest_pain_checklist.py:140-144`) là cụm **của chính protocol
  đau ngực**, khai `temp_c` vì bảng mapping cần "sốt >38.1°C kèm đau ngực". Không lạc protocol.
  ⚠️ Giả thuyết ban đầu "cụm chung gây ra câu hỏi sốt" **đã bị bác bỏ**: `common_safety` không có cụm
  sốt nào.
- *"18 lượt"* → số học tất định, xem §2 Fix C.
- Lỗi 2 và 4 → tầng sinh câu hỏi và tầng schema trích xuất, không dính việc chọn cụm.

**Một chỗ đề xuất ĐÚNG:** routing ở **lượt mở** — đó là `symptom_group_router`, và `INVARIANTS.md` §5
cho phép gọi router model ở đúng 4 trigger, trigger thứ nhất là lượt mở. Đó là Fix A.

### 1.2. Phạm vi đã chốt với chủ dự án

**Gộp câu, giữ đủ field.** Vẫn thu đủ mọi field M0/M1 (bất biến 8), người bệnh chỉ thấy 5–7 lượt.
KHÔNG cắt field xuống 5 câu — đó là đổi nội dung lâm sàng, cần Data Lead ký duyệt.

---

## 2. Sáu sửa chữa

### Fix A — Chọn đúng nhóm ngay lượt mở (lỗi 1) ✅ ĐÃ CODE

**Nguyên nhân đo được.** `registry._has_chest_pain_evidence` khớp đúng **3 chuỗi literal**
(`"dau nguc"`, `"tuc nguc"`, `"nang nguc"`) trên `chief_complaint`/`complaint_site`:

```
{'chief_complaint': 'đau ngực'}               → chest_pain
{'chief_complaint': 'đau tức vùng ngực trái'} → general    ← TRƯỢT, candidates = ()
```

Trượt rồi mà cùng lượt bắt được `fever_reported`/`temp_c` (đều trong `OPENING_HARVEST_FIELDS`) →
`candidates = ('fever',)` → protocol = **fever** → câu lâm sàng đầu tiên là `Q1-01` *"Hiện có đang
sốt không"*. Đúng triệu chứng báo cáo.

Lỗ thứ hai: `chief_complaint`/`complaint_site` **chỉ `general` khai**, nên nhánh nhận diện bằng text
chết hoàn toàn ở mọi lượt giữa phiên của protocol chuyên biệt.

**Đã sửa:**

1. `registry.OPENING_HARVEST_EXTRA_FIELDS` += `PRIMARY_SYMPTOM_FIELD.key`. Field
   `primary_symptom_group` **đã tồn tại** và `select_protocol` **đã ưu tiên nó**, chỉ là nó không nằm
   trong schema lượt mở nên extractor không bao giờ điền được. Không tốn thêm lời gọi model — nó đi
   kèm chính `extract_turn` đã có, ngân sách "2 lời gọi/lượt" giữ nguyên.
2. `hint` của `PRIMARY_SYMPTOM_FIELD` viết lại: trước đây là *"chỉ ghi sau câu hỏi phân định"*, giờ
   nói rõ ghi được từ lời kể tự do.
3. `_stated_group()` mới — mỗi `_has_*_evidence` nhận thêm căn cứ `primary_symptom_group == <nhóm>`.
   **Bắt buộc phải có bước này**: `select_protocol` chỉ dùng `preferred` khi `preferred in candidates`,
   không có nó thì field mới vô hiệu đúng lúc cần nhất (khi keyword trượt). `_stated_group` vẫn thua
   `_protocol_ruled_out` — lời phủ định tường minh thắng nhãn model.
4. `_mentions()` mới — ghép **vị trí × cảm giác** (`_PAIN_WORDS` × `_CHEST_SITES`/`_ABDOMEN_SITES`)
   thay vì liệt kê cụm hoàn chỉnh. Đây là **lưới đỡ** khi model chết, giữ vì `INVARIANTS.md` §5 đòi
   "tắt hoàn toàn SLM thì hệ thống vẫn phải chạy đúng".

**Kèm theo — lỗ hổng ping-pong đã vá:** `chest_pain_protocol.FIELD_DEPENDENCIES["chest_pain"]` thiếu
`chest_pain_duration_min`, mà `_has_chest_pain_evidence` lại đọc đúng field đó → rút lời "tôi không
đau ngực" xoá được tính chất/hướng lan nhưng thời lượng sống sót → **bằng chứng đau ngực không bao
giờ tắt**.

Kiểm bằng tay, 16/16 ca qua (`chest_pain` thắng cả khi có `fever_reported` cùng lượt).

### Fix B — Ngân sách bị cấp lại khi đổi protocol (lỗi 3, phần bội số) ✅ ĐÃ CODE

`intake_agent.run_turn` nhánh `elif protocol_switched:` gọi `stage_machine.advance(...)` **không
truyền `asked_count`** → `advance` tính `count = len(asked_ids) = 0` (`stage_machine.py:264`). Cộng
với `session.closed_ids_for_current_protocol()` trả rỗng (khoá cụm là `"<protocol>:<id>"`) và
`ledger.reset()` → **phiên được cấp lại trọn vẹn 13–16 cụm nữa**. Đổi sang fever tệ hơn: floor của
fever là `"4"`, đứng sau 25 cụm.

**Đã sửa:** truyền `asked_count=len(closed_now - (screened_ids | screened_closed))` — đúng biểu thức
nhánh thường đang dùng. `asked_ids` vẫn để rỗng (mã cụm dùng chung giữa protocol), và `advance` tách
hẳn hai tham số nên làm được điều này mà không phá gì.

> Ngân sách là **kiên nhẫn của NGƯỜI BỆNH**, không phải của protocol. Đổi protocol không làm họ có
> thêm kiên nhẫn.

### Fix C — 18 lượt → 5–7 lượt (lỗi 3, phần chính) ⬜ CHƯA LÀM — LỚN NHẤT

Ba nguyên nhân cộng dồn, **không cái nào cần đổi protocol**:

| # | Nguyên nhân | Bằng chứng |
| --- | --- | --- |
| C1 | 28/33 cụm của chest_pain là `common_safety`; chỉ 5 là cụm đặc thù nhóm | đếm `QUESTION_CLUSTERS` |
| C2 | `budget_floor_stage="3"` đứng **sau 15 cụm**, trần ngân sách chỉ **13** → không kịp cắt | `stage_machine.should_stop:379-380` |
| C3 | Stage 4 (13 cụm ở chest_pain) không có batching lẫn screening cho cụm đặc thù → hỏi lẻ từng cụm | mô phỏng: lượt 12–16 đều stage 4 |

Mô phỏng ca lành tính (`advance` + `next_probe` + `next_batch`, mọi câu trả lời âm tính):
**chest_pain 16 câu + lượt mở + quét sót ≈ 18 lượt**; breathing 18, abdominal 17, headache 16,
general 14. Vượt 2,3–2,6 lần mức 5–7 của tài liệu **ngay cả khi không có vụ đổi protocol nào**.

**Cách sửa (theo lựa chọn "gộp câu, giữ đủ field"):**

1. **Ghép 5 cụm đặc thù về đúng 5 câu của tài liệu** — ánh xạ gần 1:1, chỉ cần gộp 2 cặp:
   | Câu tài liệu | Cụm |
   | --- | --- |
   | 1 red-flag | probe stage `E` (đã tĩnh, đã 1 lượt) ✓ |
   | 2 vị trí/tính chất/lan | `CP-01` ✓ |
   | 3 khởi phát/thời lượng/kiểu | `CP-02` ✓ |
   | 4 tuổi + bệnh nền/nguy cơ tim mạch | **gộp `Q0-01` + `CP-05`** |
   | 5 triệu chứng kèm + nguy cơ VTE | **gộp `CP-03` + `CP-04`** |

   Dùng `batching.next_batch` đã có (trần 4 cụm / 7 field). **Không viết cụm mới.**
2. **Mở vùng gộp cho stage 4.** `batching._is_narrative_stage` hiện chỉ cho gộp ở stage **trước**
   `emergency_scan_stage`. ⚠️ Docstring `batching.py:116-124` ghi số đo cũ: gộp SAU gate làm hội thoại
   **dài thêm một lượt mỗi gói**. **PHẢI ĐO LẠI trước khi chốt, không sửa mù.** Số đo xấu → đi đường 3.
3. **Đưa cụm đặc thù stage 4 vào `ScreeningGroup`.** `screening.next_probe` gộp ≤3 nhóm/câu và văn bản
   **tĩnh** → an toàn hơn batching. `CP-04`/`CP-05` hiện không thuộc nhóm nào nên bị hỏi lẻ.
4. Hạ `budget_floor_stage` `"3"` → `"2"` để trần 13 thật sự có hiệu lực.

⚠️ `_unasked_mandatory_cluster_remains` (`stage_machine.py:400-401`) treo `BUDGET_EXHAUSTED` khi còn
cụm M0/M1 — 26/33 cụm chest_pain mang M0/M1. **Đó là bất biến 8, GIỮ NGUYÊN.** Việc rút ngắn phải đến
từ gộp, không từ bỏ hỏi.

Áp cùng cách cho 4 protocol còn lại.

### Fix D — Không hỏi lại thứ đã khai (lỗi 2, phần nội dung) ✅ ĐÃ LÀM

**Hai lớp cùng thủng:**

1. `intake_agent._generate_question` truyền `script_hint=cluster.script_hint` **nguyên văn cả cụm**
   vào prompt, kể cả khi chỉ còn thiếu 3/4 field. Prompt đồng thời chứa (i) câu tiếng Việt viết sẵn
   hỏi cả cụm, (ii) dòng `focus` bảo đừng hỏi phần đã biết, (iii) `known_facts` — ba tín hiệu chọi
   nhau, model bám vào cái cụ thể nhất.
   Cụm gây lỗi là **`CP-03`** (`common_safety/clusters.py:142-146`), `script_hint` = *"Có kèm **đau
   ngực**, khó thở, ho ra máu…"*. `chest_pain` nằm trong **hai** cụm (CP-01 và CP-03).
2. `output_guard` check 3 bỏ qua mọi nhãn `< _DISTINCTIVE_LABEL_WORDS = 3` từ (`output_guard.py:319`).
   Nhãn của `chest_pain` là **"Đau ngực"** — 2 từ → **field này vô hình với lưới cuối cùng.**

**Cách sửa:**
- `missing` là tập con thật sự của `cluster.fields` → **không truyền `script_hint`**; dựng prompt từ
  danh sách `(label, hint)` field còn thiếu (đúng `F01` §3.3; đường fallback về `script_hint` khi guard
  chặn / `synthesis_enabled()` tắt đã có sẵn ở `intake_agent.py:1226-1230`).
- Hạ `_DISTINCTIVE_LABEL_WORDS` xuống **2**. Check 3 chỉ bắn cho field **đã điền** nên rủi ro chặn
  nhầm thấp — vẫn cần test khẳng định câu hỏi hợp lệ không bị chặn oan.
- `_missing_in_cluster` (`intake_agent.py:132-136`) là **code chết** — docstring đúng ý này nhưng
  không ai gọi; logic bị viết lại ở `dialogue.py:235`. Dùng nó hoặc xoá; để lại là bẫy.
- `dialogue.py:235` tính `missing` bằng `is_filled`, còn `cluster_needs_answer` dùng `field_is_settled`
  — hai định nghĩa lệch nhau, thống nhất về `field_is_settled`.

### Fix E — Xưng hô nhất quán (lỗi 2, phần giọng) ✅ ĐÃ LÀM

**Nguyên nhân: không tồn tại một hằng số persona nào trong toàn hệ.** Prompt sinh câu hỏi
(`_QUESTION_ONLY_SYSTEM`, `intake_agent.py:1034-1067`) không quy định đại từ, chạy ở
`_QUESTION_TEMPERATURE = 0.7`, lại còn bị ép *"PHẢI viết khác đi cho tự nhiên hơn"*, và
`_format_history` đẩy model đổi cách nói giữa hai lượt liền nhau. Ngôi xưng là **sản phẩm phụ ngẫu
nhiên**.

Các nguồn tĩnh mỗi nơi tự chốt một kiểu: `chitchat.py:98` là nơi **duy nhất** ghi rõ *xưng "mình", gọi
người dùng là "bạn"*; `registry.OPENING_QUESTIONS`, `text_safety_signals.py:288-316`,
`screening.py:223`, `non_clinical.py:392-473`, `session.py:203,256` mỗi chỗ một biến thể. Bản thân
`docs/medical_knowledge/fever-conversation-specification.md:106` cũng lưỡng lự *"Cho em/mình hỏi"*.
`script_hint` của các cụm **không mang đại từ nào**.

**Cách sửa:**
- Một hằng số persona duy nhất (đề xuất đặt ở `phrasing.py` — module đã lo giọng nói), chốt cặp
  `mình`/`bạn` theo `chitchat.py`.
- Nhét vào **mọi** prompt sinh văn bản gửi người bệnh: `_QUESTION_ONLY_SYSTEM`, `chitchat`,
  `non_clinical`.
- Thu hẹp chỉ thị "viết khác đi" về **cấu trúc câu**; nói rõ đại từ **không** được đổi.
- Test: mọi template tĩnh chỉ dùng đúng cặp đại từ đã chốt.

### Fix F — "bạn tôi bị đau" (lỗi 4) ✅ ĐÃ LÀM

**Bốn lớp:**

1. Prompt trích xuất (`_EXTRACTION_SYSTEM`) **không có luật nào về chủ ngữ** — không phân biệt triệu
   chứng của người nhắn với của người thứ ba.
2. `_OTHER_SUBJECT_CUES` (`text_safety_signals.py:172-176`) **đã có sẵn** `"bạn tôi"`, `"bạn mình"`,
   `"người quen"`… nhưng chỉ dùng ở `:361-362` để **hạ một tín hiệu đỏ** từ CONFIRMED xuống
   NEEDS_CONFIRMATION. **Không nối vào `reporter_type`.**
3. `reporter_type` đã điền → `_safety_extra_keys` (`intake_agent.py:1988-1989`) **loại nó khỏi schema
   mọi lượt sau**, vì nó không thuộc `confirm_before_retract`. Tập đó **chỉ fever khai** (2 field sốt,
   `fever_protocol.py:684`); 5 protocol còn lại **rỗng** (`protocol.py:136`). Người dùng đính chính →
   extractor **không có ô nào để ghi** → "bảo sửa mà vẫn nhầm".
4. `dialogue.DialogueAct.CORRECTION` (`dialogue.py:112-119`) chỉ đổi `acknowledge_instruction` → agent
   **nói** đã ghi nhận, **dữ liệu không đổi**. Và `reporter_type` tier H nên **không lên phiếu** →
   điều dưỡng cũng không thấy nhầm lẫn.

**Khung lại cho đúng:** không phải "đừng ghi `chest_pain`" — bạn của người dùng **chính là bệnh
nhân**, nên `chest_pain="true"` là dữ liệu ĐÚNG. Lỗi là **ghi sai ai là bệnh nhân, rồi xưng hô sai**.

**Cách sửa:**
1. Nối `_OTHER_SUBJECT_CUES` vào bộ đặt `reporter_type="other"` tất định — **dùng lại pattern đã có,
   không viết lại danh sách** (hai bản sẽ lệch nhau).
2. Thêm `reporter_type` vào `confirm_before_retract` của **cả 5 protocol** — đúng cơ chế mà
   `_safety_extra_keys` sinh ra, và `reporter_type` khớp định nghĩa "xoá nhầm cái này thì đắt".
3. Sửa `hint` của `reporter_type` (`common_safety/fields.py:21`): hiện đóng khung là *"độ tin cậy
   thông tin"*, phải nói rõ **ai là người CÓ triệu chứng**.
4. Sửa `script_hint` của `Q0-01` (`clusters.py:31-35`) — cụm **chứa** `reporter_type` nhưng câu hỏi
   chỉ hỏi tuổi/giới, không hỏi ai đang khai.
5. Thêm `reporter_type` vào `summary_render._ALWAYS_DETAIL_KEYS` để nó lên phiếu.
6. Truyền `reporter_type` vào prompt sinh câu hỏi để đổi **chủ ngữ**: `self` → "bạn";
   `other`/`parent_caregiver` → "người bệnh". Đây là chỗ Fix E và Fix F gặp nhau.

---

## 3. Thay đổi cụ thể

| File | Fix |
| --- | --- |
| `src/services/symptom_protocol/registry.py` | A ✅ |
| `src/services/engines/chest_pain_protocol.py` (+4 protocol) | A ✅ / F ✅ / C ⬜ |
| `src/services/symptom_protocol/intake_agent.py` | B, D, E, F ✅ |
| `src/services/symptom_protocol/dialogue.py` | D ✅ |
| `src/services/symptom_protocol/batching.py`, `screening.py` | C ⬜ |
| `src/services/checklists/*_checklist.py` | C ⬜ |
| `src/services/symptom_protocol/output_guard.py` | D ✅ |
| `src/services/symptom_protocol/phrasing.py`, `chitchat.py` | E ✅ |
| `src/services/sessions/followup_writer.py` | E ✅ |
| `common_safety/fields.py`, `clusters.py`, `text_safety_signals.py` | F ✅ |
| `src/services/sessions/summary_render.py` | F ✅ |

`non_clinical.py` KHÔNG có trong bảng nữa: khảo sát lại thì mọi câu của nó là văn bản TĨNH và đã dùng
đúng cặp `mình`/`bạn`. Fix E chỉ đụng ba prompt sinh văn bản (`_QUESTION_ONLY_SYSTEM`, `chitchat`,
`followup_writer`).

## 4. Ràng buộc không được vi phạm

- `should_stop` 6 luật có thứ tự, `_gate_stages_cleared`, `ranking` 6 trọng số — `F01` §4 cấm.
- Mọi tầng ghi "KHÔNG model" ở `INVARIANTS.md` §1: L0 `text_safety_signals`, `common_safety/rules`,
  `rule_engine`, `escalation_lock`, `output_guard`, bước quét sót.
- `ScreeningGroup.probe_hint` phải giữ **tĩnh** — LLM diễn đạt lại có thể lược mất một dấu hiệu nguy
  hiểm.
- Controller **không** quyết cụm câu hỏi, **không** quyết dừng (§1.1).
- Không giảm số test hiện có, không giảm độ phủ 5 nhóm (`CLAUDE.md`).

## 5. Test bắt buộc

Tất định, chạy không cần API key:

1. `python -m pytest tests/ -q` — **9 test đang fail sẵn trên HEAD** (`test_fever_stage_machine` ×4,
   `test_flags`, `test_hitl_review`, `test_fever_flow` ×2, `test_semigran_eval`; 2 file
   `test_graph_triage` không import được do thiếu `torch`). Không được tăng thêm.
2. **Property test hoán vị** (gate cứng `B02` §5): mọi hoán vị thứ tự trả lời → phiên đóng bình thường
   thì `mandatory_unasked` **rỗng**. Thứ duy nhất chặn được việc rút ngắn bằng cách bỏ hỏi.
3. **Test đếm lượt**: mô phỏng ca lành tính của **cả 5 protocol** qua `advance` + `next_probe` +
   `next_batch`, khẳng định ≤ 7 lượt agent. Biến mục tiêu 5–7 câu thành gate thật.
4. Fix A: `select_protocol` đúng nhóm cho ≥10 cách diễn đạt/nhóm, gồm ca "đau tức vùng ngực trái +
   hơi sốt" → phải ra `chest_pain`, không ra `fever`.
5. Fix B: sau khi đổi protocol, `asked_count` không về 0.
6. Fix D: cụm điền dở → prompt **không** chứa `script_hint` cả cụm; guard chặn câu hỏi chạm nhãn 2 từ
   đã biết ("Đau ngực"); câu hỏi hợp lệ không bị chặn oan.
7. Fix F: "bạn tôi bị đau ngực" → `reporter_type="other"`; lượt sau "không, là bạn tôi chứ không phải
   tôi" → `reporter_type` còn trong schema và ghi được; có mặt trong `field_summary().details`.
8. Fix E: mọi template tĩnh chỉ dùng cặp đại từ đã chốt.
9. `python -m ruff check src/ tests/` — **5 lỗi có sẵn ở `src/graph_triage/`**, không được tăng.

Cần model thật (gate mềm, chạy tay trước Demo):

10. `python -m eval.scripts.run_conversation_eval --limit 10 --stratify` →
    `python -m eval.scripts.experience_report`.
11. Đọc mắt transcript: xưng hô nhất quán cả phiên; không câu nào hỏi lại thứ vừa khai.

## 6. Tiêu chí chấp nhận

| Chỉ số | Ngưỡng | Baseline |
| --- | --- | --- |
| `median_turns` ca lành tính | **≤ 7** | 18.0 (n=10) |
| `mandatory_unasked` rỗng | **100% phiên** — gate cứng | chưa có số thật |
| Lượt tới câu hỏi đúng nhóm | **1** | 3–4 |
| `repeat_question_rate` | gần 0 | 0.128 (n=133) |
| Emergency recall | **không tệ hơn** | 48.9% (22/45) |

**Mọi ngưỡng phần trăm phải kèm mẫu số.** Baseline hiện n=10 — đủ so trước/sau, chưa đủ làm gate.

---

## 7. Trạng thái & việc tiếp theo (2026-08-29)

### Đã code VÀ đã chạy test: A, B, D, E, F

| Fix | Nội dung | Test khoá lại |
| --- | --- | --- |
| A | `primary_symptom_group` vào schema lượt mở; `_stated_group`; `_mentions` ghép vị trí × cảm giác; `FIELD_DEPENDENCIES["chest_pain"]` += `chest_pain_duration_min` | `test_f10_routing_and_budget.py` |
| B | nhánh `protocol_switched` truyền `asked_count` | `test_f10_routing_and_budget.py` |
| D | cụm điền dở KHÔNG kèm `script_hint` cả cụm (`_SCRIPT_HINT_BLOCK`); `_DISTINCTIVE_LABEL_WORDS` 3→2 + `_GENERIC_LABEL_WORDS`; `dialogue.missing` dùng `field_is_settled`; xoá code chết `_missing_in_cluster` | `test_f10_no_repeat_question.py` |
| E | `phrasing.PERSONA_RULE` - một hằng số cho cả 3 prompt sinh văn bản; "viết khác đi" thu về CẤU TRÚC CÂU | `test_f10_persona.py` |
| F | `reporter_type_from_text` (tất định, trong `scan_opportunistic_fields`); `confirm_before_retract` có `reporter_type` ở CẢ 5 protocol; `hint` + `Q0-01` script; `_subject_note` đổi chủ ngữ prompt; lên phiếu qua `_ALWAYS_DETAIL_KEYS` | `test_f10_reporter_type.py` |

**Kết quả đo:**

- `pytest tests/` (bỏ 2 file `test_graph_triage` thiếu `torch`): **9 fail, 1423 pass** - đúng 9 test
  fail sẵn ở §5 mục 1, không tăng thêm cái nào. Baseline đầu phiên: 9 fail, 1300 pass.
- `ruff check src/services/ tests/` sạch. 5 lỗi có sẵn ở `src/graph_triage/` không đụng tới.
- +123 test mới, trong đó test Fix B và 4/9 test Fix D đã được kiểm là **fail đúng khi gỡ fix ra** -
  chúng bắt được hồi quy thật, không phải test luôn xanh.

**Một test cũ được sửa kỳ vọng:** `test_summary_outputs.test_only_safety_fields_show_up_as_unknown`
so `details` bằng danh sách chính xác, và Fix F cố ý thêm `reporter_type` vào phiếu. Đây là đổi kỳ
vọng theo một thay đổi có chủ đích, không phải nới lỏng test.

### Ba quyết định lệch khỏi bản kế hoạch, kèm lý do

1. **`_DISTINCTIVE_LABEL_WORDS` không hạ trần rồi thôi.** Docstring cũ ghi rõ ngưỡng 2 ĐÃ THỬ VÀ BỎ vì
   "Loại sốt" chặn nhầm - một số đo thật, không phải phỏng đoán. Hạ mù sẽ dựng lại đúng lỗi đó. Nên:
   hạ về 2 **kèm** `_GENERIC_LABEL_WORDS` (`loại`/`mức`/`kiểu`/`tình`/`thông`/`diễn`) - nhãn hai từ mở
   đầu bằng một trong số đó mô tả THUỘC TÍNH nên vẫn bị bỏ qua, còn "Đau ngực"/"Khó thở" gọi tên
   chính triệu chứng thì được dò.
2. **`_OTHER_SUBJECT_CUES` bị tách đôi, không dùng nguyên khối.** Bảng cũ trộn "bạn tôi" với "nghe
   nói"/"trong phim". Cả hai đều đúng cho việc hạ một tín hiệu đỏ, nhưng chỉ nhóm đầu trả lời được
   "ai là bệnh nhân". `_OTHER_PERSON_CUES` + `_HEARSAY_CUES` ghép lại thành đúng
   `_OTHER_SUBJECT_CUES` cũ, nên guard không hẹp đi (có test khẳng định).
3. **Móc `reporter_type` nằm trong `scan_opportunistic_fields`, không phải `run_turn`.** Lượt MỞ
   không đi qua `run_turn`, mà "bạn tôi bị đau ngực" gần như luôn là câu ĐẦU TIÊN. Hàm quét từ khoá
   là chỗ duy nhất cả hai nhánh cùng gọi.

### ⚠️ VIỆC TIẾP THEO — Fix C, phần lớn nhất

Fix C (§2) chưa động tới. Nó là thứ duy nhất còn chặn ngưỡng `median_turns ≤ 7`: **A/B/D/E/F không
rút ngắn hội thoại**, chúng sửa việc hỏi SAI chứ không sửa việc hỏi NHIỀU. Mô phỏng 18 lượt ở §2 vẫn
còn nguyên giá trị.

Thứ tự làm:

1. **Viết test đếm lượt TRƯỚC** (§5 mục 3) - mô phỏng ca lành tính cả 5 protocol qua `advance` +
   `next_probe` + `next_batch`. Không có nó thì mọi thay đổi ở bước sau là sửa mù.
2. **Đo lại bước C2 trước khi chốt.** Docstring `batching.py:116-124` ghi gộp SAU gate làm hội thoại
   DÀI THÊM một lượt mỗi gói. Số đo xấu → đi đường C3 (`ScreeningGroup`), an toàn hơn vì văn bản tĩnh.
3. Hạ `budget_floor_stage` `"3"` → `"2"`.
4. **Property test hoán vị** (§5 mục 2) phải xanh sau mỗi bước: `mandatory_unasked` rỗng. Đây là thứ
   duy nhất chặn được việc rút ngắn bằng cách bỏ hỏi - bất biến 8.

Gate mềm cần model thật (§5 mục 10-11) chưa chạy lần nào.

### Việc đã làm xong trước đó (2026-08-28, đã test)

Hai bug summary/detector, xem `git diff` các file `summary_render.py`, `narrative.py`,
`common_safety/fields.py`, `fever_checklist.py`:

- `FieldSummary` chỉ nhặt tri-state → **mọi field enum/số/tự do bị bỏ im lặng** (tuổi, giới, bệnh nền,
  tính chất/hướng lan/thời lượng cơn đau). Đã thêm khối `details` + bảng dịch mã enum sang tiếng Việt.
- Schema lượt mở thiếu hẳn nhóm field đau ngực → đã đổi `OPENING_HARVEST_FIELDS` từ chép tay sang
  **suy ra từ tier M0/M1** (cơ chế chống bắt trượt) + `_ALWAYS_DETAIL_KEYS`.
- `other_conditions` — lưới hứng cho thứ không field nào đỡ. **Tier "O", KHÔNG phải M0/M1**: để M1 thì
  `mandatory_fields_covered` không bao giờ xanh (không cụm nào hỏi nó) → mọi ca lành tính bị ép đi hết
  bộ câu hỏi.
- Guard entailment `rigors`: "sốt có rét" không còn bị nâng thành "rét run dữ dội". Bảng
  `_TRI_STATE_ENTAILMENT_GUARDS` là chỗ đăng ký khi phát hiện field khác bị nâng cực sai có hệ thống.

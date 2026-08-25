# Chính sách hội thoại của agent — bản cuối, triển khai theo 3 phase

> **Trạng thái: CHỐT THIẾT KẾ — triển khai theo Phase 1 → 2 → 3, không làm một cú.**
> Ngày chốt bản đầu: 2026-08-13. Ngày sửa theo review: 2026-08-13.
> Bản này thay thế hoàn toàn bản trước, sau khi hợp nhất 3 review:
> `_guidance/claude_review_agent_conversation_policy.md`,
> `_guidance/gpt_review_agent_conversation_policy.md`, `_guidance/deep-research-report.md`.
> Đọc kèm: `_guidance/need_to_check_agent.md`, `_guidance/symptom_protocol.md`,
> `_guidance/coding_convention.md` (rule 1-2).

## Context

**Phạm vi feature:** chỉ khai thác triệu chứng qua hội thoại tự nhiên. Không chẩn đoán, không mở rộng
kết luận lâm sàng.

**Mục tiêu (người dùng chốt):**
- Bắt đúng triệu chứng user nhắc tới, **không bịa** triệu chứng chưa nhắc — nhưng **giữ được phủ định
  thật** user tự nói ("đau ngực nhưng không khó thở").
- Không hỏi lặp, không hỏi lan man, vào thẳng tình trạng bệnh.
- Mở đầu bằng **câu hỏi mở** cho người bệnh tự kể → chuyển sang **câu hỏi đóng** làm rõ tính chất.
- Ngắn gọn, ưu tiên trải nghiệm, nhưng không bỏ sót dấu hiệu nguy hiểm.
- **Không đóng cứng vào sốt.** "Specific cho sốt" = *đào sâu* cho sốt, KHÔNG phải "ngoài sốt thì từ
  chối". Ví dụ phản chứng: *"tôi bị HIV/giang mai"* mà máy trả "không hỗ trợ" là hỏng — đó là bối cảnh
  nguy cơ phải ghi nhận rồi hỏi tiếp, không phải cớ để dừng.

### 5 lỗi cơ chế trong transcript thật (`logs/fever/a421eb5f-.../`)

Đã verify từng dòng code, giữ nguyên từ bản trước:

| Hiện tượng | Nguyên nhân |
|---|---|
| Nói "à tôi nhầm tôi không bị sốt" → vẫn hỏi "sốt bao lâu rồi" | `session.py:129-134` chọn cụm kế tiếp **trước** khi extract lượt này |
| Nói "không sốt" vẫn bị hỏi hết Q2-01…Q2-05 | `_SKIP_RULES` (`fever_protocol.py:420`) không có entry cho trạng thái không sốt |
| Gõ "." / "," / "Xin chào" → vẫn đi tiếp | `session.py:151` `asked_ids.add()` vô điều kiện ⇒ không bao giờ hỏi lại (bug C3) |
| "sống một mình, 19 tuổi, đo ở nách, 39 độ" → chỉ nhặt được nhiệt độ | `intake_agent.py:579` chỉ nhặt field của **stage hiện tại** |
| Câu hỏi vô hồn, không nhắc lại điều vừa nghe | prompt không nhận `answers` — LLM mù trạng thái |

Thêm: `_merge_answers` (`intake_agent.py:285`) cho ghi đè nhưng **không dọn hậu quả** ⇒ sau "không
sốt" thì `temp_c=39`, `fever_onset_at`, `fever_duration_days` vẫn nằm trong hồ sơ.

---

## §0 — Thay đổi so với bản trước (đọc mục này trước tiên)

| Bỏ / đổi | Thay bằng | Vì sao |
|---|---|---|
| "Rule đề cử top-K, **LLM chọn** cụm" | **Rule chọn duy nhất**, LLM chỉ diễn đạt | Nếu server bác `next_cluster_id` thì `next_question` đã viết cho cụm bị bác ⇒ text hỏi X, schema lượt sau là Y. LLM chọn cụm ở stage sau còn có thể nhảy qua cụm quan trọng đứng trước (`asked_ids` một chiều). Cả 3 review đều nêu |
| "Lượt mở **loại bỏ mọi `false`**" | Nhận `false` **có evidence span**, loại `false` không evidence | Blanket-drop cũng xoá phủ định thật ("đau ngực nhưng không khó thở") ⇒ hỏi lại đúng thứ user vừa nói, mâu thuẫn mục tiêu không hỏi lặp. Mở rộng đúng hướng `_negation_evidence_ok` đã có |
| `asked_ids` (một set cho mọi ý nghĩa) | `completed_cluster_ids` + `unresolved_cluster_ids` + `retry_count_by_cluster` | `partial` (điền 1/3 field) hiện vẫn bị `asked_ids.add()` ⇒ 2 field còn lại không bao giờ được hỏi. Đổi semantics từ "đã hỏi" sang "đã hoàn tất" |
| Stage giả `"-1"` trong `STAGE_ORDER` | `Session.phase = OPENING` **ngoài** protocol | `start_session` gọi `next_cluster(protocol,"-1",{})` → `None` → `current_cluster=None` → `submit_message` return ở guard phòng vệ ⇒ `run_open_turn` không có đường tới. Ngoài ra nghịch lý: phải biết protocol để chạy stage chọn protocol |
| Generic "tái dùng `_r_e_*` của fever" | `common_safety/` — fever và generic **cùng** phụ thuộc | Import hàm private xuyên module tạo dependency ngược; fever không còn sửa được an toàn |
| Test "đau ngực + hụt hơi ⇒ **chốt đỏ**" | "⇒ **hội thoại tiếp tục + handoff**" | Không có rule nào trong catalog bắt tổ hợp này. Test cũ không thể pass bằng field/rule hiện có ⇒ generic phải nhận **hợp đồng hẹp** |
| "Emergency: **không có đường quay lại**" | Khoá **disposition**, không khoá **fact** | User vẫn phải sửa được lời khai; cái không được phép là *tự động hạ mức*. Đây là 2 việc khác nhau |
| `HIV ⇒ immunocompromised=true` | `chronic_conditions += HIV`, `immunocompromised` giữ `unknown` | Suy giảm miễn dịch có ý nghĩa triage không suy ra được chỉ từ nhãn bệnh; giang mai càng không |
| 1 call gộp cho hướng E | **2 call** cho mọi stage (extract → rule → chọn cụm → render) | Hệ quả tất yếu của "rule chọn cụm": không thể biết cụm kế tiếp trước khi extract xong. Đổi lại **xoá hẳn** phân đôi hướng C/E |
| Làm một cú | **3 phase** | Bản trước gộp 3 thay đổi khác mức rủi ro: sửa correctness fever / mở rộng ngoài sốt / transaction đính chính + đổi protocol |

**Phương án đã cân nhắc và bác:** gộp về **một protocol duy nhất** (bỏ registry, cho stage sốt bị
`skip_rule` chặn khi không sốt). Lý do bác: `FEVER_PROTOCOL` có ~101 field / 9 stage, ép mọi than
phiền đi qua stage 2/4/5 của sốt thì skip rule phải phủ ~30 cụm — phức tạp hơn là tách; và
`symptom_group` downstream (hàng đợi điều dưỡng, lịch sử bệnh nhân) cần giá trị đúng, không thể luôn
là `"fever"`. Phần trùng lặp thật sự (nhân khẩu Q0-01/Q0-02, quét đỏ stage 3A) được giải quyết bằng
`common_safety/` chứ không bằng cách gộp protocol.

---

## §1 — Bất biến: ai được quyết định cái gì

Đây là bất biến cấp hệ thống, không phải convention. Mọi thay đổi ở 3 phase dưới phải giữ nguyên bảng
này.

| Thành phần | ĐƯỢC quyết định | KHÔNG được |
|---|---|---|
| LLM extractor | field nào user nhắc tới, evidence span, `answer_quality` | `triage_level`, rule match, bịa phủ định |
| `stage_machine` | cụm hiện tại, cụm kế tiếp, retry, hoàn tất stage | kết luận lâm sàng |
| `rule_engine` | `triage_level`, `reason_codes`, `triggered_rules`, chốt đỏ | sinh câu hỏi |
| LLM renderer | **cách diễn đạt** cụm rule đã chọn | chọn cụm/stage khác |
| case bridge | dịch `Session` → `TriageCase` | suy ra mức triage mới |

Thêm 3 bất biến:

1. **Không ghi fact nào nếu không có bằng chứng từ lời người dùng.** (Không phải "không ghi `false` ở
   lượt mở" — công thức cũ vừa lỏng vừa chặt sai chỗ.)
2. **`emergency_message` tĩnh**, không qua LLM (P0-2).
3. **Emergency khoá disposition, không khoá fact.** `escalation_lock = true` ⇒ không có đường tự động
   hạ mức; nhưng user vẫn sửa được lời khai, và bản sửa vẫn vào phiếu bàn giao.

---

## §2 — Phase 1: sửa correctness của fever hiện tại

Không mở rộng ra ngoài sốt. Mục tiêu: vá C1/C2/C3/M1/M3 + 5 lỗi cơ chế, giữ 227 test xanh.

### 2.1 Hợp nhất hướng C/E — mọi stage đi 2 call

Xoá `_run_turn_combined`, xoá tham số `next_cluster`, xoá look-ahead ở `session.py:129-134`. Mọi
stage đi đúng một luồng:

```text
call 1 (temperature 0) — extract-only, có evidence span
   ↓
merge (evidence-gated)
   ↓
contradiction check  →  retraction  →  derive_fields
   ↓
rule_engine.evaluate
   ↓  EMERGENCY? → emergency_message tĩnh, dừng, KHÔNG gọi call 2
stage_machine.next_cluster()  ← THUẦN RULE, chọn duy nhất
   ↓
call 2 (temperature 0.7) — render câu hỏi cho ĐÚNG cụm đã chọn
```

Đây chính là kiến trúc `_run_turn_gate` đã có sẵn, nâng lên cho mọi stage. Cái mất: +1 call/lượt ở
stage ngoài `gate_stages`. Cái được: xoá hẳn một class lỗi (câu hỏi lệch cụm), xoá phân đôi C/E, xoá
look-ahead. Đánh đổi này chấp nhận vì call 2 prompt rất ngắn.

**Cụm safety-critical dùng template tĩnh, không gọi call 2.** Danh sách: mọi cụm thuộc `gate_stages`
mà `script_hint` đã là câu chuẩn theo tài liệu (Q3-01, Q3-03 — CS §3.3A cấm diễn đạt lại).

### 2.2 Prompt call 1 — extract có evidence

`_EXTRACTION_SYSTEM` thêm khối **ĐÃ BIẾT** (bảng `label: giá trị` của field đã điền, dùng
`FieldSpec.label` không dump key thô) và **CHỈ CÒN THIẾU** (field chưa điền của cụm đang hỏi).

Output đổi từ `{"field": value}` sang:

```json
{"extracted": {
   "dyspnea": {"value": "false", "evidence_span": "không khó thở"},
   "chest_pain": {"value": "true", "evidence_span": "đau ngực từ sáng"}
 },
 "answer_quality": "answered|partial|evasive|non_answer|correction|asks_question"}
```

**Code gác, không tin prompt:** `_collect_fields` chỉ merge một giá trị khi `evidence_span` là
substring của message sau khi chuẩn hoá khoảng trắng + casefold — tái dùng `_normalize_for_evidence`
đã có. Không có/không khớp evidence ⇒ bỏ giá trị, giữ `unknown`. Áp cho **cả `true` lẫn `false`**,
không riêng phủ định.

`cluster_all_negative` giữ nguyên cơ chế cũ cho cụm `batch_negation=True`; `batch_negation=False`
tường minh cho `safety_extra_keys` (guard 2 của Phase 0, giữ nguyên).

### 2.3 `answer_quality` chỉ điều khiển UX, không đụng triage

Điều kiện retry **không** dựa vào `answer_quality` một mình — nó là output tự do của model. Điều kiện
authoritative là code tính:

```python
nothing_filled = not any(_is_filled(merged.get(k)) for k in cluster.fields)
```

Lưu ý: **không** dùng `extracted == {}`. `_collect_fields` (`intake_agent.py:261-274`) luôn ghi
`collected[key] = value` kể cả `"unknown"`, nên với cụm có tri-state thì `extracted` không bao giờ
rỗng — điều kiện cũ sẽ chết ngay.

| `answer_quality` | Hành vi |
|---|---|
| `answered` | cụm vào `completed_cluster_ids` **nếu** mọi field bắt buộc đã `_is_filled` |
| `partial` | **không** hoàn tất; lượt sau hỏi lại chỉ phần còn thiếu (khối CÒN THIẾU) |
| `non_answer` / `evasive` + `nothing_filled` | retry cùng cụm, diễn đạt khác hẳn + giải thích ngắn vì sao cần biết |
| `asks_question` | trả lời **trong ranh giới §2.5** rồi lặp lại cụm cũ, không tính là đã hỏi |
| `correction` | đi nhánh §4 |

`retry_count_by_cluster[cluster.id]` **tối đa 2**, rồi vào `unresolved_cluster_ids` và đi tiếp (chống
treo vô hạn — đúng bug Checkpoint 6 Stage 3A).

### 2.4 Trạng thái cụm — đổi tên cho đúng invariant

```python
completed_cluster_ids: set[str]      # thay asked_ids
unresolved_cluster_ids: set[str]
retry_count_by_cluster: dict[str, int]
```

`stage_machine.next_cluster` lọc theo `completed_cluster_ids | unresolved_cluster_ids` thay vì
`asked_ids`. Cụm hiện tại tiếp tục được chọn khi còn field bắt buộc chưa giải quyết và chưa bị
unresolved.

### 2.5 Ranh giới khi user hỏi ngược

`asks_question` chỉ được trả lời về **lý do cần thu thập thông tin** hoặc **cách trả lời câu hỏi**.
Mọi câu hỏi lâm sàng khác (chẩn đoán, thuốc, tiên lượng) → **thông điệp tĩnh**: hệ thống đang thu thập
thông tin, điều dưỡng sẽ đánh giá. Không để model trả lời tự do — đó là đường thoát khỏi phạm vi
"chỉ khai thác triệu chứng".

### 2.6 Mở rộng phạm vi nhặt thông tin

`intake_agent.py:579-582`: `safety_extra_keys` đổi từ *field của stage hiện tại* sang
`protocol.safety_signal_fields` ∪ *field chưa điền của cụm kế tiếp theo thứ tự tài liệu (5 cụm)* ∪
*field nhân khẩu chưa điền*.

Lý do là **chất lượng phủ**, không phải kích thước: phủ đúng nhóm field user hay nói vượt trước ("19
tuổi, sống một mình, đo ở nách, 39 độ") thay vì phủ đều cả stage. Không hứa hẹn prompt ngắn hơn.

### 2.7 Skip rule "không sốt"

`_SKIP_RULES` (`fever_protocol.py:420`) thêm predicate chung `_skip_when_no_fever` cho `Q1-02, Q1-03,
Q2-01…Q2-05`: skip khi `fever_reported == "false"` hoặc `fever_status == "none"`.

### 2.8 Đính chính, mâu thuẫn, xoá dây chuyền (trong phạm vi fever)

**`SymptomProtocol.field_dependencies: dict[str, tuple[str, ...]]`** (mặc định `{}`):

| Field lật sang giá trị "âm" | Field bị xoá về `unknown` |
|---|---|
| `fever_reported=false` / `fever_status=none` | `temp_c, temp_site, temp_measured_at, fever_onset_at, fever_duration_days, rigors, antipyretic_taken, antipyretic_drug, antipyretic_response, worse_after_defervescence` |
| `antipyretic_taken=false` | `antipyretic_drug, antipyretic_response, worse_after_defervescence` |
| `is_pregnant=false` | `gestational_weeks, obstetric_red_flags` |
| `immunocompromised=false` | `immunocompromise_cause, known_neutropenia` |
| `recent_surgery_30d=false` | `surgical_site_signs` |
| `rash_present=false` | `rash_type, non_blanching_rash` |

**`SymptomProtocol.contradiction_rules`** — cơ chế **ngược** với retraction, cần cho nửa sau của C2:

| Mâu thuẫn | Xử lý |
|---|---|
| `temp_c ≥ 38` mà `fever_status == "none"` | mở lại `Q1-01`/`Q1-02`, hỏi xác nhận; **không** xoá `temp_c` |
| `fever_reported == "false"` mà `temp_c ≥ 38` | như trên |

Retraction so `before/after` nên **không bắt được** C2 nguyên bản — C2 là lỗi ở lượt extract ĐẦU
(`fever_status: unknown → none` do hiểu nhầm *"không sốt xuất huyết"*), không phải "lật từ giá trị
dương". Nửa đầu C2 vá bằng evidence span §2.2 (`"không sốt xuất huyết"` không phải evidence cho
`fever_status=none`); nửa sau vá bằng contradiction rules ở đây.

**`symptom_protocol/retraction.py` (mới):**
`apply_retraction(protocol, before, after) -> (answers, reopened_cluster_ids)` — xoá dependents về
`unknown`, chạy lại `derive_fields`, trả id cụm chứa field vừa xoá ⇒ `completed_cluster_ids -=
reopened`.

**Vị trí gọi — quan trọng:** **bên trong** `_run_turn`, giữa `_apply_derived_fields` và
`rule_engine.evaluate`. **Không** gọi ở `session.submit_message` sau `run_turn` như bản trước — lúc đó
`rule_engine.evaluate` đã chạy trên `merged` chưa retract, nên đúng lượt user nói "tôi nhầm, không
sốt" hệ thống vẫn xếp mức trên hồ sơ còn `temp_c=39`.

**Xác nhận trước khi xoá:** `confirm_before_retract: frozenset[str]` = `{"fever_reported",
"fever_status"}` ∪ *field đỏ đang đóng góp vào `triage_level` hiện hành*.

Không lấy trọn `EMERGENCY_TRI_STATE_FIELDS` như bản trước: ~20 field đó gần như không có entry trong
`field_dependencies`, nên sẽ tốn nguyên một lượt hội thoại để xác nhận một thao tác xoá rỗng. Điều
kiện đúng là: **trong tập** VÀ (**có dependent để xoá** HOẶC **đang đóng góp vào mức hiện hành**).

**Trong lúc pending, giá trị CŨ là authoritative.** `Session.pending_retraction` lưu
`{field, before, proposed_value, dependent_fields, created_at_turn}`; `merged` được **revert** field
về `before`. Nếu không, `_merge_answers` đã ghi `false` rồi thì skip rule §2.7 đã kích hoạt — "chưa
xoá ngay" thành vô nghĩa (chưa xoá `temp_c` nhưng đã ngừng hỏi mọi câu về sốt).

**Phân loại câu xác nhận bằng intent schema riêng**, không đọc từ output tự do: `confirm | reject |
unclear`. Chỉ `confirm` mới commit; `reject` huỷ pending, giữ snapshot cũ; `unclear` hỏi lại, có retry
limit. Đây là nhánh thay đổi dữ liệu hệ trọng.

**Ngoài `confirm_before_retract`** ⇒ xoá thẳng, chèn một câu công nhận vào câu hỏi kế tiếp ("Vâng, vậy
là chưa dùng thuốc hạ sốt ạ. Cho mình hỏi…"). Không tốn lượt.

**Emergency:** `escalation_lock = true` ⇒ fact vẫn sửa được và vẫn vào phiếu bàn giao, nhưng
`triage_level` không tự hạ. Chỉ workflow/điều dưỡng quyết định bước tiếp.

### Tiêu chí hoàn tất Phase 1

- C1/C2/C3/M1/M2/M3 đều có regression test.
- Transcript cũ: sau khi phủ định sốt đã xác nhận, không còn câu nào hỏi đặc điểm sốt.
- Cụm `partial` không làm mất field.
- 227 test hiện tại vẫn xanh.

---

## §3 — Phase 2: lượt mở tự do + generic intake

### 3.1 Lượt mở là `phase`, không phải stage

`Session.phase: OPENING | COLLECTING`, **ngoài** `STAGE_ORDER` của mọi protocol. Không thêm stage
`"-1"`.

Luồng `/chat` thật (`routes.py:184-191`) là: `start_session()` → **ngay lập tức** `submit_message()`
với tin nhắn đầu của user. Nghĩa là `opening_question` **không** được bệnh nhân nhìn thấy như một lượt
riêng — nó chỉ nằm trong conversation nội bộ. Vì vậy:

- **Tin nhắn đầu của user được harvest trực tiếp** như narrative mở.
- `opening_question` (tĩnh, không qua LLM) chỉ được trả khi tin nhắn đầu quá nghèo ("xin chào", ".",
  "abc").
- UI có thể hiển thị câu mở tĩnh trước ô nhập, nhưng backend **không** phụ thuộc UI.

Câu mở tĩnh — ngắn hơn bản trước, một yêu cầu một lượt:

> "Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé."

### 3.2 Harvest lượt mở

`intake_agent.run_open_turn()` — schema = `protocol.narrative_harvest_fields` (~35-40 field): nhân
khẩu, `chief_complaint` (tự do), lõi sốt, field đỏ phổ quát, triệu chứng hay kể tự nhiên, và **bối
cảnh nguy cơ** (`chronic_conditions/immunocompromised/immunocompromise_cause/is_pregnant`).

- **Evidence span bắt buộc cho mọi giá trị** (§2.2) — cả `true` lẫn `false`. Đây là chỗ thay cho quy
  tắc "loại mọi `false`" của bản trước.
- `cluster_all_negative` cấm tuyệt đối ở lượt mở (`batch_negation=False` tường minh).
- Chạy `rule_engine.evaluate` ngay sau merge — kể co giật/tím tái ngay câu đầu là chốt đỏ luôn.
- Sau lượt mở mới lập `ConversationPlan` (chọn protocol) — tránh nghịch lý "phải biết protocol để chạy
  stage chọn protocol".

### 3.3 `common_safety/` — tách trước, dùng sau

`src/services/symptom_protocol/common_safety/` (mới):

```text
fields.py            # FieldSpec của field đỏ + nhân khẩu dùng chung
rules.py             # rule đỏ phổ quát, PUBLIC (không phải _r_e_*)
clusters.py          # cụm nhân khẩu + cụm quét đỏ dùng chung
emergency_message.py
```

`fever_protocol` và `generic_protocol` **cùng** import từ đây. Generic **không** import gì từ
`fever_*`. Đây là refactor **đầu tiên** của Phase 2 vì mọi thứ sau đó dựa lên nó.

Việc này cũng xoá luôn phần trùng lặp mà review chỉ ra: `G0-01 ≡ Q0-01`, `G0-02 ≡ Q0-02`, cụm quét đỏ
≡ stage 3A của fever — nay là **một** định nghĩa dùng chung, không phải hai bản sao.

### 3.4 `GENERIC_PROTOCOL` — hợp đồng HẸP

> Protocol thu thập ban đầu cho than phiền chưa có protocol chuyên biệt. Quét tập dấu hiệu nguy hiểm
> phổ quát **đã được phê duyệt**, rồi tạo phiếu bàn giao điều dưỡng. **Không** chẩn đoán, **không** tự
> kết luận SELF_CARE, và **không** tuyên bố bao phủ đầy đủ nguy cơ ngoài sốt.

`src/services/engines/generic_protocol.py` + `src/services/checklists/generic_checklist.py`:

| Stage | Cụm | Field |
|---|---|---|
| 0 | dùng cụm nhân khẩu của `common_safety` | `age_value/age_unit/reporter_type`, `sex` |
| 1 | G1-01 | `complaint_site`, `complaint_onset_at`, `complaint_duration_days` |
| 1 | G1-02 | `complaint_severity` (0-10), `complaint_progression` (better/same/worse) |
| 2 | dùng cụm quét đỏ của `common_safety` | tri giác, hô hấp/tuần hoàn, chảy máu/co giật |
| 3 | G3-01, G3-02 | bệnh nền / bối cảnh nguy cơ, thuốc đang dùng |

Field bắt buộc của dataclass phải khai đủ (bản trước thiếu, không construct được):

```python
gate_stages = ("2", "3")        # 2 = emergency scan, 3 = early-visit scan
budget = {...}                  # theo route, tối đa ~12 cụm
budget_floor_stage = "3"
opportunistic_keywords = COMMON_OPPORTUNISTIC_KEYWORDS
self_care_checklist_satisfied = lambda _a: False   # không bao giờ tự kết luận SELF_CARE
self_care_default_rule = _never_called             # phải truyền, không bao giờ chạy
fallback_rule = EARLY_VISIT
```

**Hệ quả có ý thức, không phải tác dụng phụ:** `self_care_checklist_satisfied` luôn `False` ⇒
`should_stop` không bao giờ trả `SUFFICIENT_EVIDENCE` ⇒ luôn `BUDGET_EXHAUSTED` ⇒ `fallback_rule` ⇒
`EARLY_VISIT` ⇒ `TriagePriority.URGENT` ("Khám sớm"). Nghĩa là **mọi** than phiền ngoài sốt vào hàng
đợi điều dưỡng ở mức "Khám sớm". Đúng tinh thần "luôn bàn giao", nhưng phải theo dõi tải hàng đợi sau
khi lên production và điều chỉnh `budget` nếu cần.

### 3.5 Thông tin nhạy cảm — không suy diễn từ nhãn bệnh

```text
"Tôi có HIV"
   → chronic_conditions += "HIV"
   → immunocompromised   giữ nguyên "unknown"
```

`immunocompromised` / `immunocompromise_cause` chỉ set khi lời khai **thực sự** hỗ trợ (đang hoá trị,
ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát). Suy giảm miễn dịch có ý nghĩa triage
không suy ra được chỉ từ việc có HIV; giang mai càng không thuộc khái niệm này.

Chỉ hỏi thêm chi tiết nhạy cảm khi nó ảnh hưởng trực tiếp tới bước khai thác an toàn. **Không** dùng
"bệnh ngoài phạm vi" làm lý do kết thúc hội thoại.

### 3.6 Case bridge phải generic

`fever_case_bridge.py` → `symptom_case_bridge.py`. Hiện file này ghi cứng `FIELDS_BY_KEY` của fever,
chief complaint mặc định "Sốt", `protocol_id="fever"`, `symptom_group="fever"`, `REASON_CODE_LABELS`
và `EMERGENCY_MESSAGE` của fever.

Nếu không sửa, agent hỏi theo generic nhưng case gửi điều dưỡng vẫn gắn nhãn "Sốt" — lỗi **dữ liệu
downstream**, không phải lỗi hiển thị.

- Bridge resolve `SymptomProtocol` từ `session.protocol_name`.
- Dùng `protocol.fields_by_key`, metadata và message của protocol tương ứng.
- `chief_complaint` ưu tiên field user cung cấp, không mặc định fever.

### Tiêu chí hoàn tất Phase 2

- Case ngoài fever **không** bị gắn `symptom_group="fever"` ở bất kỳ trường downstream nào.
- "tôi bị HIV, mấy hôm nay mệt" ⇒ ghi nhận bệnh nền, hội thoại **tiếp tục**, tuyệt đối không có chuỗi
  "không hỗ trợ".
- Red flag phổ quát **đã khai báo** được short-circuit bằng rule.
- Tình huống chưa được rule bao phủ kết thúc bằng handoff, **không** tuyên bố an toàn.
- Xoá `test_chat_non_fever_complaint_has_no_red_flag_coverage_yet` (`tests/test_api/test_routes.py`) —
  lỗ hổng `need_to_check_agent.md:215` được vá bằng `GENERIC_PROTOCOL`, không nới assert. Baseline sau
  Phase 2 là **226 + test mới**.

---

## §4 — Phase 3: chuyển protocol giữa chừng

### 4.1 Registry

`src/services/symptom_protocol/registry.py`:

```python
PROTOCOL_REGISTRY = {"fever": FEVER_PROTOCOL, "generic": GENERIC_PROTOCOL}

def protocol_for(session: Session) -> SymptomProtocol:
    return PROTOCOL_REGISTRY[session.protocol_name]
```

**Mọi** đường chạy trong `ProtocolSessionStore` phải lấy protocol qua `protocol_for(session)` —
`_walk_to_next_cluster`, `_progress`, `_finish` hiện đọc `self.protocol`. Thêm `session.protocol_name`
mà không sửa mấy chỗ này là chưa đủ. Giữ `self.protocol` làm **mặc định lúc tạo session**, không phải
nguồn thật lúc chạy.

`Session` thêm:

```python
protocol_name: str
protocol_revision: int    # tăng mỗi lần switch, để log/debug lịch sử
```

Cụm được lưu dưới dạng `(protocol_name, cluster_id)` để ID trùng giữa 2 protocol không lẫn trạng thái
completed khi chuyển qua lại.

### 4.2 Thứ tự giao dịch — cố định, không được đổi

```text
extract (evidence-gated)
→ phát hiện correction candidate
→ field hệ trọng?  → tạo pending, CHƯA merge, CHƯA switch  → hỏi xác nhận → dừng lượt
→ merge correction
→ contradiction check
→ apply_retraction
→ derive_fields
→ select_protocol / switch
→ remap stage + completed clusters
→ rule_engine.evaluate
→ next_cluster (thuần rule)
→ render câu hỏi
```

### 4.3 Chọn và đổi protocol

- Sau lượt mở: `fever_reported == "true"` hoặc `fever_status ∈ {objective, subjective}` ⇒ `fever`;
  ngược lại ⇒ `generic`. Routing theo **ngưỡng nhiệt độ số** chỉ dùng khi ngưỡng đã được duyệt và có
  test riêng.
- Đang `fever` mà `fever_reported` lật `false` (đã xác nhận theo §2.8) ⇒ `generic`, **giữ nguyên**
  field dùng chung (nhân khẩu, hoàn cảnh sống, bệnh nền, field đỏ), chỉ bỏ phần riêng của sốt qua
  `apply_retraction`.
- Đang `generic` mà user khai có sốt ⇒ `fever`; các cụm fever chưa hỏi phải được mở lại, không thừa
  hưởng trạng thái completed của generic.
- `config.RED_FLAG_RULES` **không** dùng làm lưới an toàn (ý cũ đã bỏ).

### Tiêu chí hoàn tất Phase 3

- fever → generic: giữ field chung, xoá đúng field riêng fever.
- generic → fever: không bỏ qua cụm fever cần hỏi.
- fever → generic → fever: state cũ không làm mất câu hỏi.
- Emergency: user rút lời khai ⇒ fact sửa được, `triage_level` **không** hạ.

---

## §5 — File đụng tới, theo phase

| Phase | File | Việc |
|---|---|---|
| 1 | `symptom_protocol/protocol.py` | + `field_dependencies`, `contradiction_rules`, `confirm_before_retract` |
| 1 | `symptom_protocol/intake_agent.py` | hợp nhất C/E thành 2 call; xoá `_run_turn_combined` + tham số `next_cluster`; evidence span cho mọi giá trị; khối ĐÃ BIẾT / CÒN THIẾU; mở rộng `safety_extra_keys`; `extract_cluster` **nhận thêm `answers`** (để tính `answers_delta` thật) |
| 1 | `symptom_protocol/retraction.py` | **Mới** — `apply_retraction()`, `check_contradictions()` |
| 1 | `symptom_protocol/stage_machine.py` | lọc theo `completed_cluster_ids ∪ unresolved_cluster_ids` |
| 1 | `symptom_protocol/session.py` | bỏ look-ahead; `completed_cluster_ids`/`unresolved_cluster_ids`/`retry_count_by_cluster`/`pending_retraction`/`escalation_lock` |
| 1 | `engines/fever_protocol.py` | `FIELD_DEPENDENCIES`, `CONTRADICTION_RULES`, `CONFIRM_BEFORE_RETRACT`, `_skip_when_no_fever` cho 7 cụm |
| 1 | `infra/fever_stage_log.py` | + event `retry`, `retraction`, `contradiction`, `confirmation`; sửa `answers_delta` hardcode `"unknown -> {value}"` (`:160`, `:617`) thành delta thật; sửa `tool == "red_flag_engine.evaluate"` (`:254`) → `"rule_engine.evaluate"` để `rule-engine.jsonl` được ghi |
| 2 | `symptom_protocol/common_safety/` | **Mới** — `fields.py`, `rules.py`, `clusters.py`, `emergency_message.py` |
| 2 | `symptom_protocol/protocol.py` | + `opening_question`, `narrative_harvest_fields` |
| 2 | `symptom_protocol/intake_agent.py` | + `run_open_turn()` |
| 2 | `symptom_protocol/session.py` | + `phase: OPENING \| COLLECTING` |
| 2 | `checklists/generic_checklist.py`, `engines/generic_protocol.py` | **Mới** |
| 2 | `checklists/fever_checklist.py` | + `chief_complaint` (tier H, tự do); chuyển field đỏ/nhân khẩu sang `common_safety` |
| 2 | `sessions/symptom_case_bridge.py` | **Đổi tên** từ `fever_case_bridge.py`; resolve protocol từ session |
| 2 | `api/routes.py` | `/chat`: tin nhắn đầu đi `run_open_turn`; bỏ hardwire `fever_session` |
| 3 | `symptom_protocol/registry.py` | **Mới** — `PROTOCOL_REGISTRY`, `protocol_for()`, `select_protocol()` |
| 3 | `symptom_protocol/session.py` | `protocol_name`/`protocol_revision`; mọi đường chạy dùng `protocol_for(session)`; remap state khi switch |
| 3 | `infra/fever_stage_log.py` | + event `protocol_switch` |

Tái dùng, **không viết mới**: `provider_router.complete`, `_parse_json_object`, `_negation_evidence_ok`,
`_normalize_for_evidence`, `_merge_answers`, `_coerce_enum`, `scan_opportunistic_fields`,
`rule_engine.evaluate`, và toàn bộ `FeverField` đã khai báo.

---

## §6 — Kiểm chứng

### Unit / golden

**Phase 1:**
1. Evidence span: `false` có evidence nguyên văn ⇒ giữ; `false` model bịa evidence ⇒ loại; `true`
   không evidence ⇒ loại.
2. "Tôi đau ngực, không khó thở, không ngất" ⇒ 3 field vào hồ sơ, 2 trong đó là `false`.
3. Look-ahead: `fever_reported=false` ở lượt N ⇒ cụm kế tiếp không thuộc stage 2.
4. `partial` điền 1/3 field ⇒ cụm **không** vào `completed_cluster_ids`; lượt sau hỏi 2 field còn lại.
5. Retry: `nothing_filled` ⇒ `completed_cluster_ids` không đổi; lần 3 mới vào `unresolved_cluster_ids`.
6. Renderer: `next_question` luôn thuộc cụm server đã chọn (không còn đường nào sinh lệch).
7. `apply_retraction`: `fever_status: objective → none` ⇒ `temp_c/fever_onset_at/fever_duration_days`
   về `unknown`, `Q1-02/Q2-01` rời `completed_cluster_ids`.
8. Contradiction: `fever_status=none` rồi khai `temp_c=39.2` ⇒ mở lại `Q1-01`, **không** xoá `temp_c`.
9. Negation scope: "Tôi không bị sốt xuất huyết, nhưng đang sốt 39 độ" ⇒ **không** thành
   `fever_reported=false`.
10. `pending_retraction`: lật `fever_reported` ⇒ ra câu xác nhận, `merged` vẫn giữ giá trị cũ; intent
    `confirm` ⇒ xoá; `reject` ⇒ giữ; `unclear` ⇒ hỏi lại.
11. Emergency: đang lock mà rút lại field đỏ ⇒ fact đổi, `triage_level` **không** đổi.
12. User hỏi chẩn đoán/thuốc giữa chừng ⇒ thông điệp tĩnh, không vượt scope.

**Phase 2:**
13. Lượt mở "sốt 2 ngày" ⇒ `llm-io.jsonl` không có field nào không-evidence.
14. Tin nhắn đầu "xin chào" ⇒ trả `opening_question`; tin nhắn đầu có triệu chứng ⇒ harvest ngay.
15. Ca HIV: "tôi bị HIV, mấy hôm nay mệt" ⇒ `chronic_conditions` chứa HIV, `immunocompromised` **vẫn**
    `unknown`, hội thoại tiếp tục hỏi vị trí/khởi phát/mức độ; assert tuyệt đối không có chuỗi "không
    hỗ trợ".
16. "đau ngực từ sáng, hụt hơi" ⇒ generic, hội thoại tiếp tục, kết thúc bằng handoff (**không** assert
    chốt đỏ — không có rule nào bắt tổ hợp này).
17. Case generic không chứa metadata fever ở bất kỳ trường downstream nào.
18. Generic kết thúc không red flag ⇒ handoff, **không** SELF_CARE.

**Phase 3:**
19. fever → `fever_reported=false` (đã xác nhận) ⇒ generic, `age_value`/`sex`/field đỏ giữ nguyên.
20. Switch 2 chiều rồi quay lại protocol ban đầu — không mất câu hỏi.
21. Cluster ID trùng giữa 2 protocol không lẫn completed state.

### Test tay với LLM thật — bắt buộc, không thay được bằng unit test

Cả 5 lỗi cơ chế đều tìm ra bằng chat thật.

```
uvicorn src.api.main:app --reload
```

Chạy lại đúng transcript `logs/fever/a421eb5f-...`:
- "à tôi nhầm tôi không bị sốt" ⇒ câu kế tiếp **không** hỏi đặc điểm sốt;
- "." / "," ⇒ hỏi lại, không đi tiếp;
- "sống một mình, 19 tuổi, đo ở nách, 39 độ" ⇒ 4 field vào hồ sơ trong 1 lượt;
- 3 ca ngoài sốt: đau ngực + hụt hơi, "tôi bị HIV mấy hôm nay mệt", "đau bụng 2 hôm nay" — cả 3 phải
  **hỏi tiếp**, không ca nào bị từ chối.

Đối chiếu qua `stage_log.read_all(session_id)` và `logs/fever/<sid>/session.json`. Số lượt ở ca lành
tính phải giảm so với transcript cũ.

**Mỗi lần đổi model/provider phải chạy lại toàn bộ bộ test tay** — prompt chạy đúng ở model cũ không
bảo đảm đúng ở model mới.

---

## §7 — Ngoài phạm vi lần này

- **Safety overlay theo nhóm than phiền** (đau ngực/khó thở, thần kinh cấp, đau bụng/xuất huyết tiêu
  hoá, sản khoa, phản vệ, ngộ độc, chấn thương, sức khoẻ tâm thần). Đây là hướng đúng để generic không
  phải tự nhận bao phủ toàn bộ nguy cơ, nhưng nội dung lâm sàng từng overlay phải do người có thẩm
  quyền duyệt — làm sau Phase 3, không nhét vào đây.
- **ScreeningGroup Phase 1-4** — hoãn. Skip rule §2.7 + `completed/unresolved` đã cắt phần lớn lượt
  thừa; đo lại rồi quyết.
- **Fact ledger append-only + provenance đầy đủ** — hiện chỉ cần snapshot đúng + log event. Nâng lên
  ledger khi có yêu cầu audit thật.
- **Prerequisite ngoài kỹ thuật, phải có trước production:** người có thẩm quyền duyệt rule/red flag
  và các ngưỡng lâm sàng (nhiệt độ, tuổi, thai kỳ, suy giảm miễn dịch); policy retention/access/
  redaction cho log hội thoại y tế; UI nói rõ người dùng đang tương tác với AI và điểm chuyển sang
  người thật.

**Sau khi xong:** cập nhật `_guidance/need_to_check_agent.md` — đánh dấu C1/C2/C3/M1/M2/M3 và lỗ hổng
`:215` đã vá.

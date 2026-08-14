> **CẬP NHẬT 2026-08-14:** cả 6 lỗi C1/C2/C3/M1/M2/M3 dưới đây đã VÁ và đã kiểm chứng lại bằng LLM
> thật — **không lỗi nào tái hiện**. Lỗ hổng "than phiền ngoài sốt" (mục `:215`) cũng đã vá. Xem ca
> làm việc cuối file. Giữ nguyên phần mô tả lỗi ở dưới vì nó là bản ghi vì sao từng guard tồn tại —
> xoá đi thì lần sau sẽ có người "dọn dẹp" mất một guard mà không biết nó chặn cái gì.

# Fever agent — các lỗi tìm thấy khi test thật (bản tóm tắt dễ đọc)

> Test bằng cách chat thật với agent qua API (LLM thật, model `deepseek-chat`), không phải đọc code
> suy đoán. Ngày test: 2026-08-13. Bản đầy đủ (JSON gốc, số dòng code nghi vấn) — xem lịch sử git của
> file này hoặc hỏi lại nếu cần chi tiết.

## Tóm tắt 1 dòng

Phần **quyết định** (rule engine, chốt cấp cứu) chạy đúng. Phần **nghe hiểu** (LLM trích xuất từ câu
nói của người dùng) chưa đáng tin — mắc lỗi ở việc rẻ tiền (`deepseek-chat`) đoán bừa khi câu trả lời
không nói tới một field nào đó.

## Bảng lỗi

| # | Mức độ | Lỗi | Ví dụ ngắn |
|---|---|---|---|
| C1 | 🔴 Nặng | Nói chuyện bình thường (vd "ăn uống tốt, không nôn") → hệ thống tự ý coi như đã hỏi và trả lời "KHÔNG" cho 11 dấu hiệu nguy hiểm (co giật, tím tái, xuất huyết...) dù không ai nhắc tới | Tái hiện 3/3 lần thử |
| C2 | 🔴 Nặng | Agent hiểu nhầm "bé không sốt xuất huyết" (ý là tên bệnh) thành "bé không sốt" (`fever_status=none`) — sau đó dù người dùng nói rõ "39.2 độ, đo ở nách" 3 lượt sau, hệ thống **vẫn không sửa lại** | Ngoài ra còn bịa 1 ngày sai (2023-10-05) trong lúc hôm nay là 2026-08-13 |
| C3 | 🔴 Nặng | Nếu người dùng trả lời lung tung/né tránh vài câu đầu (tuổi, giới tính), hệ thống **bỏ qua luôn**, không hỏi lại, cứ thế tiến tới câu sau | Field tuổi trống suốt cả cuộc hội thoại 7 lượt |
| M1 | 🟡 Vừa | Nói tuổi + giới tính trong CÙNG 1 câu ("45 tuổi, nam") → chỉ nhặt được tuổi, giới tính bị hỏi lại | Tái hiện 2 lần |
| M2 | 🟡 Vừa | Trả lời "tỉnh táo bình thường" bị lưu nguyên văn tiếng Việt thay vì đúng mã hệ thống cần (`alert`) → hệ thống không bao giờ nhận ra là đủ điều kiện an toàn (SELF_CARE), tự đẩy lên mức phải đi khám sớm dù không cần thiết | 1 lần |
| M3 | 🟡 Vừa | Các dấu hiệu nguy hiểm đã được xác nhận "không có" ở lượt trước, tự nhiên bị xoá về "chưa biết" ở lượt sau dù câu nói không liên quan gì | Không nguy hiểm (chỉ làm hỏi lại), nhưng cho thấy việc ghi nhớ câu trả lời cũ không ổn định |

## Vì sao lại vậy (đã bàn ở tin nhắn trước)

`deepseek-chat` là model rẻ, không mạnh về việc "chỉ điền đúng cái được hỏi, còn lại để trống" khi
schema JSON đưa cho nó có nhiều field cùng lúc — nó có xu hướng điền bừa cho "đủ" thay vì im lặng.
Không phải lỗi cấu hình, là giới hạn năng lực + cách ghép nhiều field vào 1 lần hỏi.

**3 hướng sửa đã đề xuất (chưa chọn):**
- **A** — không tin thẳng câu trả lời "không có" của model cho các dấu hiệu nguy hiểm, chỉ chấp nhận
  nếu câu nói thực sự nhắc tới chuyện đó.
- **B** — bớt nhét nhiều field vào cùng 1 lần hỏi (đỡ rối cho model, nhưng dễ quay lại tình trạng hỏi
  lại những gì người dùng đã nói).
- **C** — dùng model mạnh hơn (vd `deepseek-reasoner`, `gpt-4o`) riêng cho các lượt liên quan tới an
  toàn, giữ `deepseek-chat` cho phần còn lại để đỡ tốn.

## Việc chưa kịp test / cần làm sau

Không có — 3 lỗi nặng + 3 lỗi vừa ở trên là toàn bộ vấn đề thật sự tìm thấy (đã lọc bỏ các trường hợp
test mà agent làm đúng: chống chẩn đoán bệnh, chống bị dụ bỏ luật, chốt cấp cứu ngay lập tức, xử lý
input rác/tiếng Anh, báo lỗi sạch sẽ khi gọi sai).

---

# CA LÀM VIỆC 2026-08-13 (chiều) — thiết kế "sàng lọc theo nhóm" cho Stage 3A/3B

> **Trạng thái: PHASE 0 ĐÃ CODE XONG, PHASE 1-4 CHƯA.** Plan đầy đủ (có sơ đồ file, chữ ký hàm,
> checklist test) nằm ở:
> `C:\Users\TUAN ANH\.claude\plans\docs-medical-knowledge-fever-knowledge-delightful-cosmos.md`
> Đọc file đó trước khi làm tiếp — phần dưới đây chỉ là bản tóm tắt để nhớ lại bối cảnh.

## ▶ Làm tiếp từ đâu

> **CẬP NHẬT 2026-08-14:** bước 1 dưới đây (test tay với LLM thật) **đã chạy xong** — model chịu trả
> `negation_evidence` 4/4 lần, không phải chỉnh prompt. Lỗ hổng "than phiền ngoài sốt" cũng **đã vá**
> bằng `GENERIC_PROTOCOL`. Chỉ còn **Phase 1-4 của `ScreeningGroup`** là chưa làm, và giờ đã có số đo
> để quyết: ca lành tính hiện tốn **36 lượt** với LLM thật (`scripts/manual_llm_check.py m2m3`).

**Phase 0 ĐÃ CODE XONG** (xem mục "Phase 0 — đã làm" bên dưới). Bước kế tiếp:

1. ~~**Test tay với LLM thật** lại 3 kịch bản C1 / M2 / M3~~ — ✅ XONG 2026-08-13/14, xem ca làm việc
   cuối file. Cả 3 kịch bản đều không tái hiện lỗi.
2. **Phase 1** (`ScreeningGroup` + câu sàng lọc gộp) trong file plan — **CHƯA LÀM**, đây là việc lớn
   duy nhất còn lại của cả file này.

---

## Phase 0 — đã làm (2026-08-13)

213/213 test pass (`python -m pytest tests -q`). Ruff còn 1 lỗi nhưng là **pre-existing**, ở
`src/pipeline/weaviate_cloud.py`, không liên quan.

| Guard | Vá lỗi | Chỗ sửa |
|---|---|---|
| 1. Evidence span bắt buộc | C1 | `intake_agent._negation_evidence_ok()` — cờ `cluster_all_negative` chỉ được tin khi model trả kèm `negation_evidence` trích **nguyên văn**, verify substring sau khi chuẩn hoá khoảng trắng + casefold. Verify fail → bỏ cờ, giữ `unknown`. Prompt `_BATCH_NEGATION_RULE` đã yêu cầu khoá này. |
| 2. Turn-scoping | C1 | `_run_turn_combined` truyền `batch_negation=False` **tường minh** cho call `safety_extra_keys`. |
| 3. Tri-state đơn điệu | M3 | `_merge_answers()` — `unknown` không ghi đè được giá trị đã xác định; giá trị xác định mới vẫn ghi đè được (người dùng sửa lời khai). |
| 4. Chuẩn hoá enum | M2 | `FieldSpec.allowed_values` (`models.py`) + 21 field enum trong `fever_checklist.py` + `_coerce_enum()` loại giá trị lạ + `_field_specs()` render danh sách vào prompt. |

**Nguồn giá trị enum:** JSON Schema KM §7 (không phải bảng §3.x — bảng ghi rút gọn kèm "...").

**Đổi chữ ký (nội bộ, đã cập nhật hết caller):** `_collect_fields(..., message="")`,
`_collect(..., message="")`, `fever_intake_agent._collect(cluster, parsed, message="")`.

### 2 điều phát hiện thêm khi code (ảnh hưởng Phase 1)

1. **Phủ định gộp chỉ tác động field tri-state, không đụng field enum.** Nên một câu "không có gì cả"
   hiện KHÔNG set được `activity_vs_baseline=normal`, `urine_output=normal`… → đúng là lý do Phase 1
   cần `ScreeningGroup.negative_values`. Không phải bug, nhưng trước đây chưa ai ghi lại.
2. **Stage 3A và 3B đều nằm trong `gate_stages`** → chúng đi nhánh `_run_turn_gate` (2 call tách),
   không phải `_run_turn_combined`. Mà `safety_extra_keys` chỉ tồn tại ở nhánh combined ⇒ **guard 2
   hiện là phòng thủ trước, chưa có đường nào chạm tới**. Nó sẽ thành thiết yếu ngay khi Phase 1 thêm
   lượt sàng lọc gộp. Test của guard 2 vì vậy viết ở mức unit (`_collect_fields`), không phải qua
   `run_turn` — đừng tưởng nhầm là test viết sai tầng.

### Test đã thêm

- `tests/test_agents/test_fever_extraction.py`: evidence thiếu / bịa → từ chối; evidence lệch hoa
  thường + khoảng trắng → vẫn chấp nhận; enum tiếng Việt bị loại; enum đúng mã (khác hoa thường) được
  chuẩn hoá; field tự do không bị đụng; 3 test `_merge_answers`.
- `tests/test_agents/test_fever_emergency_shortcircuit.py`: 1 test turn-scoping.
- 2 test batch-negation cũ đã cập nhật theo hợp đồng mới (giờ phải có `negation_evidence`).

File `_guidance/need_to_check_agent.md` chưa được commit (`git status`: untracked).

## Vấn đề muốn giải

Agent hiện đi **tuần tự từng cụm**: Stage 3A 11 cụm + Stage 3B 5 cụm = 16 lượt, kể cả với ca lành tính
mà tất cả đều âm tính — đúng nhóm ca ta muốn kết thúc sớm nhất.

Ý tưởng: **hỏi 1 câu sàng lọc chung liệt kê đại diện của từng nhóm cơ quan**. Nhóm nào bị phủ định rõ
ràng → đóng luôn toàn bộ cụm bên trong. Nhóm nào dương tính → mới đào sâu từng cụm. 2+ nhóm dương tính
thì đào sâu cả 2+.

Mục tiêu: **Stage 3A 11 → 3 lượt, Stage 3B 5 → 2 lượt** cho ca âm tính hoàn toàn.

Cơ sở tài liệu: CS §3.3A đã cho phép kỹ thuật batch negation, CS §8.4 O1 còn minh hoạ một câu phủ định
gộp trải **nhiều cụm**. Code hiện chỉ áp dụng trong phạm vi **một** cụm (`QuestionCluster.batch_negation`
→ cờ `cluster_all_negative`, `intake_agent.py:196`). Việc cần làm là nâng phạm vi lên **nhóm cơ quan**.

## 3 quyết định đã chốt (đã hỏi và trả lời)

1. **Q3-01 (tri giác) và Q3-03 (co giật) vẫn hỏi riêng** đúng script chuẩn — CS §3.3A cấm suy diễn 2
   cụm này từ phủ định gộp. Nên Stage 3A tối thiểu = 3 lượt, không phải 1.
2. **Áp dụng cho cả Stage 3A và 3B** (không làm 3A trước rồi mới mở rộng).
3. **Không** dùng model mạnh riêng cho lượt sàng lọc — **chỉ chặn bằng code** (deterministic, rẻ, dễ
   test, không phụ thuộc năng lực model).

## Cảnh báo quan trọng khi làm tiếp

Câu sàng lọc gộp **khuếch đại đúng lỗi C1** ở bảng trên (model bịa "không" cho hàng loạt red flag) —
từ "bịa 11 field" thành "bịa cả Stage 3A trong 1 lượt". Vì vậy plan bắt buộc làm **Phase 0 (4 lớp chặn
an toàn) TRƯỚC**, không phải sau:

1. **Evidence span** (vá C1) — model phải trả kèm `negation_evidence` trích **nguyên văn** từ tin nhắn;
   code verify substring, verify fail → bỏ cờ phủ định, giữ `unknown`.
2. **Turn-scoping** (vá C1) — cờ `cluster_all_negative` chỉ honour khi đang trả lời đúng cụm/nhóm vừa
   hỏi; call cho `safety_extra_keys` (`intake_agent.py:531`) phải luôn `batch_negation=False`.
3. **Tri-state đơn điệu** (vá M3) — `_merge_answers` không cho `unknown` ghi đè giá trị đã xác định.
4. **Chuẩn hoá enum** (vá M2) — thêm `FieldSpec.allowed_values`, render vào prompt, loại giá trị lạ.

→ Tức là hướng **A** trong "3 hướng sửa đã đề xuất" ở trên **đã được chọn**, hướng C bị loại.

## Ý tưởng kỹ thuật đáng nhớ nhất

Khi một nhóm bị phủ định, **ghi thẳng giá trị âm tính vào `answers`** (`false` cho tri-state,
`negative_values[key]` cho enum). Từ đó `_cluster_needs_answer()` (`stage_machine.py:23-24`) tự trả
`False` và `next_cluster()` bỏ qua các cụm đó **mà không cần sửa gì cả**. Không cần drill queue, không
cần state machine mới. Trạng thái duy nhất phải nhớ thêm là số vòng sàng lọc đã dùng mỗi stage
(chống lặp vô hạn) + tập nhóm đã dương tính (để không sàng lọc lại nhóm đang cần đào sâu).

## Nhóm đã định nghĩa

**Stage 3A** (Q3-01, Q3-03 đứng ngoài): `G3A-NEURO` (Q3-04,Q3-05) · `G3A-RESP` (Q3-06,Q3-07) ·
`G3A-CIRC` (Q3-08,Q3-09) · `G3A-BLEED` (Q3-11,Q3-12) · `G3A-ABDO` (Q3-13)

**Stage 3B** (Q3-14 "gut-check" giữ nguyên ở cuối): `G3B-FUNC` (Q3-01b,Q3-08b) · `G3B-COG` (Q3-02) ·
`G3B-MSK` (Q3-13b)

## Ngoài phạm vi lần này

- **C2** (hiểu nhầm "không sốt xuất huyết" → `fever_status=none`, không tự sửa) và **C3** (né trả lời
  tuổi/giới → bỏ qua luôn) nằm ở Stage 0/1, không liên quan Stage 3A/3B → cần một ca làm việc riêng.
- **M1** (tuổi + giới trong cùng 1 câu chỉ nhặt được tuổi) cũng ở Stage 0 → chưa xử lý.
- Nhóm sàng lọc cho các bệnh khác (chest_pain, breathing…): hạ tầng `ScreeningGroup` là generic nên
  dùng lại được, nhưng nội dung nhóm từng bệnh làm sau.

---

# CA LÀM VIỆC 2026-08-13 (tối) — nối agent fever vào UI, thay pipeline rule-based cũ

> **Trạng thái: XONG, 227/227 test pass.** Ruff vẫn 1 lỗi pre-existing ở
> `src/pipeline/weaviate_cloud.py` (không liên quan, đã xác nhận bằng `git stash`).

## Vấn đề

Agent fever chỉ có API (`/api/v1/fever/*`), **không màn hình nào gọi tới** — muốn thử phải dùng
curl/Postman. Trong khi ô chat của bệnh nhân lại đang gọi `/api/v1/chat`, chạy pipeline rule-based
cũ (`src/agents/graph.py`).

Quyết định của người dùng: **thay hẳn** (phương án B trong 3 phương án đã bàn), không thêm luồng
song song.

## Cách làm — vì sao không phá gì của Dũng Mai

Điểm mấu chốt: **giữ nguyên hợp đồng API**. `/api/v1/chat` vẫn nhận `ChatRequest`, vẫn trả
`ChatResponse`, vẫn ghi case vào `case_store`. Chỉ có phần RUỘT đổi từ `agent.ainvoke` sang
`fever_session`. Nhờ vậy hàng đợi điều dưỡng, lịch sử bệnh nhân, luồng duyệt HITL **không phải sửa
một dòng nào**.

Cầu nối: `src/services/sessions/fever_case_bridge.py` (mới) — dịch `Session` của agent sang
`TriageCase`. Hai ràng buộc tự đặt cho file này:

1. **`case_id` DÙNG LUÔN `session_id`** của agent → một phiên = một case, không có bảng ánh xạ phụ
   nào để lệch nhau. Cũng nhờ vậy UI gọi thẳng được `/fever/sessions/{case_id}/confirm`.
2. **Hàm thuần**: đọc `Session` → trả `TriageCase` mới. Không LLM, không ghi store, và TUYỆT ĐỐI
   không tự suy ra mức khẩn cấp — mọi kết luận đã do `rule_engine` chốt trước khi vào đây.

## Files đã đụng

| File | Thay đổi |
|---|---|
| `src/services/sessions/fever_case_bridge.py` | **Mới** — `to_triage_case(session, patient_id, previous)` |
| `src/api/routes.py` | `/chat` chuyển sang agent fever; bỏ import `src.agents.graph.agent` |
| `src/services/engines/fever_protocol.py` | Thêm `REASON_CODE_LABELS` — 44 nhãn `RF-xx` tiếng Việt (KM §6.1), **chỉ để hiển thị**, không tham gia quyết định |
| `src/ui/new/features/patient.js` | Sidebar tiến độ, fetch `/cases/{id}` sau mỗi lượt, thẻ phiếu tóm tắt + nút xác nhận |
| `src/ui/new/state.js` | `summaryConfirmed` |
| `tests/test_services/test_fever_case_bridge.py` | **Mới** — 13 test cho bridge |
| `tests/test_api/test_routes.py` | Sửa 1 test, thêm 1 test (xem "lỗ hổng" bên dưới) |

**Lưu ý phạm vi:** `src/ui/new/` là của Dũng Mai — lần này người dùng cho phép sửa tường minh. Nếu
lần sau đụng lại thì phải hỏi trước (`_guidance/role_specific.md`).

## ✅ LỖ HỔNG ĐÃ TẠO RA — ĐÃ VÁ 2026-08-14

> Vá bằng **hướng thứ ba**, không phải A cũng không phải B trong 2 hướng bên dưới: `GENERIC_PROTOCOL`
> + lượt mở chọn protocol. Rẻ hơn A (không cần tài liệu lâm sàng cho từng bệnh) và sạch hơn B (không
> có hai cơ chế red-flag chạy song song). Chi tiết ở ca làm việc cuối file, mục 2b.
>
> Test `test_chat_non_fever_complaint_has_no_red_flag_coverage_yet` **đã xoá** đúng như dặn ở cuối
> mục này. Phần mô tả dưới đây giữ nguyên làm bản ghi lỗ hổng từng tồn tại và vì sao.

Pipeline cũ quét red flag cho **nhiều nhóm triệu chứng** (`RED_FLAG_RULES` trong `src/config.py`:
đau ngực + khó thở, dấu đột quỵ, chảy máu nặng, co giật). Agent fever chỉ có protocol cho **sốt**.

⇒ Bây giờ ai nhắn *"Tôi đau ngực từ sáng, đi vài bước là hụt hơi"* sẽ bị hỏi "bé hay người lớn, bao
nhiêu tuổi" và **không luật nào bắt được**. Trước đây case đó bị đẩy cấp cứu ngay lượt đầu.

Đã ghi lại bằng test `test_chat_non_fever_complaint_has_no_red_flag_coverage_yet`
(`tests/test_api/test_routes.py`) để lỗ hổng hiện ra trong CI thay vì nằm im. Test cũ
`test_chat_routes_red_flag_alerts_patient_immediately` đã đổi tin nhắn sang red flag SỐT — ý định
gốc (có red flag → chốt đỏ ngay lượt đầu, không lộ proposal) giữ nguyên.

**Hai hướng vá, chưa chọn:**
- **A** — viết `chest_pain_protocol.py` theo mẫu `fever_protocol.py`. Hạ tầng `symptom_protocol/` đã
  generic sẵn nên chỉ cần thêm DATA, không phải viết lại cơ chế. Sạch nhất, nhưng mỗi bệnh là một
  khối lượng tài liệu như fever.
- **B** — giữ `RED_FLAG_RULES` cũ chạy song song làm lưới an toàn cho phần ngoài sốt. Rẻ, xấu, nhưng
  bịt được lỗ ngay.

Khi nào có routing đa protocol thì test kia PHẢI hỏng → lúc đó xoá test, đừng nới assert.

## Vài chi tiết dễ quên

- `src/agents/graph.py` **vẫn tồn tại và test vẫn pass**, chỉ là không còn được `/chat` gọi nữa.
- `summary_fields` được dựng **cả khi đang thu thập** (không chỉ khi chốt phiếu) — nếu để rỗng, UI
  rơi về `validation.missing_fields` là danh sách key thô (`fever_onset_at`, `urine_output`...),
  bệnh nhân đọc không hiểu. `summary_ready` thì vẫn chỉ bật khi hết hỏi.
- UI **không hiển thị giá trị thô** (`alert`, `none_gt_6h`, `true`) cho bệnh nhân — đó là mã nội bộ
  cho điều dưỡng đọc. Bệnh nhân chỉ thấy nhãn + ✓/○ + tiến độ "đã ghi nhận 4/41".
- Phiên agent là **in-memory**: restart server là mất. `/chat` xử lý bằng cách mở phiên mới nếu
  `session_store.get(case_id)` trả None, không bắt người dùng gõ lại.
- `EARLY_VISIT` ánh xạ sang `TriagePriority.URGENT` ("Khám sớm" trong UI) — đúng nghĩa nhất trong 5
  mức có sẵn của thang hiện tại.

---

# CA LÀM VIỆC 2026-08-13 (đêm) — triển khai `agent_conversation_policy.md`

> **Trạng thái: 1.1–1.4 XONG, 251/251 test pass.** (Ruff chỉ còn 1 lỗi pre-existing ở
> `src/pipeline/weaviate_cloud.py`.) ~~Phase 2/3 và test tay với LLM thật vẫn CHƯA làm.~~
> **CẬP NHẬT 2026-08-14: Phase 2, Phase 3 và test tay với LLM thật đều đã XONG** — xem ca làm việc
> cuối file (293/293 test pass).
> Plan: `C:\Users\TUAN ANH\.claude\plans\kind-questing-rivest.md`.
> Thiết kế: `_guidance/agent_conversation_policy.md` (bản viết lại sau 3 review — xem
> `claude_review_*`, `gpt_review_*`, `deep-research-report.md` cùng thư mục).

## ✅ Phần ĐÃ XONG và đã xanh (251 passed tại checkpoint giữa ca)

| Phần | Nội dung | File |
|---|---|---|
| **Phase 0** | `structured_data.fields` từ "chỉ field đã điền" → **đủ 101 field của protocol**. Chiều JSON cố định, `"false"` giữ được, `"unknown"` cho field chưa hỏi. `symptom_group` lấy từ `FEVER_PROTOCOL.name`. Đây là JSON bên triage (model xác suất của Dũng Mai) tiêu thụ. | `sessions/fever_case_bridge.py` |
| **1.5** | `_no_fever_confirmed` + skip rule cho Q1-02, Q1-03, Q2-01…Q2-05. `"unknown"` KHÔNG được coi là không sốt. Rút lại lời khai sốt KHÔNG làm im lặng Stage 3A. | `engines/fever_protocol.py` |
| **1.6** | `_RULE_ENGINE_TOOLS` nhận cả `red_flag_engine.evaluate` (engine cũ) lẫn `rule_engine.evaluate` (engine agent) — trước đây `rule-engine.jsonl` **luôn rỗng** trên đường agent. `answers_delta` hardcode `"unknown -> x"` → delta thật. | `infra/fever_stage_log.py`, `symptom_protocol/intake_agent.py` |

Test mới: `tests/test_services/test_fever_no_fever_skip.py` (22 test) + 2 test bridge + 1 test log.

## 🔴 LỖI AN TOÀN PRE-EXISTING ĐÃ PHÁT HIỆN VÀ VÁ (ngoài phạm vi plan)

**Các rule đỏ theo NHIỆT ĐỘ chưa bao giờ chạy trên đường agent.**

`_coerce_enum` biến mọi field không-tri-state thành **chuỗi** (`temp_c` → `"40.5"`), trong khi 10 rule
kiểm `isinstance(temp, (int, float))`. Kiểm chứng thật:

```
temp_c sau khi qua agent  ->  '40.5'  (str)
R-E-16 với số 40.5        ->  ('R-E-16',)   EMERGENCY
R-E-16 với chuỗi '40.5'   ->  ('R-G-02',)   chỉ EARLY_VISIT
```

Nghĩa là **sốt 40°C kèm rối loạn tri giác đang bị xếp nhầm xuống "khám sớm"**. Đã thêm `_as_float()`
và sửa cả 10 chỗ (`temp_c` ×4, `fever_duration_days` ×3, `spo2_percent` ×2,
`caregiver_concern_level` ×1). Sau khi sửa, cả số lẫn chuỗi đều ra `R-E-16`.

→ **Cần review lâm sàng xác nhận** đây đúng là hành vi mong muốn (tôi cho là hiển nhiên đúng, nhưng
nó đổi kết luận triage nên không nên do một mình engineer chốt).

## ✅ Phần 1.1 / 1.2 / 1.3 / 1.4 — ĐÃ XONG (chốt ngày 2026-08-13, xem "Chốt A/B/C" cuối mục này)

Đã code xong về mặt cấu trúc, ban đầu **12 test đỏ**:

```
tests/test_agents/test_fever_extraction.py           4 fail
tests/test_agents/test_fever_emergency_shortcircuit.py 3 fail
tests/test_api/test_fever_flow.py                     5 fail
```

### Đã làm gì

- **1.1** Hợp nhất hướng C/E: xoá `_run_turn_combined`, xoá `_COMBINED_SYSTEM`, xoá tham số
  `next_cluster`, xoá look-ahead ở `session.py`. Mọi stage đi 1 luồng:
  `extract → merge → retraction/contradiction → derive → rule_engine → [EMERGENCY? dừng] →
  next_cluster (thuần rule) → render`. Việc hỏi lại cụm cũ quyết định **bên trong** `run_turn`
  (`retry_this_cluster`) — nếu để session ép sau thì câu hỏi đã sinh cho cụm khác.
- **1.2** `_evidence_in_message()` + `_value_and_evidence()` dùng chung; `_negation_evidence_ok` gọi
  lại; `_collect_fields(..., require_evidence=)`; prompt yêu cầu `evidence_span` + `answer_quality`;
  thêm khối **ĐÃ BIẾT** vào cả 2 prompt.
- **1.3** `asked_ids` → `completed_cluster_ids` + `unresolved_cluster_ids` +
  `retry_count_by_cluster` + `closed_cluster_ids`. `_record_cluster_outcome()` là chỗ vá C3.
  `escalation_lock` (khoá quyết định, không khoá dữ kiện).
- **1.4** `symptom_protocol/retraction.py` **mới**: `apply_retraction()` (dương→âm ⇒ xoá field con)
  + `find_contradictions()` (chiều NGƯỢC: mâu thuẫn ⇒ mở lại cụm, KHÔNG xoá). `SymptomProtocol`
  thêm `field_dependencies`, `contradiction_rules`, `confirm_before_retract`; fever khai
  `FIELD_DEPENDENCIES` (7 nhóm), `_contradiction_no_fever_but_hot` (vá nửa sau C2).

### 🔑 NGUYÊN NHÂN GỐC của 12 test đỏ — cần QUYẾT ĐỊNH THIẾT KẾ, không phải sửa test

`require_evidence=True` đang áp cho **mọi field, mọi giá trị**. Các fake provider trong test trả JSON
**phẳng** (`{"consciousness_level": "alert"}`) không có `evidence_span` ⇒ **mọi field bị loại** ⇒
`cluster_resolved=False` ⇒ retry ⇒ hội thoại không bao giờ kết thúc (test E2E lặp "vâng ạ" 60 lượt).

**Đây không chỉ là lỗi test.** Nó phơi ra một rủi ro thật: nếu model thật không chịu trả
`evidence_span`, agent sẽ **treo** chứ không phải "an toàn nhưng dài dòng" như dự đoán ở Phase 0.

Ba hướng, CHƯA CHỌN:

- **A — siết theo hướng rủi ro** (tôi nghiêng về hướng này): chỉ bắt buộc evidence cho
  (a) mọi giá trị `"false"` — đây đúng là hướng của C1; (b) mọi giá trị của field **không thuộc cụm
  đang hỏi** (`safety_keys` — người dùng chưa được hỏi); (c) giá trị cụ thể của field không-tri-state
  (vá C2: model bịa ngày `2023-10-05`). Riêng `"true"` của field ĐANG được hỏi thì không bắt buộc —
  người dùng vừa được hỏi đúng câu đó, và bịa `"true"` chỉ gây quá mức (an toàn), không bỏ sót.
- **B — giữ siết toàn bộ + lưới an toàn**: nếu **cả response** không có `evidence_span` nào thì coi
  như model không hiểu format, chấp nhận dạng phẳng và ghi `parse_degraded` vào log. Rẻ nhưng mở lại
  đúng lỗ hổng C1 khi model kém.
- **C — giữ nguyên**, sửa toàn bộ fake trong test sang định dạng mới. Sạch nhất về nguyên tắc nhưng
  4 test là **golden ghi lại output model THẬT** (`test_golden_o1_*`, `..._survives_bareword_unknown_from_real_model_output`)
  — sửa tay tức là bịa lại golden, mất giá trị chứng cứ. **Không nên làm.**

### ✅ Chốt A/B/C — đã chọn **A, có siết lại phạm vi** (2026-08-13)

Chọn A. Nhưng khi code thì đo được 2 hậu quả khiến bản A "nguyên văn" (bắt evidence cho *mọi* giá trị
`false` + *mọi* giá trị field không-tri-state) **không dùng được** — cả hai đều do test bắt được, không
phải suy đoán:

1. **Guard tự tạo ra lỗi tệ hơn lỗi nó vá.** Với `{"seizure_occurred": "true", "seizure_active_now":
   "true"}` (model trả phẳng, không kèm trích dẫn) trên câu *"tay chân đang giật, mắt trợn lên"*, CẢ HAI
   red flag bị loại → không chốt EMERGENCY → agent hỏi tiếp như ca thường. Tức là **bỏ sót cấp cứu
   (P0-5)** — nặng hơn hẳn C1. Lưới từ khoá `scan_opportunistic_fields` KHÔNG đỡ được vì "tay chân đang
   giật" không chứa chuỗi "co giật".
2. **Ca lành tính không bao giờ kết thúc.** Gần như mọi câu trả lời của người bệnh là phủ định; bắt tất
   cả phải có trích dẫn ⇒ cụm nào cũng "chưa thu được gì" ⇒ hỏi lại tới hạn mức ⇒ H1/V1 vượt 60 lượt.
   Và H1 **không thể** đạt SELF_CARE vì checklist tự chăm sóc đòi red flag ÂM TÍNH, không phải chưa biết.

**Quy tắc cuối cùng** (`intake_agent._needs_evidence`): chỉ field người dùng **CHƯA được hỏi**
(`safety_keys`) mới phải kèm `evidence_span`, và chỉ ở chiều rủi ro —

| | `"true"` | `"false"` | enum/số/ngày |
|---|---|---|---|
| Field của cụm ĐANG hỏi (`"asked"`) | không cần | không cần | không cần |
| Field NGOÀI cụm đang hỏi (`"unasked"`) | không cần | **cần** | **cần** |

Lý do phân vai: `"true"` bịa chỉ đẩy ca lên mức thận trọng hơn (P0-6 chấp nhận), còn loại nhầm một
`"true"` thật là bỏ sót cấp cứu (P0-5). Câu trả lời cho **đúng câu vừa hỏi** thì cả tin nhắn chính là
bằng chứng, không phải suy diễn. **Cả 3 lần tái hiện C1 đều xảy ra ở field ngoài cụm đang hỏi** hoặc do
cờ phủ định gộp lan ra ngoài cụm — đúng hai đường mà bảng trên chặn, và hai đường đó vẫn còn guard riêng
(`_negation_evidence_ok` + `batch_negation=False` cho safety keys).

→ 4 golden ở `test_fever_extraction.py` xanh lại **mà không sửa một chữ nào trong golden** (đúng ràng
buộc đã đặt ra: hướng C bị loại vì sẽ phải bịa lại golden).

### 2 việc phát sinh khi sửa (không có trong plan)

1. **Retry làm hội thoại dài gấp ba.** `_record_cluster_outcome` (vá C3) hỏi lại mọi cụm chưa thu được
   gì, tối đa 2 lần ⇒ mỗi cụm tốn tới 3 lượt. Đã thêm `intake_agent._worth_retrying()`: **chỉ hỏi lại
   cụm còn thiếu field bắt buộc (tier ngoài O/H)** — cùng tiêu chí tier với
   `stage_machine._cluster_is_optional_tier`, nên "cụm nào được phép bỏ qua" nhất quán giữa ngân sách và
   retry. Kèm theo `TurnResult.retried_same_cluster` để `session._record_cluster_outcome` theo ĐÚNG
   quyết định của agent — nếu session tự tính lại thì cụm agent đã bỏ qua vẫn nằm ngoài
   `closed_cluster_ids` và bị `next_cluster` chọn lại ⇒ lặp vô hạn.
2. **`_ScriptedProvider` trong `test_fever_flow.py` mô phỏng sai người bệnh.** Bản cũ để trống mọi field
   không có trong fixture ⇒ mô phỏng một người **không bao giờ phủ định điều gì**. Bản ghi ca Part 8 chỉ
   liệt kê những gì CÓ, nên với ca lành tính mọi red flag không được liệt kê nghĩa là người bệnh đã trả
   lời "không có". Đã sửa: field **tri-state** không có trong fixture → `"false"`; field enum/số vẫn để
   trống (không bịa giá trị cụ thể thay người bệnh). Đây là sửa *simulator*, không phải sửa golden — cái
   được kiểm vẫn là `expected_triage_level` trong fixture.

### Việc tiếp theo

1. **Test tay với LLM thật** — ✅ ĐÃ CHẠY (2026-08-13/14). Xem ca làm việc cuối file.
2. **Phase 2 + Phase 3** — ✅ ĐÃ XONG. Xem ca làm việc cuối file.
3. Vẫn treo: **review lâm sàng** cho `_as_float()` (đổi kết luận triage của 10 rule theo nhiệt độ).

---

# CA LÀM VIỆC 2026-08-13 → 14 — test LLM thật + Phase 2 + Phase 3

> **Trạng thái: XONG. 293/293 test pass.** Ruff còn 3 lỗi pre-existing (`scripts/log_hook.py` ×2,
> `src/pipeline/weaviate_cloud.py` ×1), không liên quan.
> Plan: `C:\Users\TUAN ANH\.claude\plans\kind-questing-rivest.md` · thiết kế:
> `_guidance/agent_conversation_policy.md`.

## 1. Test với LLM thật — câu hỏi trung tâm đã có đáp án

Viết `scripts/manual_llm_check.py` (chạy lại được, không phải chat tay từng lượt): lái phiên thật
in-process qua 7 kịch bản rồi đo. `python scripts/manual_llm_check.py --list` để xem danh sách.

Model thật dùng lần này là **`gemini-3.1-flash-lite`**, KHÔNG phải `deepseek-chat` như lần trước
(`DEEPSEEK_API_KEY` đã comment trong `.env`; `openrouter` trả HTTP 402 hết số dư nên rơi xuống
gemini). **Đổi model ⇒ phải chạy lại toàn bộ.**

| Đo được | Kết quả |
|---|---|
| Model có chịu trả `evidence_span`? | **CÓ — 453/453 giá trị có, 0 giá trị dạng phẳng** |
| `negation_evidence` khi đặt cờ phủ định gộp | 4/4 lần đều kèm trích dẫn |
| C1 / C2 / C3 / M1 / M2 | **không tái hiện** |
| Ca lành tính | kết thúc 36 lượt → `SELF_CARE` / `SUFFICIENT_EVIDENCE` |
| Red flag ngay lượt đầu | chốt cấp cứu, `RF-02` |

⇒ Nỗi lo lớn nhất của Phase 1 (model bỏ khoá `evidence_span` ⇒ agent treo) **không xảy ra**. Không
phải nới lỏng verify, không phải chỉnh prompt.

**Lưu ý môi trường:** gemini free tier trả HTTP 429 khi gọi liên tục — 10/40 lượt của lần chạy đầu
hỏng vì lý do này (agent xử lý đúng: mọi field về `unknown`, không crash). Script có `--delay` (mặc
định 3s) để tránh.

### 3 lỗi MỚI mà chỉ LLM thật mới lộ ra (đã vá + có test hồi quy)

| # | Mức | Lỗi | Vá ở đâu |
|---|---|---|---|
| N1 | 🔴 | **Câu hỏi RỖNG ở mọi ranh giới stage** — regression của Phase 1.1. `run_turn` chỉ gọi `next_cluster` cho stage HIỆN TẠI; hết cụm là trả tin nhắn trống, rồi session lặng lẽ nhảy sang cụm đầu stage sau. Người bệnh không được hỏi gì nhưng lượt sau vẫn bị trích theo schema cụm đó. Đo được 5/40 lượt. | `stage_machine.advance()` — hàm duyệt THUẦN, băng qua stage, dùng chung cho cả `run_turn` (sinh câu hỏi) lẫn `session` (cập nhật trạng thái). Xoá `session._walk_to_next_cluster` trùng lặp. |
| N2 | 🟡 | **`non_blanching_rash` (red flag M0) bị xoá về `unknown`** — nó bị khai là field CON của `rash_present`, nên "không có ban" xoá luôn một dấu hiệu đỏ đã xác nhận ÂM TÍNH. Âm tính là dữ kiện, không phải vô nghĩa. | Bỏ nó khỏi `FIELD_DEPENDENCIES["rash_present"]`. Hai field chọi nhau là việc của `contradiction_rules` (hỏi lại), không phải im lặng xoá. |
| N3 | 🟡 | **Một chữ "Không" trần được nhận làm bằng chứng** — chính là C1 ở dạng nhỏ: người bệnh trả lời "Không, không bị co giật" thì model ghi luôn `rash_present="false"` kèm trích dẫn "Không" (có thật trong tin nhắn nên guard chấp nhận). Hạt phủ định trần chứng minh được MỌI thứ. | `intake_agent._EMPTY_EVIDENCE` — loại hạt phủ định trần, nhưng CHỈ ngoài cụm đang hỏi. Trong cụm vừa hỏi thì "Không" là câu trả lời trực tiếp, vẫn nhận. |

## 2. Phase 2 — `common_safety/` + `GENERIC_PROTOCOL` + lượt mở

### 2a. `symptom_protocol/common_safety/` (mới)

`predicates.py` · `fields.py` · `clusters.py` · `rules.py` · `emergency_message.py`.

Nguyên tắc: **co giật, tím tái, sốc, ban không mất khi ấn kính KHÔNG phải kiến thức về sốt** — chúng
là kiến thức về "người bệnh đang nguy kịch". Để chúng trong `fever_checklist.py` nghĩa là protocol
thứ hai hoặc phải import từ fever (sai chiều phụ thuộc), hoặc phải chép lại (hai bản sao sẽ lệch).

- 72 field + 28 rule đỏ chuyển sang, `fever_*` import lại. Fever **không đổi hành vi**: test
  `test_fever_rule_catalog_order_is_unchanged_after_extracting_common_rules` ghim nguyên thứ tự 42
  rule (thứ tự là hợp đồng thật — `r_e_21` đọc `matches_so_far`).
- Cụm dùng chung là **HÀM theo stage** (`emergency_scan_clusters("3A")` cho fever, `("2")` cho
  generic) vì `QuestionCluster.stage` là một phần của cụm.
- Mã cụm giữ nguyên giữa các protocol (`Q3-03` là cụm co giật ở cả hai) — mã là đường truy ngược về
  tài liệu lâm sàng. Trùng mã không gây lẫn state vì trạng thái cụm lưu theo `"<protocol>:<id>"`.
- Test `test_common_safety_never_imports_a_specific_protocol` canh chiều phụ thuộc (duyệt bằng `ast`,
  không quét chuỗi — docstring của chính các file đó có nhắc tên "fever", đúng chỗ).

### 2b. `GENERIC_PROTOCOL` — vá lỗ hổng `:215`

`engines/generic_protocol.py` + `checklists/generic_checklist.py`. 78 field, 30 cụm, 30 rule — chỉ
**6 field và 2 cụm là thật sự mới** (phần mô tả than phiền), còn lại đi mượn `common_safety`.

`self_care_checklist_satisfied` luôn `False` ⇒ không bao giờ `SUFFICIENT_EVIDENCE` ⇒ luôn
`BUDGET_EXHAUSTED` ⇒ `EARLY_VISIT` ⇒ `URGENT` ("Khám sớm"). **Mọi** than phiền ngoài sốt vào hàng đợi
điều dưỡng ở mức Khám sớm — hệ quả CÓ Ý THỨC: protocol này chỉ quét được tập dấu hiệu phổ quát, nó
không có căn cứ nào để nói "cứ ở nhà". **Cần theo dõi tải hàng đợi sau khi lên production.**

Đo bằng LLM thật: *"Tôi đau ngực từ sáng, đi vài bước là hụt hơi"* → protocol `general`,
`EARLY_VISIT` + `RF-12`, câu hỏi kế tiếp không nhắc gì tới sốt. Trước đó ca này không luật nào quét.

Test `test_chat_non_fever_complaint_has_no_red_flag_coverage_yet` **đã xoá** (đúng ràng buộc đã đặt:
vá bằng protocol, không nới assert), thay bằng 3 test thật ở `tests/test_api/test_routes.py`.

### 2c. Lượt mở (`SessionPhase.OPENING`)

Phiên từ ô chat **không ghim protocol**: tin nhắn đầu là lời kể tự do, `select_protocol` chạy SAU khi
trích xuất. Tin nhắn quá nghèo ("xin chào") → hỏi lại câu mở tĩnh, **không** chọn protocol (chọn từ
một tin nhắn không có thông tin là đoán mò, và đoán sai kéo dài suốt phiên).

Ở lượt mở mọi field đều là "chưa được hỏi" (`evidence="unasked"`) — đây là lượt dễ bịa nhất (schema
rộng, tin nhắn tự do) nên cũng là lượt siết chặt nhất. `cluster_all_negative` bị cấm tuyệt đối.

### 2d. Bridge generic hoá

`fever_case_bridge.py` → `symptom_case_bridge.py`, resolve protocol từ `session.protocol_name`. Thêm
4 field hiển thị vào `SymptomProtocol` (`chief_complaint_field`, `default_chief_complaint`,
`onset_field`, `severity_field`) + `reason_code_labels`, để bridge không phải biết tên field của từng
bệnh. Trước đó ca đau bụng vẫn được gửi đi kèm `symptom_group="fever"` và chief complaint "Sốt" —
**sai DỮ LIỆU** (bên triage huấn luyện trên JSON này), không phải sai hiển thị.

### 2e. HIV / thông tin nhạy cảm

Chặn ở `hint` của `immunocompromised`/`immunocompromise_cause`: chỉ đặt `true` khi lời khai thực sự
hỗ trợ (hoá trị, ghép tạng, thuốc ức chế miễn dịch, HIV KHÔNG kiểm soát); riêng "có HIV" thì ghi vào
`chronic_conditions`. Đo bằng LLM thật: *"Tôi bị HIV, mấy hôm nay người mệt lắm"* →
`chronic_conditions='HIV'`, `immunocompromised='unknown'`, hội thoại tiếp tục bình thường.

## 3. Phase 3 — đổi protocol giữa chừng

`symptom_protocol/registry.py`: `PROTOCOL_REGISTRY`, `protocol_for`, `select_protocol`,
`OPENING_PROTOCOL`. **MỘT** `ProtocolSessionStore` cho toàn hệ thống (`sessions/symptom_session.py`) —
hai store là hai không gian `case_id`, và `/fever/sessions/{case_id}/confirm` sẽ 404 với case mở từ ô
chat.

Chỗ đổi nằm trong `run_turn`, **sau** đính chính/xoá dây chuyền và **trước** rule engine: sau, vì căn
cứ để đổi là hồ sơ đã được đính chính; trước, vì kết luận của chính lượt này phải do luật protocol MỚI
chấm.

**`Session.protocol_pinned`** — endpoint chuyên biệt (`/api/v1/fever/*`) tuyên bố protocol thì hệ
thống không được đoán lại. Không có cờ này, ca H1 (Part 8) bị kéo sang `general` giữa chừng rồi không
bao giờ đạt `SELF_CARE` nữa.

### 2 lỗi nữa lộ ra khi làm Phase 3 (đều đã vá)

1. **Người bệnh KHÔNG THỂ đính chính field ngoài cụm đang hỏi.** `_safety_extra_keys` loại mọi field
   đã điền ("đã biết rồi thì không cần trích lại"), nên câu "à tôi nhầm, tôi không sốt" ở một lượt
   đang hỏi chuyện khác không có đường nào ghi nhận — toàn bộ cơ chế `retraction` không bao giờ có dữ
   liệu để chạy. Vá: giữ `protocol.confirm_before_retract` trong schema NGAY CẢ KHI đã điền (đúng tập
   protocol đã tự khai "xoá nhầm cái này thì đắt", cũng là tập hay bị đính chính nhất).
2. **Phiên `general` không bao giờ chuyển lại được sang `fever`.** `temp_c`/`fever_reported` không
   nằm trong registry của `general` nên câu "bé sốt 39.2 độ" không có chỗ để ghi. Vá:
   `registry.with_switch_detection()` nới schema TRÍCH XUẤT thêm 3 field nhận diện — không vào
   registry thật, nên JSON gửi bên triage của ca đau bụng vẫn không có `temp_c`. (Cố ý KHÔNG dùng quét
   từ khoá: "sốt" có trong cả "không bị **sốt** xuất huyết" — đúng bằng cách tái tạo bug C2.)

## Việc còn lại

1. **Review lâm sàng `_as_float()`** — vẫn treo từ ca trước, đổi kết luận triage của 10 rule theo
   nhiệt độ. Không nên để một mình engineer chốt.
2. **Theo dõi tải hàng đợi điều dưỡng** sau khi generic protocol lên production (mọi ca ngoài sốt =
   "Khám sớm"). Chỉnh `BUDGET` của `generic_protocol.py` nếu quá tải.
3. Ca lành tính vẫn dài (36 lượt). Ý tưởng `ScreeningGroup` (sàng lọc theo nhóm cơ quan, ca làm việc
   2026-08-13 chiều) là hướng rút ngắn — hoãn từ trước, giờ đo lại được rồi thì quyết được.
4. Protocol thứ ba (chest_pain riêng) nếu muốn hỏi sâu hơn mức generic: hạ tầng đã sẵn, chỉ cần thêm
   DATA + tài liệu lâm sàng, KHÔNG sửa engine.

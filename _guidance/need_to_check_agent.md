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

**Phase 0 ĐÃ CODE XONG** (xem mục "Phase 0 — đã làm" bên dưới). Bước kế tiếp:

1. **Test tay với LLM thật** lại 3 kịch bản C1 / M2 / M3 — test tự động chỉ chứng minh guard chạy đúng
   khi model trả JSON như giả định, chưa chứng minh model chịu trả `negation_evidence`. Nếu model bỏ
   qua khoá này thì mọi phủ định gộp bị từ chối → agent hỏi lại nhiều hơn trước (an toàn nhưng dài
   dòng); lúc đó phải chỉnh prompt, không nới lỏng verify.
2. Xong bước 1 mới sang **Phase 1** (`ScreeningGroup` + câu sàng lọc gộp) trong file plan.

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

# Đánh giá lại kế hoạch V2 — Medical Conversation Agent

> Ngày đánh giá: 2026-08-19
> Tài liệu được đánh giá: `_guidance/medical_conversation_agent_plan_v2.md` (2224 dòng)
> Bản đánh giá tham chiếu: `_guidance/medical_conversation_agent_plan_v2_gpt_5.6__hight.md`
> Phương pháp: đối chiếu từng đề xuất của V2 với **code đang chạy** và với **các quyết định đã chốt**
> trong repo. Mọi khẳng định về hiện trạng đều kèm `file:line` để kiểm chứng lại.

---

## 1. Kết luận điều hành

**Quyết định: KHÔNG duyệt V2 làm kế hoạch triển khai. Giữ lại như tài liệu giải thích.**

Đây là kết luận khác với bản GPT ("duyệt có điều kiện"), và lý do khác nằm ở một dữ kiện mà bản GPT
chỉ nói một nửa: **phần lớn nội dung V2 đã được implement rồi, ở mức chặt chẽ hơn V2 đề xuất**, và
tài liệu `_guidance/what_to_do_next.md` (1179 dòng, đã đối chiếu code 2026-08-17) đang là kế hoạch
nâng cấp chính thức, bao trùm gần như toàn bộ V2 cộng thêm test suite, metric và acceptance gate.

Ba vấn đề ở mức kế hoạch, quan trọng hơn mọi chi tiết kỹ thuật bên dưới:

1. **V2 đọc sai hiện trạng.** Nó viết như thể hệ thống mới chỉ có "General Protocol + Fever Protocol"
   và chưa có state machine, coverage, stop policy, red-flag layer. Thực tế `src/services/symptom_protocol/`
   có 6717 dòng gồm reducer theo sự kiện, coverage ledger, ranking tất định, stage machine với 4
   stop reason, output guard, và tầng L0 text safety độc lập model. V2 mô tả đích đến mà repo đã đi
   qua từ hai tuần trước.
2. **Ở những chỗ V2 khác code hiện tại, nó khác theo chiều KÉM AN TOÀN HƠN**: Stop Agent bằng LLM
   thay cho `should_stop` tất định, LLM router thay cho router rule, RAG sinh câu hỏi lâm sàng thay
   cho checklist đã duyệt, và cross-conversation memory chứa PHI. Nếu implement V2 nguyên văn thì đây
   là **regression an toàn**, không phải nâng cấp.
3. **V2 không chạm vào việc lớn nhất còn lại của MVP.** `CLAUDE.md` chốt 5 nhóm triệu chứng; repo có
   `FEVER_PROTOCOL` + `GENERIC_PROTOCOL` (`src/services/symptom_protocol/registry.py:22-25`) —
   **1/5 nhóm**. 4 protocol còn thiếu là hạng mục lớn nhất và vẫn chưa có người chủ trì
   (`what_to_do_next.md:932-950`, §14 mục 1). V2 dành 2224 dòng cho lớp generic đã tồn tại và 0 dòng
   cho 4 protocol chưa tồn tại.

Điều V2 làm tốt: nó là bản diễn giải dễ đọc, có ví dụ hội thoại tiếng Việt cụ thể — hữu ích để
onboard người mới hoặc giải thích cho PM/PO. Đó là giá trị thật, nhưng không phải giá trị của một
implementation plan.

---

## 2. Chấm điểm

| Hạng mục | Điểm | Nhận xét |
|---|---:|---|
| Độ chính xác về hiện trạng repo | 2/10 | Coi như chưa có engine; không một `file:line` nào được dẫn |
| Tầm nhìn sản phẩm | 7/10 | Ranh giới hội thoại/triage rõ, nhưng đặt sai chỗ (xem §4.1) |
| Mô hình hội thoại | 6/10 | Batching, correction, hybrid memory đúng — đều đã có trong code |
| An toàn y khoa | 3/10 | Thấp hơn bản GPT chấm: V2 chuyển 3 quyết định an toàn từ code sang LLM |
| Hợp đồng dữ liệu | 4/10 | ISBAR xuất hiện từ đâu không rõ; xung đột `HandoffSummary` đang chạy |
| Tương thích quyết định đã chốt | 3/10 | Xung đột ADR-003, FR-05, `ARCHITECTURE.md` ràng buộc 1 và 3 |
| Kiểm thử và đo lường | 2/10 | Không metric, không threshold, không golden case, dù repo đã có `eval/` |
| Giá trị gia tăng so với `what_to_do_next.md` | 2/10 | Chủ yếu trùng lặp; phần khác biệt là phần nên bỏ |

**Mức sẵn sàng triển khai: 2/10.** Không phải vì viết sơ sài — mà vì nếu đội làm đúng theo V2 thì
phải tháo bỏ những thứ đã chạy và đã có test.

---

## 3. Bảng đối chiếu: V2 đề xuất gì, repo đã có gì

Đây là phần quan trọng nhất của bản đánh giá này.

| Mục V2 | Trạng thái | Nơi đã tồn tại trong code |
|---|---|---|
| §4 Conversation State 4 giá trị | **Đã có, và chặt hơn** | `reducer.py` — snapshot chỉ 3 giá trị, `unset` là *operation* kèm audit, không phải giá trị thứ tư (`reducer.py:22-27`) |
| §6 Protocol Router | **Đã có (tất định)** | `registry.select_protocol()` (`registry.py:40-58`) — chỉ chuyển khi có căn cứ dương tính rõ ràng |
| §7 Fallback Protocol | **Đã có** | `GENERIC_PROTOCOL` là default; "generic không bao giờ kết luận an toàn" (`registry.py:27-30`) |
| §8–9 Extraction positive/negative/unknown | **Đã có** | `FieldEvent` + `certainty` suy ra bằng code từ `evidence_span`, không tin nhãn model (`reducer.py:44-70`) |
| §10 User sửa thông tin cũ + audit log | **Đã có, và chặt hơn** | `retraction.py`, `AuditEvent`, `confirm_before_retract`, `pending_confirmation` (`reducer.py:72-100`) |
| §11 Red-flag detection | **Đã có, 2 tầng** | L0 `common_safety/text_safety_signals.py` (383 dòng, độc lập model) + `common_safety/rules.py` (443 dòng) |
| §12 Guardrails thay rule cứng | **Đã có** | `output_guard.check()` chặn tên bệnh và câu hỏi ngoài field đã khai báo (`output_guard.py:91-163`) |
| §14 Coverage Checker | **Đã có** | `coverage.CoverageLedger` + `mandatory_remaining()` (`coverage.py:33-88`) |
| §15–18 Question Planner + ưu tiên | **Đã có (tất định)** | `ranking.py` + `stage_machine.select_cluster()` (`stage_machine.py:140`); tier M0/M1/C/O/H (`models.py:9`) |
| §16–17 Batch câu hỏi, không dump 20 câu | **Đã có** | `batching.py` (206 dòng) + `ScreeningGroup` phủ định gộp (`models.py:36-64`) |
| §19–20 Hybrid memory + summarizer | **Có một phần** | `Session` giữ snapshot + `dialogue.build_response_plan()`; nén context dài chưa có |
| §23–36 Stop Policy đa điều kiện | **Đã có, và test được** | `stage_machine.should_stop()` (`stage_machine.py:285-336`), 4 reason code: `RED_FLAG` / `SUFFICIENT_EVIDENCE` / `BUDGET_EXHAUSTED` / `USER_CANNOT_CONTINUE` (`stage_machine.py:20`) |
| §27 Coverage threshold thay full coverage | **Đã có, tốt hơn** | `_has_sufficient_evidence()` — 3 điều kiện AND, gồm "đã quét xong cả 2 gate stage" là ràng buộc lâm sàng cứng (`stage_machine.py:241-283`) |
| §33 Soft turn budget | **Đã có** | `protocol.budget` + `budget_floor_stage`; budget **không được** cắt cụm mang field M0/M1 chưa hỏi (`stage_machine.py:345-357`) |
| §38–41 Nurse summary + bỏ field rỗng | **Đã có schema** | `HandoffSummary` (`src/models/schemas.py:138-149`) có `missing_information` — đúng cái `data_gaps` mà bản GPT đề nghị thêm |
| §5 Active Field Set động theo router | **Có một phần** | Field set gắn với protocol; merge nhiều protocol cùng lúc chưa có (V2 nói đúng — xem §5.1) |
| §25 Stop theo user intent tường minh | **CHƯA có** | `user_can_continue` có trong signature (`stage_machine.py:293`) nhưng chưa ai suy nó ra từ tin nhắn (xem §5.2) |
| §13 RAG cho 5 tầng | **CHƯA có ở runtime** | `pipeline/weaviate_cloud.py` là nhánh tooling, không nằm trong luồng chuẩn |
| §21–22 Long-term memory 3 phiên gần nhất | **CHƯA có — và không nên có trong MVP** | xem §4.4 |

**Tỷ lệ: 16/19 mục đã tồn tại. 1 mục nên loại. 2 mục là gap thật.**

---

## 4. Lỗi phải sửa nếu vẫn muốn dùng V2 (P0)

### 4.1. Ranh giới "Summary → Triage" của V2 xung đột với PRD và với kiến trúc đang chạy

V2 §42 lập luận: agent không được ghi `triage_category` vì sẽ tạo circular dependency — "cần triage
để tạo summary nhưng cần summary để chạy triage".

**Lập luận này sai, và hệ quả của nó phá vỡ ba nguồn thật:**

- Không có vòng lặp nào. Triage đọc **state snapshot**, không đọc natural summary:
  `rule_engine.evaluate(protocol, answers)` (`rule_engine.py:27`). Summary và triage là hai
  *renderer song song* của cùng một snapshot, không phải hai bước tuần tự.
- `docs/prd.md:65` FR-05 (P0): "Agent tạo phiếu tóm tắt triệu chứng tự động **kèm mức ưu tiên đề xuất**".
- `ARCHITECTURE.md:15-19` ràng buộc 1: "mức ưu tiên do rule engine thuần quyết định"; ràng buộc 3:
  "red-flag được quyết định **ngay trong lượt**, không chờ hết checklist".
- `HandoffSummary.proposed_priority` đã tồn tại trong schema đang chạy (`src/models/schemas.py:145`).

Điều V2 muốn bảo vệ là đúng: **LLM không được xếp mức ưu tiên**. Nhưng cách nó diễn đạt ("agent không
quyết định triage, downstream mới quyết") lại đẩy rule engine tất định ra khỏi agent — trong khi rule
engine chính là thứ khiến hệ thống an toàn. Ranh giới đúng là:

```text
KHÔNG phải:  Agent (LLM) → Summary → Triage module → mức ưu tiên
Mà là:       Extractor (LLM) → snapshot → rule engine (CODE) → mức ĐỀ XUẤT
                                       └→ summary renderer → phiếu bàn giao
             → điều dưỡng duyệt (HITL) → mới có hiệu lực
```

Đây cũng là chỗ bản GPT bỏ sót: nó chấp nhận framing của V2 và chỉ bàn `triage_category` như một vấn
đề schema, trong khi đây là vấn đề kiến trúc.

### 4.2. Stop Agent bằng LLM là bước lùi so với `should_stop` đã có

V2 §35 định nghĩa Stop Agent nhận JSON và trả `decision: CONTINUE | SUMMARIZE`. Nếu quyết định này do
model đưa ra thì cùng một state có thể dừng khác nhau giữa các lần chạy, và không test được bằng fake
LLM.

Code hiện tại đã là hàm thuần, thứ tự ưu tiên rõ (`stage_machine.py:296-336`):

```text
user_can_continue = False        -> USER_CANNOT_CONTINUE
emergency signal / EMERGENCY     -> RED_FLAG
_has_sufficient_evidence         -> SUFFICIENT_EVIDENCE
chưa tới budget_floor_stage      -> tiếp tục
còn cụm mang M0/M1 chưa hỏi      -> tiếp tục (budget KHÔNG được cắt)
                                 -> BUDGET_EXHAUSTED
```

So với pseudo-logic V2 §36, hàm này **đã bao trùm** và còn có thêm ràng buộc gate stage. Cái V2 thêm
được mà code chưa có là **user intent tường minh** ("tóm tắt cho tôi đi", "tôi không trả lời nữa") —
tức là **một input mới cho hàm cũ**, không phải một agent mới. Đây là gap thật duy nhất trong toàn bộ
§23–36 của V2.

### 4.3. "Dynamic questions" + RAG sinh câu hỏi lâm sàng vi phạm ADR-003

`docs/context/decisions.md` ADR-003 (đã chốt 04/08/2026): "Agent **chỉ được hỏi trong phạm vi
checklist cố định** theo từng nhóm triệu chứng, có guard rail chặn câu hỏi ngoài phạm vi".
`docs/prd.md:61` FR-01 nhắc lại. V2 §7 lại đề xuất "Không tìm thấy protocol chuyên biệt → General +
RAG medical context → Dynamic questions".

Bản GPT nêu đúng vấn đề này (P0.2) nhưng để mở hai phương án. Ở đây không có hai phương án: ADR-003
đã chốt và `output_guard.py:145-163` đã implement guard theo nó. Muốn đổi thì phải viết ADR supersede
kèm lập luận an toàn — không phải viết một kế hoạch mới rồi implement.

Ranh giới đúng đã có trong code và có lý do được ghi lại: `ScreeningGroup.probe_hint` nói rõ câu sàng
lọc được **ghép tĩnh** từ hint chứ không qua LLM diễn đạt lại, vì "LLM diễn đạt lại thì có thể lược
mất vài ý trong danh sách" (`models.py:52-56`). Và `EMERGENCY_MESSAGE` là hằng số tĩnh, có comment
giải thích tại sao nó không được đi qua LLM (`common_safety/emergency_message.py:1-6`).

### 4.4. Long-term memory: nên gỡ khỏi phạm vi, không phải "bổ sung consent"

V2 §21–22 đề xuất mở conversation mới thì tự nạp 3 summary gần nhất. Đây là PHI. `CLAUDE.md` nguyên
tắc 5: "chỉ nhân viên y tế được gán ca mới truy cập được".

Bản GPT khuyến nghị hoãn tới khi có consent/retention/isolation — tôi đồng ý và đi xa hơn: **việc này
không nằm trên đường tới MVP nào cả**. Nó không có trong PRD, không có trong 5 feature spec của
Sprint 2, và `ARCHITECTURE.md:364-369` ghi rõ `session_store` còn **mất khi restart** — tức là phiên
đang dở chưa persist được, mà V2 đã bàn tới ký ức xuyên phiên. Sai thứ tự.

Việc đúng thứ tự: persist phiên đang dở (event log/snapshot sau mỗi lượt được nhận), hoặc ghi rõ đây
là giới hạn MVP kèm UX phục hồi.

### 4.5. ISBAR có nguồn ngoài repo, nhưng vẫn chưa đi qua ADR-006

*Cập nhật 2026-08-19: đã nhận được template gốc — slide "Cấu trúc ISBAR chuẩn cho AI sinh ra phiếu tóm
tắt [WHO]" của team. Nguyên văn template và bảng đối chiếu với schema đang chạy: xem [§9](#9-phụ-lục--template-isbar-của-team-và-đối-chiếu-với-handoffsummary).*

Vậy phê bình ban đầu ("ISBAR từ đâu ra?") không còn đúng: nó là một quyết định nghiệp vụ có chủ đích
của team, không phải V2 tự nghĩ ra. Ba vấn đề còn lại thì vẫn nguyên:

1. **Nguồn nằm ngoài repo.** Tìm toàn bộ `docs/` — không một chỗ nào nhắc ISBAR. Template sống trong
   slide, còn code chạy theo `HandoffSummary` (`src/models/schemas.py:138-149`) là cấu trúc phẳng theo
   wireframe W-07. ADR-006 ("format phiếu tóm tắt phải chốt trước khi viết schema JSON") vẫn để trống.
   Một quyết định format chỉ tồn tại trong slide thì không ràng buộc được ai.
2. **V2 dùng template nhưng sửa nó mà không nói.** Template có `Triage Category` trong [I] và có nguyên
   khối [R]; V2 §42–43 bỏ cả hai. Đó có thể là lựa chọn đúng hoặc sai, nhưng nó là **đề xuất thay đổi
   template của team** — phải nêu rõ như vậy, không phải trình bày như thể template vốn thế.
3. **Chi phí migrate không được nhắc.** Nếu ISBAR thắng thì phải migrate `HandoffSummary`,
   `NurseQueueItem`, `engines/summary_generator.py` và UI W-07. V2 không có dòng nào về việc này.

Bản thân template cũng có **hai điểm cần chốt lại trước khi đưa vào schema** (chi tiết ở §9.3): trường
`AI Action` ở khối [R] viết dưới dạng hành động đã thực hiện, còn `Bệnh nền: chỉ hiển thị bệnh có liên
quan nếu AI có khả năng lọc` là một lệnh lọc y khoa giao cho LLM. Cả hai đụng nguyên tắc an toàn 1 và 3
trong `CLAUDE.md`.

---

## 5. Hai chỗ V2 nói đúng và repo còn thiếu

Đây là phần đáng giữ lại của V2. Chỉ có hai mục, nhưng cả hai đều thật.

### 5.1. Multi-protocol đồng thời (`primary` + `secondary[]`) — V2 §6

Code hiện tại gắn **một** protocol cho một phiên (`registry.select_protocol` trả một tên). Ca thật
"đau bụng + sốt 39" phải chọn một trong hai. V2 nêu đúng vấn đề nhưng chưa trả lời được câu khó — bản
GPT liệt kê đúng các câu đó (P0.5): field cùng tên khác nghĩa merge thế nào, tier/budget/rule của
protocol nào thắng, đổi primary thì cụm đã hỏi map ra sao.

Bổ sung một điều kiện mà cả V2 và bản GPT đều không nêu: `CoverageLedger.reset()` hiện **xoá sạch nợ
hoãn khi đổi protocol** vì mã cụm dùng chung giữa các protocol (`coverage.py:80-86`). Multi-protocol
đồng thời sẽ phá giả định này — hoặc phải namespace mã cụm, hoặc phải bỏ `reset()`. Việc này cũng
không có nghĩa trước khi 4 protocol còn thiếu tồn tại, nên **nó nằm sau track PC**.

### 5.2. User intent làm input của stop policy — V2 §25

Như §4.2: `should_stop` chưa có đường nào để "tóm tắt cho tôi đi" hoặc "tôi không muốn trả lời nữa"
tác động vào. `user_can_continue` đã có sẵn trong signature (`stage_machine.py:293`) nhưng chưa ai
suy nó ra từ tin nhắn. Việc nhỏ, giá trị rõ, làm được ngay:

- classifier intent tất định (từ khoá) + fallback model, chỉ được set `user_can_continue=False`;
- **không** cho intent bỏ qua nhánh red flag;
- stop vì intent phải đánh dấu phiếu là **incomplete** kèm `missing_information`, không được để
  downstream đọc thành ca lành tính.

> **Phát hiện phụ, độc lập với V2:** trong `should_stop`, `user_can_continue` được xét **trước**
> `provisional_emergency_signal` (`stage_machine.py:296-300`). Nghĩa là nếu người bệnh nói "thôi khỏi"
> ở đúng lượt vừa khai một dấu hiệu cấp cứu, phiên dừng với `USER_CANNOT_CONTINUE` thay vì `RED_FLAG`.
> Đây là lỗi an toàn tiềm ẩn đã có trong code — nên mở issue riêng và thêm test case, không chờ V2.

---

## 6. Đánh giá bản GPT 5.6

Bản GPT chính xác hơn V2 rất nhiều và đáng đọc. Các điểm nó nêu đúng, tôi đã kiểm chứng lại:

- Xung đột ADR-003 về dynamic question (P0.2) — đúng.
- Xung đột nguồn thật về thông điệp red-flag cho bệnh nhân (P0.1) — **đúng và đây là xung đột thật,
  chưa ai giải quyết**: `ARCHITECTURE.md:15-19` + `docs/prd.md:64` FR-04 + ADR-004 nói hiện banner
  ngay cho bệnh nhân, còn `docs/planning/Feature_Specification_VMedTriage.md:253-256` nói **không gửi
  gì cho bệnh nhân** và loại thẳng phương án (a) "banner tự động gửi ngay" của thiết kế v1.0.
- Stop policy phải tất định (P0.4), semantics multi-protocol (P0.5), long-term memory thiếu điều kiện
  bảo mật (P0.7), `conversation_id` không nên là timestamp (P1.2), model chưa benchmark (P1.4) — đúng.

Bốn chỗ tôi đánh giá khác:

1. **"Duyệt có điều kiện" là quá nhẹ.** Nếu 16/19 mục đã có trong code và phần khác biệt là phần nên
   bỏ, thì kết quả không phải "sửa rồi dùng" mà là "không dùng làm plan". Danh sách 7 điều kiện ở §11
   bản GPT, nếu làm đủ, sẽ tạo ra chính `what_to_do_next.md` — một tài liệu đã tồn tại.
2. **P0.3 "State chưa đủ để làm nguồn sự thật" đã được giải quyết trong code.** Bản GPT đề xuất
   `status ∈ {unasked, answered, unknown, refused, not_applicable, retracted}`. Repo đã chọn thiết kế
   khác **và có lý do được ghi lại**: snapshot giữ đúng 3 giá trị, các trạng thái kia biểu diễn bằng
   `operation` + `AuditEvent` + `field_not_applicable()`, vì "thêm giá trị thứ tư là thay đổi lan ra
   toàn bộ tầng luật an toàn" (`reducer.py:22-27`, `stage_machine.py:38-56`). Hai thiết kế tương đương
   về semantics; đề xuất của bản GPT đắt hơn nhiều — nên giữ cái đang có.
3. **P0.6 "Output contract chưa chốt" — chốt một nửa rồi.** `HandoffSummary` đã là Pydantic schema có
   `missing_information` (đúng `data_gaps`) và `proposed_priority`. Việc còn lại đúng là ADR-006 và
   versioning, nhưng phải nói rõ đó là *sửa cái đang chạy*, không phải *thiết kế từ đầu*.
4. **"Kiểm thử 3/10" đúng với V2, nhưng dễ bị đọc thành repo không có gì.** Repo có `eval/scripts/`
   (`run_eval.py`, `run_conversation_eval.py`, `simulated_patient.py`), baseline
   `eval/baselines/2026-08-17-p0-summary.md`, và acceptance gate ở `what_to_do_next.md:1015-1081`.
   Baseline đó có hai con số quan trọng hơn mọi tranh luận kiến trúc trong cả hai tài liệu:
   **emergency recall 48.9% (22/45)** và **red-flag recall 0% do lệch từ vựng mã**.

---

## 7. Khuyến nghị

### 7.1. Xử lý V2

- Đổi tiêu đề thành *"Ghi chú thiết kế — mô hình hội thoại thu thập triệu chứng"*, đánh dấu
  **superseded by `what_to_do_next.md`** ở đầu file, giữ lại làm tài liệu giải thích cho PM/PO.
- Trích ra đúng 2 mục còn giá trị (§5.1 multi-protocol, §5.2 user intent) thành 2 issue.
- Xoá khỏi phạm vi: LLM Stop Agent, RAG sinh câu hỏi lâm sàng, long-term memory xuyên phiên.
- ISBAR: giữ lại nhưng chuyển thành đầu vào của ADR-006 theo §9, không tự chốt trong V2.

### 7.2. Thứ tự việc thật, theo mức chặn

| # | Việc | Loại | Vì sao ở vị trí này |
|---|---|---|---|
| 1 | **Bảng quy đổi mã red flag** (`RF-07`/`TEXT_SIGNAL_*` ↔ `RF-TRAUMA-POISONING-001`) | Quyết định lâm sàng | red-flag recall đang đo ra 0% dù hệ thống có phát hiện; chặn gate ở §12 |
| 2 | **Giải quyết xung đột thông điệp red-flag cho bệnh nhân** (ADR-004 vs Feature Spec :253-256) | ADR mới | Hai nguồn thật đang ngược nhau; ảnh hưởng cả UI và `EMERGENCY_MESSAGE` |
| 3 | **Clinical governance ký duyệt `SHORT_CIRCUIT_CODES`** (32/100 mã) | Quyết định lâm sàng | Hệ thống đang an toàn nhưng kém nhạy — liên quan trực tiếp recall 48.9% |
| 4 | **Track PC — 4 protocol lâm sàng còn thiếu** | Chủ yếu lâm sàng | 4/5 nhóm MVP chưa tồn tại; chặn router, ranking và cả demo |
| 5 | **Sửa thứ tự `USER_CANNOT_CONTINUE` vs `RED_FLAG`** trong `should_stop` | Engineering nhỏ | Lỗi an toàn tiềm ẩn phát hiện trong bản đánh giá này (§5.2) |
| 6 | **User intent → `user_can_continue`** | Engineering | Gap thật duy nhất của V2 §23–36 |
| 7 | **Metric trải nghiệm** (`user_led_ratio`, `repeat_question_rate`, `mandatory_coverage_at_close`) | Engineering | Dữ liệu thô đã có trong `stage_log` + `CoverageLedger.snapshot`, chỉ thiếu script |
| 8 | **Chốt ADR-006** (giữ `HandoffSummary` hay chuyển ISBAR — template team đã có, xem §9) | PM + điều dưỡng | Chặn versioning schema; nhưng KHÔNG chặn 1–7 |
| 9 | Persist phiên đang dở | Engineering | Điều kiện tiên quyết của bất kỳ bàn luận memory nào |
| 10 | Multi-protocol đồng thời | Engineering | Chỉ có nghĩa sau khi #4 xong |

Bốn việc đầu **không phải việc engineering**. Đó là lý do sprint có thể trông như đang chạy mà vẫn
không nhích được gate an toàn.

### 7.3. Bất biến không được đánh đổi (áp cho mọi kế hoạch, kể cả V2 sửa lại)

1. Tầng ghi "KHÔNG model" không bao giờ được thay bằng lời gọi model: L0 text safety, controller,
   reducer, rule engine, output guard.
2. Không có đường nào để một lỗi model (timeout, JSON sai, route sai) làm mất red flag.
3. Mức ưu tiên do rule engine tất định quyết; LLM chỉ trích xuất và diễn đạt.
4. Văn bản safety-facing là template tĩnh đã duyệt.
5. Mọi stop có reason code ổn định; stop vì user intent phải đánh dấu phiếu incomplete.
6. Dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.
7. Natural summary và phiếu bàn giao đọc **cùng một** snapshot đã validate.

---

## 8. Điều kiện để V2 (bản sửa) được duyệt

Không phải 7 điều kiện như bản GPT. Chỉ 3, vì phần lớn công việc kia đã xong:

1. Viết lại phần hiện trạng có `file:line`, loại bỏ mọi mục đã tồn tại trong code — dự kiến tài liệu
   còn dưới 300 dòng.
2. Sửa §42–43: mức ưu tiên do rule engine sinh trong agent boundary, đúng FR-05 và
   `ARCHITECTURE.md:15-19`. Bỏ lập luận circular dependency.
3. Với 2 mục còn giá trị (multi-protocol, user intent): mỗi mục kèm bất biến, test case và metric —
   theo đúng mẫu §11/§12 của `what_to_do_next.md`.

Sau đó nó không còn là "kế hoạch V2" nữa, mà là hai issue nhập vào kế hoạch đang chạy. Đó là kết quả
đúng.

---

## 9. Phụ lục — Template ISBAR của team và đối chiếu với `HandoffSummary`

> Nguồn: slide *"Cấu trúc ISBAR chuẩn cho AI sinh ra phiếu tóm tắt [WHO]"* do team cung cấp
> (bổ sung vào bản đánh giá ngày 2026-08-19). Đây là **nguồn thật của ISBAR** mà §4.5 bản đầu
> nói là không tìm thấy trong repo.

### 9.1. Nguyên văn template

```text
Cấu trúc ISBAR chuẩn cho AI sinh ra phiếu tóm tắt  [WHO]

[I] Identify:
  - Patient: [Tuổi], [Giới tính]
  - Triage Category: [RED / YELLOW / GREEN]            ← đánh dấu đỏ trong slide

[S] Situation (Chief Complaint):
  - Lý do vào viện (1 câu ngắn gọn).
  - Ví dụ: "Bệnh nhân nam 45 tuổi khai báo đau ngực trái lan ra tay bắt đầu từ 1 giờ trước."

[B] Background (Relevant History):
  - Dị ứng: [Có/Không/Unknown]
  - Bệnh nền: [Liệt kê] (Chỉ hiển thị bệnh có liên quan nếu AI có khả năng lọc,
    nếu không liệt kê tất cả).
  - Thuốc đang dùng: [Liệt kê].

[A] Assessment (Structured Symptoms):
  - Onset: [Thời gian]
  - Severity: [Thang điểm/Mức độ]
  - Red Flags Detected: [Yes (Chi tiết) / None detected]
  - Missing Information: [VD: Bệnh nhân không có nhiệt kế để đo nhiệt độ chính xác].

[R] Recommendation / Action Taken:                      ← đánh dấu đỏ trong slide
  - AI Action: [Khuyên bệnh nhân đến bệnh viện ngay / Đặt lịch hẹn ngày mai].
  - Pending Action: [Chờ Nurse gọi lại xác nhận].
```

### 9.2. Đối chiếu với schema đang chạy

`HandoffSummary` (`src/models/schemas.py:138-149`) đã phủ được phần lớn template. Khoảng cách thật
nhỏ hơn nhiều so với ấn tượng "phải làm lại từ đầu":

| Khối ISBAR | Trường template | Trạng thái trong code | Ghi chú |
|---|---|---|---|
| [I] | Patient: Tuổi, Giới tính | **Thiếu** | `HandoffSummary` không có `age`/`sex`; hiện nằm ở tầng khác hoặc chưa thu thập |
| [I] | Triage Category RED/YELLOW/GREEN | **Đã có, khác tên** | `proposed_priority: TriagePriority` (`schemas.py:145`) — 3 mức *Cấp cứu / Khám sớm / Tự theo dõi* theo `CLAUDE.md`; RED/YELLOW/GREEN chỉ là nhãn hiển thị |
| [S] | Chief complaint 1 câu | **Đã có** | `chief_complaint` |
| [B] | Dị ứng Có/Không/Unknown | **Thiếu trường riêng** | Ba giá trị này trùng đúng semantics 3-value của `reducer` — không cần kiểu mới |
| [B] | Bệnh nền | **Thiếu** | Xem cảnh báo §9.3 mục 2 |
| [B] | Thuốc đang dùng | **Thiếu** | |
| [A] | Onset | **Đã có** | `onset` |
| [A] | Severity | **Đã có** | `severity: str \| int \| None` |
| [A] | Red Flags Detected | **Đã có, giàu hơn** | `red_flags: list[RedFlagFinding]` — có mã và bằng chứng, không chỉ Yes/None |
| [A] | Missing Information | **Đã có** | `missing_information: list[str]` — đúng cái bản GPT gọi là `data_gaps` |
| [A] | (không có trong template) | Code có thêm | `protocol_reason`, `detect_source`, `grounding_source` — nên **giữ**, đây là dấu vết truy nguyên |
| [R] | AI Action | **Không có, và không nên có ở boundary agent** | Xem §9.3 mục 1 |
| [R] | Pending Action | **Đã có ở tầng khác** | `CaseStatus` / `approval_status` trong `NurseQueueItem` — là trạng thái workflow, không phải nội dung phiếu |

Tổng kết: **7/13 trường đã có, 4 trường thiếu là dữ liệu hành chính/tiền sử đơn giản, 2 trường cần
quyết định lâm sàng.** Đây là công việc bổ sung field, không phải migrate kiến trúc — ngược với ấn
tượng mà V2 §40–43 tạo ra.

### 9.3. Hai điểm trong template cần chốt lại trước khi đưa vào schema

**1. `[R] AI Action` viết như hành động đã thực hiện — đụng nguyên tắc HITL.**

Template ghi `AI Action: [Khuyên bệnh nhân đến bệnh viện ngay / Đặt lịch hẹn ngày mai]`. Đọc theo mặt
chữ thì AI đã *khuyên bệnh nhân* trước khi điều dưỡng duyệt. `CLAUDE.md` nguyên tắc 1: "không có đường
nào gửi hướng xử trí cho bệnh nhân mà bỏ qua bước duyệt".

Nhiều khả năng ý định của người viết là "hành động **được đề xuất**", không phải "hành động **đã làm**".
Nhưng đây là phiếu định nghĩa hợp đồng dữ liệu — chữ nào vào schema thì tầng dưới đọc đúng chữ đó. Đề
xuất sửa tên trường ngay trong template:

```text
[R] Recommendation (Proposed — chưa có hiệu lực cho tới khi điều dưỡng duyệt):
  - Proposed Action: [...]        (do rule engine sinh, không do LLM diễn đạt lại)
  - Approval Status: [pending_nurse_review | approved | modified]
```

Lưu ý ngoại lệ đã chốt: red flag **được** escalate ngay không chờ duyệt (`CLAUDE.md` nguyên tắc 4), và
văn bản đó là `EMERGENCY_MESSAGE` — hằng số tĩnh, không đi qua LLM
(`common_safety/emergency_message.py:1-6`). Nên `[R]` cho ca cấp cứu không phải do model sinh.

**2. `Bệnh nền: chỉ hiển thị bệnh có liên quan nếu AI có khả năng lọc` — giao phán đoán y khoa cho LLM.**

"Bệnh nào liên quan tới triệu chứng hiện tại" là một phán đoán lâm sàng. Để LLM lọc thì nó có thể loại
bỏ một bệnh nền quan trọng khỏi phiếu, và điều dưỡng không có cách nào biết cái gì đã bị giấu — đây là
lỗi im lặng, loại nguy hiểm nhất. Nó cũng đi ngược `CLAUDE.md` nguyên tắc 3 (grounded, chống bịa).

Đề xuất cho MVP: **liệt kê tất cả, không lọc.** Nếu muốn ưu tiên hiển thị thì làm bằng danh sách
liên quan tĩnh gắn theo protocol (do lâm sàng ký duyệt, giống `SHORT_CIRCUIT_CODES`), và **luôn kèm nút
"xem đầy đủ"** — sắp xếp lại thì được, giấu đi thì không.

**3. Về `Triage Category` trong `[I]` — template đúng, V2 §42 sai.**

V2 bỏ trường này với lý do circular dependency. Template của team giữ nó, và template đúng: mức ưu tiên
do `rule_engine.evaluate()` (`rule_engine.py:27`) sinh ra từ snapshot, song song với summary chứ không
phụ thuộc summary. Xem lập luận đầy đủ ở §4.1. Việc cần làm chỉ là ghi rõ trong template rằng trường
này **do code tất định điền, không do LLM**.

### 9.4. Việc phát sinh cho ADR-006

Template này biến ADR-006 từ "thiết kế format từ đầu" thành "chốt 5 câu hỏi", nhẹ hơn nhiều:

1. Giữ cấu trúc phẳng `HandoffSummary` và map ISBAR ở tầng render, hay đổi schema thành lồng theo
   I/S/B/A/R? — **Khuyến nghị: giữ phẳng, map khi render.** Rẻ hơn, không đụng `NurseQueueItem`, và
   `HandoffSummary` vẫn là một snapshot duy nhất cho cả summary lẫn triage (bất biến §7.3 mục 7).
2. Bổ sung 4 trường còn thiếu: `age`, `sex`, `allergies`, `comorbidities`, `current_medications`.
   Allergies dùng đúng 3-value hiện có, không thêm kiểu mới.
3. Chốt lại `[R]` theo §9.3 mục 1 (đổi tên thành *proposed* + `approval_status`).
4. Chốt `Bệnh nền` là liệt kê đầy đủ (§9.3 mục 2).
5. Nhãn hiển thị: RED/YELLOW/GREEN hay *Cấp cứu / Khám sớm / Tự theo dõi*? `CLAUDE.md` và UI đang
   dùng tiếng Việt; nếu phiếu cho điều dưỡng dùng màu WHO thì phải là **nhãn hiển thị**, còn giá trị
   lưu trong `TriagePriority` giữ nguyên.

Cả 5 câu hỏi này là quyết định của PM + điều dưỡng, và vẫn **không chặn** các việc 1–7 ở §7.2.

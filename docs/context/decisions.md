# Decisions Log (ADR-style) — VMedTriage

> Log các quyết định quan trọng của dự án theo phong cách Architecture Decision Record (ADR). Mỗi entry: bối cảnh → quyết định → phương án khác đã xem xét → hệ quả. Thêm entry mới ở cuối file, không sửa/xoá entry cũ — nếu quyết định thay đổi, tạo entry mới ghi rõ "Supersedes ADR-xxx".

---

## ADR-001: Phân loại ưu tiên theo 3 mức, không dùng thang 5 mức

- **Ngày:** 01/08/2026 · **Trạng thái:** Đã chốt (PRD v1.0)
- **Bối cảnh:** Brief ban đầu để ngỏ câu hỏi nên dùng thang 3 mức hay 5 mức theo hướng dẫn Bộ Y tế VN.
- **Quyết định:** Dùng 3 mức — Cấp cứu / Khám sớm / Tự theo dõi.
- **Phương án khác:** Thang 5 mức kiểu ESI (quốc tế) — không chọn vì brief yêu cầu rõ 3 mức để giữ MVP đơn giản, giảm độ phức tạp khi đo đồng thuận AI–điều dưỡng.
- **Hệ quả:** Mọi checklist, rule red-flag, UI (queue-row màu đỏ/vàng/xanh) đều thiết kế quanh 3 mức này.

## ADR-002: HITL bắt buộc 100%, không auto-approve theo mức độ

- **Ngày:** 04/08/2026 · **Trạng thái:** Đã chốt
- **Bối cảnh:** Cân nhắc tự động duyệt các ca mức "Tự theo dõi" (thấp nhất) để giảm tải điều dưỡng.
- **Quyết định:** Không auto-approve bất kỳ mức nào — mọi ca đều phải qua xác nhận của nhân viên y tế trước khi gửi kết quả.
- **Phương án khác:** Auto-approve mức "Tự theo dõi" — bị loại vì brief yêu cầu HITL 100%, không có ngoại lệ theo mức độ ưu tiên; rủi ro AI đánh giá sai mức thấp trong khi thực tế nghiêm trọng hơn.
- **Hệ quả:** Feature #2 (Hàng đợi & Duyệt ca) thiết kế API `/approve` bắt buộc cho mọi case, không có route bypass. Chỉ số 0% thông báo gửi chưa duyệt được đo bằng audit log.

## ADR-003: Agent hỏi theo checklist cố định, không cho phép hỏi tự do

- **Ngày:** 04/08/2026 · **Trạng thái:** Đã chốt
- **Bối cảnh:** Cân nhắc để agent tự do đặt câu hỏi dựa trên ngữ cảnh thay vì bám checklist cứng.
- **Quyết định:** Agent chỉ được hỏi trong phạm vi checklist cố định theo từng nhóm triệu chứng, có guard rail chặn câu hỏi ngoài phạm vi.
- **Phương án khác:** Agent hỏi tự do (open-ended) — bị loại vì rủi ro hỏi lan man, khó kiểm soát an toàn y tế, dễ hallucination và khó đo tỷ lệ thu thập đủ trường (≥90%).
- **Hệ quả:** Feature #1 (Agent) implement state machine dựa trên checklist, không dùng agent hoàn toàn tự do.

## ADR-004: Banner khẩn cấp hiển thị ngay cho bệnh nhân, không chờ duyệt

- **Ngày:** 04/08/2026 · **Trạng thái:** ⛔ **SUPERSEDED bởi ADR-008 (19/08/2026)** — phần "hiển thị ngay, không chờ duyệt" được GIỮ; phần "khẳng định cấp cứu" bị thay bằng "nêu nghi ngờ"
- **Bối cảnh:** Xung đột giữa nguyên tắc HITL (ADR-002) và nhu cầu cảnh báo tức thời khi có red-flag.
- **Quyết định:** Banner khẩn cấp (W-04) hiển thị ngay cho bệnh nhân khi phát hiện red-flag, **không chờ** nhân viên y tế duyệt — đây là ngoại lệ có chủ đích của ADR-002.
- **Phương án khác:** Để bệnh nhân chờ chung với luồng duyệt bình thường như mọi ca khác — bị loại vì an toàn tức thời (khuyến cáo gọi 115) quan trọng hơn việc chờ xác nhận nội dung chi tiết.
- **Hệ quả:** Ca vẫn bắt buộc vào hàng đợi để được xác nhận tiếp ở W-07; cảnh báo tự động không thay thế xác nhận của con người, chỉ là cảnh báo bổ sung.

## ADR-005: Hàng đợi dùng polling, không dùng realtime WebSocket cho MVP

- **Ngày:** 01/08/2026 · **Trạng thái:** Đã chốt (PRD v1.0)
- **Bối cảnh:** Cân nhắc giữa polling đơn giản và WebSocket realtime cho màn hình hàng đợi của nhân viên y tế.
- **Quyết định:** Dùng polling cho MVP.
- **Phương án khác:** Realtime WebSocket — bị loại, đưa vào "Out of scope" để giảm độ phức tạp kỹ thuật trong 6 tuần, ưu tiên nguồn lực cho phần Agent/HITL.
- **Hệ quả:** API `/queue` thiết kế dạng REST polling định kỳ, không cần hạ tầng WebSocket.

## ADR-006: Phiếu tóm tắt giữ schema PHẲNG, ISBAR map ở tầng render; hai output song song

- **Ngày:** 19/08/2026 · **Trạng thái:** Đã chốt
- **Bối cảnh:** `HandoffSummary` (`src/models/schemas.py`) đã chạy và UI W-07 đã dựng theo nó, trong khi team có một template ISBAR chuẩn (WHO). Đối chiếu: 7/13 trường đã có, 4 trường thiếu là dữ liệu hành chính/tiền sử đơn giản, 2 trường cần quyết định. Tức là **bổ sung field, không phải migrate kiến trúc**.
- **Quyết định:**
  1. **Giữ `HandoffSummary` PHẲNG.** Việc nhóm thành 5 khối I/S/B/A/R xảy ra ở **renderer**, không ở schema lưu trữ. Không đụng `NurseQueueItem`, không đụng UI đang chạy.
  2. **Hai output song song, đọc CÙNG MỘT snapshot đã validate** — đây là điều kiện duy nhất khiến chúng không mâu thuẫn nhau:
     - `summary_text` — văn xuôi do LLM viết lại, dùng để **lưu DB và làm memory** về sau;
     - `summary_json` — `HandoffSummary` phẳng, renderer map sang **bảng ISBAR** cho điều dưỡng.
  3. Bổ sung 5 trường còn thiếu: `age`, `sex`, `allergies`, `comorbidities`, `current_medications`. Dị ứng dùng đúng semantics 3 giá trị (`true`/`false`/`unknown`) của reducer, **không thêm kiểu mới**.
  4. Khối `[R]` của template viết như hành động đã thực hiện (*"AI Action: Khuyên bệnh nhân đến bệnh viện ngay"*) — đọc theo mặt chữ thì AI đã khuyên bệnh nhân trước khi điều dưỡng duyệt, ngược `CLAUDE.md` nguyên tắc 1. **Đổi thành `proposed_action` + `approval_status`.**
  5. **Bệnh nền: liệt kê TẤT CẢ.** Template gợi ý "chỉ hiển thị bệnh có liên quan nếu AI có khả năng lọc" — đó là giao một phán đoán lâm sàng cho LLM, và lọc sai thì điều dưỡng không có cách nào biết cái gì đã bị giấu (lỗi im lặng, ngược nguyên tắc 3). Sắp xếp lại thì được; giấu đi thì không.
- **Phương án khác:** Đổi schema thành lồng I/S/B/A/R — bị loại: đắt hơn, kéo theo `NurseQueueItem` và UI W-07, và không được thêm gì mà tầng render không làm được.
- **Hệ quả:** `Triage Category` nằm trong khối `[I]` của bảng nhưng **do code tất định điền, không do LLM** — phải ghi rõ điều đó trong chính template, vì đó là chỗ dễ bị hiểu nhầm nhất. Quy tắc render: trường rỗng **không xuất**, nhưng **snapshot giữ đủ ba giá trị** (lọc ở renderer, không ở nguồn); **ngoại lệ — field an toàn luôn được render** kể cả khi `false`/`unknown`.

## ADR-008: Hệ thống nêu NGHI NGỜ red-flag, không khẳng định cấp cứu — supersede ADR-004

> ⚠️ **Lưu ý đánh số:** `_guidance/what_to_do_next.md` §4.12 gọi quyết định này là "ADR-007". Số 007
> đã bị entry "Lựa chọn LLM provider" (đang pending) chiếm từ 03/08/2026, nên nó nhận số **008**.
> Khi đọc §4.12 hãy hiểu "ADR-007" ở đó = ADR-008 ở đây.

- **Ngày:** 19/08/2026 · **Trạng thái:** Đã chốt — **supersede ADR-004**
- **Bối cảnh:** Xung đột giữa ADR-004 (banner khẳng định cấp cứu, hiển thị ngay) và Feature Spec :253-256 (hệ thống không được tự khẳng định kết luận lâm sàng chưa qua người). Chọn một bên thì bên kia vẫn đúng.
- **Quyết định:** Hệ thống **không khẳng định cấp cứu**. Nó nêu **nghi ngờ**, đẩy ca lên ưu tiên cao nhất, và điều dưỡng — trực **24/7** — mới là người kết luận. Đây là nguyên tắc y tế chuẩn: *công cụ sàng lọc nêu nghi ngờ, lâm sàng viên kết luận.* Ba thông điệp TĨNH, ba thời điểm, ba người nói (`common_safety/emergency_message.py`):

  | Câu | Ai "nói" | Khi nào |
  | --- | --- | --- |
  | `SUSPECTED_RED_FLAG_MESSAGE` | hệ thống | t=0, ngay lượt phát hiện |
  | `SLA_BREACH_MESSAGE` | hệ thống | quá SLA mà chưa điều dưỡng nào **mở** ca |
  | `EMERGENCY_MESSAGE` | **điều dưỡng** | SAU khi duyệt — mặc định cho `approved_response` |

- **Vì sao nó giải được xung đột thay vì chọn một bên:** nó thoả mãn lo ngại *thật* của cả hai tài liệu. Feature Spec sợ hệ thống tự khẳng định → không còn khẳng định nào. ADR-004 sợ bệnh nhân bị bỏ mặc chờ → trực 24/7 **cộng** một lưới an toàn phổ quát ngay từ t=0 (*"nếu bạn thấy tình trạng xấu đi, hãy gọi 115 ngay — đừng chờ phản hồi ở đây"*), câu này đúng với mọi người bệnh trong mọi tình huống nên nói ra không phải là chẩn đoán.
- **SLA = 5 phút (chốt tạm)**, tính từ lúc ca vào hàng đợi tới lúc một điều dưỡng **MỞ** ca (không phải tới lúc duyệt xong). Cảnh báo nội bộ ở 60% (3 phút). Cấu hình ở `sessions/red_flag_sla.py`. **Đây là câu hỏi cho PM và người tổ chức ca trực, không phải cho engineering** — nhưng nó phải có một giá trị, vì thiếu nó thì `SLA_BREACH_MESSAGE` không bao giờ bắn và cam kết 24/7 chỉ có trên giấy.
- **Cảnh báo khi hiệu chỉnh về sau:** `SLA_clinical` (được phép chờ bao lâu, suy từ nhu cầu lâm sàng) và `p99_observed` (đang đáp ứng bao lâu, suy từ đo) là **hai số, không phải một**. Đặt `SLA = p99` thì `sla_breach_rate` luôn ≈ 1% theo đúng định nghĩa, và SLA thôi không còn là yêu cầu an toàn — nó trở thành bản mô tả năng lực hiện tại. `p99_observed > SLA_clinical` là **vấn đề nhân sự**, không phải vấn đề cấu hình.
- **Phạm vi — thứ KHÔNG đổi:** `triage_level = "EMERGENCY"` giữ nguyên. Rule engine, `escalation_lock`, thứ tự hàng đợi, mọi luật an toàn không đổi. Đây thuần tuý là thay đổi **tầng ngôn ngữ và tầng hiển thị** — đó cũng là lý do nó làm được trong một sprint ngắn.
- **Hệ quả:** `SymptomProtocol.emergency_message` đổi tên thành `patient_red_flag_message` (tên cũ đã thành một lời nói dối: nội dung không còn khẳng định cấp cứu). Chỉ số theo dõi từ ngày đầu: `sla_breach_rate`, **phải gần 0** — không gần 0 thì cam kết trực 24/7 chỉ có trên giấy và lập luận an toàn của quyết định này sụp.

## ADR-007 (pending): Lựa chọn LLM provider

- **Ngày:** _chưa chốt_ · **Trạng thái:** ⏳ Đang chờ (task T-007, deadline 03/08/2026)
- **Bối cảnh:** Cần chọn provider LLM thật để tích hợp Agent, dựa trên chi phí, latency, khả năng xuất structured output.
- **Quyết định:** _TBD — cập nhật entry này thành ADR chính thức ngay khi Tuấn Anh chốt provider.
- **Hệ quả tạm thời:** Mọi phần thiết kế liên quan LLM trong Feature Spec ghi "chốt ở Sprint 2" thay vì tên provider cụ thể.

## ADR-009: C6 safety gate chỉ nâng priority sau rule-engine, giữ HITL 100%

- **Ngày:** 21/08/2026 · **Trạng thái:** Thử nghiệm có feature flag, mặc định tắt
- **Bối cảnh:** Benchmark Semigran 45 ca cho C6 (GPT direct OR Fusion OR documented-rule emergency)
  đạt emergency recall 100% (15/15), đổi lại accuracy 66.67% và có over-triage. Runtime thực tế đã
  dùng `symptom_protocol.rule_engine` để phát hiện red flag và xếp hàng đợi đồng bộ, nhưng Part 2
  trước đây chỉ là ý kiến tham khảo và còn bị bỏ qua với case `ESCALATED`.
- **Quyết định:** Giữ rule engine là sàn priority tức thời. Khi
  `graph_triage_mode="c6"`, mọi case đã chốt được chạy C6 với GPT direct, Fusion và documented-rule;
  C6 không nạp LogReg, PhoBERT độc lập hay LLM quyết định tổng của ensemble. Với case `ESCALATED`, C6
  chạy nền sau khi case đã được lưu và phản hồi an toàn đã được gửi. C6 chỉ được nâng priority, không
  được hạ priority, sửa red flag, tự duyệt, hay gửi nội dung cho bệnh nhân. Case đã `APPROVED` không
  bị sửa bởi một kết quả C6 đến muộn.
- **Hệ quả:** C6 có audit source khi nâng priority, rồi chuyển nhãn hiệu lực cuối cùng
  (`max(rule-engine, C6)`) cùng evidence đã kiểm sang Part 3 để trích nguồn y văn (nếu
  `source_support_enabled=true`); mọi kết luận vẫn phải được điều dưỡng duyệt.
  C6 là một candidate safety gate, chưa là bằng chứng triển khai: benchmark dùng vignette có phân
  phối khác phiếu tóm tắt production, cần hold-out độc lập và review lâm sàng trước rollout.
- **Ghi chú phạm vi:** `ProtocolTriageEngine`, `RedFlagSafetyLayer`, và `TriagePipeline` được nhắc
  trong một số tài liệu cũ không phải nguồn priority của luồng `/chat` hiện tại. Việc dọn dead code
  được tách thành công việc riêng, không nằm trong ADR này.

## ADR-010: Gợi ý bệnh viện gần nhất — adapter 3 nhà cung cấp, và một ngoại lệ có phạm vi hẹp với ADR-002

- **Ngày:** 25/08/2026 · **Trạng thái:** Đã chốt (tính năng mới, ngoài phạm vi `docs/brief.md`/`docs/prd.md` gốc — xem lưu ý bên dưới)
- **Bối cảnh:** Bệnh nhân chỉ nhận được khuyến cáo dạng văn bản tĩnh ("đến cơ sở y tế gần nhất",
  `docs/prd.md:38`), không có địa điểm cụ thể. Cần tích hợp một API địa điểm bên thứ 3 để tìm bệnh
  viện gần vị trí bệnh nhân. Đây là tính năng hoàn toàn mới, không nằm trong đặc tả MVP gốc — brief
  đã liệt kê "Scope creep" là rủi ro Cao/Cao (mục 8); tính năng này nên được PM/mentor biết trước khi
  merge lên nhánh chính, dù không bị chặn ở bước lập kế hoạch.
- **Quyết định 1 — nhà cung cấp:** Adapter chung (`src/services/hospital_lookup/`), 3 implementation
  cùng chữ ký hàm (`goong.py`, `google_maps.py`, `openstreetmap.py`), chọn qua
  `Settings.hospital_lookup_provider` (mặc định `"goong"`). Lý do không chốt cứng một nhà cung cấp:
  Goong (free 1.000 request/ngày, không cần thẻ quốc tế, dữ liệu địa chỉ VN tốt, nhưng KHÔNG có
  nearby-search theo category nên phải tự ghép `Place/AutoComplete` + `Place/Detail`, tức 1 lượt tốn
  1+N request) và Google Maps Platform (có `type=hospital` thật, 1 request/lượt, nhưng cần bật billing
  bằng thẻ quốc tế) mỗi bên có đánh đổi riêng; OpenStreetMap (Nominatim + Overpass, miễn phí tuyệt
  đối nhưng server công cộng giới hạn 1 request/giây và ToS cấm dùng production quy mô lớn) là
  phương án dự phòng khi hết free tier hai bên kia. Đổi nhà cung cấp là đổi một biến môi trường,
  không sửa router/DB/frontend.
- **Quyết định 2 (nhạy cảm, đọc kỹ trước khi áp dụng cho tính năng khác) — không có bước duyệt của
  điều dưỡng:** Gợi ý bệnh viện hiển thị **trực tiếp cho bệnh nhân** ngay sau khi tra cứu — route
  `/cases/{case_id}/hospital-suggestions` chỉ có role `PATIENT`, không có role `NURSE`, không có
  endpoint duyệt. Đây là **ngoại lệ có phạm vi hẹp** với ADR-002 (HITL bắt buộc 100%), lý lẽ: danh
  sách bệnh viện là **thông tin logistics** (tên/địa chỉ/khoảng cách/SĐT lấy nguyên văn từ nhà cung
  cấp bản đồ), không phải **đề xuất xử trí lâm sàng** mà CLAUDE.md nguyên tắc 1 nói tới — cùng tinh
  thần với ngoại lệ đã có cho banner red-flag (ADR-004/008, nơi an toàn tức thời được ưu tiên hơn chờ
  duyệt). **Ngoại lệ này CHỈ áp dụng cho chính tính năng gợi ý bệnh viện** — không phải tiền lệ để bất
  kỳ output nào khác của Agent (checklist, red-flag, mức ưu tiên, hướng dẫn xử trí) bỏ qua HITL.
- **Phương án khác đã xem xét:**
  - Google Maps Platform làm nhà cung cấp duy nhất — bị loại vì rào cản thẻ billing quốc tế cho một
    sản phẩm MVP tiếng Việt; giữ làm một trong 3 lựa chọn trong adapter thay vì loại hẳn.
  - Gợi ý bệnh viện vẫn qua màn hình duyệt của điều dưỡng như luồng triage chính (tái dùng
    `hitl_review.py`/`nurse_triage_decisions`) — bị loại: đây là track duyệt độc lập về thời điểm
    (bệnh nhân có thể xin gợi ý bất kỳ lúc nào, kể cả sau khi case chính đã `approved`) và độc lập về
    nội dung (không đụng `TriageCase.status`/`priority`); nhét chung sẽ phình `NurseReviewRequest` và
    trộn hai audit domain khác nhau.
- **Hệ quả:** Bảng cache `hospital_suggestions` (`src/models/hospital_suggestion.py`, FK vào
  `triage_cases.case_id`, không có cột trạng thái duyệt) chỉ đóng vai trò cache + audit trail (tái
  dùng `audit_log` chung qua action `hospital_suggestion_requested`, không tạo bảng audit riêng).
  Route mới bắt buộc khai báo trong `src/middleware/auth.py::ROUTE_POLICIES` (middleware đó fail-open
  — thiếu dòng khai báo nghĩa là route mở public không cần token). Thiếu cấu hình nhà cung cấp đang
  chọn (API key/contact email) → tính năng tự tắt (`ProviderNotConfiguredError` → HTTP 503), không
  crash luồng triage chính, đúng nguyên tắc best-effort toàn repo (xem `src/source_support/`). Vị trí
  bệnh nhân lấy qua GPS trình duyệt (HTML5 Geolocation), fallback nhập địa chỉ text khi từ chối quyền/
  không hỗ trợ — geocode qua chính nhà cung cấp đang chọn.

## ADR-011: Rule engine chỉ là sàn cho cấp cứu, không còn là sàn cho khám sớm/tự theo dõi — thu hẹp phạm vi ADR-009

- **Ngày:** 27/08/2026 · **Trạng thái:** Đã chốt (thu hẹp phạm vi phần "không hạ priority" của ADR-009)
- **Bối cảnh:** ADR-009 đặt quy tắc `max(rule-engine, C6)` cho CẢ BA mức, với lý do C6 benchmark chỉ
  đạt accuracy 66.67% nên không đủ tin cậy để tự quyết định một mình. Đo thêm ngày 27/08/2026
  (`eval/scripts/eval_rule_plus_c6.py`, 45 ca Semigran, dùng nhánh `documented_rule` của C6 làm rule
  engine độc lập vì rule engine thật của `symptom_protocol` cần structured checklist answers mà
  Semigran - văn bản tự do - không có) cho thấy quy tắc `max()` áp dụng ngoài phạm vi cấp cứu làm
  ĐỘ CHÍNH XÁC GIẢM chứ không tăng: C6-only 65.0% (26/40) > rule-only 57.5% (23/40) >
  combined-max 50.0% (20/40). Toàn bộ 6 ca combine sai đều là rule kéo nhầm một ca C6 đã đúng
  ("tự theo dõi") lên "khám sớm"; rule chưa từng cứu được ca nào mà C6 sai một mình (0/40). Xem
  `result_model/eval_rule_plus_c6.txt` và `.jsonl` cho chi tiết từng ca.
- **Quyết định:** Sửa `_effective_c6_label` (`src/graph_triage/service.py`): rule engine
  (`symptom_protocol.rule_engine`, chạy đồng bộ khi phiếu tóm tắt chốt) chỉ còn là sàn khi nó đã chốt
  `EMERGENCY` — C6 không được phép hạ xuống dưới cấp cứu trong trường hợp đó, giữ nguyên đúng tinh
  thần ADR-009/nguyên tắc 4 CLAUDE.md (escalate ngay, không chờ). Khi rule engine KHÔNG chốt cấp cứu,
  việc chọn "khám sớm" hay "tự theo dõi" hoàn toàn do C6 quyết định — kể cả khi kết quả thấp hơn đề
  xuất tạm thời của rule engine. Không đổi gì ở phần cấp cứu: mọi nhánh escalate-ngay (Guard đỏ,
  `_apply_c6_safety_gate`, thông điệp tĩnh cho bệnh nhân) giữ nguyên.
- **Hệ quả:** `PRIORITY_RANK`/`c6_label_for_priority` không còn dùng trong so sánh này (gỡ khỏi
  import của `service.py`, hàm `c6_label_for_priority` vẫn giữ lại ở `priority_labels.py` vì là tiện
  ích dùng chung, không phải dead code bắt buộc xoá). Cảnh báo phạm vi số liệu: nhánh `documented_rule`
  dùng để đóng vai "rule engine" trong phép đo này KHÔNG tái lập được (đã ghi nhận trước đó - chạy 3
  lần ra 3 kết quả khác nhau) và không phải rule engine thật của production (rule engine thật đọc
  structured checklist, không qua tầng LLM trích fact) — số đo dùng để chọn hướng thiết kế, không phải
  bằng chứng accuracy cuối cùng của rule engine thật trên production.

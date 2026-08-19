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

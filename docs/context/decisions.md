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

- **Ngày:** 04/08/2026 · **Trạng thái:** Đã chốt (add-on, đã đưa vào MVP)
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

## ADR-006: Định nghĩa format phiếu tóm tắt (nghiệp vụ) phải chốt trước khi viết schema JSON (kỹ thuật)

- **Ngày:**  _chưa chốt_ · **Trạng thái:** 
- **Bối cảnh:** 
- **Quyết định:** 
- **Phương án khác:** 
- **Hệ quả:**

## ADR-007 (pending): Lựa chọn LLM provider

- **Ngày:** _chưa chốt_ · **Trạng thái:** ⏳ Đang chờ (task T-007, deadline 03/08/2026)
- **Bối cảnh:** Cần chọn provider LLM thật để tích hợp Agent, dựa trên chi phí, latency, khả năng xuất structured output.
- **Quyết định:** _TBD — cập nhật entry này thành ADR chính thức ngay khi Tuấn Anh chốt provider.
- **Hệ quả tạm thời:** Mọi phần thiết kế liên quan LLM trong Feature Spec ghi "chốt ở Sprint 2" thay vì tên provider cụ thể.

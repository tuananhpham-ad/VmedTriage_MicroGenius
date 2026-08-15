# Project Brief — VMedTriage

**Team:** MicroGenius
**Phiên bản:** 1.0 
**Người soạn :** Nguyễn Thị Thương
**Ngày khởi tạo :** 31/07/2026

## 1. Bối cảnh & vấn đề
Nhân viên y tế mất nhiều thời gian khai thác triệu chứng và phân loại mức độ khẩn cấp ban đầu (cấp cứu / khám sớm / tự theo dõi) khi tiếp nhận tư vấn online, đặc biệt trong giờ cao điểm. Việc phân loại thủ công dẫn đến kết quả không đồng nhất giữa các lần tư vấn hoặc giữa các điều dưỡng khác nhau.

## 2. Giải pháp đề xuất
AI Agent hỗ trợ thu thập triệu chứng theo kịch bản có cấu trúc (hỏi-đáp dựa trên checklist cố định, không hỏi ngoài phạm vi), phát hiện dấu hiệu cảnh báo (red-flag), phân loại mức độ ưu tiên dưới dạng **đề xuất** (không phải kết luận) và tạo phiếu tóm tắt để điều dưỡng xác nhận trước khi bất kỳ hướng xử trí nào được gửi tới bệnh nhân.

## 3. Mục tiêu
### Mục tiêu SMART (theo Milestones: 6 tuần, W1–W6)
- Xây dựng AI Agent hỗ trợ tối thiểu **5 nhóm triệu chứng** phổ biến, tỷ lệ thu thập đầy đủ **≥90%** các trường thông tin theo checklist.
- Thời gian trung bình từ khi bệnh nhân bắt đầu khai báo đến khi có hướng dẫn xử trí ban đầu **< 3 phút** (đo trên 100 ca thử nghiệm).
- Mức đồng thuận **≥80%** giữa AI và điều dưỡng trong phân loại mức độ ưu tiên (đo trên tập test tách riêng).
- **100%** ca có dấu hiệu red-flag trong bộ test case red-flag được phát hiện và escalate đúng — không bỏ sót.
- **0%** thông báo hướng xử trí được gửi đến bệnh nhân mà chưa qua xác nhận của nhân viên y tế (kiểm chứng bằng audit log).

## 4. Đối tượng người dùng
- **Bệnh nhân**: người dùng khai báo triệu chứng qua giao diện hội thoại có cấu trúc, nhận hướng dẫn xử trí (sau khi đã được điều dưỡng duyệt).
- **Nhân viên y tế (điều dưỡng)**: xem hàng đợi ca chờ duyệt, xem phiếu tóm tắt tự động, duyệt/chỉnh sửa/ghi đè mức ưu tiên AI đề xuất, escalate thủ công khi cần.

## 5. Phạm vi (Scope)

### Trong phạm vi (MVP)
- **Core Agent**: AI Agent hội thoại tự do (free-text) phát hiện triệu chứng, triệu chứng liên quan & Red-flag; triage cho 5 nhóm triệu chứng (Sốt, Đau bụng, Đau ngực, Khó thở, Đau đầu/Chấn thương đầu nhẹ)
- **Nhân viên y tế**: hàng đợi ca chờ duyệt (polling, chưa cần realtime); phiếu tóm tắt triệu chứng tự động; duyệt/chỉnh sửa/ghi đè mức ưu tiên; escalate thủ công
- **Bệnh nhân**: giao diện khai báo triệu chứng dạng hội thoại; disclaimer & giới hạn hệ thống hiển thị cố định
- **Hệ thống**: web app responsive, 2 role (nhân viên y tế + bệnh nhân), auth cơ bản; flag "đã duyệt/chưa duyệt" trong DB trước khi gửi cho bệnh nhân; bộ 100 ca thử nghiệm để đánh giá

### Add-on (nếu đủ nguồn lực)
- Banner cảnh báo khẩn cấp tức thời khi phát hiện red-flag 
- Log audit: ai duyệt, lúc nào, thay đổi gì so với đề xuất AI
- Mã hoá/ẩn danh cơ bản dữ liệu PII trong lưu trữ và log

### Ngoài phạm vi 
- AI Agent dự đoán/kết luận bệnh cụ thể
- Tính năng đặt lịch khám
- Đa kênh (voice/hình ảnh)
- Mở rộng thêm các nhóm triệu chứng phức tạp ngoài 5 nhóm MVP
- Realtime WebSocket, giải thích lý do phân loại có trích dẫn guideline

## 6. Ràng buộc bắt buộc 
- **HITL bắt buộc**: kết quả triage là ĐỀ XUẤT; điều dưỡng/bác sĩ phải phê duyệt trước khi thông báo hướng xử trí được gửi tới bệnh nhân
- AI **tuyệt đối không** kết luận chẩn đoán bệnh cụ thể
- Grounded trên protocol triage chuẩn, chống bịa (no hallucination), luôn ưu tiên an toàn
- Nghi ngờ red-flag (đau ngực, khó thở, dấu hiệu đột quỵ nặng, chảy máu nặng, co giật) → escalate cấp cứu ngay, cảnh báo rõ ràng
- Bảo mật PII/PHI
- Hiển thị rõ giới hạn hệ thống & khuyến cáo gặp nhân viên y tế
- Nền tảng MVP: **Web app (responsive)**
- Phân loại ưu tiên: **3 mức** — Cấp cứu / Khám sớm / Tự theo dõi

## 7. Nguồn lực & Timeline
- 4 người x 30 giờ/tuần = 120 giờ/tuần
- Timeline: 6 tuần
- Công cụ: GitHub, Discord, Google Drive; Claude/Codex (team tự chi trả)

| Cột mốc | Tuần | Ngày dự kiến | Sản phẩm nộp | Người chịu trách nhiệm |
|---|---|---|---|---|
| Kickoff & Project Charter	| W1 | 29/07-02/08	| Project Charter + Quy chế	| Nguyễn Thị Thương |
| Đề xuất giải pháp 	| W2 |	03-09/08 | Solution Design + Architecture | Phạm Tuấn Anh |
| Demo 1 với đối tác	 | W3 | 10-16/08 | Bản Demo 1 + Phản hồi từ đối tác/ khảo sát | Team |
| Hoàn thiện sản phẩm | W4-W5 | 17-23/08 | Sản phẩm hoàn thiện + Deploy	| Team |
| Demo 2 với đối tác | W5 | 24-30/08 | Bản Demo 2 + Đánh giá hài lòng | Team |
| Đánh giá cuối kỳ | W6	| 31/08-05/09 | Báo cáo tác động + Slide thuyết trình | Phạm Tuấn Anh |

## 8. Rủi ro chính
| Rủi ro | Xác suất | Tác động | Xử lý |
|---|---|---|---|
| Không thu thập được bộ test case đo đồng thuận AI-điều dưỡng | Cao | Cao | Xác định đối tác sớm, raise với mentor |
| Scope creep | Cao | Cao | Giữ đúng phạm vi đã chốt, mọi thay đổi thảo luận với mentor trước |
| Thiếu hụt kỹ thuật AI/ML/DevOps | Trung bình | Trung bình | Dùng API thay tự build, nhờ mentor hướng dẫn |
| Thành viên vắng mặt/không hoàn thành việc | Thấp | Cao | Phân việc rõ ràng, check daily |
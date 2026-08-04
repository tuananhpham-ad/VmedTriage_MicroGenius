# PRD — VMedTriage

**Version:** 1.0
**Ngày cập nhật:** 01/08/2026
**Liên kết Brief:** docs/brief.md
**Nền tảng:** Web app (responsive)

## Lịch sử thay đổi
| Version | Ngày | Thay đổi | Lý do |
|---|---|---|---|
| 1.0 | 01/08/2026 | Ver 1.0 | Khởi tạo dự án |

---

## 1. Tóm tắt
VMedTriage là web app hỗ trợ điều dưỡng phân loại mức độ ưu tiên ban đầu cho bệnh nhân tư vấn online, thông qua AI Agent thu thập triệu chứng có cấu trúc, phát hiện red-flag, và đề xuất mức ưu tiên (Cấp cứu / Khám sớm / Tự theo dõi) — luôn cần điều dưỡng xác nhận trước khi gửi cho bệnh nhân.

## 2. Vai trò (Roles)
| Role | Mô tả |
|---|---|
| Bệnh nhân | Khai báo triệu chứng, nhận hướng dẫn xử trí sau khi đã được duyệt |
| Nhân viên y tế (Điều dưỡng) | Xem hàng đợi, duyệt/chỉnh sửa/ghi đè đề xuất AI, escalate thủ công |

## 3. Nhóm triệu chứng MVP (bản đầu, có thể điều chỉnh bổ sung)
| # | Nhóm triệu chứng | Red-flag liên quan cần phát hiện |
|---|---|---|
| 1 | Sốt | Co giật do sốt cao, dấu hiệu nhiễm trùng nặng |
| 2 | Đau bụng | Chảy máu nặng (nôn/đại tiện ra máu), đau dữ dội cấp |
| 3 | Đau ngực | Nghi tim mạch cấp |
| 4 | Khó thở | Nghi hô hấp/dị ứng nặng |
| 5 | Đau đầu / Chấn thương đầu nhẹ | Dấu hiệu đột quỵ, chảy máu |


## 4. Mức độ ưu tiên 
| Mức | Ý nghĩa | Hành động đề xuất |
|---|---|---|
| Cấp cứu | Có dấu hiệu red-flag hoặc nguy cơ cao | Escalate ngay, khuyến cáo đến cơ sở y tế gần nhất |
| Khám sớm | Cần được khám trong thời gian ngắn (không phải cấp cứu) | Khuyến cáo đặt lịch khám sớm |
| Tự theo dõi | Triệu chứng nhẹ, có thể tự chăm sóc tại nhà | Hướng dẫn tự theo dõi, tái khám nếu nặng hơn |

## 5. User Stories

| ID | Là | Tôi muốn | Để | Ưu tiên |
|---|---|---|---|---|
| US-01 | Bệnh nhân | Khai báo triệu chứng qua hội thoại có cấu trúc | Được hỗ trợ phân loại mức độ khẩn cấp ban đầu | P0 |
| US-02 | Bệnh nhân | Thấy disclaimer & giới hạn hệ thống ngay từ đầu | Hiểu đây là công cụ hỗ trợ, không thay thế bác sĩ | P0 |
| US-03 | Bệnh nhân | Nhận hướng dẫn xử trí sau khi đã được điều dưỡng duyệt | Có thông tin đáng tin cậy để hành động | P0 |
| US-04 | Bệnh nhân | Nhận cảnh báo khẩn cấp ngay lập tức nếu có red-flag | Được xử trí kịp thời trong tình huống nguy hiểm | P1 |
| US-05 | Nhân viên y tế | Xem hàng đợi các ca đang chờ duyệt | Ưu tiên xử lý ca khẩn cấp trước | P0 |
| US-06 | Nhân viên y tế | Xem phiếu tóm tắt triệu chứng đã được AI tổng hợp | Tiết kiệm thời gian khai thác lại từ đầu | P0 |
| US-07 | Nhân viên y tế | Duyệt / chỉnh sửa / ghi đè mức ưu tiên AI đề xuất | Đảm bảo quyết định cuối cùng luôn thuộc về con người | P0 |
| US-08 | Nhân viên y tế | Escalate thủ công một ca dù AI không gắn cờ | Không bỏ sót ca nghi ngờ theo kinh nghiệm lâm sàng | P0 |
| US-09 | Bệnh nhân / Nhân viên y tế | Đăng nhập vào hệ thống với tài khoản riêng theo role | Truy cập đúng chức năng, đảm bảo bảo mật | P0 |
| US-10 (add-on) | Nhân viên y tế | Xem log audit ai duyệt, lúc nào, thay đổi gì | Có thể truy vết trách nhiệm | P1 |

## 6. Functional Requirements

| ID | Mô tả | Liên kết | Ưu tiên |
|---|---|---|---|
| FR-01 | Agent hỏi-đáp dựa trên checklist cố định theo từng nhóm triệu chứng, không hỏi ngoài checklist | US-01 | P0 |
| FR-02 | Agent đạt tỷ lệ thu thập đầy đủ ≥90% các trường checklist bắt buộc | US-01 | P0 |
| FR-03 | Agent phát hiện red-flag trong quá trình hội thoại và gắn cờ ca ngay lập tức | US-04 | P0 |
| FR-04 | Hệ thống hiển thị banner cảnh báo khẩn cấp cho bệnh nhân ngay khi phát hiện red-flag, không chờ điều dưỡng duyệt (add-on) | US-04 | P1 |
| FR-05 | Agent tạo phiếu tóm tắt triệu chứng tự động (format lại dữ liệu đã thu thập) kèm mức ưu tiên đề xuất | US-06 | P0 |
| FR-06 | Hệ thống lưu flag "đã duyệt / chưa duyệt" trong DB — hướng xử trí chỉ được gửi cho bệnh nhân khi flag = đã duyệt | US-03, US-07 | P0 |
| FR-07 | Điều dưỡng có thể duyệt nguyên trạng, chỉnh sửa, hoặc ghi đè mức ưu tiên AI đề xuất | US-07 | P0 |
| FR-08 | Điều dưỡng có thể escalate thủ công một ca bất kỳ, kể cả khi AI không gắn cờ red-flag | US-08 | P0 |
| FR-09 | Hàng đợi ca chờ duyệt hiển thị theo cơ chế polling (chưa cần realtime/WebSocket ở MVP) | US-05 | P0 |
| FR-10 | Hệ thống có auth cơ bản, phân quyền theo 2 role (bệnh nhân / nhân viên y tế) | US-09 | P0 |
| FR-11 | Bệnh nhân thấy disclaimer & giới hạn hệ thống hiển thị cố định trước khi bắt đầu khai báo | US-02 | P0 |
| FR-12 | Log audit ghi nhận: ai duyệt, thời điểm, thay đổi gì so với đề xuất AI (add-on) | US-10 | P1 |
| FR-13 | Dữ liệu PII được mã hoá/ẩn danh cơ bản trong lưu trữ và log (add-on) | — | P1 |

## 7. Non-functional Requirements
- **An toàn/Đạo đức**: AI tuyệt đối không kết luận chẩn đoán cụ thể; mọi output phải grounded trên protocol triage chuẩn; chống bịa (anti-hallucination)
- **HITL**: 0% thông báo xử trí gửi tới bệnh nhân mà chưa qua duyệt của nhân viên y tế — kiểm chứng bằng audit log
- **Hiệu năng**: thời gian trung bình từ bắt đầu khai báo đến có hướng dẫn xử trí ban đầu < 3 phút
- **Độ chính xác**: mức đồng thuận AI–điều dưỡng ≥80% trong phân loại mức ưu tiên; phát hiện 100% ca red-flag trong test set
- **Bảo mật**: bảo vệ PII/PHI của bệnh nhân theo chuẩn tối thiểu cho dữ liệu y tế
- **Khả dụng**: hệ thống deploy chạy được, không crash trong quá trình demo/người dùng sử dụng

## 8. Luồng người dùng chính (User Flows)

**Luồng Bệnh nhân:**
1. Đăng nhập/đăng ký → xem disclaimer → bắt đầu khai báo triệu chứng
2. Chọn/agent xác định nhóm triệu chứng → hội thoại có cấu trúc theo checklist
3. [Nếu phát hiện red-flag] → hiển thị banner cảnh báo khẩn cấp ngay
4. Agent tạo phiếu tóm tắt → chuyển vào hàng đợi chờ điều dưỡng duyệt
5. Bệnh nhân chờ / nhận thông báo hướng xử trí sau khi đã được duyệt

**Luồng Nhân viên y tế:**
1. Đăng nhập → xem hàng đợi ca chờ duyệt (sắp xếp theo mức ưu tiên AI đề xuất và thời gian bệnh nhân bắt đầu chat)
2. Chọn 1 ca → xem phiếu tóm tắt chi tiết
3. Duyệt nguyên trạng / chỉnh sửa / ghi đè mức ưu tiên → xác nhận gửi
4. (Tuỳ chọn) Escalate thủ công nếu nghi ngờ dù AI không gắn cờ

## 9. Success Metrics 
- ≥90% tỷ lệ thu thập đầy đủ trường checklist
- <3 phút thời gian trung bình đến khi có hướng dẫn xử trí ban đầu
- ≥80% đồng thuận AI–điều dưỡng
- 100% ca red-flag trong test set được phát hiện, không bỏ sót
- 0% thông báo gửi chưa qua duyệt

## 10. Out of scope
- AI Agent dự đoán/kết luận bệnh cụ thể
- Tính năng đặt lịch khám
- Đa kênh (voice/hình ảnh)
- Mở rộng nhóm triệu chứng ngoài 5 nhóm MVP
- Realtime WebSocket, giải thích lý do phân loại có trích guideline

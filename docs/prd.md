# PRD — VMedTriage

**Version:** 2.0
**Ngày cập nhật:** 11/08/2026
**Liên kết Brief:** docs/brief.md
**Nền tảng:** Web app (responsive)

## Lịch sử thay đổi
| Version | Ngày | Thay đổi | Lý do |
|---|---|---|---|
| 1.0 | 01/08/2026 | Ver 1.0 | Khởi tạo dự án |
| 2.0 | 10/08/2026 | Ver 2.0 | Bổ sung Acceptance Criteria |

---

## 1. Tóm tắt
VMedTriage là web app hỗ trợ điều dưỡng phân loại mức độ ưu tiên ban đầu cho bệnh nhân tư vấn online, thông qua AI Agent thu thập triệu chứng có cấu trúc, phát hiện red-flag, và đề xuất mức ưu tiên (Cấp cứu / Khám sớm / Tự theo dõi).

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
| US-01 | Bệnh nhân | Khai báo triệu chứng qua hội thoại tự nhiên (free-text), được agent chủ động hỏi thêm về các triệu chứng liên quan mà tôi chưa tự nhắc tới  | Được hỗ trợ phân loại mức độ khẩn cấp ban đầu | P0 |
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
3. [Nếu phát hiện red-flag] → hiển thị  banner cảnh báo cụ thể cho bệnh nhân ngay lập tức, case tự động đẩy lên đầu hàng đợi mức Cấp cứu, điều dưỡng trực nhận thông báo ưu tiên xử lý.
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

---

## 11. Acceptance Criteria theo tính năng

### Tính năng 1: AI Agent hội thoại tự do phát hiện triệu chứng & Red-flag (US-01, US-04 · FR-01, FR-02, FR-03)

### Acceptance Criteria

- Given bệnh nhân đã đăng nhập và chưa có case đang mở
  When bệnh nhân gửi tin nhắn khai báo triệu chứng đầu tiên qua `POST /cases`
  Then hệ thống trả về `case_id`, `next_message` (câu hỏi tiếp theo hoặc null), `detected_symptom_group` tương ứng, `summary_ready=false`

- Given bệnh nhân mô tả nội dung có dấu hiệu red-flag ngay trong tin nhắn đầu tiên
  When agent xử lý tin nhắn qua `POST /cases` hoặc `POST /cases/{id}/responses`
  Then response trả về `red_flag=true`.

- Given bệnh nhân gửi tin nhắn rỗng hoặc chỉ chứa khoảng trắng tới `POST /cases/{id}/responses`
  When request được gửi
  Then hệ thống trả về mã lỗi 400 kèm message rõ ràng, không sinh `next_message` suy diễn từ input rỗng

- Given bệnh nhân trả lời một câu hỏi của agent một cách mơ hồ, agent không map được vào field checklist
  When agent xử lý câu trả lời đó
  Then agent hỏi lại đúng 1 lần cho field đó; nếu lần hỏi lại vẫn không rõ, field được đánh dấu "Thiếu thông tin" và hội thoại tiếp tục, không bị chặn luồng

- Given tất cả trường bắt buộc trong schema dữ liệu của nhóm triệu chứng đã được thu thập đủ
  When agent xử lý câu trả lời cuối cùng cần thiết
  Then response trả về `summary_ready=true` và `next_message=null`

- Given bệnh nhân đang hội thoại dở với agent
  When kết nối mạng bị gián đoạn và bệnh nhân quay lại phiên
  Then lịch sử hội thoại được giữ nguyên, bệnh nhân không bị yêu cầu trả lời lại từ đầu

- Given agent đã thu thập đủ dữ liệu để đề xuất mức ưu tiên cho một case
  When bản ghi `priority_flag` được tạo
  Then trường `grounding_source` được điền từ nguồn Bộ Y tế VN/WHO, còn `detect_source` chỉ phản ánh nguồn dùng để phát hiện triệu chứng (không dùng để kết luận mức ưu tiên)

- Given người dùng chưa đăng nhập hoặc không có role "Bệnh nhân"
  When gọi `POST /cases` hoặc `POST /cases/{id}/responses`
  Then hệ thống từ chối request với mã lỗi 401/403

---

### Tính năng 2: Hàng đợi ca chờ duyệt & Duyệt/Chỉnh sửa/Từ chối/Hỏi thêm — HITL (US-05, US-06, US-07, US-08 · FR-06, FR-07, FR-08, FR-09)

### Acceptance Criteria

- Given có nhiều case đang ở trạng thái chờ duyệt với các mức ưu tiên khác nhau
  When điều dưỡng gọi `GET /queue`
  Then danh sách case trả về được sắp xếp theo mức ưu tiên (Cấp cứu trước), trong cùng mức ưu tiên sắp theo thời gian chờ

- Given một case đang chờ duyệt với `ai_priority` xác định
  When điều dưỡng gọi `POST /cases/{id}/approve`
  Then `approval_status.final_priority` được ghi bằng đúng `ai_priority`, `approved_by`/`approved_at` được ghi nhận, và một bản ghi `audit_log` được tạo

- Given điều dưỡng không đồng ý với `ai_priority` đề xuất
  When điều dưỡng gọi `POST /cases/{id}/override` kèm mức ưu tiên mới
  Then `approval_status.final_priority` được cập nhật thành giá trị mới, và `audit_log` ghi lại cả `old_value` (giá trị AI đề xuất) và `new_value` (giá trị điều dưỡng chọn)

- Given một case đang chờ duyệt
  When điều dưỡng gọi `POST /cases/{id}/reject`
  Then hệ thống ghi nhận hành động từ chối vào `audit_log` kèm actor và thời điểm, case không còn hiển thị ở trạng thái chờ duyệt như ban đầu

- Given người dùng có role "Bệnh nhân"
  When gọi `GET /queue` hoặc bất kỳ endpoint duyệt/chỉnh sửa/từ chối/hỏi thêm nào
  Then hệ thống trả về mã lỗi 403

- Given điều dưỡng thực hiện một hành động duyệt/chỉnh sửa/từ chối tại màn hình W-07
  When việc lưu quyết định vào DB thất bại
  Then hệ thống không xác nhận thành công và không cho phép rời màn hình W-07 cho đến khi lưu thành công

- Given không có case nào đang ở trạng thái chờ duyệt
  When điều dưỡng gọi `GET /queue`
  Then hệ thống trả về danh sách rỗng, không phát sinh lỗi

- Given phiếu tóm tắt của một case có field không thu thập được giá trị (bệnh nhân bỏ trống)
  When điều dưỡng xem case tại W-07
  Then field đó hiển thị nhãn "Thiếu thông tin" màu cam thay vì để trống

---

### Tính năng 3: Đăng nhập/Đăng ký & Phân quyền theo Role (US-09 · FR-10)

### Acceptance Criteria

- Given người dùng đã có tài khoản hợp lệ với email/số điện thoại và mật khẩu đúng
  When gọi `POST /auth/login`
  Then hệ thống trả về token kèm role tương ứng, mã 200

- Given người dùng nhập sai email/mật khẩu
  When gọi `POST /auth/login`
  Then hệ thống hiển thị inline error màu đỏ, giữ nguyên giá trị email đã nhập, không trả token

- Given form đăng nhập đang trống (chưa nhập email hoặc mật khẩu)
  When người dùng chưa điền đủ thông tin
  Then nút đăng nhập ở trạng thái disable, không gửi được request

- Given người dùng có role "Bệnh nhân" đã đăng nhập thành công
  When dùng token đó gọi một endpoint dành riêng cho role "Nhân viên y tế"
  Then hệ thống trả về mã lỗi 403

- Given một request gọi tới endpoint yêu cầu xác thực mà không kèm header Authorization hợp lệ
  When middleware kiểm tra request
  Then hệ thống trả về mã lỗi 401

- Given kết nối tới server bị lỗi trong lúc đăng nhập
  When request `POST /auth/login` không nhận được phản hồi từ server
  Then hệ thống hiển thị toast "Không thể kết nối, vui lòng thử lại", không làm crash ứng dụng

- Given người dùng đăng ký tài khoản mới với mật khẩu hợp lệ
  When mật khẩu được lưu vào bảng `users`
  Then giá trị lưu trong `password_hash` là dạng đã hash, không phải plaintext của mật khẩu gốc

- Given token của người dùng đã quá thời hạn hiệu lực
  When người dùng dùng token đó gọi một endpoint được bảo vệ
  Then hệ thống trả về mã lỗi 401, yêu cầu đăng nhập lại

---

### Tính năng 4: Disclaimer, Thông báo ưu tiên xử lý ca khẩn cấp & Màn hình kết quả sau duyệt (US-02, US-03, US-04 · FR-04, FR-11)

### Acceptance Criteria

- Given bệnh nhân bắt đầu một phiên làm việc mới
  When bệnh nhân truy cập vào luồng khai báo triệu chứng
  Then màn hình W-02 Disclaimer luôn được hiển thị bắt buộc xem trước khi cho phép bắt đầu khai báo

- Given agent phát hiện red-flag trong quá trình hội thoại
  When case được gắn cờ `red_flag=true`
  Then case tự động được đẩy lên đầu hàng đợi ở mức Cấp cứu, điều dưỡng trực nhận thông báo nội bộ ưu tiên, phía bệnh nhân chỉ hiển thị thông điệp hiển thị nội dung cảnh báo y tế cụ thể.

- Given `approval_status` của case chưa ở trạng thái "đã duyệt"
  When bệnh nhân gọi `GET /cases/{id}/result`
  Then response chỉ trả về trạng thái chờ + thời gian ước tính (kèm cờ `red_flag`), không chứa nội dung xử trí/cảnh báo y tế cụ thể

- Given `approval_status` của case đã ở trạng thái "đã duyệt"
  When bệnh nhân gọi `GET /cases/{id}/result`
  Then response trả về đầy đủ nội dung hướng xử trí đã được điều dưỡng duyệt

- Given case thuộc về bệnh nhân A
  When bệnh nhân B (đã đăng nhập) gọi `GET /cases/{id}/result` với id của case thuộc bệnh nhân A
  Then hệ thống từ chối trả dữ liệu (401/403/404), không lộ thông tin case của người khác

---

### Tính năng 5: Phiếu tóm tắt triệu chứng — chuyển hội thoại thành dạng cấu trúc y tế (US-06 · FR-05)

### Acceptance Criteria

- Given case đã thu thập đủ trường bắt buộc trong schema dữ liệu (hoặc bị ngắt do red-flag)
  When agent xử lý câu trả lời khiến điều kiện trên được thoả
  Then response của `POST /cases/{id}/responses` chứa field `summary` gồm `summary_fields` (mảng {label, value, is_missing}), `ai_priority`, `red_flag`, `red_flag_reason`

- Given một câu trả lời của bệnh nhân không đủ rõ để map vào field chuẩn
  When agent sinh `summary_fields` cho field đó
  Then field đó có `is_missing=true` và không chứa giá trị tự suy diễn ngoài nội dung bệnh nhân đã cung cấp

- Given case bị ngắt giữa chừng do phát hiện red-flag trước khi đủ trường bắt buộc
  When agent sinh phiếu tóm tắt
  Then phiếu tóm tắt vẫn được sinh ra từ các câu trả lời đã thu thập được tới thời điểm đó, không chờ đủ trường bắt buộc

- Given một case đã có `summary` được sinh ra
  When điều dưỡng gọi `GET /cases/{id}`
  Then response trả về đúng nội dung `summary_json` đã lưu, khớp với `summary` đã sinh trước đó

- Given phiếu tóm tắt của một case đã được sinh
  When điều dưỡng xem phiếu tại W-07
  Then phiếu hiển thị kèm 2 dòng "Nguồn đối chiếu detect" và "Nguồn grounding kết luận" tương ứng với `detect_source`/`grounding_source` lưu trong `summary_json`

- Given một tài khoản có role "Nhân viên y tế" không được gán quyền truy cập case đó
  When tài khoản đó cố truy cập phiếu tóm tắt của case qua API
  Then hệ thống từ chối trả dữ liệu

---

## 12. Bảng tổng hợp Acceptance Criteria

| Feature | Acceptance Criteria | Ready for QA | Missing Information |
|---|---|---|---|
| Tính năng 1 — AI Agent hội thoại tự do phát hiện triệu chứng & Red-flag | 8 | Ready | — |
| Tính năng 2 — Hàng đợi ca chờ duyệt & Duyệt/Chỉnh sửa/Từ chối/Hỏi thêm (HITL) | 8 | Ready | — |
| Tính năng 3 — Đăng nhập/Đăng ký & Phân quyền theo Role | 8 | Ready | — |
| Tính năng 4 — Disclaimer, Thông báo ưu tiên xử lý ca khẩn cấp & Màn hình kết quả sau duyệt | 5 | Incomplete | Bổ sung ngưỡng SLA cụ thể (số phút) cho "thời gian ước tính ngắn hơn" của ca red-flag ở màn hình chờ|
| Tính năng 5 — Phiếu tóm tắt triệu chứng (chuyển hội thoại thành dạng cấu trúc y tế) | 6 | Incomplete | Chưa viết được AC phân quyền chi tiết theo từng nhân viên y tế được gán |

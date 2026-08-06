# ĐẶC TẢ TÍNH NĂNG / FEATURE SPECIFICATION — VMedTriage

Mô tả chi tiết từng tính năng theo cấu trúc: **Động lực → Thiết kế → Kế hoạch**

> **Ghi chú phiên bản:** File này đã cập nhật theo quyết định chuyển luồng thu thập triệu chứng từ checklist cố định sang hội thoại free-text, tách 2 nguồn tri thức theo vai trò (Mayo Clinic để *detect*, Bộ Y tế VN/WHO để *grounding kết luận*), và loại bỏ ngoại lệ gửi cảnh báo tự động cho bệnh nhân — mọi thông báo, kể cả red-flag, đều bắt buộc qua duyệt của điều dưỡng (HITL 100%, không ngoại lệ).

---

## ĐẶC TẢ #1 — AI Agent hội thoại tự do phát hiện triệu chứng & Red-flag 🆕

| | |
|---|---|
| **Mã User Story liên quan** | US-01, US-04 |
| **Tên tính năng** | AI Agent hội thoại tự do (free-text) phát hiện triệu chứng, triệu chứng liên quan & Red-flag |
| **Người viết** | Thương |
| **Ngày tạo** | 03/08/2026 |
| **Ngày cập nhật gần nhất** | 06/08/2026 |
| **Trạng thái** | Đang review |

### 1. Động lực (Motivation)

**Vấn đề cần giải quyết**
Nhân viên y tế mất nhiều thời gian khai thác triệu chứng thủ công, đặc biệt vào giờ cao điểm; kết quả phân loại không đồng nhất giữa các lần tư vấn hoặc giữa các điều dưỡng khác nhau.

**Người dùng mục tiêu**
Bệnh nhân là người trực tiếp khai báo qua hội thoại tự nhiên (free-text), không bị ép theo checklist cứng; nhân viên y tế là người hưởng lợi gián tiếp vì nhận được phiếu tóm tắt đã chuẩn hoá thay vì phải hỏi lại từ đầu.

**Mục tiêu kỳ vọng**
≥90% tỷ lệ thu thập đầy đủ các trường bắt buộc trong schema dữ liệu; phát hiện 100% ca red-flag trong bộ test set (kể cả khi phát hiện ngay từ tin nhắn đầu); thời gian trung bình từ khi bắt đầu khai báo đến khi có phiếu tóm tắt < 3 phút (ca nhẹ có thể nhanh hơn nhờ hội thoại rút gọn).

**Phương án thay thế đã xem xét**
(a) Form tĩnh nhiều bước thay vì hội thoại — bị loại vì trải nghiệm cứng nhắc, khó xử lý câu trả lời tự do. (b) Checklist cố định, hỏi tuần tự không được hỏi ngoài phạm vi (thiết kế v1.0) — bị loại vì bỏ lỡ triệu chứng liên quan bệnh nhân tự nhắc tới sớm, làm chậm phát hiện red-flag nằm ngoài checklist đang hỏi dở. (c) Agent hỏi tự do hoàn toàn, không có nguồn tham chiếu — bị loại vì rủi ro hỏi lan man, dễ hallucination, không grounded. → **Chọn phương án hội thoại free-text có 2 lớp kiểm soát**: dùng nguồn tham chiếu uy tín (Mayo Clinic symptom reference) để biết cần hỏi/làm rõ gì, và dùng nguồn chính thống (Bộ Y tế VN/WHO) để grounding mọi kết luận mức ưu tiên.

### 2. Thiết kế (Design)

**Kiến trúc hệ thống**
Frontend chat (W-03) gửi tin nhắn tự do → Backend API → Agent module gồm 2 bước: **(1) Detect module** đối chiếu nội dung với nguồn tham chiếu (Mayo Clinic) để nhận diện nhóm triệu chứng + các triệu chứng liên quan cần làm rõ; **(2) Extraction module** map câu trả lời vào schema dữ liệu ẩn theo từng nhóm (thay cho checklist hiển thị) → ghi vào bảng checklist_responses → khi đủ trường bắt buộc hoặc phát hiện red-flag (có thể xảy ra ngay từ tin nhắn đầu tiên, không cần đợi hỏi hết) → mọi kết luận mức ưu tiên grounded trên nguồn chính thống (Bộ Y tế VN/WHO) → sinh phiếu tóm tắt → đẩy case vào hàng đợi chờ duyệt.

**Thiết kế giao diện (UI/UX)**
W-03 Khai báo triệu chứng: ô nhập tự do là trung tâm, chip nhóm triệu chứng chỉ là gợi ý nhanh (không bắt buộc chọn trước); bubble hội thoại agent/bệnh nhân.
**Thiết kế API**
POST /cases (tạo case mới — không bắt buộc chọn sẵn nhóm triệu chứng, agent có thể tự detect từ tin nhắn đầu tiên) — POST /cases/{id}/responses (gửi tin nhắn tự do, nhận phản hồi tiếp theo của agent). Response luôn kèm case_id, next_message (câu hỏi/phản hồi tiếp theo, hoặc null nếu đã đủ), detected_symptom_group, summary_ready (boolean), red_flag (boolean). Lỗi input trả 400 kèm message rõ ràng, không để agent tự suy diễn khi input rỗng.

**Mô hình dữ liệu**
`cases(id, patient_id, symptom_group, status, created_at)` · `checklist_responses(id, case_id, field_key, answer, answered_at)` · `priority_flag(case_id, ai_priority, red_flag, red_flag_reason, detect_source, grounding_source)`.

**Thiết kế AI/ML**
LLM provider chốt đầu Sprint 2 (spike T-008); prompt dùng **2 nguồn tách vai trò**: (1) nguồn tham chiếu detect (Mayo Clinic symptom reference) để nhận diện triệu chứng/triệu chứng liên quan và biết cần hỏi/làm rõ gì tiếp theo; (2) nguồn grounding chính thống (Bộ Y tế VN/WHO, do PM biên soạn ngưỡng Cấp cứu/Khám sớm cho 5 nhóm) để agent căn cứ khi đề xuất mức ưu tiên. Guard rail: (a) chặn agent dùng nguồn detect để kết luận mức ưu tiên; (b) chặn output mang tính kết luận chẩn đoán bệnh cụ thể; (c) độ dài hội thoại thích ứng theo mức nghi ngờ — ca rõ ràng nhẹ hỏi tối thiểu, ca nghi ngờ/giáp ranh red-flag hỏi đến khi đủ yếu tố phân biệt. Chỉ số đánh giá: % đồng thuận AI–điều dưỡng (tách riêng cho cặp Khám sớm/Tự theo dõi), % phát hiện red-flag trong test set.

**Trường hợp đặc biệt và Xử lý lỗi**
Bệnh nhân bỏ trống/trả lời không rõ → agent hỏi lại tối đa 1 lần, sau đó đánh dấu "Thiếu thông tin" và tiếp tục, không chặn luồng. Mất kết nối giữa chừng → giữ nguyên lịch sử chat, không bắt trả lời lại từ đầu.

**Bảo mật và Quyền riêng tư**
Câu trả lời của bệnh nhân chỉ nhân viên y tế được gán quyền mới truy cập được thông qua hàng đợi (Feature #2).

### 3. Kế hoạch (Plan)

**Các bước thực hiện**
(1) Chốt bộ ngưỡng Cấp cứu/Khám sớm cho 5 nhóm (nguồn Bộ Y tế VN/WHO) — (2) Chuẩn bị nguồn tham chiếu detect (Mayo Clinic) cho 5 nhóm — (3) Thiết kế schema dữ liệu ẩn per nhóm — (4) Chọn LLM provider + spike gọi API thật — (5) Implement logic detect + hỏi bù field còn thiếu, độ dài thích ứng theo mức nghi ngờ — (6) Implement guard rail (tách vai trò 2 nguồn, chặn kết luận chẩn đoán) & phát hiện red-flag ngay từ lượt đầu — (7) Implement xuất phiếu tóm tắt JSON (kèm nguồn detect/grounding) — (8) Test agent độc lập qua script — (9) Tích hợp vào backend + UI thật — (10) Tune prompt theo kết quả eval.

**Công việc con (liên kết Backlog)**


**Phụ thuộc**
Cần chốt nguồn protocol triage chuẩn (Bộ Y tế VN/WHO) cho cả 2 mức Cấp cứu và Khám sớm trước khi viết prompt grounding. Cần chuẩn bị xong nguồn tham chiếu detect (Mayo Clinic) trước khi implement logic detect. Cần chọn xong LLM provider trước khi implement logic hỏi-đáp.

**Timeline dự kiến**
03/08 → 13/08/2026 (Sprint 2, W2-W3).

**Kế hoạch kiểm thử**
Chạy ≥20 test case (bao gồm riêng nhóm ca "Khám sớm" ở vùng ranh giới không rõ ràng, không chỉ chia nhị phân có/không red-flag), đủ 5 nhóm, qua agent, đối chiếu kết quả với điều dưỡng chuẩn (Thương). Tiêu chí nghiệm thu: ≥80% đồng thuận priority (đo riêng cho cặp Khám sớm/Tự theo dõi), 100% red-flag được phát hiện kể cả khi xuất hiện ngay từ tin nhắn đầu.

**Kế hoạch triển khai**
Release nội bộ trên staging cuối Sprint 2 (Demo 1). Chưa dùng feature flag vì MVP chỉ có 1 phiên bản. Theo dõi số ca red-flag/số ca thường qua audit log sau khi lên staging.

**Tiêu chí thành công**
≥90% tỷ lệ thu thập đủ trường bắt buộc trong schema; ≥80% đồng thuận AI–điều dưỡng; 100% red-flag phát hiện trong test set; thời gian trung bình < 3 phút.

**Rủi ro và Cách giảm thiểu**
Hallucination/agent tự chẩn đoán → guard rail + review thủ công (T-053). Thiếu nguồn protocol chuẩn → xác định sớm trong 2 ngày đầu Sprint, có phương án fallback dùng thang triage quốc tế nếu chưa có hướng dẫn VN phù hợp.Agent tự suy luận cảm tính ở vùng xám "Khám sớm" (không có trigger nhị phân rõ như red-flag) → bắt buộc phải có bộ ngưỡng cụ thể per nhóm triệu chứng trước khi viết prompt, không để model tự phán đoán tổ hợp yếu tố.

---

## ĐẶC TẢ #2 — Hàng đợi ca chờ duyệt & Duyệt/Chỉnh sửa/Escalate mức ưu tiên (HITL)

| | |
|---|---|
| **Mã User Story liên quan** | US-05, US-06, US-07, US-08 |
| **Tên tính năng** | Hàng đợi ca chờ duyệt & Duyệt/Chỉnh sửa mức ưu tiên (HITL) |
| **Người viết** | Thương |
| **Ngày tạo** | 03/08/2026 |
| **Ngày cập nhật gần nhất** | — |
| **Trạng thái** | Đang review |

### 1. Động lực (Motivation)

**Vấn đề cần giải quyết**
Nếu không có bước xác nhận con người, hệ thống có nguy cơ gửi hướng xử trí sai/nguy hiểm trực tiếp tới bệnh nhân — vi phạm ràng buộc an toàn cốt lõi của dự án (0% thông báo gửi chưa qua duyệt).

**Người dùng mục tiêu**
Nhân viên y tế (điều dưỡng) — hiện đang phải tự khai thác và tự phân loại thủ công, dễ sai lệch giữa các lần trực và giữa các điều dưỡng khác nhau.

**Mục tiêu kỳ vọng**
0% thông báo gửi bệnh nhân mà chưa qua duyệt, đo bằng audit log; điều dưỡng xử lý ca nhanh hơn nhờ có sẵn phiếu tóm tắt đã chuẩn hoá.

**Phương án thay thế đã xem xét**
Auto-approve các ca mức "Tự theo dõi" (thấp nhất) để giảm tải điều dưỡng — bị loại vì brief yêu cầu HITL 100%, không có ngoại lệ theo mức độ ưu tiên.

### 2. Thiết kế (Design)

**Kiến trúc hệ thống**
Backend expose API hàng đợi theo cơ chế polling (chưa realtime) → Frontend W-06 poll định kỳ → điều dưỡng chọn 1 ca → W-07 hiển thị phiếu tóm tắt + 3 hành động → ghi quyết định vào approval_status và audit_log.

**Thiết kế giao diện (UI/UX)**
W-06 Hàng đợi: danh sách ca theo màu ưu tiên (đỏ/vàng/xanh), sắp theo mức ưu tiên và thời gian chờ, ca Cấp cứu chờ lâu được highlight viền đỏ. W-07 Duyệt ca: phiếu tóm tắt, cờ red-flag, 3 nút Duyệt nguyên trạng / Chỉnh sửa mức ưu tiên.

**Thiết kế API**
GET /queue (polling, trả danh sách case sắp theo priority + thời gian chờ) — POST /cases/{id}/approve (giữ nguyên đề xuất AI) — POST /cases/{id}/override (chỉnh mức ưu tiên, ghi log giá trị cũ/mới) — POST /cases/{id}/escalate (luôn set mức Cấp cứu bất kể AI đề xuất gì).

**Mô hình dữ liệu**
`approval_status(case_id, approved_by, approved_at, final_priority)` · `audit_log(case_id, actor, action, old_value, new_value, timestamp)`.

**Thiết kế AI/ML**
Không áp dụng trực tiếp ở tính năng này — chỉ tiêu thụ mức ưu tiên đề xuất do Feature #1 (Agent) sinh ra.

**Trường hợp đặc biệt và Xử lý lỗi**
Field trong schema dữ liệu bị thiếu (bệnh nhân bỏ trống) → hiển thị nhãn cam "Thiếu thông tin", không để trống gây hiểu lầm là không có triệu chứng. Lỗi khi lưu quyết định duyệt → không cho thoát màn hình W-07 cho đến khi lưu thành công. Mất kết nối khi tải hàng đợi → giữ nguyên danh sách cũ, không xoá trắng dữ liệu.

**Bảo mật và Quyền riêng tư**
Chỉ role "Nhân viên y tế" truy cập được W-06/W-07. Mọi hành động duyệt ghi nhận actor (ai duyệt, lúc nào, thay đổi gì) vào audit_log để truy vết trách nhiệm.

### 3. Kế hoạch (Plan)

**Các bước thực hiện**
(1) Thiết kế schema priority_flag/approval_status/audit_log — (2) Build UI W-06 với data giả — (3) Implement API hàng đợi polling — (4) Build UI W-07 — (5) Implement API duyệt/chỉnh sửa/escalate — (6) Enforce chặn trả kết quả khi chưa duyệt — (7) QA toàn luồng.

**Công việc con (liên kết Backlog)**


**Phụ thuộc**
Cần Feature #1 (Agent) hoàn tất phần xuất phiếu tóm tắt JSON trước khi build UI hiển thị đầy đủ. Cần DB schema chốt trước khi build API.

**Timeline dự kiến**
03/08 → 13/08/2026.

**Kế hoạch kiểm thử**
Test case thủ công cho cả 3 hành động (duyệt/chỉnh sửa/escalate); test case cố tình bỏ qua bước duyệt để xác nhận hệ thống chặn đúng (phụ thuộc Feature #4); test trạng thái rỗng và lỗi tải hàng đợi.

**Kế hoạch triển khai**
Release cùng đợt với Feature #1 trong Demo 1 cuối Sprint 2.

**Tiêu chí thành công**
0% thông báo gửi khi chưa duyệt (audit log xác nhận); điều dưỡng thao tác được cả 3 hành động không lỗi trên staging.

**Rủi ro và Cách giảm thiểu**
Nhân viên y tế bỏ sót ca Cấp cứu chờ lâu → highlight viền đỏ đặc biệt trong UI hàng đợi (đã có trong wireframe). Lỗi polling gây trễ hiển thị ca mới → theo dõi thời gian polling thực tế trong bước QA.

---

## ĐẶC TẢ #3 — Đăng nhập/Đăng ký & Phân quyền theo Role

| | |
|---|---|
| **Mã User Story liên quan** | US-09 |
| **Tên tính năng** | Đăng nhập/Đăng ký & Phân quyền theo Role (Bệnh nhân / Nhân viên y tế) |
| **Người viết** | Thương |
| **Trạng thái** | Đang review |

### 1. Động lực (Motivation)

**Vấn đề cần giải quyết**
Hệ thống xử lý dữ liệu y tế nhạy cảm và có 2 nhóm người dùng với quyền truy cập hoàn toàn khác nhau (bệnh nhân chỉ thấy ca của mình; nhân viên y tế thấy toàn bộ hàng đợi) — nếu không phân quyền rõ, rủi ro lộ dữ liệu PII/PHI.

**Người dùng mục tiêu**
Cả Bệnh nhân và Nhân viên y tế — hiện chưa có cách nào để hệ thống biết ai đang thao tác, mọi tính năng khác đều phụ thuộc vào tính năng này.

**Mục tiêu kỳ vọng**
100% request vào đúng khu vực chức năng theo role; không có ca truy cập chéo lọt qua trong test.

**Phương án thay thế đã xem xét**
Đăng nhập không phân role, để người dùng tự chọn giao diện thủ công — bị loại vì không đảm bảo được ranh giới bảo mật giữa 2 nhóm người dùng.

### 2. Thiết kế (Design)

**Kiến trúc hệ thống**
Frontend gửi credential → Backend xác thực → sinh session/token gắn kèm role → mọi API sau đó đi qua middleware kiểm tra role trước khi xử lý request.

**Thiết kế giao diện (UI/UX)**
W-01 Đăng nhập: email/số điện thoại + mật khẩu + chọn vai trò, có inline error khi sai thông tin, disable nút khi form trống — theo đúng Wireframe.

**Thiết kế API**
POST /auth/register, POST /auth/login (trả token + role). Mọi endpoint khác yêu cầu header Authorization; middleware kiểm tra role tương ứng route (patient-only / staff-only), trả 401/403 khi sai.

**Mô hình dữ liệu**
`users(id, email_or_phone, password_hash, role, created_at)`.

**Thiết kế AI/ML**
Không áp dụng.

**Trường hợp đặc biệt và Xử lý lỗi**
Sai email/mật khẩu → inline error đỏ, giữ nguyên giá trị email đã nhập. Lỗi mạng/server → toast riêng "Không thể kết nối, vui lòng thử lại".

**Bảo mật và Quyền riêng tư**
Mật khẩu hash trước khi lưu (không lưu plaintext); token có thời hạn; middleware chặn cứng ở tầng backend mọi request sai role, không chỉ ẩn ở tầng giao diện.

### 3. Kế hoạch (Plan)

**Các bước thực hiện**
(1) Thiết kế bảng users — (2) Implement API đăng ký/đăng nhập — (3) Implement middleware phân quyền — (4) Build UI W-01 — (5) Test cả 2 role và các case lỗi.

**Công việc con (liên kết Backlog)**

**Phụ thuộc**
Không phụ thuộc tính năng khác — nên làm sớm nhất trong Sprint 2 vì mọi tính năng còn lại đều cần auth trước.

**Timeline dự kiến**
03/08 → 04/08/2026. Tổng dự kiến 10 giờ (Dũng).

**Kế hoạch kiểm thử**
Test đăng nhập đúng/sai cho cả 2 role; test truy cập chéo (bệnh nhân gọi API dành cho nhân viên y tế) phải bị chặn 403.

**Kế hoạch triển khai**
Release toàn bộ ngay đầu Sprint 2, không chia giai đoạn — là điều kiện tiên quyết cho mọi tính năng khác.

**Tiêu chí thành công**
100% test case phân quyền pass; không có request nào lọt qua middleware sai role.

**Rủi ro và Cách giảm thiểu**
Thiếu thời gian test kỹ do làm sớm và gấp → bổ sung test case phân quyền vào checklist QA end-to-end cuối Sprint.

---

## ĐẶC TẢ #4 — Disclaimer, Thông báo ưu tiên xử lý ca khẩn cấp & Màn hình kết quả sau duyệt 🆕

| | |
|---|---|
| **Mã User Story liên quan** | US-02, US-03, US-04 |
| **Tên tính năng** | Disclaimer, Thông báo ưu tiên xử lý ca khẩn cấp (nội bộ) & Màn hình kết quả sau duyệt |
| **Người viết** | Thương |
| **Ngày tạo** | 03/08/2026 |
| **Ngày cập nhật gần nhất** | 06/08/2026 |
| **Trạng thái** | Đang review |

### 1. Động lực (Motivation)

**Vấn đề cần giải quyết**
Bệnh nhân cần hiểu rõ giới hạn của công cụ trước khi dùng (không thay thế bác sĩ); ca có dấu hiệu nguy hiểm cần được điều dưỡng xử lý ưu tiên nhanh nhất có thể — nhưng nội dung cảnh báo/hướng xử trí chi tiết chỉ được gửi sau khi con người xác nhận, để tránh cảnh báo sai (false positive) gây hoang mang không cần thiết.

**Người dùng mục tiêu**
Bệnh nhân — người trực tiếp đọc disclaimer, được ưu tiên xử lý nhanh nếu có red-flag, và chờ/nhận kết quả cuối cùng sau khi điều dưỡng duyệt.

**Mục tiêu kỳ vọng**
100% bệnh nhân thấy disclaimer trước khi khai báo; ca red-flag được đẩy ưu tiên xử lý ngay trong hàng đợi (không chờ như ca thường); **0% nội dung cảnh báo/hướng xử trí chi tiết được gửi tới bệnh nhân khi chưa qua duyệt của điều dưỡng — không có ngoại lệ.**

**Phương án thay thế đã xem xét**
(a) Banner tự động gửi ngay không chờ duyệt (thiết kế v1.0) — bị loại vì rủi ro cảnh báo sai (false positive) gây hoang mang không cần thiết, và vi phạm nguyên tắc HITL 100% không ngoại lệ. (b) Không tách riêng, xử lý ca red-flag y hệt ca thường trong hàng đợi — bị loại vì mất tính ưu tiên, điều dưỡng có thể không nhận ra ca cần xử lý ngay. → **Chọn**: ca red-flag tự động đẩy lên đầu hàng đợi + thông báo ưu tiên tức thời tới điều dưỡng trực (không gửi gì cho bệnh nhân); nội dung cảnh báo cụ thể chỉ gửi sau khi điều dưỡng xác nhận.

### 2. Thiết kế (Design)

**Kiến trúc hệ thống**
Khi Agent (Feature #1) phát hiện red-flag → case tự động set priority = Cấp cứu và đẩy lên đầu hàng đợi (Feature #2) + gửi thông báo ưu tiên tới điều dưỡng trực (kênh nội bộ, không phải banner cho bệnh nhân). Màn hình phía bệnh nhân (W-04/W-05) luôn query approval_status trước khi hiển thị bất kỳ nội dung cảnh báo/xử trí nào.

**Thiết kế giao diện (UI/UX)**
W-02 Disclaimer (nội dung tĩnh, bắt buộc xem mỗi phiên mới) → W-03 khai báo → [nếu red-flag] **W-04 (thiết kế lại)**: hiển thị "Ca của bạn đang được ưu tiên xem xét", KHÔNG hiển thị nội dung cảnh báo y tế cụ thể → W-05 Kết quả (trạng thái "Chưa duyệt" có ước tính thời gian chờ — ca red-flag có thời gian ước tính ngắn hơn; "Đã duyệt" hiển thị hướng xử trí đầy đủ).

**Thiết kế API**
GET /cases/{id}/result — trả về approval_status và red_flag; chỉ trả nội dung xử trí/cảnh báo cụ thể khi approval_status = "đã duyệt", ngược lại chỉ trả trạng thái chờ + thời gian ước tính (kèm cờ red_flag để frontend hiển thị thông điệp "đang được ưu tiên xem xét" phù hợp, không lộ nội dung y tế).

**Mô hình dữ liệu**
Tái sử dụng bảng cases, approval_status từ Feature #1 và #2 — không cần bảng mới.

**Thiết kế AI/ML**
Không áp dụng — đây là tầng hiển thị, không xử lý AI trực tiếp.

**Trường hợp đặc biệt và Xử lý lỗi**


**Bảo mật và Quyền riêng tư**
Endpoint kết quả chỉ trả dữ liệu của đúng bệnh nhân đang đăng nhập (kiểm tra ownership theo user_id), không cho truy cập case của người khác qua đổi id trên URL.

### 3. Kế hoạch (Plan)

**Các bước thực hiện**
(1) Viết nội dung Disclaimer — (2) Build UI W-02 — (3) Build UI W-04 (bản thiết kế lại: thông điệp trấn an, không lộ nội dung y tế) — (4) Build UI W-05 Kết quả — (5) Implement API kết quả có enforce HITL — (6) QA cả 2 trạng thái chờ/đã duyệt, kèm test cố ý kiểm tra red-flag không bị lộ trước khi duyệt.

**Công việc con (liên kết Backlog)**


**Phụ thuộc**
Cần Feature #1 (phát hiện red-flag) và Feature #2 (approval_status) hoàn tất phần backend trước khi nối API thật cho W-05.

**Timeline dự kiến**
05/08 → 12/08/2026.

**Kế hoạch kiểm thử**
Test hiển thị disclaimer ở mỗi phiên mới; test ca red-flag được đẩy ưu tiên đúng trong hàng đợi (không phải test banner gửi ngay); test màn hình kết quả **tuyệt đối không lộ nội dung cảnh báo/xử trí khi approval_status khác "đã duyệt", kể cả với ca red-flag**.

**Kế hoạch triển khai**
Release cùng Demo 1 cuối Sprint 2 — đây là các màn hình bắt buộc để demo được toàn bộ luồng bệnh nhân.

**Tiêu chí thành công**
100% bệnh nhân thấy disclaimer; 100% ca red-flag được đẩy ưu tiên xử lý trong hàng đợi ngay khi phát hiện; **0% nội dung cảnh báo/xử trí bị gửi tới bệnh nhân trước khi duyệt** (kiểm chứng qua test cố ý truy cập sớm).

**Rủi ro và Cách giảm thiểu**
Ca red-flag không được điều dưỡng xử lý kịp thời do không còn cảnh báo tự động thúc bệnh nhân gọi cấp cứu → bù bằng highlight đặc biệt trong hàng đợi (đã có ở W-06) + cơ chế nhắc bổ sung nếu vượt SLA. Bệnh nhân lo lắng vì không thấy phản hồi cụ thể dù có dấu hiệu nguy hiểm → W-04 cần thông điệp trấn an rõ ràng ("đang được ưu tiên xem xét") dù không tiết lộ đánh giá y tế cụ thể.

---

## ĐẶC TẢ #5 — Phiếu tóm tắt triệu chứng — chuyển hội thoại thành dạng cấu trúc y tế 🆕

| | |
|---|---|
| **Mã User Story liên quan** | US-06 |
| **Tên tính năng** | Phiếu tóm tắt triệu chứng — chuyển câu trả lời hội thoại thành dạng cấu trúc y tế |
| **Người viết** | Thương |
| **Ngày tạo** | 03/08/2026 |
| **Ngày cập nhật gần nhất** | 06/08/2026 |
| **Trạng thái** | Đang review |

### 1. Động lực (Motivation)

**Vấn đề cần giải quyết**
Câu trả lời của bệnh nhân trong hội thoại là văn bản tự do, rời rạc theo từng câu hỏi. Nếu để nguyên dạng thô, nhân viên y tế phải tự đọc lại toàn bộ đoạn chat để tổng hợp thông tin trước khi ra quyết định — mất thời gian và dễ bỏ sót chi tiết quan trọng, đặc biệt với ca cần xử lý nhanh.

**Người dùng mục tiêu**
Nhân viên y tế (điều dưỡng) là người trực tiếp đọc phiếu tóm tắt ở màn hình Duyệt ca (W-07) để ra quyết định; bệnh nhân được hưởng lợi gián tiếp vì rút ngắn thời gian chờ xử lý.

**Mục tiêu kỳ vọng**
100% case đủ trường bắt buộc trong schema dữ liệu (hoặc bị ngắt do red-flag) đều tự động sinh được phiếu tóm tắt có cấu trúc; điều dưỡng đọc hiểu phiếu trong dưới 90 giây thay vì phải đọc lại nguyên đoạn chat; phiếu luôn đi kèm mức ưu tiên đề xuất (theo FR-05).

**Phương án thay thế đã xem xét**
(a) Hiển thị nguyên văn đoạn hội thoại cho điều dưỡng tự đọc — bị loại vì mất thời gian, không có cấu trúc để so sánh nhanh giữa các ca. (b) Để agent tự viết đoạn văn tóm tắt tự do, không theo template cố định — bị loại vì khó đảm bảo đủ trường bắt buộc và dễ hallucination khi agent tự diễn giải thêm.

### 2. Thiết kế (Design)

**Kiến trúc hệ thống**
Khi checklist_responses đủ trường bắt buộc trong schema (hoặc bị ngắt giữa chừng do red-flag) → Agent module map câu trả lời tự do sang các trường cấu trúc cố định theo format y tế chuẩn (đã định nghĩa ở T-030) → sinh JSON phiếu tóm tắt **kèm 2 trường mới: nguồn đối chiếu detect và nguồn grounding kết luận (Bộ Y tế VN/WHO)** → lưu vào DB → API trả về cho Frontend W-07 hiển thị dạng phiếu field-value, giống hồ sơ bệnh án rút gọn.

**Thiết kế giao diện (UI/UX)**
W-07 Duyệt ca hiển thị phiếu tóm tắt dạng bảng field-value (VD: Thời gian khởi phát, Mức độ đau, Kèm khó thở, Vã mồ hôi lạnh...), **kèm dòng "Nguồn đối chiếu detect" và "Nguồn grounding kết luận" ở cuối phiếu** để điều dưỡng biết căn cứ; field không map được dữ liệu hiển thị nhãn cam "Thiếu thông tin" thay vì để trống — theo đúng Wireframe 07.

**Thiết kế API**
Không có endpoint riêng — phiếu tóm tắt được nhúng trong response của POST /cases/{id}/responses (khi đủ trường bắt buộc trong schema) dưới field `summary`, và trả lại qua GET /cases/{id} cho màn hình duyệt ca. Cấu trúc gồm `summary_fields` (mảng {label, value, is_missing}), `ai_priority`, `red_flag`, `red_flag_reason`.

**Mô hình dữ liệu**
Tái sử dụng checklist_responses (nguồn dữ liệu thô) và priority_flag; thêm cột `summary_json` (kiểu JSON, **gồm cả detect_source và grounding_source**) vào bảng priority_flag để lưu bản tóm tắt đã cấu trúc hoá — không cần tạo bảng mới.

**Thiết kế AI/ML**
Dùng LLM để map câu trả lời tự do (VD: "đau khoảng nửa tiếng rồi") sang trường chuẩn hoá ("Thời gian khởi phát: 30 phút trước"). Prompt ràng buộc chỉ được trích xuất/diễn giải lại thông tin đã có trong câu trả lời, tuyệt đối không tự thêm chi tiết y khoa không có trong hội thoại. Nếu câu trả lời không đủ rõ để map vào field → đánh dấu `is_missing=true` thay vì đoán.

**Trường hợp đặc biệt và Xử lý lỗi**
Bệnh nhân trả lời mơ hồ, không map được vào field chuẩn → field đó đánh dấu "Thiếu thông tin" (is_missing=true), không chặn luồng tạo phiếu. Case bị ngắt giữa chừng do red-flag → phiếu tóm tắt vẫn được sinh từ các câu trả lời đã có tới thời điểm đó, không chờ đủ trường bắt buộc.

**Bảo mật và Quyền riêng tư**
Phiếu tóm tắt chứa dữ liệu PHI (triệu chứng, mức độ đau...) — chỉ nhân viên y tế được gán ca mới truy cập được qua API; hạn chế xuất hiện ở dạng plaintext không cần thiết trong log (liên quan add-on ẩn danh PII, FR-13).

### 3. Kế hoạch (Plan)

**Các bước thực hiện**
(1) định nghĩa format phiếu tóm tắt chuẩn theo từng nhóm triệu chứng, gồm cả cách hiển thị nguồn detect/grounding — (2) định nghĩa schema JSON kỹ thuật khớp format — (3) thêm cột summary_json vào bảng priority_flag — (4) implement logic map câu trả lời sang field chuẩn qua LLM, gắn kèm nguồn detect/grounding dùng cho từng field — (5) implement API trả phiếu tóm tắt trong response — (6) build UI hiển thị phiếu tóm tắt tại W-07 (bổ sung 2 dòng nguồn) — (7) Test với bộ test case, đối chiếu độ chính xác mapping.

**Công việc con (liên kết Backlog)**

**Phụ thuộc**
Phụ thuộc trực tiếp vào Feature #1 (AI Agent thu thập triệu chứng) vì cần checklist_responses làm nguồn dữ liệu đầu vào. 

**Timeline dự kiến**
03/08 → 08/08/2026 (Sprint 2, W2). 

**Kế hoạch kiểm thử**
Chạy trên bộ ≥20 test case (dùng chung với Feature #1), so sánh phiếu tóm tắt do agent sinh ra với phiếu do điều dưỡng tự tổng hợp thủ công. Tiêu chí: field bắt buộc phải khớp ≥90%; field không map được phải được đánh dấu "Thiếu thông tin" thay vì bỏ trống hoặc bịa.

**Kế hoạch triển khai**
Release cùng đợt với Feature #1 và #2 trong Demo 1 cuối Sprint 2, không tách giai đoạn vì đây là output trung gian bắt buộc giữa Agent và màn hình Duyệt ca.

**Tiêu chí thành công**
100% case đủ trường bắt buộc (hoặc bị red-flag) sinh được phiếu tóm tắt; ≥90% field bắt buộc map đúng so với điều dưỡng chuẩn; 0% trường hợp agent tự bịa thông tin không có trong hội thoại gốc.

**Rủi ro và Cách giảm thiểu**
LLM diễn giải sai/thêm chi tiết không có trong câu trả lời gốc khi map field → ràng buộc prompt chỉ trích xuất, không suy diễn, kèm review thủ công trên bộ test case để phát hiện sớm. Format phiếu tóm tắt thay đổi giữa chừng gây phải sửa lại schema JSON.

---


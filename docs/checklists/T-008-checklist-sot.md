# Checklist câu hỏi cố định — Nhóm Sốt

**Version:** 1.2
**Ngày soạn:** 04/08/2026
**Người soạn:** Thương 
**Liên kết:** `docs/prd.md` mục 3–4

## Lịch sử thay đổi
| Version | Ngày | Thay đổi | Lý do |
|---|---|---|---|
| 1.0 | 04/08/2026 | Khởi tạo: checklist câu hỏi, rule red-flag, mapping 3 mức ưu tiên | Thực hiện T-008 |
| 1.1 | 04/08/2026 | Bỏ phần câu hỏi bổ trợ; cập nhật căn cứ Bộ Y tế từ QĐ 3705/QĐ-BYT (2019, đã hết hiệu lực) sang QĐ 2760/QĐ-BYT (04/07/2023); bổ sung nguồn Mayo Clinic | Đồng bộ với văn bản pháp lý hiện hành, bổ sung nguồn tham khảo quốc tế |
| 1.2 | 04/08/2026 | Thêm lại `severe_abdominal_pain` vào checklist + rule red-flag; thêm lại `onset_duration` vào checklist; bỏ risk factor `antipyretic_response` khỏi mapping Khám sớm | Khớp lại với dấu hiệu cảnh báo Dengue (QĐ 2760/QĐ-BYT, Mayo Clinic) |

---

## Trạng thái

Nội dung dựa trên Emergency Severity Index (ESI), Manchester Triage System (MTS), trang thông tin sức khỏe Mayo Clinic (mayoclinic.org), và hướng dẫn chẩn đoán/điều trị sốt xuất huyết Dengue của Bộ Y tế VN (Quyết định 2760/QĐ-BYT ngày 04/07/2023 — thay thế Quyết định 3705/QĐ-BYT năm 2019 đã hết hiệu lực) — không phải kết luận lâm sàng có thẩm quyền.

## Nguyên tắc áp dụng

Checklist cố định, không hỏi ngoài phạm vi; red-flag escalate ngay không chờ hết checklist; AI chỉ đề xuất mức ưu tiên, không kết luận chẩn đoán; mọi kết quả đều cần điều dưỡng xác nhận trước khi gửi bệnh nhân.

**Thứ tự xử lý của agent:**
1. Hỏi lần lượt các câu ở Phần 1, nếu trong câu trả lời của bệnh nhân đã bao gồm câu trả lời cho các ý sau thì không cần hỏi lại.
2. Sau mỗi câu trả lời, kiểm tra ngay rule red-flag ở Phần 2 — nếu trigger, dừng checklist, hiển thị banner khẩn cấp và đẩy ca vào hàng đợi mức Cấp cứu.
3. Nếu hoàn thành hết Phần 1 mà không có red-flag nào trigger, áp dụng mapping logic ở Phần 3 để chọn giữa Khám sớm / Tự theo dõi.

---

## 1. Checklist bắt buộc (12 câu — mục tiêu hoàn thành <3 phút, ≥90% completion)

| # | Field | Câu hỏi | Loại trả lời |
|---|---|---|---|
| 1 | `patient_age_group` | Người đang bị sốt bao nhiêu tuổi ạ? | Dưới 1 tháng tuổi / 1–3 tháng tuổi / 3 tháng–3 tuổi / Trên 3 tuổi |
| 2 | `seizure_present` | Hiện tại có đang co giật, hoặc vừa co giật xong không? | Có / Không |
| 3 | `consciousness_level` | Có tỉnh táo bình thường không, hay đang lơ mơ, khó đánh thức, hoặc quấy khóc/kích động bất thường? | Tỉnh táo bình thường / Lơ mơ, khó đánh thức / Quấy khóc, kích động bất thường |
| 4 | `respiratory_distress` | Có thở nhanh, khó thở, hoặc môi/da tím tái không? | Có / Không |
| 5 | `neck_stiffness_photophobia` | Bạn có bị cứng cổ HOẶC rất sợ ánh sáng (kèm đau đầu dữ dội) không? Chỉ cần có 1 trong 2 dấu hiệu này. | Có / Không |
| 6 | `rash_present` | Trên da có xuất hiện nốt hoặc chấm đỏ bất thường không? | Có / Không |
| 7 | `bleeding_signs` | Có dấu hiệu chảy máu bất thường không, như chảy máu cam, chảy máu chân răng, nôn ra máu, hoặc đi ngoài phân đen/có máu? | Có / Không |
| 8 | `persistent_vomiting` | Có bị nôn nhiều lần không? | Nôn từ 3 lần trở lên trong vài giờ qua / Nôn 1–2 lần / Không nôn |
| 9 | `severe_abdominal_pain` | Có đau bụng dữ dội không? | Đau đến mức không làm được việc gì khác / Đau nhưng vẫn sinh hoạt được / Không đau |
| 10 | `measured_temperature_c` | Bạn có đo nhiệt độ không? Nếu có, nhiệt độ cao nhất là bao nhiêu? | Dưới 38°C / 38–39°C / Trên 39°C / Không đo được |
| 11 | `onset_duration` | Bạn bị sốt được bao lâu rồi ạ? | Dưới 6 giờ / 6–24 giờ / 1–3 ngày / Hơn 3 ngày |
| 12 | `underlying_condition` | Có đang mắc bệnh nền nào không, ví dụ tiểu đường, bệnh thận, đang hóa trị, hoặc suy giảm miễn dịch? | Có / Không / Không rõ |

## 2. Rule phát hiện Red-flag (escalate ngay, không chờ hoàn thành checklist — ADR-004)

| Điều kiện red-flag | Câu hỏi kích hoạt | Giá trị/ngưỡng kích hoạt | Hành động đề xuất |
|---|---|---|---|
| Co giật do sốt cao | `seizure_present` | = "Có" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Nghi viêm màng não | `neck_stiffness_photophobia` | = "Có" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Rối loạn ý thức | `consciousness_level` | = "Lơ mơ, khó đánh thức" HOẶC "Quấy khóc, kích động bất thường" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Suy hô hấp | `respiratory_distress` | = "Có" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Trẻ sơ sinh sốt | `patient_age_group` | = "Dưới 1 tháng tuổi" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Trẻ nhỏ sốt cao | `patient_age_group` + `measured_temperature_c` | "1–3 tháng tuổi" + "Trên 39°C" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Nghi nhiễm trùng huyết | `rash_present` | = "Có" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Xuất huyết bất thường | `bleeding_signs` | = "Có" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Cảnh báo Dengue — nôn nhiều | `persistent_vomiting` | = "Nôn từ 3 lần trở lên..." | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |
| Cảnh báo Dengue — đau bụng dữ dội | `severe_abdominal_pain` | = "Đau đến mức không làm được việc gì khác" | Banner khẩn cấp ngay + đẩy vào hàng đợi Cấp cứu |


## 3. Mapping logic — Khám sớm / Tự theo dõi (khi KHÔNG có red-flag nào trigger)

**Thứ tự đánh giá:** chỉ áp dụng bảng này sau khi đã kiểm tra hết Phần 2 và không có rule nào trigger.

### Risk factor cho mức "Khám sớm" (chỉ cần 1 điều kiện đúng — logic OR)

| # | Field | Giá trị kích hoạt | Lý do |
|---|---|---|---|
| 1 | `onset_duration` | = "Hơn 3 ngày" | Sốt kéo dài bất thường, quá ngưỡng tự khỏi thông thường của virus thông thường |
| 2 | `measured_temperature_c` | = "Trên 39°C" | Sốt cao dù chưa kèm dấu hiệu red-flag khác, vẫn cần khám sớm hơn theo dõi tại nhà |
| 3 | `underlying_condition` | = "Có" HOẶC "Không rõ" | Có bệnh nền (hoặc không chắc chắn) → tăng nguy cơ diễn tiến nặng dù triệu chứng bề mặt nhẹ |
| 4 | `patient_age_group` | = "1–3 tháng tuổi" | Trẻ sơ sinh có sốt luôn cần đánh giá y tế sớm, không bao giờ để ở mức Tự theo dõi |
| 5 | `seizure_history` (nếu có hỏi) | = "Đã từng" | Tiền sử co giật do sốt → nguy cơ tái phát, cần theo dõi y tế chặt hơn dù hiện tại chưa co giật |
| 6 | `recent_outbreak_exposure` (nếu có hỏi) | = "Có" | Yếu tố dịch tễ nghi sốt xuất huyết/bệnh truyền nhiễm, cần khám để loại trừ dù chưa có warning sign rõ |

### Điều kiện mức "Tự theo dõi"

Chỉ gán **Tự theo dõi** khi đồng thời thỏa mãn:
- Không có red-flag nào trigger (Phần 2), **và**
- Không có risk factor nào ở bảng trên trigger.

### Bảng tổng hợp 3 mức

| Mức ưu tiên | Điều kiện | Ghi chú |
|---|---|---|
| **Cấp cứu** | Có ≥1 rule red-flag ở Phần 2 trigger | Escalate ngay, không chờ hết checklist |
| **Khám sớm** | Không có red-flag, nhưng có ≥1 risk factor ở Phần 3 | Khuyến cáo đặt lịch khám sớm |
| **Tự theo dõi** | Không có red-flag và không có risk factor nào | Hướng dẫn tự theo dõi, tái khám nếu nặng hơn |

## 4. Tài liệu tham khảo
- https://media.emscimprovement.center/documents/Emergency_Severity_Index_Handbook.pdf
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5016055/
- https://www.researchgate.net/publication/50351023_Safety_of_the_Manchester_Triage_System_to_identify_less_urgent_patients_in_paediatric_emergence_care_a_prospective_observational_study
- https://medconnection.ucsfbenioffchildrens.org/febrile-infant-guidelines
- https://www.vinmec.com/vie/bai-viet/sot-o-tre-em-va-nguoi-lon-khi-nao-can-di-kham-vi
- https://www.mayoclinic.org/diseases-conditions/fever/symptoms-causes/syc-20352759 (Mayo Clinic — Fever: Symptoms & causes)
- https://www.mayoclinic.org/diseases-conditions/fever/diagnosis-treatment/drc-20352764 (Mayo Clinic — Fever: Diagnosis & treatment)
- https://www.mayoclinic.org/diseases-conditions/febrile-seizure/diagnosis-treatment/drc-20372527 (Mayo Clinic — Febrile seizure: Diagnosis & treatment)
- https://luatvietnam.vn/y-te/quyet-dinh-2760-qd-byt-2023-huong-dan-chan-doan-dieu-tri-sot-xuat-huyet-dengue-258941-d1.html 
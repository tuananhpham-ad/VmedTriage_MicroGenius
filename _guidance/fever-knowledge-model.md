# MEDICAL KNOWLEDGE MODEL — TRIỆU CHỨNG: SỐT (FEVER)

**Sản phẩm:** VMedTriage — AI Symptom Assessment & Triage
**Loại tài liệu:** Medical Knowledge Model (single source of truth cho Engineering / AI / Product / Medical Reviewer)
**Symptom group:** `FEVER`
**Phiên bản:** v1.0 — DRAFT (chưa được hội đồng chuyên môn phê duyệt)
**Ngày soạn:** 2026-08-10

---

## 0. Phạm vi, giới hạn và quy ước đọc tài liệu

### 0.1. Hệ thống LÀM gì và KHÔNG LÀM gì

| Hệ thống LÀM | Hệ thống KHÔNG LÀM |
|---|---|
| Thu thập triệu chứng có cấu trúc | Chẩn đoán bệnh (không đưa tên bệnh làm kết luận) |
| Phát hiện dấu hiệu nguy hiểm (red flag) | Kê đơn, chỉ định liều thuốc điều trị |
| Đánh giá mức độ khẩn cấp | Chỉ định xét nghiệm/hình ảnh |
| Phân 3 mức triage + hướng xử trí | Thay thế đánh giá của nhân viên y tế |
| Sinh phiếu tóm tắt cho điều dưỡng duyệt (HITL) | Tự động thông báo kết quả khi chưa có người duyệt |

> **Lưu ý quan trọng:** Tên bệnh (sốt xuất huyết, viêm màng não, nhiễm khuẩn huyết…) xuất hiện trong tài liệu này **chỉ để giải thích lý do lâm sàng**. Chúng **không được** hiển thị cho người bệnh dưới dạng kết luận chẩn đoán.

### 0.2. Ba mức triage (output duy nhất của hệ thống)

| Mã | Nhãn hiển thị | Ý nghĩa lâm sàng | Khung thời gian | Hành động gợi ý |
|---|---|---|---|---|
| `EMERGENCY` | Cấp cứu | Nguy cơ đe dọa tính mạng hoặc tổn thương cơ quan; cần đánh giá y tế ngay | **Ngay lập tức (0 giờ)** | Gọi 115 / đến khoa cấp cứu gần nhất; escalate ngay cho điều dưỡng |
| `EARLY_VISIT` | Khám sớm | Cần bác sĩ khám trực tiếp nhưng chưa có dấu hiệu đe dọa tính mạng tức thì | **Trong 24 giờ** (một số rule: trong 4–6 giờ) | Đặt lịch khám / đến cơ sở y tế trong ngày |
| `SELF_CARE` | Tự chăm sóc & theo dõi tại nhà | Nguy cơ thấp; chăm sóc triệu chứng + theo dõi có điều kiện quay lại | Theo dõi, tái đánh giá | Hướng dẫn chăm sóc + **danh sách safety-netting bắt buộc** |

**Nguyên tắc (invariant):** Mức triage cuối cùng = **mức cao nhất** trong tất cả rule khớp. Không có rule nào được phép *hạ* mức đã được đặt bởi rule khác. Nguyên tắc này lấy từ mô hình traffic-light của NICE NG143: "quản lý theo đặc điểm có nguy cơ cao nhất hiện diện".

### 0.3. Quy ước phân biệt EVIDENCE vs ENGINEERING

Toàn tài liệu dùng nhãn:

| Nhãn | Ý nghĩa |
|---|---|
| **[E]** — Evidence-based | Có nguồn guideline/y văn trực tiếp. |
| **[EN]** — Engineering recommendation | Do nhóm thiết kế đề xuất để hệ thống chạy được (ngưỡng kỹ thuật, cách xử lý dữ liệu thiếu, cấu trúc field, thứ tự hỏi).|
| **[LOCAL]** | Điều chỉnh theo bối cảnh Việt Nam (dịch tễ, văn bản Bộ Y tế).|

### 0.4. Ràng buộc "không chẩn đoán" ở tầng sinh ngôn ngữ **[EN]**

| Cấm | Thay bằng |
|---|---|
| "Bạn bị sốt xuất huyết" | "Các dấu hiệu bạn mô tả cần được bác sĩ khám ngay hôm nay" |
| "Có thể là viêm màng não" | "Có dấu hiệu cần loại trừ tình trạng nguy hiểm — cần cấp cứu" |
| "Nên uống kháng sinh" | "Bác sĩ sẽ quyết định thuốc phù hợp sau khi khám" |

Rule engine trả về `reason_codes` (mã dấu hiệu), **không** trả về `disease_codes`. Lớp NLG chỉ được diễn giải từ `reason_codes`.

### 0.5. Trạng thái pháp lý & an toàn **[EN]**

- Tài liệu là **thiết kế**, chưa phải sản phẩm đã thẩm định.
- Mọi kết quả `EMERGENCY` phải hiển thị **ngay** cho người dùng dưới dạng cảnh báo, **không chờ** duyệt HITL. Các mức còn lại chờ duyệt.

---

## PART 1 — ĐỊNH NGHĨA LÂM SÀNG CỦA SỐT

### 1.1. Định nghĩa nền

Sốt là tình trạng **tăng thân nhiệt trung tâm vượt quá dao động sinh lý bình thường trong ngày**, do điểm điều nhiệt (set-point) ở vùng dưới đồi bị nâng lên — tức là một **đáp ứng có điều hòa** của cơ thể. **[E]** (NICE NG143 mục định nghĩa)

Phân biệt — ảnh hưởng tới triage:

| Khái niệm | Cơ chế | Hệ quả triage |
|---|---|---|
| **Fever (sốt)** | Set-point tăng, cơ chế điều nhiệt còn nguyên vẹn | Triage theo bảng rule sốt |
| **Hyperthermia (tăng thân nhiệt bệnh lý)** — say nắng/say nóng, sốt do thuốc, hội chứng serotonin, tăng thân nhiệt ác tính | Set-point **không** đổi; sinh nhiệt vượt quá thải nhiệt | **Luôn `EMERGENCY`** nếu thân nhiệt cao + rối loạn tri giác + bối cảnh phơi nhiễm nhiệt/thuốc. Thuốc hạ sốt **không** hiệu quả. **[E]** |
| **Hypothermia (hạ thân nhiệt)** ở trẻ nhỏ/người già/người suy giảm miễn dịch | Mất khả năng đáp ứng sốt | Là **red flag tương đương sốt** **[E]** |

### 1.2. Sốt khách quan (objective fever)

Có **đo được nhiệt độ** bằng nhiệt kế, ghi nhận kèm **vị trí đo**.

| Vị trí đo | Ngưỡng gọi là sốt | Ghi chú |
|---|---|---|
| Trực tràng (rectal) | **≥ 38,0 °C** | Xấp xỉ thân nhiệt trung tâm tốt nhất trong các phương pháp không xâm lấn |
| Tai (infrared tympanic) | **≥ 38,0 °C** | Cần kỹ thuật đúng; sai số cao nếu ráy tai / kéo vành tai sai |
| Miệng (oral) | **≥ 37,8 – 38,0 °C** | Sai lệch nếu vừa ăn/uống nóng-lạnh, thở miệng |
| **Nách (axillary)** | **≥ 37,5 °C** | Thấp hơn thân nhiệt trung tâm trung bình ~0,5 °C; **là vị trí phổ biến nhất ở VN** **[LOCAL]** |
| Trán hồng ngoại không tiếp xúc | Không đặt ngưỡng chẩn đoán độc lập | Độ tin cậy thấp hơn; dùng để sàng lọc |

**Ngưỡng vận hành của hệ thống [EN] + [E]:**

```
is_fever_objective =
    (site ∈ {rectal, tympanic, oral, temporal} AND temp_c ≥ 38.0)
 OR (site == axillary                          AND temp_c ≥ 37.5)
```

**Các mốc nhiệt độ có ý nghĩa rule:**

| Mốc | Ý nghĩa | Nguồn |
|---|---|---|
| ≥ 38,0 °C ở trẻ **< 3 tháng** | Red flag tuyệt đối | NICE NG143 (traffic light: red); AAP 2021 (áp dụng cho trẻ 8–60 ngày, ngưỡng ≥38,0 °C / 100,4 °F) **[E]** |
| ≥ 39,0 °C ở trẻ **3–6 tháng** | Amber → `EARLY_VISIT` | NICE NG143 **[E]** |
| ≥ 38,5 °C | Ngưỡng cân nhắc dùng thuốc hạ sốt (không phải ngưỡng triage) | Bộ Y tế VN — QĐ 2760/QĐ-BYT **[LOCAL]** |
| ≥ 40,0 °C (đặc biệt ≥ 41 °C) | Cân nhắc hyperthermia; là amber trong nhiều thang, **[E]** yếu về giá trị tiên lượng đơn độc | Xem §1.6 |
| < 36,0 °C ở trẻ nhỏ / người cao tuổi / suy giảm miễn dịch | Red flag (hạ thân nhiệt) | NICE NG51 sepsis; IMCI **[E]** |

> **Điểm phải nhớ khi thiết kế rule:** **độ cao của sốt kém tương quan với mức độ nặng** ở phần lớn người bệnh. NICE NG143 nêu rõ **không dùng thời gian sốt để dự đoán khả năng bệnh nặng** (ngoại trừ mốc ≥5 ngày để cân nhắc bệnh Kawasaki). Vì vậy rule engine phải **ưu tiên dấu hiệu chức năng** (tri giác, hô hấp, tuần hoàn, mất nước) hơn con số nhiệt độ. **[E]**

### 1.3. Sốt chủ quan (subjective fever)

Người dùng **cảm thấy sốt / người nhà sờ thấy nóng** nhưng **không đo** hoặc không nhớ số đo.

**Nguyên tắc bắt buộc [E]:** NICE NG143 yêu cầu **coi trọng báo cáo sốt của cha mẹ/người chăm sóc** (kể cả khi không có số đo). Với VMedTriage — vốn là kênh **remote assessment**, không đo được sinh hiệu — đây là tình huống **thường gặp nhất**, không phải ngoại lệ.

**Xử lý [EN]:**

```
IF fever_reported == true AND temp_measured == null:
      fever_status = "SUBJECTIVE"
      → KHÔNG loại bỏ ca
      → KHÔNG hạ mức triage vì thiếu số đo
      → Rule dựa hoàn toàn vào red flag + nhóm nguy cơ + triệu chứng kèm
      → Nếu bệnh nhân thuộc nhóm nguy cơ cao (§Part 5): áp mức thận trọng như đã có sốt khách quan
```

Độ tin cậy của "sờ trán": độ nhạy khá (người chăm sóc phát hiện được phần lớn ca sốt thật) nhưng **độ đặc hiệu thấp** (nhiều dương tính giả). Hệ quả: dùng để **mở** nhánh hỏi, **không** dùng để loại trừ.

**Bắt buộc [EN]:** khi `fever_status = SUBJECTIVE`, hệ thống phải (a) hướng dẫn cách đo tại nhà, (b) đánh dấu `measurement_confidence = low` trên phiếu bàn giao để điều dưỡng biết.

### 1.4. Phương pháp đo & độ tin cậy

**Khuyến cáo phương pháp theo tuổi [E]** (NICE NG143):

| Nhóm tuổi | Phương pháp khuyến cáo | Không khuyến cáo |
|---|---|---|
| < 4 tuần tuổi | Nhiệt kế điện tử ở **nách** | Đo miệng, trực tràng thường quy |
| 4 tuần – 5 tuổi | Nhiệt kế điện tử ở nách, nhiệt kế dán hóa chất ở nách, hoặc hồng ngoại ở tai | Đo miệng/trực tràng thường quy; nhiệt kế dán hóa chất ở **trán** |
| > 5 tuổi & người lớn | Miệng, tai, nách, trán hồng ngoại đều chấp nhận được | — |

**Bảng độ tin cậy [E/EN]:**

| Phương pháp | Ưu | Nhược / nguồn sai số | `measurement_confidence` gợi ý |
|---|---|---|---|
| Trực tràng | Sát thân nhiệt trung tâm nhất | Xâm lấn, khó chấp nhận, chống chỉ định tương đối ở trẻ giảm bạch cầu hạt / giảm tiểu cầu | high |
| Điện tử nách | Rẻ, an toàn, phổ biến VN | Phụ thuộc thời gian giữ, mồ hôi, kẹp không kín; đọc thấp hơn thực tế | medium |
| Hồng ngoại tai | Nhanh | Kỹ thuật kéo vành tai, ráy tai, viêm tai; không dùng cho trẻ rất nhỏ ống tai hẹp | medium |
| Trán hồng ngoại không tiếp xúc | Nhanh, sàng lọc hàng loạt | Ảnh hưởng bởi mồ hôi, gió, điều hòa, vừa từ ngoài nắng vào | low |
| Dán hóa chất ở trán | — | **Không đáng tin cậy — không dùng [E]** | reject |
| Sờ tay (không đo) | Luôn sẵn có | Độ đặc hiệu thấp | subjective |


### 1.5. Các đặc trưng khác của sốt cần mô hình hóa

| Đặc trưng | Mô tả | Vì sao cần |
|---|---|---|
| Thời gian sốt (`fever_duration_days`) | Tính từ lần sốt đầu tiên | Mốc ≥5 ngày (Kawasaki, NICE) **[E]**; mốc ≥7 ngày (WHO IMCI: sốt kéo dài → chuyển tuyến đánh giá) **[E]**; mốc 3–7 ngày = giai đoạn nguy hiểm của SXHD **[LOCAL]** |
| Kiểu sốt (`fever_pattern`) | Liên tục / dao động / cơn / tái phát | Giá trị chẩn đoán hạn chế **[E]** nhưng "sốt cơn kèm rét run" hoặc "hết sốt rồi nặng lên" là tín hiệu quan trọng |
| Rét run dữ dội (`rigors`) | Run bần bật không kiểm soát được, đắp chăn không đỡ | Amber trong NICE NG143 (trẻ) **[E]**; gợi ý nhiễm khuẩn huyết / sốt rét ở người lớn |
| Đáp ứng thuốc hạ sốt (`antipyretic_response`) | Có hạ / không hạ | **KHÔNG dùng để loại trừ bệnh nặng [E]** — đây là sai lầm phổ biến. Chỉ ghi nhận mô tả. |
| **"Khó chịu hơn dù đã hạ sốt"** | Người bệnh mệt/li bì hơn sau khi hết sốt | **Dấu hiệu cần khám lại ngay theo QĐ 2760/QĐ-BYT** — đặc biệt quan trọng ở VN vì trùng thời điểm vào giai đoạn nguy hiểm của SXHD **[LOCAL][E]** |

### 1.6. Quần thể đặc biệt — định nghĩa sốt **thay đổi**

| Quần thể | Định nghĩa/ngưỡng riêng | Nguồn |
|---|---|---|
| **Trẻ < 3 tháng** | Bất kỳ nhiệt độ ≥ 38,0 °C = tình trạng nguy cơ cao, không phân biệt vẻ ngoài "vẫn chơi ngoan" | NICE NG143 (red); AAP 2021 (8–60 ngày, ≥38,0 °C, và guideline **chỉ áp dụng cho trẻ trông khỏe** — trẻ trông mệt nằm ngoài phạm vi, tức càng nặng hơn) **[E]** |
| **Trẻ sơ sinh < 28 ngày** | Như trên; ngoài ra **hạ thân nhiệt < 36 °C cũng là dấu hiệu nặng** | AAP/NICE **[E]** |
| **Trẻ 3–6 tháng** | ≥ 39,0 °C → nguy cơ trung gian | NICE NG143 **[E]** |
| **Người giảm bạch cầu hạt (neutropenia) / đang hóa trị** | Sốt = **một lần đo ≥ 38,3 °C** *hoặc* **≥ 38,0 °C kéo dài ≥ 1 giờ** | Định nghĩa kinh điển IDSA về febrile neutropenia **[E]** |
| **Người cao tuổi (≥ 65–75)** | **Đáp ứng sốt bị cùn** — có thể nhiễm khuẩn nặng mà nhiệt độ chỉ tăng nhẹ hoặc không sốt. Thay đổi tri giác/té ngã/ăn kém có thể là biểu hiện duy nhất | Y văn lão khoa; NICE NG51 xếp ≥75 tuổi là yếu tố nguy cơ sepsis **[E]** |
| **Phụ nữ mang thai** | Ngưỡng nhiệt độ như người lớn, **nhưng sinh lý nền khác**: 3 tháng cuối mạch nhanh hơn 10–15 l/ph, HA tâm thu thấp hơn 5–10 mmHg, Hct giảm → **dấu hiệu sốc xuất hiện muộn** | QĐ 2760/QĐ-BYT **[LOCAL][E]** |
| **Người suy giảm miễn dịch (HIV, ghép tạng, corticoid kéo dài, thuốc sinh học, cắt lách)** | Có thể **không sốt** dù nhiễm khuẩn nặng; ngược lại sốt đơn độc cũng đã là dấu hiệu nguy cơ cao | NICE NG51; y văn nhiễm trùng **[E]** |
| **Người có bệnh mạn tính nặng, thalassemia** | Ngưỡng như thường nhưng diễn tiến nặng nhanh hơn | QĐ 2760/QĐ-BYT nêu riêng thalassemia trong SXHD **[LOCAL]** |
| **Trẻ có chậm phát triển / khuyết tật học tập** | Cần diễn giải thang traffic light **theo mức nền của trẻ** | NICE NG143 **[E]** |

---

## PART 2 — CÁC KHÁI NIỆM LÂM SÀNG (CLINICAL CONCEPTS)

Nhóm khái niệm dưới đây là **ontology** để engineering đặt tên field và AI đặt câu hỏi. Mỗi khái niệm ghi rõ **vì sao thu thập**.

### Nhóm A — Đặc điểm của sốt (Fever characteristics)

| Khái niệm | Vì sao quan trọng |
|---|---|
| Có sốt (khách quan/chủ quan) | Cổng vào của toàn bộ protocol; xác định nhánh hỏi |
| Nhiệt độ đo được + đơn vị | Đầu vào cho rule ngưỡng theo tuổi |
| **Vị trí đo** | Không có vị trí thì con số vô nghĩa (chênh tới 0,5–1 °C) |
| Thời điểm đo gần nhất | Số đo cũ 8 giờ trước không phản ánh hiện trạng |
| Thời gian sốt (ngày) | Mốc ≥5 ngày (Kawasaki), ≥7 ngày (IMCI), 3–7 ngày (giai đoạn nguy hiểm SXHD) |
| Kiểu sốt / rét run | Rét run dữ dội = amber; gợi ý nhiễm khuẩn huyết, sốt rét |
| Đã dùng thuốc hạ sốt & đáp ứng | Nhiệt độ hiện tại có thể bị "che"; **không** dùng để loại trừ bệnh nặng |
| Hạ thân nhiệt (< 36 °C) | Dấu hiệu nặng, không phải dấu hiệu hồi phục |
| Sốt tái phát sau khi đã hết | Gợi ý diễn tiến hai pha (đặc trưng nhiều bệnh do virus, kể cả SXHD) |

### Nhóm B — Tình trạng toàn thân & tri giác (General appearance)

| Khái niệm | Vì sao quan trọng |
|---|---|
| Mức độ tỉnh táo / đáp ứng | **Yếu tố tiên lượng mạnh nhất** trong mọi thang triage; li bì/khó đánh thức = red |
| Đáp ứng xã hội ở trẻ (cười, giao tiếp mắt, khóc bình thường) | Cấu phần lõi của traffic light NICE; thay thế được cho khám thực thể trong remote assessment |
| Lú lẫn mới xuất hiện / thay đổi hành vi | Ở người lớn & người cao tuổi, đây có thể là biểu hiện **duy nhất** của nhiễm khuẩn nặng |
| Khả năng ăn/uống/bú | IMCI general danger sign: **không uống được/không bú được** → chuyển viện khẩn |
| Mức độ hoạt động so với ngày thường | Chuẩn hóa theo baseline cá nhân, quan trọng ở trẻ khuyết tật/người già |
| **Mức độ lo lắng của người chăm sóc** | NICE ghi nhận "carer/clinician concern" là tín hiệu độc lập có giá trị — **phải mô hình hóa thành field** |

### Nhóm C — Hô hấp

| Khái niệm | Vì sao quan trọng |
|---|---|
| Khó thở / thở nhanh / thở gắng sức | Cấu phần red-amber của traffic light; đầu vào của rule sốc/nhiễm khuẩn nặng |
| Rút lõm lồng ngực, phập phồng cánh mũi, thở rên (grunting) | Dấu hiệu suy hô hấp ở trẻ → red |
| Tím môi/đầu chi | Red tuyệt đối |
| Thở rít thì hít vào (stridor) / chảy dãi, không nuốt được, ngồi chồm ra trước | Nghi tắc nghẽn đường thở trên → cấp cứu, **không** yêu cầu người nhà há miệng khám họng |
| Đau ngực, ho ra máu | Mở rộng sang protocol đau ngực/khó thở (cross-protocol) |
| SpO₂ (nếu tự đo được) | Bổ trợ; ≤ 95% khí trời là amber ở trẻ. Lưu ý sai số ở da sẫm màu |

### Nhóm D — Tuần hoàn & mất nước

| Khái niệm | Vì sao quan trọng |
|---|---|
| Da lạnh ẩm, nổi vân tím, đầu chi lạnh | Dấu hiệu sốc — red |
| Thời gian làm đầy mao mạch (CRT) ≥ 3 giây | Amber/red; hướng dẫn người dùng tự đo được (ấn móng tay/ức) |
| Mạch nhanh, yếu / choáng khi đứng dậy | Giảm thể tích tuần hoàn |
| Lượng nước tiểu (số lần/tã ướt); **không tiểu > 6 giờ** | Chỉ dấu tưới máu thận; QĐ 2760 dùng mốc **6 giờ** làm dấu hiệu khám lại ngay **[LOCAL]** |
| Môi khô, mắt trũng, khóc không nước mắt, thóp lõm | Mất nước ở trẻ |
| Nôn nhiều / không giữ được nước | IMCI danger sign "nôn tất cả mọi thứ"; cũng là dấu hiệu cảnh báo SXHD |

### Nhóm E — Thần kinh

| Khái niệm | Vì sao quan trọng |
|---|---|
| Co giật (đang co giật / vừa co giật) | IMCI general danger sign → cấp cứu |
| Đặc điểm cơn: khu trú, kéo dài > 5 phút, tái diễn, tuổi < 6 tháng hoặc > 6 tuổi | Phân biệt co giật do sốt đơn thuần và co giật phức tạp; NICE nâng mức nguy cơ với co giật khu trú/trạng thái động kinh |
| Cứng gáy, sợ ánh sáng, đau đầu dữ dội | Nghi nhiễm khuẩn thần kinh trung ương → cấp cứu |
| Thóp phồng ở trẻ nhũ nhi | Red trong NICE NG143 |
| Yếu liệt khu trú, nói khó | Cross-protocol sang đột quỵ/viêm não |

### Nhóm F — Da & niêm mạc

| Khái niệm | Vì sao quan trọng |
|---|---|
| **Ban không mất khi ấn kính (non-blanching)** | Red flag kinh điển nghi nhiễm não mô cầu; NICE nhấn mạnh, đặc biệt kèm ban tử ban > 2 mm, CRT ≥ 3 s, cứng gáy |
| Ban khác (dạng sởi, mề đay, phỏng nước) | Định hướng mức độ; tay chân miệng nằm trong chẩn đoán phân biệt của BYT |
| Chấm/mảng xuất huyết dưới da | Dấu hiệu SXHD **[LOCAL]** |
| Chảy máu chân răng, chảy máu mũi, nôn ra máu, phân đen, rong kinh | **Xuất huyết niêm mạc = dấu hiệu cảnh báo SXHD → nhập viện [LOCAL][E]** |
| Sưng nóng đỏ khu trú, vết loét, áp xe, viêm mô tế bào | Ổ nhiễm khuẩn khu trú cần khám |
| Vàng da mới xuất hiện | Tổn thương gan / nhiễm khuẩn nặng |

### Nhóm G — Triệu chứng kèm theo theo cơ quan (Associated symptoms)

| Nhóm | Ví dụ | Vì sao |
|---|---|---|
| Tiêu hóa | Đau bụng (vị trí, mức độ), nôn, tiêu chảy, phân máu | Đau bụng nhiều + nôn nhiều = dấu hiệu cảnh báo SXHD; bụng ngoại khoa cấp |
| Tiết niệu | Tiểu buốt, tiểu rắt, đau hông lưng | NICE khuyến cáo **luôn nghĩ tới nhiễm khuẩn tiết niệu ở trẻ < 5 tuổi sốt không rõ ổ** — nên bắt buộc hỏi |
| Hô hấp trên | Đau họng, chảy mũi, đau tai | Định hướng ổ nhiễm khuẩn lành tính hơn |
| Cơ xương khớp | **Sưng đau khớp/chi, không chịu đi, không dùng tay chân** | Amber NICE — nghi nhiễm khuẩn xương khớp, dễ bỏ sót |
| Toàn thân | Đau cơ, đau hốc mắt, đau đầu | Bộ triệu chứng gợi ý bệnh do virus lưu hành tại VN |

### Nhóm H — Cờ đỏ (Red flags)

→ Xem chi tiết **Part 4**. Ở tầng ontology, red flag được mô hình hóa là **các field boolean độc lập**, không nhét chung vào một trường text.

### Nhóm I — Tiền sử bệnh (Medical history)

| Khái niệm | Vì sao |
|---|---|
| Bệnh mạn tính: tim, phổi (hen/COPD), gan, thận, đái tháo đường, bệnh máu/thalassemia | QĐ 2760 liệt kê đây là lý do **cân nhắc nhập viện** dù sốt chưa nặng **[LOCAL]**; NICE NG51 xếp là yếu tố nguy cơ sepsis |
| Bệnh lý thần kinh, động kinh | Diễn giải co giật khác đi |
| Suy dinh dưỡng / béo phì | Béo phì làm khó đánh giá & tăng nặng trong SXHD **[LOCAL]** |
| Tiền sử co giật do sốt | Giảm hoảng loạn nhưng **không** hạ mức nếu cơn bất thường |
| Đã từng nằm viện vì bệnh tương tự | Chỉ dấu mức độ nặng cá nhân |

### Nhóm J — Yếu tố nguy cơ & bối cảnh xã hội (Risk factors)

| Khái niệm | Vì sao |
|---|---|
| Tuổi (đặc biệt < 3 tháng, < 5 tuổi, ≥ 65/75) | Biến số nguy cơ mạnh nhất sau tri giác |
| **Sống một mình / không ai theo dõi** | QĐ 2760 nêu là lý do cân nhắc nhập viện — vì self-care an toàn **phụ thuộc người theo dõi** **[LOCAL]** |
| **Khoảng cách tới cơ sở y tế / khả năng đến viện kịp khi trở nặng** | Cùng nguồn trên; ảnh hưởng trực tiếp tới việc có được cho `SELF_CARE` hay không |
| Khả năng tái khám/theo dõi | Điều kiện tiên quyết của safety-netting |
| Tình trạng tiêm chủng | Trẻ chưa tiêm chủng đủ → nguy cơ bệnh có thể phòng ngừa; NICE lưu ý **một số vắc-xin gây sốt ở trẻ < 3 tháng** (yếu tố nhiễu) |

### Nhóm K — Tiền sử phơi nhiễm & dịch tễ (Exposure history) **[LOCAL rất quan trọng]**

| Khái niệm | Vì sao |
|---|---|
| Người xung quanh/khu vực đang có dịch (SXHD, cúm, sởi, tay chân miệng…) | Thay đổi xác suất nền; QĐ 2760 có phụ lục riêng về xử trí tại tuyến cơ sở **khi có dịch** |
| Muỗi đốt / khu vực có SXHD | Kích hoạt bộ câu hỏi dấu hiệu cảnh báo SXHD |
| Tiếp xúc người bệnh lao/sởi/thủy đậu | An toàn cộng đồng + định hướng |
| Tiếp xúc động vật, gia cầm, chuột, lợn bệnh, chó mèo cào cắn | Bệnh lây từ động vật (liên cầu lợn nằm trong chẩn đoán phân biệt của BYT) |
| Nguồn nước/lũ lụt, lội nước bẩn | Bệnh do Leptospira sau mưa lũ |
| Ăn uống không đảm bảo / bệnh cùng lúc trong gia đình | Ngộ độc, bệnh lây qua đường tiêu hóa |

### Nhóm L — Tiền sử du lịch (Recent travel)

| Khái niệm | Vì sao |
|---|---|
| Nơi đến & thời gian trong **12 tháng** (nhấn mạnh 1 tháng gần nhất) | **Sốt sau khi trở về từ vùng sốt rét lưu hành là cấp cứu tiềm tàng** — sốt rét ác tính diễn tiến tử vong trong vài ngày. BYT xếp sốt rét trong chẩn đoán phân biệt sốt |
| Du lịch quốc tế / vùng có dịch đang bùng phát | Bệnh truyền nhiễm cần khai báo, ảnh hưởng an toàn cộng đồng |
| Có dùng thuốc dự phòng sốt rét không | Không loại trừ được bệnh nhưng ảnh hưởng cách diễn giải |

### Nhóm M — Thai kỳ & hậu sản (Pregnancy)

| Khái niệm | Vì sao |
|---|---|
| Đang mang thai / tuần thai | Sinh lý nền che lấp dấu hiệu sốc; SXHD ở thai phụ nặng hơn, dễ biến chứng chảy máu **[LOCAL]** |
| Sinh/sảy/nạo hút trong 6 tuần | Nguy cơ nhiễm khuẩn hậu sản — NICE NG51 có nhánh riêng cho người đang/vừa mang thai |
| Đau bụng, ra máu/dịch âm đạo, giảm cử động thai | Nâng mức khẩn cấp; cross-protocol sản khoa |

### Nhóm N — Suy giảm miễn dịch (Immunocompromised status)

| Khái niệm | Vì sao |
|---|---|
| Đang hóa trị / xạ trị (đặc biệt **trong 6 tuần gần đây**) | Sốt giảm bạch cầu hạt là **cấp cứu nội khoa** — chậm kháng sinh làm tăng tử vong |
| Ghép tạng/tủy, đang dùng thuốc ức chế miễn dịch | Diễn tiến nhanh, biểu hiện nghèo nàn |
| Corticoid liều cao/kéo dài, thuốc sinh học | Che lấp triệu chứng viêm |
| HIV không kiểm soát | Nhiễm trùng cơ hội |
| Cắt lách / không có lách chức năng | Nguy cơ nhiễm khuẩn tối cấp do vi khuẩn có vỏ |
| Suy dinh dưỡng nặng, đái tháo đường kiểm soát kém | Nguy cơ nhiễm khuẩn nặng |

### Nhóm O — Phẫu thuật/thủ thuật & thiết bị y tế (Recent surgery / devices)

| Khái niệm | Vì sao |
|---|---|
| Phẫu thuật/thủ thuật xâm lấn trong **30 ngày** (NICE NG51 dùng mốc 6 tuần cho một số bối cảnh) | Nhiễm khuẩn vết mổ, áp xe sâu — NICE xếp là yếu tố nguy cơ sepsis |
| Vết mổ sưng đỏ, chảy dịch, hở | Ổ nhiễm khuẩn rõ |
| Catheter tĩnh mạch trung tâm, sonde tiểu, dẫn lưu, van dẫn lưu não thất | Đường vào nhiễm khuẩn; sốt + thiết bị = nguy cơ cao |
| Chấn thương/vết thương hở, bỏng, vết cắn động vật | Uốn ván, nhiễm khuẩn mô mềm |
| Tiêm chích, thủ thuật thẩm mỹ gần đây | Ổ nhiễm khuẩn/nhiễm khuẩn huyết |

### Nhóm P — Thuốc đang dùng (Medication history)

| Khái niệm | Vì sao |
|---|---|
| Thuốc hạ sốt đã dùng: loại, liều, thời điểm | Nguy cơ **quá liều paracetamol** (BYT: tổng liều ≤ 60 mg/kg/24 giờ); che lấp nhiệt độ |
| **NSAID/aspirin/ibuprofen** | **Cấm trong SXHD** theo QĐ 2760 (tăng nguy cơ xuất huyết, toan máu). Vì VN là vùng SXHD lưu hành, hệ thống **không được** gợi ý NSAID khi chưa loại trừ **[LOCAL] — đây là ràng buộc an toàn bắt buộc** |
| Kháng sinh đang dùng / tự mua | Sốt dai dẳng dù dùng kháng sinh = tín hiệu cần khám |
| Thuốc ức chế miễn dịch, corticoid | Xem nhóm N |
| Thuốc mới bắt đầu trong 4–6 tuần | Sốt do thuốc; hội chứng serotonin/an thần kinh ác tính (kèm cứng cơ, kích thích) |
| Dị ứng thuốc đã biết | An toàn cho tuyến sau |
| Chống đông | Diễn giải chảy máu khác đi |

### Nhóm Q — Metadata phiên đánh giá **[EN]**

| Khái niệm | Vì sao |
|---|---|
| Người khai là ai (bản thân / người nhà) | Độ tin cậy thông tin; trẻ em luôn do người khác khai |
| Độ tin cậy tự đánh giá / thông tin mâu thuẫn | Charter yêu cầu "xử lý thông tin thiếu/mâu thuẫn bằng câu hỏi làm rõ" |
| Trường không trả lời / "không biết" | Bắt buộc phân biệt `false` và `unknown` (xem §3.1) |
| Thời điểm bắt đầu/kết thúc phiên | Audit, tái đánh giá |

---

## PART 3 — INFORMATION MODEL (MÔ HÌNH THÔNG TIN)

### 3.1. Quy ước dữ liệu bắt buộc **[EN]**

1. **Tri-state cho mọi câu hỏi có/không:** `true` | `false` | `unknown`. **Cấm** map `unknown → false`. Đây là quyết định an toàn quan trọng nhất của mô hình dữ liệu: "chưa hỏi được" không đồng nghĩa "không có".
2. **Xử lý `unknown` với red flag:** nếu một red flag critical còn `unknown` **và** người bệnh thuộc nhóm nguy cơ cao → rule engine **nâng** mức lên `EARLY_VISIT` tối thiểu và đánh dấu `data_gap = true` để điều dưỡng hỏi thêm ("Ask more").
3. **Mandatory (M)** = không được kết luận triage nếu thiếu. **Conditional (C)** = bắt buộc khi điều kiện kích hoạt. **Optional (O)** = làm giàu thông tin.
4. Mọi trường thời gian dùng ISO-8601; nhiệt độ dùng **°C**, một chữ số thập phân.
5. Trường tự do (`*_note`) **không** được dùng làm đầu vào rule cứng; chỉ hiển thị cho người duyệt.

### 3.2. Nhóm PATIENT — Nhân khẩu & bối cảnh

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `patient_id` | Định danh nội bộ | Truy vết, audit | string (uuid) | — | M | `"9f3a…"` |
| `reporter_type` | Ai đang khai báo | Độ tin cậy dữ liệu | enum | `self`, `parent_caregiver`, `other` | M | `"parent_caregiver"` |
| `age_value` + `age_unit` | Tuổi | **Biến phân tầng chính**: <28 ngày, <3 tháng, 3–6 tháng, <5 tuổi, ≥65, ≥75 | number + enum | unit: `day`, `month`, `year` | M | `45` + `"day"` |
| `sex` | Giới tính sinh học | Diễn giải nhánh sản khoa/tiết niệu | enum | `male`, `female`, `unknown` | M | `"female"` |
| `weight_kg` | Cân nặng | Chỉ dùng để cảnh báo quá liều paracetamol; **không** dùng tính liều điều trị | number | 0.5–300 | O | `18.5` |
| `lives_alone` | Sống một mình | Điều kiện an toàn của `SELF_CARE` | boolean/tri | true/false/unknown | M | `false` |
| `caregiver_available` | Có người theo dõi 24h | Như trên | tri-state | — | M | `true` |
| `access_to_care_minutes` | Thời gian tới cơ sở y tế gần nhất | Ảnh hưởng ngưỡng thận trọng | integer (phút) | 0–1440 | O | `20` |
| `can_return_for_followup` | Có thể tái khám khi trở nặng | Tiền đề safety-netting | tri-state | — | C (khi hướng `SELF_CARE`) | `true` |

### 3.3. Nhóm FEVER — Đặc điểm sốt

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `fever_reported` | Người dùng khai có sốt | Cổng vào protocol | boolean | true/false | M | `true` |
| `fever_status` | Loại sốt | Điều hướng nhánh xử lý dữ liệu thiếu | enum | `objective`, `subjective`, `none` | M | `"subjective"` |
| `temp_c` | Nhiệt độ đo được | Đầu vào rule ngưỡng | number (1 dp) | 30.0–43.0 | C (khi `objective`) | `38.7` |
| `temp_site` | Vị trí đo | **Quyết định ngưỡng áp dụng** | enum | `axillary`, `oral`, `rectal`, `tympanic`, `temporal`, `unknown` | C | `"axillary"` |
| `temp_measured_at` | Thời điểm đo | Số đo cũ → độ tin cậy thấp | datetime | ISO-8601 | C | `"2026-08-10T07:20+07:00"` |
| `temp_device_type` | Loại nhiệt kế | Gán `measurement_confidence` | enum | `digital`, `infrared_ear`, `infrared_forehead`, `mercury_glass`, `chemical_dot`, `unknown` | O | `"digital"` |
| `measurement_confidence` | Độ tin cậy số đo (hệ thống tự gán) | Hiển thị cho điều dưỡng | enum | `high`, `medium`, `low`, `subjective` | M (derived) | `"medium"` |
| `temp_max_24h_c` | Nhiệt độ cao nhất 24 giờ qua | Bắt được đỉnh sốt bị che bởi thuốc | number | 30.0–43.0 | O | `39.4` |
| `fever_onset_at` | Thời điểm bắt đầu sốt | Tính `fever_duration_days` | date | ISO-8601 | M | `"2026-08-07"` |
| `fever_duration_days` | Số ngày sốt (derived) | Mốc 5 ngày / 7 ngày / 3–7 ngày | integer | 0–365 | M (derived) | `3` |
| `fever_pattern` | Kiểu sốt | Mô tả, giá trị hạn chế | enum | `continuous`, `intermittent`, `relapsing`, `unknown` | O | `"continuous"` |
| `rigors` | Rét run dữ dội | Amber (NICE); gợi ý nhiễm khuẩn huyết/sốt rét | tri-state | — | M | `true` |
| `hypothermia_reported` | Nhiệt độ < 36 °C | **Red flag**, không phải cải thiện | tri-state | — | C (nhóm nguy cơ) | `false` |
| `antipyretic_taken` | Đã dùng thuốc hạ sốt | Nhiệt độ hiện tại có thể bị che | tri-state | — | M | `true` |
| `antipyretic_drug` | Tên hoạt chất | **Sàng lọc NSAID trong bối cảnh SXHD** | enum | `paracetamol`, `ibuprofen`, `aspirin`, `other`, `unknown` | C | `"ibuprofen"` |
| `antipyretic_total_24h_mg` | Tổng liều 24h | Cảnh báo quá liều paracetamol | number | ≥0 | O | `3000` |
| `antipyretic_response` | Có hạ sau khi uống | **Không dùng để loại trừ bệnh nặng** | enum | `resolved`, `partial`, `none`, `unknown` | O | `"partial"` |
| `worse_after_defervescence` | Mệt/khó chịu hơn dù đã hạ sốt | **Dấu hiệu khám lại ngay (QĐ 2760)** | tri-state | — | M | `true` |

### 3.4. Nhóm GENERAL — Tri giác & toàn trạng

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `consciousness_level` | Mức tỉnh táo | Yếu tố tiên lượng mạnh nhất | enum | `alert`, `drowsy_but_rousable`, `difficult_to_rouse`, `unresponsive`, `unknown` | M | `"alert"` |
| `new_confusion` | Lú lẫn/thay đổi hành vi mới | Có thể là biểu hiện duy nhất ở người già | tri-state | — | M | `false` |
| `social_response_child` | Đáp ứng xã hội của trẻ | Lõi traffic light NICE | enum | `normal`, `reduced`, `no_response`, `not_applicable` | C (tuổi < 5) | `"reduced"` |
| `activity_vs_baseline` | Hoạt động so với thường ngày | Chuẩn hóa theo baseline | enum | `normal`, `reduced`, `markedly_reduced`, `unknown` | M | `"reduced"` |
| `feeding_intake` | Ăn/uống/bú | IMCI danger sign | enum | `normal`, `reduced`, `unable`, `unknown` | M | `"reduced"` |
| `caregiver_concern_level` | Mức lo lắng của người chăm sóc | Tín hiệu độc lập có giá trị (NICE) | integer | 0–10 | M | `8` |
| `looks_very_unwell` | "Trông rất mệt/khác hẳn thường ngày" | Proxy cho ill-appearance khi không khám được | tri-state | — | M | `true` |

### 3.5. Nhóm RESPIRATORY

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `breathing_difficulty` | Khó thở | Cấu phần red/amber | enum | `none`, `mild`, `severe`, `unknown` | M | `"none"` |
| `rapid_breathing` | Thở nhanh hơn bình thường | Dấu hiệu nặng, dễ nhận biết từ xa | tri-state | — | M | `false` |
| `chest_indrawing` | Rút lõm lồng ngực | Suy hô hấp ở trẻ → red | tri-state | — | C (tuổi < 5) | `false` |
| `nasal_flaring_grunting` | Phập phồng cánh mũi / thở rên | Red ở trẻ | tri-state | — | C (tuổi < 5) | `false` |
| `cyanosis` | Tím môi/đầu chi | Red tuyệt đối | tri-state | — | M | `false` |
| `stridor_or_drooling` | Thở rít / chảy dãi, không nuốt được | Nghi tắc nghẽn đường thở trên | tri-state | — | M | `false` |
| `chest_pain` | Đau ngực | Cross-protocol | tri-state | — | M | `false` |
| `hemoptysis` | Ho ra máu | Cần khám | tri-state | — | O | `false` |
| `spo2_percent` | SpO₂ tự đo | Bổ trợ; ≤95% khí trời = amber ở trẻ | integer | 50–100 | O | `97` |

### 3.6. Nhóm CIRCULATION & HYDRATION

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `cold_clammy_skin` | Da lạnh, ẩm, nổi vân tím | Dấu hiệu sốc → red | tri-state | — | M | `false` |
| `capillary_refill_ge_3s` | CRT ≥ 3 giây | Amber/red; người dùng tự làm được | tri-state | — | M | `false` |
| `dizziness_on_standing` | Choáng khi đứng dậy | Giảm thể tích | tri-state | — | M | `true` |
| `urine_output` | Lượng nước tiểu | Tưới máu thận | enum | `normal`, `reduced`, `none_gt_6h`, `unknown` | M | `"reduced"` |
| `dehydration_signs` | Dấu mất nước | Đa dấu hiệu | array[enum] | `dry_mouth`, `sunken_eyes`, `no_tears`, `sunken_fontanelle`, `reduced_skin_turgor` | O | `["dry_mouth"]` |
| `vomiting_severity` | Mức độ nôn | "Nôn tất cả" = danger sign; "nôn nhiều" = cảnh báo SXHD | enum | `none`, `occasional`, `frequent`, `unable_to_keep_fluids` | M | `"frequent"` |

### 3.7. Nhóm NEUROLOGICAL

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `seizure_occurred` | Có co giật trong đợt bệnh này | IMCI danger sign | tri-state | — | M | `false` |
| `seizure_active_now` | Đang co giật | Cấp cứu tối khẩn | tri-state | — | C | `false` |
| `seizure_features` | Đặc điểm cơn | Phân biệt cơn phức tạp | array[enum] | `focal`, `duration_gt_5min`, `recurrent_24h`, `incomplete_recovery` | C | `["focal"]` |
| `neck_stiffness` | Cứng gáy | Nghi nhiễm khuẩn TKTW | tri-state | — | M | `false` |
| `photophobia` | Sợ ánh sáng | Đi kèm cứng gáy | tri-state | — | O | `false` |
| `severe_headache` | Đau đầu dữ dội/khác thường | Cross-protocol đau đầu | tri-state | — | M | `false` |
| `bulging_fontanelle` | Thóp phồng | Red ở nhũ nhi | tri-state | — | C (tuổi < 18 tháng) | `false` |
| `focal_neuro_deficit` | Yếu liệt/nói khó mới | Cross-protocol đột quỵ/viêm não | tri-state | — | M | `false` |

### 3.8. Nhóm SKIN & BLEEDING

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `non_blanching_rash` | Ban không mất khi ấn kính | **Red flag kinh điển** | tri-state | — | M | `false` |
| `rash_present` | Có ban | Định hướng | tri-state | — | M | `true` |
| `rash_type` | Kiểu ban | Mô tả cho người duyệt | enum | `petechial`, `maculopapular`, `vesicular`, `urticarial`, `other`, `unknown` | C | `"petechial"` |
| `mucosal_bleeding` | Chảy máu chân răng/mũi/âm đạo bất thường | **Dấu hiệu cảnh báo SXHD → nhập viện** | tri-state | — | M | `false` |
| `gi_bleeding` | Nôn ra máu / phân đen | Xuất huyết nặng | tri-state | — | M | `false` |
| `jaundice_new` | Vàng da mới | Tổn thương gan/nhiễm khuẩn nặng | tri-state | — | O | `false` |
| `localized_infection_signs` | Sưng nóng đỏ khu trú/áp xe/vết loét | Ổ nhiễm khuẩn | tri-state | — | O | `false` |

### 3.9. Nhóm ASSOCIATED SYMPTOMS

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `abdominal_pain_severity` | Mức độ đau bụng | Đau bụng nhiều = cảnh báo SXHD; bụng ngoại khoa | enum | `none`, `mild`, `moderate`, `severe` | M | `"severe"` |
| `abdominal_pain_location` | Vị trí | Định hướng | enum | `diffuse`, `ruq`, `rlq`, `epigastric`, `other`, `unknown` | C | `"ruq"` |
| `abdominal_guarding` | Bụng cứng/ấn rất đau | Nghi bụng ngoại khoa | tri-state | — | C | `false` |
| `diarrhea` | Tiêu chảy | Mất nước, nguồn nhiễm | tri-state | — | M | `true` |
| `bloody_stool` | Phân máu | Cần khám | tri-state | — | C | `false` |
| `urinary_symptoms` | Tiểu buốt/rắt/đau hông lưng | **Bắt buộc hỏi ở trẻ <5 tuổi sốt không rõ ổ (NICE)** | tri-state | — | M | `false` |
| `sore_throat` / `ear_pain` / `cough` | Triệu chứng hô hấp trên | Định hướng ổ nhiễm khuẩn | tri-state | — | O | `true` |
| `joint_limb_swelling` | Sưng đau khớp/chi | Amber NICE — nghi nhiễm khuẩn xương khớp | tri-state | — | M | `false` |
| `non_weight_bearing` | Không chịu đi/không dùng chi | Amber NICE | tri-state | — | C (tuổi < 16) | `false` |
| `myalgia_retroorbital_pain` | Đau cơ, đau hốc mắt | Bộ triệu chứng gợi ý bệnh virus lưu hành VN | tri-state | — | O | `true` |

### 3.10. Nhóm RISK — Tiền sử, phơi nhiễm, thai kỳ, miễn dịch

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `chronic_conditions` | Bệnh mạn tính | Lý do cân nhắc nhập viện (QĐ 2760); yếu tố nguy cơ sepsis | array[enum] | `cardiac`, `pulmonary`, `renal`, `hepatic`, `diabetes`, `hematologic_thalassemia`, `neurologic_epilepsy`, `malignancy`, `none`, `unknown` | M | `["diabetes"]` |
| `obesity_or_malnutrition` | Béo phì / suy dinh dưỡng | Tăng nặng, khó đánh giá | enum | `none`, `obesity`, `malnutrition`, `unknown` | O | `"obesity"` |
| `immunocompromised` | Suy giảm miễn dịch | Nhóm nguy cơ cao nhất | tri-state | — | M | `false` |
| `immunocompromise_cause` | Nguyên nhân | Phân tầng nội bộ | array[enum] | `chemotherapy_6w`, `transplant`, `long_term_steroid`, `biologic_therapy`, `hiv_uncontrolled`, `asplenia`, `other` | C | `["chemotherapy_6w"]` |
| `known_neutropenia` | Đã biết giảm bạch cầu hạt | Kích hoạt ngưỡng sốt 38,3 °C / 38,0 °C ≥1h | tri-state | — | C | `true` |
| `is_pregnant` | Đang mang thai | Nhánh riêng | tri-state | — | C (nữ 10–60 tuổi) | `false` |
| `gestational_weeks` | Tuần thai | 3 tháng cuối sinh lý khác | integer | 1–42 | C | `32` |
| `postpartum_6w` | Sinh/sảy/nạo hút trong 6 tuần | Nhiễm khuẩn hậu sản | tri-state | — | C | `false` |
| `obstetric_red_flags` | Đau bụng, ra máu/dịch, giảm cử động thai | Nâng mức khẩn | array[enum] | `abdominal_pain`, `vaginal_bleeding`, `fluid_leak`, `reduced_fetal_movement` | C | `[]` |
| `recent_surgery_30d` | Phẫu thuật/thủ thuật ≤30 ngày | Nguy cơ nhiễm khuẩn vết mổ/sepsis | tri-state | — | M | `false` |
| `surgical_site_signs` | Vết mổ sưng đỏ/chảy dịch/hở | Ổ nhiễm khuẩn rõ | tri-state | — | C | `false` |
| `indwelling_device` | Thiết bị lưu | Đường vào nhiễm khuẩn | array[enum] | `central_line`, `urinary_catheter`, `drain`, `vp_shunt`, `prosthesis`, `none` | M | `["none"]` |
| `recent_wound_or_bite` | Vết thương hở/bỏng/động vật cắn | Nhiễm khuẩn mô mềm, uốn ván, dại | tri-state | — | O | `false` |
| `travel_history_12m` | Du lịch 12 tháng | **Sốt sau vùng sốt rét = nguy cơ cao** | array[object: `place`, `return_date`] | — | M | `[{"place":"Bình Phước","return_date":"2026-07-25"}]` |
| `malaria_risk_area` | Vùng đến có sốt rét lưu hành | Rule cấp cứu tiềm tàng | tri-state | — | C | `true` |
| `outbreak_exposure` | Ổ dịch quanh khu vực/gia đình | Thay đổi xác suất nền | array[enum] | `dengue`, `influenza`, `measles`, `hfmd`, `covid`, `other`, `none`, `unknown` | M | `["dengue"]` |
| `mosquito_exposure` | Bị muỗi đốt/vùng có SXHD | Kích hoạt bộ câu hỏi cảnh báo SXHD **[LOCAL]** | tri-state | — | M | `true` |
| `animal_water_exposure` | Tiếp xúc động vật/lội nước lũ | Bệnh lây từ động vật, Leptospira | array[enum] | `poultry`, `swine`, `rodent`, `dog_cat_bite`, `floodwater`, `none` | O | `["floodwater"]` |
| `sick_contact` | Tiếp xúc người bệnh tương tự | Dịch tễ | tri-state | — | O | `true` |
| `immunization_status` | Tiêm chủng | Nguy cơ bệnh phòng ngừa được; vắc-xin gần đây có thể gây sốt | enum | `up_to_date`, `incomplete`, `unknown` | C (tuổi <5) | `"up_to_date"` |
| `recent_vaccination_48h` | Tiêm chủng trong 48 giờ | Yếu tố nhiễu khi diễn giải sốt | tri-state | — | C (tuổi <5) | `false` |

### 3.11. Nhóm MEDICATION

| Field name | Mô tả | Ý nghĩa lâm sàng | Data type | Allowed values | M/C/O | Ví dụ |
|---|---|---|---|---|---|---|
| `current_medications` | Thuốc đang dùng | Sốt do thuốc; tương tác an toàn | array[string] | — | O | `["metformin"]` |
| `nsaid_use` | Đang dùng NSAID/aspirin | **Cảnh báo an toàn bắt buộc trong bối cảnh SXHD [LOCAL]** | tri-state | — | M | `true` |
| `anticoagulant_use` | Đang dùng chống đông | Diễn giải chảy máu | tri-state | — | O | `false` |
| `antibiotic_current` | Đang dùng kháng sinh | Sốt dai dẳng dù KS = cần khám | tri-state | — | M | `false` |
| `new_medication_6w` | Thuốc mới trong 6 tuần | Sốt do thuốc | tri-state | — | O | `false` |
| `drug_allergies` | Dị ứng thuốc | An toàn cho tuyến sau | array[string] | — | O | `[]` |

### 3.12. Nhóm SESSION & OUTPUT **[EN]**

| Field name | Mô tả | Data type | Allowed values | M/C/O |
|---|---|---|---|---|
| `session_id` | Định danh phiên | string (uuid) | — | M |
| `started_at` / `completed_at` | Mốc thời gian | datetime | ISO-8601 | M |
| `answered_fields_count` / `unknown_fields` | Độ đầy đủ dữ liệu | integer / array[string] | — | M |
| `data_gap` | Có khoảng trống dữ liệu ảnh hưởng kết luận | boolean | — | M |
| `contradiction_flags` | Mâu thuẫn phát hiện được | array[string] | — | O |
| `triage_level` | Kết quả | enum | `EMERGENCY`, `EARLY_VISIT`, `SELF_CARE` | M |
| `triage_distribution` | Phân bố % 3 mức (theo luồng đã chốt) | object{emergency, early_visit, self_care} | 0–1 | M |
| `time_target` | Khung thời gian hành động | enum | `now`, `within_4h`, `within_24h`, `monitor` | M |
| `reason_codes` | Mã dấu hiệu kích hoạt (**không** phải mã bệnh) | array[string] | `RF-01`… | M |
| `triggered_rules` | Rule đã khớp | array[string] | `R-E-01`… | M |
| `guideline_refs` | Nguồn trích dẫn cho phần giải thích | array[string] | — | M |
| `safety_netting_items` | Danh sách dấu hiệu phải quay lại ngay | array[string] | — | M (khi `SELF_CARE`) |
| `hitl_status` | Trạng thái duyệt | enum | `pending`, `approved`, `edited`, `rejected`, `ask_more` | M |
| `reviewer_id` / `reviewer_note` | Người duyệt | string | — | C |

---

## PART 4 — RED FLAGS (DẤU HIỆU NGUY HIỂM)

### 4.1. Cách đọc bảng

- **Urgency:** `EMERGENCY` = mức cao nhất, không thể bị hạ; `EARLY_VISIT` = amber.
- **Applies to:** nhóm tuổi/quần thể áp dụng.
- Mỗi red flag có **mã ổn định** (`RF-xx`) — mã này đi vào `reason_codes`, dùng cho log kiểm toán và cho phần "giải thích lý do phân độ" trong charter.

### 4.2. Nhóm A — Tri giác, thần kinh

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-01** | Giảm ý thức | `consciousness_level ∈ {difficult_to_rouse, unresponsive}` hoặc trẻ chỉ tỉnh khi kích thích kéo dài | Li bì/hôn mê là dấu hiệu tiên lượng xấu mạnh nhất, chung cho nhiễm khuẩn thần kinh, sốc, hạ đường huyết, sốt rét ác tính | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 (red); WHO IMCI general danger sign; NICE NG51 |
| **RF-02** | Đang co giật / vừa co giật | `seizure_active_now = true` hoặc `seizure_occurred = true` | IMCI xếp co giật vào general danger sign → chuyển viện khẩn. Không phân biệt được co giật do sốt lành tính với nhiễm khuẩn TKTW qua kênh từ xa | `EMERGENCY` | Mọi lứa tuổi | WHO IMCI; NICE NG143 |
| **RF-03** | Co giật phức tạp | `seizure_features` chứa `focal`/`duration_gt_5min`/`recurrent_24h`/`incomplete_recovery` | Cơn khu trú hoặc trạng thái động kinh nâng mức nguy cơ bệnh nặng | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 |
| **RF-04** | Cứng gáy / thóp phồng / sợ ánh sáng | Bất kỳ trong `neck_stiffness`, `bulging_fontanelle`, `photophobia` + sốt | Bộ ba gợi ý nhiễm khuẩn màng não — cửa sổ điều trị tính bằng giờ | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 (red) |
| **RF-05** | Lú lẫn/thay đổi hành vi mới | `new_confusion = true` | Ở người ≥65 và người suy giảm miễn dịch, có thể là **biểu hiện duy nhất** của nhiễm khuẩn huyết | `EMERGENCY` | ≥16 tuổi, ưu tiên ≥65 | NICE NG51 (tiêu chí nguy cơ cao) |
| **RF-06** | Dấu thần kinh khu trú mới | `focal_neuro_deficit = true` | Cross-protocol: viêm não, áp xe não, đột quỵ | `EMERGENCY` | Mọi lứa tuổi | NICE NG143/NG51 |

### 4.3. Nhóm B — Hô hấp

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-07** | Khó thở nặng | `breathing_difficulty = severe` | Suy hô hấp là nguyên nhân tử vong sớm; ở SXHD còn do tràn dịch màng phổi/quá tải | `EMERGENCY` | Mọi lứa tuổi | NICE NG51; NG143 |
| **RF-08** | Tím tái | `cyanosis = true` | Thiếu oxy nặng | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 (red) |
| **RF-09** | Dấu suy hô hấp ở trẻ | `chest_indrawing` hoặc `nasal_flaring_grunting` | Rút lõm lồng ngực, thở rên là dấu hiệu nặng ở trẻ nhỏ | `EMERGENCY` | < 5 tuổi | NICE NG143; IMCI |
| **RF-10** | Thở rít / chảy dãi, không nuốt được | `stridor_or_drooling = true` | Nghi tắc nghẽn đường thở trên — cấm thao tác gây kích thích | `EMERGENCY` | Mọi lứa tuổi | Thực hành cấp cứu nhi/ENT |
| **RF-11** | Thở nhanh + SpO₂ ≤ 95% khí trời | `rapid_breathing = true` AND `spo2_percent ≤ 95` | Amber trong NICE ở trẻ; ở đây nâng thành cấp cứu khi phối hợp | `EMERGENCY` nếu SpO₂ ≤92; `EARLY_VISIT` nếu 93–95 | Mọi lứa tuổi | NICE NG143 (amber) |
| **RF-12** | Đau ngực / ho ra máu kèm sốt | `chest_pain` hoặc `hemoptysis` | Cross-protocol; nghi viêm phổi nặng, thuyên tắc phổi, viêm cơ tim | `EARLY_VISIT` (nâng lên `EMERGENCY` nếu kèm khó thở/ngất) | ≥12 tuổi | Cross-protocol |

### 4.4. Nhóm C — Tuần hoàn / sốc / mất nước

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-13** | Dấu hiệu sốc | `cold_clammy_skin = true` hoặc `capillary_refill_ge_3s = true` (kèm sốt) | Da lạnh ẩm nổi vân tím, CRT kéo dài là biểu hiện giảm tưới máu — trong SXHD tương ứng giai đoạn sốc | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 (red, CRT ≥3 s); QĐ 2760/QĐ-BYT |
| **RF-14** | Không tiểu > 6 giờ | `urine_output = none_gt_6h` | Mốc 6 giờ được BYT dùng làm dấu hiệu **khám lại ngay** trong SXHD | `EMERGENCY` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT **[LOCAL]** |
| **RF-15** | Không uống được / nôn tất cả | `feeding_intake = unable` hoặc `vomiting_severity = unable_to_keep_fluids` | IMCI general danger sign: không uống/không bú được, nôn tất cả → chuyển viện khẩn | `EMERGENCY` | Mọi lứa tuổi | WHO IMCI |
| **RF-16** | Mất nước có dấu hiệu | ≥2 mục trong `dehydration_signs` hoặc `urine_output = reduced` + `feeding_intake = reduced` | Mất nước tiến triển nhanh ở trẻ nhỏ | `EARLY_VISIT` | Mọi lứa tuổi | NICE NG143 (amber) |
| **RF-17** | Choáng/ngất khi đứng dậy | `dizziness_on_standing = true` | Giảm thể tích tuần hoàn — tiền sốc | `EARLY_VISIT` (→ `EMERGENCY` nếu kèm RF-13) | ≥12 tuổi | Thực hành cấp cứu |

### 4.5. Nhóm D — Da, xuất huyết

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-18** | **Ban không mất khi ấn kính** | `non_blanching_rash = true` | Dấu hiệu kinh điển nghi nhiễm khuẩn huyết do não mô cầu; NICE nhấn mạnh đặc biệt khi kèm tử ban >2 mm, CRT ≥3 s hoặc cứng gáy. Diễn tiến tử vong trong vài giờ | `EMERGENCY` | Mọi lứa tuổi | NICE NG143 |
| **RF-19** | Xuất huyết niêm mạc | `mucosal_bleeding = true` | **Dấu hiệu cảnh báo SXHD → chỉ định nhập viện** theo BYT | `EMERGENCY` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT **[LOCAL]** |
| **RF-20** | Xuất huyết tiêu hóa | `gi_bleeding = true` | Xuất huyết nặng; nguy cơ mất máu cấp | `EMERGENCY` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT |
| **RF-21** | Vàng da mới | `jaundice_new = true` | Tổn thương gan/tan máu/nhiễm khuẩn nặng; là tiêu chí bệnh nặng trong sốt rét | `EARLY_VISIT` (→`EMERGENCY` nếu kèm RF-01) | Mọi lứa tuổi | WHO (severe malaria criteria) |

### 4.6. Nhóm E — Đặc trưng của sốt & tuổi

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-22** | **Sốt ở trẻ < 3 tháng** | `age < 3 tháng` AND (`temp_c ≥ 38.0` rectal/tympanic hoặc `≥37.5` nách hoặc `fever_status = subjective`) | Trẻ nhũ nhi rất nhỏ có nguy cơ nhiễm khuẩn nặng xâm lấn cao và biểu hiện nghèo nàn; guideline AAP chỉ áp dụng cho trẻ **trông khỏe** và vẫn yêu cầu đánh giá tại cơ sở y tế | `EMERGENCY` | < 3 tháng | NICE NG143 (red); AAP 2021 |
| **RF-23** | Sốt cao ở trẻ 3–6 tháng | `age 3–6 tháng` AND `temp_c ≥ 39.0` | Amber trong traffic light | `EARLY_VISIT` | 3–6 tháng | NICE NG143 |
| **RF-24** | Hạ thân nhiệt | `temp_c < 36.0` hoặc `hypothermia_reported = true` | Mất khả năng đáp ứng sốt = dấu hiệu nặng, thường gặp ở nhũ nhi, người già, suy giảm miễn dịch | `EMERGENCY` | < 3 tháng, ≥65, suy giảm miễn dịch | NICE NG51; IMCI |
| **RF-25** | Nghi tăng thân nhiệt bệnh lý (say nắng/say nóng) | `temp_c ≥ 40.0` AND (`consciousness_level ≠ alert` hoặc bối cảnh phơi nhiễm nhiệt/gắng sức/thuốc) | Hyperthermia không đáp ứng thuốc hạ sốt, tổn thương cơ quan tiến triển theo phút | `EMERGENCY` | Mọi lứa tuổi | Thực hành cấp cứu |
| **RF-26** | Sốt kéo dài ≥ 5 ngày | `fever_duration_days ≥ 5` | NICE: **không** dùng thời lượng sốt để dự đoán bệnh nặng, **nhưng** ≥5 ngày cần đánh giá bệnh Kawasaki | `EARLY_VISIT` | < 5 tuổi (áp dụng rộng hơn ở VN) | NICE NG143 |
| **RF-27** | Sốt kéo dài ≥ 7 ngày | `fever_duration_days ≥ 7` | Sốt kéo dài cần đánh giá tại cơ sở y tế (IMCI: sốt >7 ngày → chuyển tuyến đánh giá) | `EARLY_VISIT` | Mọi lứa tuổi | WHO IMCI |
| **RF-28** | Rét run dữ dội | `rigors = true` | Amber NICE; ở người lớn gợi ý nhiễm khuẩn huyết/sốt rét | `EARLY_VISIT` | Mọi lứa tuổi | NICE NG143 |
| **RF-29** | **Khó chịu hơn dù đã hạ sốt** | `worse_after_defervescence = true` | BYT liệt kê là dấu hiệu **khám lại ngay**; trùng thời điểm chuyển sang giai đoạn nguy hiểm của SXHD | `EMERGENCY` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT **[LOCAL]** |

### 4.7. Nhóm F — Nhóm nguy cơ đặc biệt

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-30** | **Sốt + giảm bạch cầu hạt / hóa trị ≤6 tuần** | `known_neutropenia = true` hoặc `chemotherapy_6w` AND sốt (≥38,3 °C một lần hoặc ≥38,0 °C ≥1 giờ) | Sốt giảm bạch cầu hạt là **cấp cứu nội khoa**: cần kháng sinh trong vòng ~1 giờ; chậm trễ làm tăng tử vong | `EMERGENCY` | Mọi lứa tuổi | IDSA febrile neutropenia; NICE CG151 |
| **RF-31** | Sốt + suy giảm miễn dịch khác | `immunocompromised = true` | Biểu hiện nghèo nàn, diễn tiến nhanh; không thể phân tầng an toàn từ xa | `EMERGENCY` nếu kèm bất kỳ dấu hiệu toàn thân; nếu không → `EARLY_VISIT` (≤4h) | Mọi lứa tuổi | NICE NG51 |
| **RF-32** | Sốt + thai kỳ hoặc hậu sản ≤6 tuần | `is_pregnant = true` hoặc `postpartum_6w = true` | NICE NG51 có nhánh riêng cho người đang/vừa mang thai; dấu hiệu sốc xuất hiện muộn do sinh lý thai kỳ | `EARLY_VISIT` (≤4h); `EMERGENCY` nếu kèm `obstetric_red_flags` hoặc bất kỳ RF nhóm A–E | Nữ mang thai/hậu sản | NICE NG51; QĐ 2760 |
| **RF-33** | Sốt + phẫu thuật/thủ thuật ≤30 ngày | `recent_surgery_30d = true` | Phẫu thuật gần đây là yếu tố nguy cơ nhiễm khuẩn huyết được NICE liệt kê | `EARLY_VISIT`; `EMERGENCY` nếu `surgical_site_signs = true` | Mọi lứa tuổi | NICE NG51 |
| **RF-34** | Sốt + thiết bị lưu trong cơ thể | `indwelling_device` ≠ `none` | Đường vào nhiễm khuẩn trực tiếp vào máu/TKTW (van dẫn lưu não thất) | `EARLY_VISIT`; `EMERGENCY` nếu có van dẫn lưu não thất kèm đau đầu/nôn | Mọi lứa tuổi | NICE NG51 |
| **RF-35** | **Sốt sau du lịch vùng sốt rét ≤3 tháng** | `malaria_risk_area = true` AND `fever_reported = true` | Sốt rét ác tính có thể tử vong trong vài ngày; sốt rét nằm trong chẩn đoán phân biệt sốt của BYT. Không thể loại trừ nếu không xét nghiệm | `EMERGENCY` nếu trở về ≤1 tháng hoặc có bất kỳ RF nào; `EARLY_VISIT` (trong ngày) nếu >1 tháng và không RF | Mọi lứa tuổi | WHO; BYT (chẩn đoán phân biệt) |
| **RF-36** | Sốt + bệnh mạn tính nặng | `chronic_conditions` chứa mục nặng (tim/phổi/gan/thận/thalassemia/ung thư) | BYT nêu bệnh mạn tính kèm theo là lý do **cân nhắc nhập viện** dù SXHD chưa có dấu hiệu cảnh báo | `EARLY_VISIT` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT **[LOCAL]** |
| **RF-37** | Sốt ở người ≥ 75 tuổi | `age ≥ 75` | NICE NG51 xếp tuổi ≥75 là yếu tố nguy cơ; đáp ứng sốt bị cùn nên mức độ nặng dễ bị đánh giá thấp | `EARLY_VISIT` (mặc định), nâng nếu có bất kỳ RF | ≥75 tuổi | NICE NG51 |
| **RF-38** | Sống một mình / không ai theo dõi / xa cơ sở y tế | `lives_alone = true` hoặc `caregiver_available = false` hoặc `access_to_care_minutes` lớn | BYT nêu đây là lý do cân nhắc nhập viện: **self-care an toàn phụ thuộc vào người theo dõi** | Không tự sinh mức, nhưng **chặn** `SELF_CARE` → nâng lên `EARLY_VISIT` | Mọi lứa tuổi | QĐ 2760/QĐ-BYT **[LOCAL]** |

### 4.8. Nhóm G — Ổ nhiễm khuẩn khu trú & triệu chứng kèm

| Mã | Dấu hiệu | Định nghĩa vận hành | Lập luận lâm sàng | Urgency | Applies to | Nguồn |
|---|---|---|---|---|---|---|
| **RF-39** | Đau bụng dữ dội / bụng cứng | `abdominal_pain_severity = severe` hoặc `abdominal_guarding = true` | Đau bụng nhiều là dấu hiệu cảnh báo SXHD; đồng thời nghi bụng ngoại khoa cấp | `EMERGENCY` | Mọi lứa tuổi | QĐ 2760; thực hành ngoại khoa |
| **RF-40** | Nôn nhiều | `vomiting_severity = frequent` | Dấu hiệu cảnh báo SXHD → chỉ định nhập viện | `EARLY_VISIT` (→ `EMERGENCY` nếu `unable_to_keep_fluids`) | Mọi lứa tuổi | QĐ 2760/QĐ-BYT |
| **RF-41** | Sưng đau khớp/chi, không đi được, không dùng chi | `joint_limb_swelling` hoặc `non_weight_bearing` | Amber NICE — nghi nhiễm khuẩn xương khớp, di chứng nặng nếu chậm | `EARLY_VISIT` | Mọi lứa tuổi | NICE NG143 |
| **RF-42** | Triệu chứng tiết niệu ở trẻ < 5 tuổi sốt không rõ ổ | `age < 5` AND sốt AND không có ổ nhiễm khuẩn rõ | NICE khuyến cáo **luôn cân nhắc nhiễm khuẩn tiết niệu** ở trẻ <5 tuổi sốt; cần xét nghiệm nước tiểu tại cơ sở y tế | `EARLY_VISIT` | < 5 tuổi | NICE NG143 + NICE UTI guideline |
| **RF-43** | Ổ nhiễm khuẩn khu trú tiến triển | `localized_infection_signs = true` | Viêm mô tế bào/áp xe có thể tiến triển thành nhiễm khuẩn huyết | `EARLY_VISIT` | Mọi lứa tuổi | NICE NG51 |
| **RF-44** | Mức lo lắng người chăm sóc rất cao / "trông khác hẳn" | `caregiver_concern_level ≥ 8` hoặc `looks_very_unwell = true` | NICE ghi nhận lo lắng của người chăm sóc là tín hiệu có giá trị độc lập; trong đánh giá từ xa đây là proxy quan trọng nhất cho "ill-appearance" | `EARLY_VISIT` tối thiểu; `EMERGENCY` nếu kèm bất kỳ RF nhóm A–D | Mọi lứa tuổi | NICE NG143 |

### 4.9. Ràng buộc an toàn về nội dung tư vấn **[LOCAL] — bắt buộc**

| Ràng buộc | Lý do | Nguồn |
|---|---|---|
| **Không bao giờ gợi ý ibuprofen / aspirin / analgin** cho người đang sốt chưa loại trừ SXHD | BYT nêu rõ không dùng aspirin, analgin, ibuprofen vì có thể gây xuất huyết, toan máu | QĐ 2760/QĐ-BYT |
| Chỉ đề cập paracetamol đơn chất, kèm cảnh báo tổng liều ≤ 60 mg/kg/24 giờ và **không đưa liều cụ thể** cho từng người | Tránh vượt phạm vi "không kê đơn" của hệ thống | QĐ 2760 + §0.1 |
| Không tư vấn "dùng nước đá/cồn để lau hạ sốt" | Không phù hợp khuyến cáo; BYT hướng dẫn lau bằng **nước ấm** | QĐ 2760 |
| Nếu `nsaid_use = true` và có nghi ngờ SXHD → nâng thông điệp cảnh báo và ưu tiên `EARLY_VISIT` trở lên | Nguy cơ xuất huyết | QĐ 2760 |

---

## PART 5 — QUẦN THỂ NGUY CƠ CAO (HIGH-RISK POPULATIONS)

### 5.1. Nguyên tắc chung

Với ba quần thể dưới đây, ba điều **luôn** thay đổi:

1. **Ngưỡng phát hiện thấp hơn** — dấu hiệu ít hơn cũng đủ để nâng mức.
2. **Giá trị tiên đoán âm thấp hơn** — "không có red flag" **không** đủ an toàn để cho về nhà.
3. **Thời gian phản ứng ngắn hơn** — cùng một dấu hiệu nhưng khung thời gian rút ngắn (`within_24h` → `within_4h` → `now`).

**Quy tắc vận hành [EN]:** mỗi quần thể có một hệ số `conservatism_tier` (0/1/2). Rule engine áp dụng:

```
tier 0 (thường):        áp bảng rule chuẩn
tier 1 (nguy cơ cao):   MỌI kết quả SELF_CARE  → nâng thành EARLY_VISIT
                        MỌI kết quả EARLY_VISIT → time_target = within_4h
tier 2 (nguy cơ rất cao): MỌI kết quả          → tối thiểu EMERGENCY hoặc EARLY_VISIT ≤4h
                        + escalate HITL ngay, không xếp hàng đợi thường
```

### 5.2. Bảng quần thể

| Quần thể | Vì sao khác biệt (sinh lý/lâm sàng) | Đánh giá sốt thay đổi thế nào | Tier | Mức triage trở nên thận trọng ra sao |
|---|---|---|---|---|
| **Trẻ < 28 ngày** | Hàng rào miễn dịch chưa hoàn thiện; nhiễm khuẩn xâm lấn biểu hiện cực kỳ nghèo nàn; có thể **hạ thân nhiệt** thay vì sốt | Bỏ qua toàn bộ đánh giá "trông có khỏe không" — vẻ ngoài bình thường **không** loại trừ bệnh nặng. Hỏi thêm: bú kém, thóp, vàng da, rốn, thân nhiệt thấp | **2** | **Luôn `EMERGENCY`** khi có sốt (khách quan hoặc chủ quan) hoặc hạ thân nhiệt. Không tồn tại nhánh `SELF_CARE`. |
| **Trẻ 28 ngày – < 3 tháng** | Như trên, nguy cơ giảm dần nhưng vẫn cao | AAP 2021 phân 3 nhóm tuổi (8–21, 22–28, 29–60 ngày) với mức độ can thiệp khác nhau — nhưng **mọi nhóm đều cần đánh giá tại cơ sở y tế** | **2** | **Luôn `EMERGENCY`** (RF-22). Không `SELF_CARE`. |
| **Trẻ 3–6 tháng** | Vẫn khó đánh giá; NICE đặt mốc nhiệt độ riêng | `temp ≥ 39 °C` → amber ngay cả khi không triệu chứng khác | **1** | `SELF_CARE` chỉ khi không có bất kỳ RF nào **và** nhiệt độ <39 °C **và** có người theo dõi. |
| **Trẻ 6 tháng – 5 tuổi** | Ổ nhiễm khuẩn hay bị giấu (tiết niệu, xương khớp) | Bắt buộc hỏi triệu chứng tiết niệu và khớp/chi; dùng traffic light | **0–1** | `SELF_CARE` được phép nếu green hoàn toàn + safety-netting đầy đủ. |
| **Người ≥ 65 tuổi (đặc biệt ≥ 75)** | Đáp ứng sốt bị cùn; ngưỡng nhiệt độ chuẩn có thể **không đạt** dù nhiễm khuẩn nặng; nhiều bệnh nền, nhiều thuốc | Trọng số chuyển từ nhiệt độ sang **thay đổi tri giác, té ngã, ăn kém, giảm hoạt động**. `new_confusion` được coi ngang một red flag chính | **1** (≥75: **1–2**) | Mặc định `EARLY_VISIT` (RF-37). `SELF_CARE` chỉ khi sốt ngắn, có ổ rõ ràng lành tính, hoàn toàn tỉnh táo, ăn uống bình thường, có người ở cùng. |
| **Người suy giảm miễn dịch (không giảm bạch cầu hạt)** | Phản ứng viêm bị ức chế → triệu chứng nghèo nàn; nhiễm trùng cơ hội | Không dựa vào "có ổ nhiễm khuẩn rõ hay không". Bất kỳ sốt nào cũng là tín hiệu | **1–2** | Tối thiểu `EARLY_VISIT ≤ 4h`; `EMERGENCY` nếu kèm bất kỳ dấu hiệu toàn thân. **Không bao giờ** `SELF_CARE`. |
| **Người giảm bạch cầu hạt / hóa trị ≤ 6 tuần** | Không còn hàng rào bạch cầu → nhiễm khuẩn huyết tiến triển trong vài giờ | Ngưỡng sốt riêng: **≥38,3 °C một lần** hoặc **≥38,0 °C kéo dài ≥1 giờ** | **2** | **`EMERGENCY` tuyệt đối** (RF-30), escalate ngay. |
| **Phụ nữ mang thai** | 3 tháng cuối: mạch nhanh hơn 10–15 l/ph, HA tâm thu thấp hơn 5–10 mmHg, Hct giảm → **dấu hiệu sốc bị che lấp và xuất hiện muộn**. Đau bụng dễ nhầm chuyển dạ | Không dùng mạch/HA để "yên tâm". Bổ sung bộ câu hỏi sản khoa (ra máu/dịch, cử động thai, cơn co) | **1–2** | Tối thiểu `EARLY_VISIT ≤ 4h` (RF-32). `EMERGENCY` nếu có red flag sản khoa hoặc bất kỳ RF nhóm A–E. Hướng người bệnh tới **cơ sở có sản khoa**. |
| **Phụ nữ hậu sản / sau sảy, nạo hút ≤ 6 tuần** | Nguy cơ nhiễm khuẩn hậu sản diễn tiến nhanh | Hỏi sản dịch hôi, đau tử cung, vết mổ | **2** | `EMERGENCY` nếu sốt + bất kỳ dấu hiệu toàn thân; nếu không → `EARLY_VISIT ≤4h`. |
| **Người mới phẫu thuật ≤ 30 ngày / có thiết bị lưu** | Có đường vào nhiễm khuẩn trực tiếp | Hỏi vết mổ, thiết bị, thời điểm mổ | **1** | `EARLY_VISIT`; `EMERGENCY` nếu vết mổ nhiễm khuẩn hoặc có van dẫn lưu não thất kèm đau đầu/nôn. |
| **Người có bệnh mạn tính nặng, thalassemia, béo phì** | Dự trữ sinh lý thấp; trong SXHD có Hct nền thấp (thalassemia) làm che dấu cô đặc máu; béo phì gây khó đánh giá | Không dùng "đang khỏe" để hạ mức | **1** | `EARLY_VISIT` (RF-36); `SELF_CARE` chỉ khi bệnh nền ổn định + không RF + có người theo dõi. |
| **Người trở về từ vùng sốt rét ≤ 3 tháng** | Sốt rét ác tính diễn tiến tử vong nhanh; không thể loại trừ trên lâm sàng | Bắt buộc hỏi lịch sử du lịch trước khi kết luận bất kỳ mức nào | **1–2** | `EMERGENCY` nếu về ≤1 tháng hoặc kèm RF; `EARLY_VISIT` trong ngày nếu >1 tháng và không RF. |
| **Người sống một mình / xa cơ sở y tế / không ai theo dõi** | Không phải nguy cơ sinh học mà là **nguy cơ hệ thống**: nếu trở nặng, không ai phát hiện | Không thay đổi cách đánh giá triệu chứng, nhưng thay đổi **điều kiện an toàn của quyết định** | **1** | **Chặn `SELF_CARE`** → nâng lên `EARLY_VISIT` (RF-38). |
| **Trẻ khuyết tật học tập / chậm phát triển** | Baseline hành vi khác → dễ đọc sai traffic light | Chuẩn hóa câu hỏi theo baseline: "so với ngày thường của bé" | **1** | Nghiêng về `EARLY_VISIT` khi có nghi ngờ; ưu tiên `caregiver_concern_level`. |

### 5.3. Ma trận tương tác quần thể × dấu hiệu **[EN]**

Khi một người thuộc **≥2 quần thể** nguy cơ cao (ví dụ: thai phụ đang hóa trị), lấy **tier cao nhất**, và cộng thêm cờ `multi_risk = true` để điều dưỡng ưu tiên trong hàng đợi.

### 5.4. Điều kiện tối thiểu để được kết luận `SELF_CARE` **[EN] — checklist bắt buộc**

Chỉ cho `SELF_CARE` khi **TẤT CẢ** đúng:

- [ ] Không có bất kỳ red flag `EMERGENCY` nào (RF nhóm A–G).
- [ ] Không có bất kỳ red flag `EARLY_VISIT` nào.
- [ ] `conservatism_tier = 0`.
- [ ] Tuổi ≥ 6 tháng.
- [ ] `fever_duration_days < 5`.
- [ ] `consciousness_level = alert`, `feeding_intake ∈ {normal, reduced}`, `urine_output = normal`.
- [ ] `caregiver_available = true` **hoặc** người bệnh là người lớn tự chăm sóc được.
- [ ] `can_return_for_followup = true`.
- [ ] Không có field mandatory nào ở trạng thái `unknown` ảnh hưởng tới rule (`data_gap = false`).
- [ ] Đã hiển thị **đầy đủ** danh sách safety-netting (§5.5).

### 5.5. Safety-netting bắt buộc kèm mọi kết luận `SELF_CARE` **[E][LOCAL]**

Danh sách này hợp nhất khuyến cáo của NICE NG143 (lời khuyên cho cha mẹ) và danh sách "khám lại ngay" của QĐ 2760/QĐ-BYT. **Không được rút gọn.**

> **Đi khám ngay / gọi cấp cứu nếu xuất hiện bất kỳ dấu hiệu nào sau đây:**
> 1. Li bì, khó đánh thức, lú lẫn, hoặc thay đổi hành vi bất thường
> 2. Co giật
> 3. Nổi ban đỏ/tím **không mất đi khi ấn kính vào**
> 4. Khó thở, thở nhanh, tím môi
> 5. Tay chân lạnh, ẩm, nổi vân tím
> 6. Nôn nhiều, không ăn uống được
> 7. Đau bụng nhiều
> 8. Chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen, ra máu âm đạo bất thường
> 9. **Không đi tiểu trên 6 giờ**
> 10. **Cảm thấy khó chịu/mệt hơn dù đã hạ sốt hoặc hết sốt**
> 11. Sốt kéo dài **từ 5 ngày trở lên**
> 12. Cứng gáy, đau đầu dữ dội, sợ ánh sáng
> 13. Người chăm sóc cảm thấy trẻ/người bệnh "khác hẳn thường ngày" và lo lắng

Kèm theo (NICE): kiểm tra người bệnh **cả trong đêm**, bảo đảm uống đủ nước, hướng dẫn cách nhận biết ban không mất khi ấn kính.

---

## PART 6 — COVERAGE VALIDATION (MA TRẬN ĐỐI SOÁT)

### 6.1. Rule catalog (để tham chiếu trong ma trận) **[EN cấu trúc / E nội dung]**

| Rule ID | Điều kiện (rút gọn) | Kết quả | Red flag nguồn |
|---|---|---|---|
| `R-E-01` | `consciousness_level ∈ {difficult_to_rouse, unresponsive}` | EMERGENCY / now | RF-01 |
| `R-E-02` | `seizure_occurred` OR `seizure_active_now` OR co giật phức tạp | EMERGENCY / now | RF-02, RF-03 |
| `R-E-03` | `neck_stiffness` OR `bulging_fontanelle` OR `photophobia` | EMERGENCY / now | RF-04 |
| `R-E-04` | `new_confusion` AND age ≥16 | EMERGENCY / now | RF-05 |
| `R-E-05` | `focal_neuro_deficit` | EMERGENCY / now | RF-06 |
| `R-E-06` | `breathing_difficulty = severe` OR `cyanosis` OR `stridor_or_drooling` | EMERGENCY / now | RF-07, RF-08, RF-10 |
| `R-E-07` | age <5 AND (`chest_indrawing` OR `nasal_flaring_grunting`) | EMERGENCY / now | RF-09 |
| `R-E-08` | `spo2_percent ≤ 92` | EMERGENCY / now | RF-11 |
| `R-E-09` | `cold_clammy_skin` OR `capillary_refill_ge_3s` | EMERGENCY / now | RF-13 |
| `R-E-10` | `urine_output = none_gt_6h` | EMERGENCY / now | RF-14 |
| `R-E-11` | `feeding_intake = unable` OR `vomiting_severity = unable_to_keep_fluids` | EMERGENCY / now | RF-15 |
| `R-E-12` | `non_blanching_rash` | EMERGENCY / now | RF-18 |
| `R-E-13` | `mucosal_bleeding` OR `gi_bleeding` | EMERGENCY / now | RF-19, RF-20 |
| `R-E-14` | age <3 tháng AND (sốt khách quan HOẶC chủ quan) | EMERGENCY / now | RF-22 |
| `R-E-15` | `temp_c < 36.0` AND tier ≥1 | EMERGENCY / now | RF-24 |
| `R-E-16` | `temp_c ≥ 40` AND (`consciousness_level ≠ alert` OR phơi nhiễm nhiệt) | EMERGENCY / now | RF-25 |
| `R-E-17` | `worse_after_defervescence` | EMERGENCY / now | RF-29 |
| `R-E-18` | `known_neutropenia` OR `chemotherapy_6w`, kèm sốt theo ngưỡng riêng | EMERGENCY / now | RF-30 |
| `R-E-19` | `malaria_risk_area` AND về ≤1 tháng | EMERGENCY / now | RF-35 |
| `R-E-20` | `abdominal_pain_severity = severe` OR `abdominal_guarding` | EMERGENCY / now | RF-39 |
| `R-E-21` | `is_pregnant`/`postpartum_6w` AND (`obstetric_red_flags` ≠ ∅ OR bất kỳ R-E-xx) | EMERGENCY / now | RF-32 |
| `R-V-01` | age 3–6 tháng AND `temp_c ≥ 39` | EARLY_VISIT / 24h | RF-23 |
| `R-V-02` | `fever_duration_days ≥ 5` | EARLY_VISIT / 24h | RF-26 |
| `R-V-03` | `fever_duration_days ≥ 7` | EARLY_VISIT / 24h | RF-27 |
| `R-V-04` | `rigors` | EARLY_VISIT / 24h | RF-28 |
| `R-V-05` | `spo2_percent` 93–95 OR `rapid_breathing` | EARLY_VISIT / 4h | RF-11 |
| `R-V-06` | ≥2 `dehydration_signs` OR (`urine_output = reduced` AND `feeding_intake = reduced`) | EARLY_VISIT / 4h | RF-16 |
| `R-V-07` | `dizziness_on_standing` | EARLY_VISIT / 24h | RF-17 |
| `R-V-08` | `jaundice_new` | EARLY_VISIT / 24h | RF-21 |
| `R-V-09` | `immunocompromised` (không neutropenia) | EARLY_VISIT / 4h | RF-31 |
| `R-V-10` | `is_pregnant` OR `postpartum_6w` | EARLY_VISIT / 4h | RF-32 |
| `R-V-11` | `recent_surgery_30d` OR `indwelling_device ≠ none` | EARLY_VISIT / 24h | RF-33, RF-34 |
| `R-V-12` | `chronic_conditions` chứa mục nặng | EARLY_VISIT / 24h | RF-36 |
| `R-V-13` | age ≥ 75 | EARLY_VISIT / 24h | RF-37 |
| `R-V-14` | `vomiting_severity = frequent` | EARLY_VISIT / 4h | RF-40 |
| `R-V-15` | `joint_limb_swelling` OR `non_weight_bearing` | EARLY_VISIT / 24h | RF-41 |
| `R-V-16` | age <5 AND sốt AND không có ổ nhiễm khuẩn rõ | EARLY_VISIT / 24h | RF-42 |
| `R-V-17` | `localized_infection_signs` | EARLY_VISIT / 24h | RF-43 |
| `R-V-18` | `caregiver_concern_level ≥ 8` OR `looks_very_unwell` | EARLY_VISIT / 4h | RF-44 |
| `R-V-19` | `chest_pain` OR `hemoptysis` | EARLY_VISIT / 4h | RF-12 |
| `R-V-20` | `malaria_risk_area` AND về >1 tháng, không RF | EARLY_VISIT / 24h | RF-35 |
| `R-G-01` | `lives_alone` OR `caregiver_available = false` | **Chặn** SELF_CARE → EARLY_VISIT | RF-38 |
| `R-G-02` | Bất kỳ field mandatory nào `unknown` VÀ tier ≥1 | **Chặn** SELF_CARE, `data_gap = true` | §3.1 |
| `R-G-03` | `nsaid_use` AND (`mosquito_exposure` OR `outbreak_exposure` chứa dengue) | Gắn cảnh báo an toàn + tối thiểu EARLY_VISIT | §4.9 |
| `R-G-04` | `contradiction_flags ≠ ∅` | Kích hoạt câu hỏi làm rõ, không kết luận vội | Charter |
| `R-S-01` | Không rule nào khớp VÀ checklist §5.4 đủ | SELF_CARE / monitor + safety-netting | — |

### 6.2. Ma trận đối soát

| Information (field) | Vì sao thu thập | Dùng bởi rule | Bắt buộc? |
|---|---|---|---|
| `age_value` / `age_unit` | Phân tầng nguy cơ chính; quyết định ngưỡng nhiệt độ | `R-E-14`, `R-E-07`, `R-V-01`, `R-V-13`, `R-V-16`, toàn bộ tier | **M** |
| `sex` | Điều hướng nhánh sản khoa | `R-E-21`, `R-V-10` | **M** |
| `reporter_type` | Độ tin cậy dữ liệu; hiển thị cho người duyệt | `R-G-04` | **M** |
| `fever_reported` | Cổng vào protocol | Mọi rule | **M** |
| `fever_status` | Điều hướng khi thiếu số đo | `R-E-14`, `R-G-02` | **M** |
| `temp_c` | Ngưỡng theo tuổi | `R-E-14`, `R-E-15`, `R-E-16`, `R-E-18`, `R-V-01` | **C** (khi objective) |
| `temp_site` | Quyết định ngưỡng áp dụng (chênh 0,5 °C) | Cùng nhóm trên | **C** |
| `temp_measured_at` | Số đo cũ → giảm độ tin cậy | `measurement_confidence` | **C** |
| `temp_device_type` | Gán độ tin cậy; loại bỏ nhiệt kế dán trán | `measurement_confidence` | O |
| `temp_max_24h_c` | Bắt đỉnh sốt bị thuốc che | `R-V-01` (bổ trợ) | O |
| `fever_onset_at` → `fever_duration_days` | Mốc 5/7 ngày | `R-V-02`, `R-V-03` | **M** |
| `rigors` | Amber NICE; gợi ý nhiễm khuẩn huyết/sốt rét | `R-V-04` | **M** |
| `hypothermia_reported` | Dấu hiệu nặng ở nhóm nguy cơ | `R-E-15` | **C** |
| `antipyretic_taken` / `antipyretic_drug` | Nhiệt độ bị che; sàng lọc NSAID | `R-G-03` | **M** / **C** |
| `antipyretic_total_24h_mg` | Cảnh báo quá liều paracetamol | Cảnh báo an toàn (không đổi mức) | O |
| `antipyretic_response` | Ghi nhận mô tả; **không** dùng loại trừ | Không dùng trong rule cứng | O |
| `worse_after_defervescence` | Dấu hiệu khám lại ngay (BYT) | `R-E-17` | **M** |
| `consciousness_level` | Tiên lượng mạnh nhất | `R-E-01`, checklist §5.4 | **M** |
| `new_confusion` | Biểu hiện duy nhất ở người già | `R-E-04` | **M** |
| `social_response_child` | Lõi traffic light | `R-V-18` (bổ trợ), tier | **C** (<5 tuổi) |
| `activity_vs_baseline` | Chuẩn hóa theo baseline cá nhân | `R-V-18` | **M** |
| `feeding_intake` | IMCI danger sign | `R-E-11`, `R-V-06` | **M** |
| `caregiver_concern_level` | Tín hiệu độc lập có giá trị | `R-V-18` | **M** |
| `looks_very_unwell` | Proxy ill-appearance khi không khám được | `R-V-18` | **M** |
| `breathing_difficulty` | Cấu phần red | `R-E-06` | **M** |
| `rapid_breathing` | Dấu hiệu nặng nhận biết từ xa | `R-V-05` | **M** |
| `chest_indrawing`, `nasal_flaring_grunting` | Suy hô hấp ở trẻ | `R-E-07` | **C** (<5 tuổi) |
| `cyanosis` | Red tuyệt đối | `R-E-06` | **M** |
| `stridor_or_drooling` | Tắc nghẽn đường thở trên | `R-E-06` | **M** |
| `chest_pain`, `hemoptysis` | Cross-protocol | `R-V-19` | **M** / O |
| `spo2_percent` | Bổ trợ hô hấp | `R-E-08`, `R-V-05` | O |
| `cold_clammy_skin` | Dấu hiệu sốc | `R-E-09` | **M** |
| `capillary_refill_ge_3s` | Giảm tưới máu | `R-E-09` | **M** |
| `dizziness_on_standing` | Tiền sốc | `R-V-07` | **M** |
| `urine_output` | Tưới máu thận; mốc 6 giờ của BYT | `R-E-10`, `R-V-06`, §5.4 | **M** |
| `dehydration_signs` | Mất nước | `R-V-06` | O |
| `vomiting_severity` | Danger sign + cảnh báo SXHD | `R-E-11`, `R-V-14` | **M** |
| `seizure_occurred`, `seizure_active_now`, `seizure_features` | Danger sign; cơn phức tạp | `R-E-02` | **M** / **C** |
| `neck_stiffness`, `photophobia`, `bulging_fontanelle` | Nghi nhiễm khuẩn TKTW | `R-E-03` | **M** / O / **C** |
| `severe_headache` | Cross-protocol | `R-E-03` (bổ trợ) | **M** |
| `focal_neuro_deficit` | Cross-protocol | `R-E-05` | **M** |
| `non_blanching_rash` | Red flag kinh điển | `R-E-12` | **M** |
| `rash_present`, `rash_type` | Định hướng cho người duyệt | Hiển thị | **M** / **C** |
| `mucosal_bleeding`, `gi_bleeding` | Cảnh báo SXHD / xuất huyết nặng | `R-E-13` | **M** |
| `jaundice_new` | Tổn thương gan / bệnh nặng | `R-V-08` | O |
| `localized_infection_signs` | Ổ nhiễm khuẩn | `R-V-17` | O |
| `abdominal_pain_severity`, `abdominal_guarding` | Cảnh báo SXHD + bụng ngoại khoa | `R-E-20` | **M** / **C** |
| `abdominal_pain_location` | Định hướng cho người duyệt | Hiển thị | **C** |
| `diarrhea`, `bloody_stool` | Mất nước, nguồn nhiễm | `R-V-06` (bổ trợ) | **M** / **C** |
| `urinary_symptoms` | NICE: luôn cân nhắc NKTN ở trẻ <5 | `R-V-16` | **M** |
| `sore_throat`, `ear_pain`, `cough` | Xác định ổ nhiễm khuẩn (ảnh hưởng `R-V-16`) | `R-V-16` | O |
| `joint_limb_swelling`, `non_weight_bearing` | Amber NICE — nhiễm khuẩn xương khớp | `R-V-15` | **M** / **C** |
| `myalgia_retroorbital_pain` | Bộ triệu chứng virus lưu hành VN | Hiển thị + `R-G-03` | O |
| `chronic_conditions` | Lý do cân nhắc nhập viện (BYT) | `R-V-12`, tier | **M** |
| `obesity_or_malnutrition` | Tăng nặng, khó đánh giá | tier | O |
| `immunocompromised`, `immunocompromise_cause` | Nhóm nguy cơ cao nhất | `R-V-09`, `R-E-18`, tier | **M** / **C** |
| `known_neutropenia` | Ngưỡng sốt riêng, cấp cứu | `R-E-18` | **C** |
| `is_pregnant`, `gestational_weeks`, `postpartum_6w`, `obstetric_red_flags` | Nhánh sản khoa | `R-E-21`, `R-V-10` | **C** |
| `recent_surgery_30d`, `surgical_site_signs` | Nguy cơ nhiễm khuẩn vết mổ | `R-V-11` | **M** / **C** |
| `indwelling_device` | Đường vào nhiễm khuẩn | `R-V-11` | **M** |
| `recent_wound_or_bite` | Nhiễm khuẩn mô mềm, dại, uốn ván | `R-V-17` | O |
| `travel_history_12m`, `malaria_risk_area` | Sốt rét — cấp cứu tiềm tàng | `R-E-19`, `R-V-20` | **M** / **C** |
| `outbreak_exposure`, `mosquito_exposure` | Xác suất nền SXHD; kích hoạt bộ câu hỏi cảnh báo | `R-G-03`, thứ tự hỏi | **M** |
| `animal_water_exposure`, `sick_contact` | Bệnh lây từ động vật / dịch tễ | Hiển thị | O |
| `immunization_status`, `recent_vaccination_48h` | Nguy cơ bệnh phòng ngừa được; yếu tố nhiễu | Hiển thị + `R-V-16` (bổ trợ) | **C** (<5 tuổi) |
| `nsaid_use` | **Ràng buộc an toàn SXHD** | `R-G-03` | **M** |
| `anticoagulant_use` | Diễn giải chảy máu | `R-E-13` (bổ trợ) | O |
| `antibiotic_current` | Sốt dai dẳng dù KS | `R-V-02` (bổ trợ) | **M** |
| `new_medication_6w`, `current_medications`, `drug_allergies` | Sốt do thuốc; an toàn tuyến sau | Hiển thị | O |
| `lives_alone`, `caregiver_available` | Điều kiện an toàn của self-care | `R-G-01`, §5.4 | **M** |
| `access_to_care_minutes` | Ngưỡng thận trọng | `R-G-01` (bổ trợ) | O |
| `can_return_for_followup` | Tiền đề safety-netting | §5.4 | **C** |
| `unknown_fields`, `data_gap` | Chặn kết luận thiếu căn cứ | `R-G-02` | **M** |
| `contradiction_flags` | Kích hoạt câu hỏi làm rõ | `R-G-04` | O |

### 6.3. Kiểm tra độ phủ (coverage checks) **[EN]**

| Kiểm tra | Tiêu chí đạt |
|---|---|
| Mọi red flag có ít nhất 1 rule | 44/44 RF được ánh xạ ✔ |
| Mọi rule có ít nhất 1 field đầu vào | ✔ |
| Mọi field **M** được ít nhất 1 rule hoặc checklist dùng | ✔ (field chỉ hiển thị được đánh dấu O/C) |
| Không có rule nào hạ mức | ✔ (chỉ có rule nâng và rule chặn) |
| Mỗi RF có nguồn tham chiếu | ✔ (xem Part 4 + §9) |
| Mọi nhánh kết thúc bằng 1 trong 3 mức | ✔ (mặc định `R-S-01`) |
| Không tồn tại nhánh nào cho `SELF_CARE` ở tier 2 | ✔ |

---

## PART 7 — ENGINEERING-READY JSON SCHEMA

**File độc lập:** `fever-assessment.schema.json` — JSON Schema 

### 7.1. Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://vmedtriage.local/schemas/fever-assessment/v1.0.0.json",
  "title": "VMedTriage — Fever Symptom Assessment",
  "description": "Structured clinical information model for fever triage. Output is a 3-level urgency classification only. This schema MUST NOT be used to represent or transmit a disease diagnosis.",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "session", "patient", "fever", "general", "respiratory", "circulation", "neurological", "skin", "risk_factors"],
  "properties": {
    "schema_version": { "type": "string", "const": "1.0.0" },

    "session": {
      "type": "object",
      "additionalProperties": false,
      "required": ["session_id", "started_at", "reporter_type"],
      "properties": {
        "session_id": { "type": "string", "format": "uuid" },
        "patient_id": { "type": "string" },
        "started_at": { "type": "string", "format": "date-time" },
        "completed_at": { "type": ["string", "null"], "format": "date-time" },
        "reporter_type": { "type": "string", "enum": ["self", "parent_caregiver", "other"] },
        "locale": { "type": "string", "default": "vi-VN" },
        "unknown_fields": { "type": "array", "items": { "type": "string" }, "default": [] },
        "data_gap": { "type": "boolean", "default": false },
        "contradiction_flags": { "type": "array", "items": { "type": "string" }, "default": [] }
      }
    },

    "patient": {
      "type": "object",
      "additionalProperties": false,
      "required": ["age_value", "age_unit", "sex", "lives_alone", "caregiver_available"],
      "properties": {
        "age_value": { "type": "number", "minimum": 0, "maximum": 130 },
        "age_unit": { "type": "string", "enum": ["day", "month", "year"] },
        "age_days_derived": { "type": ["integer", "null"], "minimum": 0, "description": "Derived. Canonical age in days for rule evaluation." },
        "sex": { "type": "string", "enum": ["male", "female", "unknown"] },
        "weight_kg": { "type": ["number", "null"], "minimum": 0.5, "maximum": 300 },
        "lives_alone": { "$ref": "#/$defs/triState" },
        "caregiver_available": { "$ref": "#/$defs/triState" },
        "access_to_care_minutes": { "type": ["integer", "null"], "minimum": 0, "maximum": 1440 },
        "can_return_for_followup": { "$ref": "#/$defs/triState" }
      }
    },

    "fever": {
      "type": "object",
      "additionalProperties": false,
      "required": ["fever_reported", "fever_status", "rigors", "antipyretic_taken", "worse_after_defervescence"],
      "properties": {
        "fever_reported": { "type": "boolean" },
        "fever_status": { "type": "string", "enum": ["objective", "subjective", "none"] },
        "temp_c": { "type": ["number", "null"], "minimum": 30.0, "maximum": 43.0, "description": "Celsius, 1 decimal place. Rounding enforced at application layer (multipleOf 0.1 is unreliable with IEEE-754 floats)." },
        "temp_site": { "type": ["string", "null"], "enum": ["axillary", "oral", "rectal", "tympanic", "temporal", "unknown", null] },
        "temp_measured_at": { "type": ["string", "null"], "format": "date-time" },
        "temp_device_type": { "type": ["string", "null"], "enum": ["digital", "infrared_ear", "infrared_forehead", "mercury_glass", "chemical_dot", "unknown", null] },
        "measurement_confidence": { "type": ["string", "null"], "enum": ["high", "medium", "low", "subjective", null], "description": "Derived by system, not asked." },
        "temp_max_24h_c": { "type": ["number", "null"], "minimum": 30.0, "maximum": 43.0 },
        "fever_onset_at": { "type": ["string", "null"], "format": "date" },
        "fever_duration_days": { "type": ["integer", "null"], "minimum": 0, "maximum": 365 },
        "fever_pattern": { "type": ["string", "null"], "enum": ["continuous", "intermittent", "relapsing", "unknown", null] },
        "rigors": { "$ref": "#/$defs/triState" },
        "hypothermia_reported": { "$ref": "#/$defs/triState" },
        "antipyretic_taken": { "$ref": "#/$defs/triState" },
        "antipyretic_drug": { "type": ["string", "null"], "enum": ["paracetamol", "ibuprofen", "aspirin", "other", "unknown", null] },
        "antipyretic_total_24h_mg": { "type": ["number", "null"], "minimum": 0 },
        "antipyretic_response": { "type": ["string", "null"], "enum": ["resolved", "partial", "none", "unknown", null] },
        "worse_after_defervescence": { "$ref": "#/$defs/triState" }
      },
      "allOf": [
        {
          "if": { "properties": { "fever_status": { "const": "objective" } }, "required": ["fever_status"] },
          "then": { "required": ["temp_c", "temp_site", "temp_measured_at"] }
        }
      ]
    },

    "general": {
      "type": "object",
      "additionalProperties": false,
      "required": ["consciousness_level", "new_confusion", "activity_vs_baseline", "feeding_intake", "caregiver_concern_level", "looks_very_unwell"],
      "properties": {
        "consciousness_level": { "type": "string", "enum": ["alert", "drowsy_but_rousable", "difficult_to_rouse", "unresponsive", "unknown"] },
        "new_confusion": { "$ref": "#/$defs/triState" },
        "social_response_child": { "type": ["string", "null"], "enum": ["normal", "reduced", "no_response", "not_applicable", null] },
        "activity_vs_baseline": { "type": "string", "enum": ["normal", "reduced", "markedly_reduced", "unknown"] },
        "feeding_intake": { "type": "string", "enum": ["normal", "reduced", "unable", "unknown"] },
        "caregiver_concern_level": { "type": "integer", "minimum": 0, "maximum": 10 },
        "looks_very_unwell": { "$ref": "#/$defs/triState" }
      }
    },

    "respiratory": {
      "type": "object",
      "additionalProperties": false,
      "required": ["breathing_difficulty", "rapid_breathing", "cyanosis", "stridor_or_drooling", "chest_pain"],
      "properties": {
        "breathing_difficulty": { "type": "string", "enum": ["none", "mild", "severe", "unknown"] },
        "rapid_breathing": { "$ref": "#/$defs/triState" },
        "chest_indrawing": { "$ref": "#/$defs/triState" },
        "nasal_flaring_grunting": { "$ref": "#/$defs/triState" },
        "cyanosis": { "$ref": "#/$defs/triState" },
        "stridor_or_drooling": { "$ref": "#/$defs/triState" },
        "chest_pain": { "$ref": "#/$defs/triState" },
        "hemoptysis": { "$ref": "#/$defs/triState" },
        "cough": { "$ref": "#/$defs/triState" },
        "spo2_percent": { "type": ["integer", "null"], "minimum": 50, "maximum": 100 }
      }
    },

    "circulation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["cold_clammy_skin", "capillary_refill_ge_3s", "dizziness_on_standing", "urine_output", "vomiting_severity"],
      "properties": {
        "cold_clammy_skin": { "$ref": "#/$defs/triState" },
        "capillary_refill_ge_3s": { "$ref": "#/$defs/triState" },
        "dizziness_on_standing": { "$ref": "#/$defs/triState" },
        "urine_output": { "type": "string", "enum": ["normal", "reduced", "none_gt_6h", "unknown"] },
        "dehydration_signs": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["dry_mouth", "sunken_eyes", "no_tears", "sunken_fontanelle", "reduced_skin_turgor"] },
          "default": []
        },
        "vomiting_severity": { "type": "string", "enum": ["none", "occasional", "frequent", "unable_to_keep_fluids", "unknown"] }
      }
    },

    "neurological": {
      "type": "object",
      "additionalProperties": false,
      "required": ["seizure_occurred", "neck_stiffness", "severe_headache", "focal_neuro_deficit"],
      "properties": {
        "seizure_occurred": { "$ref": "#/$defs/triState" },
        "seizure_active_now": { "$ref": "#/$defs/triState" },
        "seizure_features": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["focal", "duration_gt_5min", "recurrent_24h", "incomplete_recovery"] },
          "default": []
        },
        "neck_stiffness": { "$ref": "#/$defs/triState" },
        "photophobia": { "$ref": "#/$defs/triState" },
        "severe_headache": { "$ref": "#/$defs/triState" },
        "bulging_fontanelle": { "$ref": "#/$defs/triState" },
        "focal_neuro_deficit": { "$ref": "#/$defs/triState" }
      }
    },

    "skin": {
      "type": "object",
      "additionalProperties": false,
      "required": ["non_blanching_rash", "rash_present", "mucosal_bleeding", "gi_bleeding"],
      "properties": {
        "non_blanching_rash": { "$ref": "#/$defs/triState" },
        "rash_present": { "$ref": "#/$defs/triState" },
        "rash_type": { "type": ["string", "null"], "enum": ["petechial", "maculopapular", "vesicular", "urticarial", "other", "unknown", null] },
        "mucosal_bleeding": { "$ref": "#/$defs/triState" },
        "gi_bleeding": { "$ref": "#/$defs/triState" },
        "jaundice_new": { "$ref": "#/$defs/triState" },
        "localized_infection_signs": { "$ref": "#/$defs/triState" }
      }
    },

    "associated_symptoms": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "abdominal_pain_severity": { "type": "string", "enum": ["none", "mild", "moderate", "severe", "unknown"] },
        "abdominal_pain_location": { "type": ["string", "null"], "enum": ["diffuse", "ruq", "rlq", "epigastric", "other", "unknown", null] },
        "abdominal_guarding": { "$ref": "#/$defs/triState" },
        "diarrhea": { "$ref": "#/$defs/triState" },
        "bloody_stool": { "$ref": "#/$defs/triState" },
        "urinary_symptoms": { "$ref": "#/$defs/triState" },
        "sore_throat": { "$ref": "#/$defs/triState" },
        "ear_pain": { "$ref": "#/$defs/triState" },
        "joint_limb_swelling": { "$ref": "#/$defs/triState" },
        "non_weight_bearing": { "$ref": "#/$defs/triState" },
        "myalgia_retroorbital_pain": { "$ref": "#/$defs/triState" },
        "symptom_note": { "type": "string", "maxLength": 1000, "description": "Free text. Display only. MUST NOT be used as hard rule input." }
      }
    },

    "risk_factors": {
      "type": "object",
      "additionalProperties": false,
      "required": ["chronic_conditions", "immunocompromised", "recent_surgery_30d", "indwelling_device", "outbreak_exposure", "mosquito_exposure"],
      "properties": {
        "chronic_conditions": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["cardiac", "pulmonary", "renal", "hepatic", "diabetes", "hematologic_thalassemia", "neurologic_epilepsy", "malignancy", "other", "none", "unknown"] }
        },
        "obesity_or_malnutrition": { "type": ["string", "null"], "enum": ["none", "obesity", "malnutrition", "unknown", null] },
        "immunocompromised": { "$ref": "#/$defs/triState" },
        "immunocompromise_cause": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["chemotherapy_6w", "transplant", "long_term_steroid", "biologic_therapy", "hiv_uncontrolled", "asplenia", "other"] },
          "default": []
        },
        "known_neutropenia": { "$ref": "#/$defs/triState" },
        "recent_surgery_30d": { "$ref": "#/$defs/triState" },
        "surgical_site_signs": { "$ref": "#/$defs/triState" },
        "indwelling_device": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["central_line", "urinary_catheter", "drain", "vp_shunt", "prosthesis", "none", "unknown"] }
        },
        "recent_wound_or_bite": { "$ref": "#/$defs/triState" },
        "travel_history_12m": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["place"],
            "properties": {
              "place": { "type": "string", "maxLength": 200 },
              "return_date": { "type": ["string", "null"], "format": "date" }
            }
          },
          "default": []
        },
        "malaria_risk_area": { "$ref": "#/$defs/triState" },
        "outbreak_exposure": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["dengue", "influenza", "measles", "hfmd", "covid", "other", "none", "unknown"] }
        },
        "mosquito_exposure": { "$ref": "#/$defs/triState" },
        "animal_water_exposure": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["poultry", "swine", "rodent", "dog_cat_bite", "floodwater", "none"] },
          "default": []
        },
        "sick_contact": { "$ref": "#/$defs/triState" },
        "immunization_status": { "type": ["string", "null"], "enum": ["up_to_date", "incomplete", "unknown", null] },
        "recent_vaccination_48h": { "$ref": "#/$defs/triState" }
      }
    },

    "obstetric": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "is_pregnant": { "$ref": "#/$defs/triState" },
        "gestational_weeks": { "type": ["integer", "null"], "minimum": 1, "maximum": 42 },
        "postpartum_6w": { "$ref": "#/$defs/triState" },
        "obstetric_red_flags": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "enum": ["abdominal_pain", "vaginal_bleeding", "fluid_leak", "reduced_fetal_movement"] },
          "default": []
        }
      }
    },

    "medications": {
      "type": "object",
      "additionalProperties": false,
      "required": ["nsaid_use", "antibiotic_current"],
      "properties": {
        "current_medications": { "type": "array", "items": { "type": "string", "maxLength": 120 }, "default": [] },
        "nsaid_use": { "$ref": "#/$defs/triState" },
        "anticoagulant_use": { "$ref": "#/$defs/triState" },
        "antibiotic_current": { "$ref": "#/$defs/triState" },
        "new_medication_6w": { "$ref": "#/$defs/triState" },
        "drug_allergies": { "type": "array", "items": { "type": "string", "maxLength": 120 }, "default": [] }
      }
    },

    "triage_result": {
      "type": "object",
      "additionalProperties": false,
      "required": ["triage_level", "time_target", "reason_codes", "triggered_rules", "hitl_status"],
      "properties": {
        "triage_level": { "type": "string", "enum": ["EMERGENCY", "EARLY_VISIT", "SELF_CARE"] },
        "triage_distribution": {
          "type": "object",
          "additionalProperties": false,
          "required": ["emergency", "early_visit", "self_care"],
          "properties": {
            "emergency": { "type": "number", "minimum": 0, "maximum": 1 },
            "early_visit": { "type": "number", "minimum": 0, "maximum": 1 },
            "self_care": { "type": "number", "minimum": 0, "maximum": 1 }
          }
        },
        "time_target": { "type": "string", "enum": ["now", "within_4h", "within_24h", "monitor"] },
        "conservatism_tier": { "type": "integer", "enum": [0, 1, 2] },
        "multi_risk": { "type": "boolean", "default": false },
        "reason_codes": {
          "type": "array",
          "minItems": 0,
          "uniqueItems": true,
          "items": { "type": "string", "pattern": "^RF-[0-9]{2}$" },
          "description": "Danger-sign codes only. Disease codes are explicitly forbidden."
        },
        "triggered_rules": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "pattern": "^R-[EVGS]-[0-9]{2}$" }
        },
        "guideline_refs": { "type": "array", "items": { "type": "string" }, "default": [] },
        "safety_netting_items": { "type": "array", "items": { "type": "string" }, "default": [] },
        "explanation_text": { "type": "string", "maxLength": 2000, "description": "NLG output. MUST NOT contain a diagnosis, drug dose, or test order." },
        "hitl_status": { "type": "string", "enum": ["pending", "approved", "edited", "rejected", "ask_more"] },
        "reviewer_id": { "type": ["string", "null"] },
        "reviewer_note": { "type": ["string", "null"], "maxLength": 2000 },
        "reviewed_at": { "type": ["string", "null"], "format": "date-time" }
      },
      "allOf": [
        {
          "if": { "properties": { "triage_level": { "const": "SELF_CARE" } }, "required": ["triage_level"] },
          "then": {
            "properties": {
              "safety_netting_items": { "minItems": 13 },
              "conservatism_tier": { "const": 0 }
            },
            "required": ["safety_netting_items", "conservatism_tier"]
          }
        },
        {
          "if": { "properties": { "triage_level": { "const": "EMERGENCY" } }, "required": ["triage_level"] },
          "then": {
            "properties": { "time_target": { "const": "now" }, "reason_codes": { "minItems": 1 } },
            "required": ["reason_codes"]
          }
        }
      ]
    }
  },

  "$defs": {
    "triState": {
      "type": ["boolean", "string", "null"],
      "enum": [true, false, "unknown", null],
      "description": "Tri-state. 'unknown' MUST NOT be coerced to false by any consumer."
    }
  }
}
```

### 7.2. Kết quả kiểm định schema **[EN]**

| Test | Kỳ vọng | Kết quả |
|---|---|---|
| Schema hợp lệ theo draft 2020-12 | pass | ✔ |
| Ca hợp lệ: trẻ 45 ngày, nách 38,4 °C → `EMERGENCY` | pass | ✔ |
| `SELF_CARE` mà thiếu đủ 13 mục safety-netting | **fail** | ✔ bắt được |
| `EMERGENCY` mà `time_target ≠ now` hoặc `reason_codes` rỗng | **fail** | ✔ bắt được |
| `fever_status = objective` nhưng thiếu `temp_c` | **fail** | ✔ bắt được |
| `reason_codes` chứa mã bệnh thay vì `RF-xx` | **fail** | ✔ bắt được |
| Giá trị enum tri giác sai | **fail** | ✔ bắt được |

### 7.3. Ghi chú triển khai **[EN]**

1. **`triState` là kiểu quan trọng nhất.** Mọi consumer (FE, rule engine, LLM prompt builder) phải xử lý `"unknown"` tường minh. Khuyến nghị viết unit test khẳng định `unknown !== false` ở tầng rule engine.
2. **`temp_c` không dùng `multipleOf: 0.1`** — số dấu phẩy động IEEE-754 làm ràng buộc này báo lỗi sai (38.4 bị coi là không chia hết cho 0.1). Làm tròn ở tầng ứng dụng.
3. **`reason_codes` bị ràng buộc regex `^RF-[0-9]{2}$`** — đây là cơ chế kỹ thuật thực thi ràng buộc "không chẩn đoán" ở §0.4: schema sẽ **từ chối** bất kỳ mã bệnh nào lọt vào output.
4. **Điều kiện `if/then` trong schema chỉ bắt được ràng buộc cấu trúc.** Logic triage (rule catalog §6.1) phải nằm ở rule engine riêng, có phiên bản riêng, có test riêng — **không** nhúng vào LLM prompt.
5. **Versioning:** `schema_version` + `$id` có số phiên bản. Mọi thay đổi nội dung **[E]** → tăng minor; thay đổi phá vỡ cấu trúc → tăng major; ghi log ai duyệt.
6. **Lưu trữ:** cân nhắc tách `triage_result` sang bảng riêng để giữ lịch sử nhiều lần chạy trên cùng một `session_id` (khi điều dưỡng chọn "Ask more" rồi chạy lại).

---

## PART 8 — NGUỒN THAM CHIẾU

### 8.1. Guideline quốc tế

| Mã | Nguồn | Dùng cho |
|---|---|---|
| `NICE-NG143` | NICE. *Fever in under 5s: assessment and initial management*. NG143. Xuất bản 7/11/2019; cập nhật 26/11/2021 (chỉnh sửa nhỏ 11/2025). https://www.nice.org.uk/guidance/ng143 | Traffic light, ngưỡng tuổi/nhiệt độ, safety-netting, phương pháp đo, khuyến cáo về thời lượng sốt |
| `NICE-QS64` | NICE. *Fever in under 5s* — Quality standard QS64 (2014) | Định nghĩa sốt, yêu cầu ghi nhận nguy cơ bằng traffic light |
| `NICE-NG51` | NICE. *Suspected sepsis: recognition, diagnosis and early management*. NG51, bản cập nhật 1/2024 (đưa NEWS2 vào phân tầng) | Yếu tố nguy cơ nhiễm khuẩn huyết, tiêu chí nguy cơ cao ở cộng đồng, nhánh thai kỳ |
| `AAP-2021` | Pantell RH, Roberts KB, Adams WG, et al. *Clinical Practice Guideline: Evaluation and Management of Well-Appearing Febrile Infants 8 to 60 Days Old*. Pediatrics. 2021;148(2):e2021052228 | Ngưỡng 38,0 °C, phân nhóm 8–21/22–28/29–60 ngày, giới hạn "chỉ áp dụng cho trẻ trông khỏe" |
| `WHO-IMCI` | WHO. *Integrated Management of Childhood Illness — Assess and Classify the Sick Child* | General danger signs: không uống/bú được, nôn tất cả, co giật, li bì/hôn mê |
| `IDSA-FN` | IDSA. Hướng dẫn về sốt giảm bạch cầu hạt ở người bệnh ung thư | Ngưỡng ≥38,3 °C một lần hoặc ≥38,0 °C ≥1 giờ |
| `SSC` | Surviving Sepsis Campaign (2021) | Khuyến cáo không dùng qSOFA đơn độc để sàng lọc |

### 8.2. Văn bản Việt Nam **[LOCAL]**

| Mã | Nguồn | Dùng cho |
|---|---|---|
| `BYT-2760` | Quyết định **2760/QĐ-BYT** ngày 04/7/2023 của Bộ Y tế — *Hướng dẫn chẩn đoán, điều trị Sốt xuất huyết Dengue* (thay thế QĐ 3705/QĐ-BYT năm 2019). Còn hiệu lực | Dấu hiệu cảnh báo SXHD; danh sách "khám lại ngay"; tiêu chí cân nhắc nhập viện (sống một mình, xa cơ sở y tế, không ai theo dõi, nhũ nhi, béo phì, thai phụ, ≥60 tuổi, bệnh mạn tính); cấm NSAID/aspirin; sinh lý thai kỳ; mốc không tiểu 6 giờ |

### 8.3. Cảnh báo về nguồn **[EN]**

- Các nguồn trên là **guideline dành cho nhân viên y tế có thể khám trực tiếp và làm xét nghiệm**. VMedTriage vận hành ở tầng **trước đó** (remote, không sinh hiệu, không xét nghiệm) → mọi ngưỡng đều phải dịch sang phiên bản **bảo thủ hơn**, không được áp thẳng.
- Guideline được cập nhật định kỳ. Đặt lịch **rà soát mỗi 12 tháng**, hoặc ngay khi có văn bản BYT mới về SXHD/bệnh truyền nhiễm.

---


## PART 9 — TÓM TẮT CHO ENGINEERING (1 TRANG)

```
INPUT   : fever-assessment.schema.json (draft 2020-12)
RULES   : 21 rule EMERGENCY + 20 rule EARLY_VISIT + 4 rule GUARD + 1 default
OUTPUT  : { triage_level, time_target, reason_codes[RF-xx], triggered_rules[R-x-xx],
            safety_netting_items[13 mục nếu SELF_CARE], hitl_status }

THỨ TỰ THỰC THI (bắt buộc):
  1. Chuẩn hóa tuổi → age_days_derived
  2. Tính conservatism_tier (Part 5)
  3. Chạy toàn bộ rule EMERGENCY  → nếu khớp bất kỳ: dừng, trả EMERGENCY, hiển thị NGAY (không chờ HITL)
  4. Chạy toàn bộ rule EARLY_VISIT
  5. Áp rule GUARD (chặn SELF_CARE)
  6. Áp tier escalation
  7. Nếu vẫn trống → SELF_CARE + checklist §5.4 + 13 mục safety-netting
  8. Đẩy vào hàng đợi HITL

BẤT BIẾN (viết test cho từng dòng):
  - Không rule nào hạ mức đã đặt
  - "unknown" ≠ false ở mọi nơi
  - tier 2 không bao giờ ra SELF_CARE
  - EMERGENCY luôn có ≥1 reason_code và time_target = now
  - SELF_CARE luôn kèm đủ 13 mục safety-netting
  - reason_codes chỉ chứa RF-xx, không bao giờ chứa tên/mã bệnh
  - Không có output nào chứa liều thuốc cụ thể hoặc chỉ định xét nghiệm
```

---

**HẾT TÀI LIỆU — v1.0 DRAFT**
*Chưa có hiệu lực lâm sàng cho tới khi được hội đồng chuyên môn ký duyệt. Mọi thay đổi mục **[E]** phải qua medical reviewer.*

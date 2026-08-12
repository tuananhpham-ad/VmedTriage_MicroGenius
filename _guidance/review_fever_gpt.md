# Review: Fever Conversation Specification & Fever Knowledge Model

**Files reviewed**

- `_guidance/fever-conversation-specification.md`
- `_guidance/fever-knowledge-model.md`

**Reviewer note:** Đây là review về logic sản phẩm, mô hình triage, tính khả thi hội thoại và khả năng triển khai. Không thay thế review chuyên môn của hội đồng y khoa.

---

## 1. Kết luận ngắn

Hai tài liệu có nền tảng tốt: phân tách đúng vai trò `knowledge model = WHAT/WHY` và `conversation spec = HOW`, có tri-state `unknown`, rule engine 3 mức, nguyên tắc không chẩn đoán, HITL, và cơ chế dừng ngay khi có `EMERGENCY`.

Vấn đề lớn nhất hiện tại là **knowledge model đang đánh dấu quá nhiều field là Mandatory (M)**. Conversation spec kế thừa trực tiếp định nghĩa này, dẫn tới thiết kế hội thoại phải hỏi gần như toàn bộ checklist trước khi kết luận, đặc biệt khi muốn ra `SELF_CARE`. Điều này làm tăng số lượt hỏi, giảm UX, tăng tỉ lệ bỏ cuộc, và có thể làm performance rule/LLM kém hơn do phải duy trì quá nhiều state bắt buộc.

Khuyến nghị chính: **không nên dùng một nhãn `M` duy nhất cho mọi thứ quan trọng**. Cần tách `M` thành các lớp có ý nghĩa vận hành khác nhau:

- `M0` / `P0 Safety Gate`: bắt buộc hỏi sớm, nếu dương tính có thể đổi mức ngay.
- `M1` / `Rule-critical`: bắt buộc nếu còn khả năng ra `SELF_CARE`, nhưng có thể bỏ khi đã đủ căn cứ `EARLY_VISIT`/`EMERGENCY`.
- `C` / Conditional: chỉ hỏi khi tuổi/giới/bối cảnh kích hoạt.
- `H` / Handoff-required: cần cho phiếu điều dưỡng, nhưng không nên chặn kết luận triage.
- `O`: làm giàu, không chặn.

Nếu áp dụng cách này, luồng có thể giảm từ khoảng **25-35 trường bắt buộc** xuống còn khoảng **10-14 câu hỏi cụm cho ca nguy cơ thấp**, vẫn giữ nguyên nguyên tắc an toàn: không bỏ red flag, không map `unknown` thành `false`, và không cho `SELF_CARE` nếu thiếu field thật sự ảnh hưởng checklist an toàn.

---

## 2. Nhận xét về conversation specification

### Điểm đúng/hợp lý

1. **Nguyên tắc dừng khi `EMERGENCY` là đúng.** Part 4.1 nêu rõ khi đã xác nhận một rule cấp cứu thì dừng hỏi thêm, hiển thị cảnh báo ngay. Đây là thiết kế hợp lý vì không rule nào có thể hạ mức `EMERGENCY`.

2. **Gộp câu hỏi theo cụm lâm sàng là hướng đúng.** Stage 3 gom tri giác/toàn trạng, hô hấp, tuần hoàn, thần kinh, da/xuất huyết, tiêu hóa. Cách này tốt hơn hỏi từng field rời rạc.

3. **Có skip condition và max follow-up.** Điều này giúp hạn chế vòng hỏi lại vô hạn, đặc biệt với câu trả lời mơ hồ.

4. **Có tách P0/P1/P2/P3 trong hội thoại.** Đây là lớp ưu tiên tốt hơn nhãn `M` của knowledge model. Tuy nhiên hiện tại nó bị ràng buộc ngược bởi danh sách `M` quá rộng ở KM.

### Điểm chưa hợp lý

1. **Part 1.1 đang kế thừa `M` quá cứng.** Dòng "nếu bất kỳ field nào còn unknown thì không được kết luận triage" khiến conversation phải hỏi rất nhiều câu để đi tới `SELF_CARE`. Điều này mâu thuẫn một phần với mục tiêu "hỏi bao nhiêu là đủ".

2. **Stage 3 có 14 câu P0, nhưng một số không thật sự P0.** Ví dụ `caregiver_concern_level`, `looks_very_unwell`, `chest_pain`, `rash_present`, `abdominal_pain_severity` quan trọng, nhưng không phải cùng cấp với co giật đang diễn ra, tím tái, khó đánh thức, không tiểu >6h, ban không mất khi ấn, xuất huyết tiêu hóa. Nên phân lớp trong Stage 3 thành:
   - `P0a`: cấp cứu tuyệt đối, hỏi sớm nhất.
   - `P0b`: red/amber high-yield.
   - `P1`: chỉ cần để loại trừ `SELF_CARE`.

3. **Q5-05 bị yêu cầu hỏi kể cả khi đã cấp cứu.** NSAID là quan trọng trong bối cảnh sốt xuất huyết, nhưng khi đã có `EMERGENCY`, ưu tiên là gọi cấp cứu. Câu hỏi NSAID có thể chuyển sang "sau cảnh báo" hoặc chỉ ghi nhắc "nói với nhân viên y tế thuốc đã dùng". Không nên làm nó thành bước có vẻ bắt buộc trước khi hoàn tất thông điệp cấp cứu.

4. **SELF_CARE vẫn quá đắt.** Part 4.2 nói không được bỏ Stage 3, hợp lý. Nhưng do Stage 3 + Stage 4 + Stage 5 đang chứa quá nhiều field bắt buộc, ca nhẹ vẫn phải qua quá nhiều câu hỏi. Nên xác định rõ "minimum self-care packet" thay vì "toàn bộ field M".

5. **Đường dẫn nguồn trong conversation spec có vẻ sai.** File ghi tài liệu nguồn là `docs/medical_knowledge/fever-knowledge-model.md`, nhưng file thực tế đang review nằm ở `_guidance/fever-knowledge-model.md`; trong workspace hiện tại không thấy đường dẫn `docs/medical_knowledge/fever-knowledge-model.md`.

---

## 3. Nhận xét về knowledge model

### Điểm đúng/hợp lý

1. **Tri-state `unknown` là quyết định đúng.** Với remote triage, không được suy luận im lặng là âm tính. Đây là nền tảng an toàn quan trọng.

2. **Rule "mức cao nhất thắng" là đúng.** Không có rule hạ mức giúp tránh lỗi logic nguy hiểm.

3. **Tách rule `EMERGENCY`, `EARLY_VISIT`, `GUARD`, `SELF_CARE` rõ.** Cấu trúc này phù hợp để engineering triển khai test.

4. **Các nhóm nguy cơ cao được đưa vào tier thận trọng.** Trẻ nhỏ, thai phụ, suy giảm miễn dịch, người cao tuổi, sốt rét, hậu sản, phẫu thuật/thiết bị là các nhóm hợp lý để không cho tự chăm sóc dễ dàng.

### Vấn đề lớn: định nghĩa `M` đang lẫn 4 ý nghĩa

Trong Part 3 và Part 6, `M` hiện đang bao gồm:

1. Field bắt buộc để mở protocol: `age`, `fever_reported`, `fever_status`.
2. Field red flag thật sự đổi mức ngay: `consciousness_level`, `breathing_difficulty`, `cyanosis`, `seizure_occurred`, `non_blanching_rash`, `mucosal_bleeding`, `gi_bleeding`, `urine_output`.
3. Field chỉ cần khi muốn cho `SELF_CARE`: `lives_alone`, `caregiver_available`, `can_return_for_followup`.
4. Field chủ yếu để handoff/làm giàu hoặc rule yếu hơn: `reporter_type`, `rash_present`, `diarrhea`, `antibiotic_current`, `travel_history_12m` rộng 12 tháng, `chest_pain` trong fever protocol, `caregiver_concern_level` dạng số 0-10.

Khi tất cả đều là `M`, hệ thống không còn biết field nào đáng hỏi trước, field nào có thể hoãn, field nào chỉ chặn `SELF_CARE`, field nào chỉ cần cho điều dưỡng.

### Chương 6: ma trận đối soát đang làm phình hội thoại

Part 6.2 đánh dấu rất nhiều field là `M`: hô hấp, tuần hoàn, thần kinh, da, bụng, tiêu chảy, tiết niệu, khớp, bệnh nền, miễn dịch, phẫu thuật, thiết bị, du lịch, dịch tễ, muỗi, NSAID, kháng sinh, sống một mình. Nếu conversation spec tuân thủ cứng thì một ca sốt nhẹ ở người lớn vẫn bị hỏi:

- thông tin sốt;
- 14 câu red flag;
- miễn dịch, bệnh mạn, phẫu thuật/thiết bị, du lịch, dịch tễ, muỗi;
- tiết niệu, khớp, tiêu chảy, NSAID, kháng sinh;
- sống một mình/người theo dõi.

Đây là quá dài cho user, trong khi nhiều field không đổi kết luận nếu đã đủ căn cứ `EARLY_VISIT`, hoặc không cần nếu đã có ổ triệu chứng rõ và không hướng tới `SELF_CARE`.

---

## 4. Đề xuất cải thiện: phân lớp lại bắt buộc

### 4.1. Đổi định nghĩa `M`

Đề xuất thay dòng định nghĩa hiện tại:

> Mandatory (M) = không được kết luận triage nếu thiếu.

thành:

> `M0` = bắt buộc để mở hoặc ngắt luồng an toàn; thiếu thì không chạy rule chính xác.  
> `M1` = bắt buộc trước khi kết luận `SELF_CARE`; nếu thiếu có thể ra tối thiểu `EARLY_VISIT`/`ASK_MORE` tùy tier.  
> `C` = bắt buộc khi điều kiện kích hoạt.  
> `H` = cần cho handoff/điều dưỡng nhưng không chặn triage.  
> `O` = làm giàu.

### 4.2. Tập `M0` đề xuất

Nên giữ nhỏ, hỏi ở đầu hoặc trong scan cấp cứu:

- `age_value`, `age_unit`
- `sex` hoặc ít nhất `sex_at_birth/sex` để kích hoạt thai kỳ khi phù hợp
- `fever_reported`, `fever_status`
- `temp_c`, `temp_site` chỉ khi objective
- `fever_duration_days` hoặc onset xấp xỉ
- `consciousness_level`
- `breathing_difficulty`, `cyanosis`
- `seizure_occurred` / `seizure_active_now`
- `feeding_intake`, `vomiting_severity`
- `urine_output`
- `cold_clammy_skin`
- `non_blanching_rash`
- `mucosal_bleeding`, `gi_bleeding`
- `worse_after_defervescence`

Các field này có khả năng đổi mức nhanh sang `EMERGENCY` hoặc chặn `SELF_CARE` trực tiếp.

### 4.3. Tập `M1` đề xuất, chỉ bắt buộc nếu muốn kết luận `SELF_CARE`

- `activity_vs_baseline`
- `rapid_breathing`
- `capillary_refill_ge_3s`
- `neck_stiffness`
- `severe_headache`
- `focal_neuro_deficit`
- `abdominal_pain_severity`
- `joint_limb_swelling`
- `caregiver_available`
- `can_return_for_followup`
- `lives_alone` với người lớn hoặc người không có caregiver rõ
- `nsaid_use` nếu có khả năng tư vấn chăm sóc tại nhà hoặc có nguy cơ dengue

Nếu các field này chưa rõ, không nên trả `SELF_CARE`; nhưng có thể kết luận `EARLY_VISIT` mà không cần hỏi tiếp khi đã có rule amber khác.

### 4.4. Chuyển một số `M` hiện tại xuống `C/H/O`

Đề xuất cụ thể:

| Field hiện tại | Đề xuất | Lý do |
|---|---|---|
| `reporter_type` | H | Hữu ích cho audit/handoff, nhưng không nên chặn triage. |
| `new_confusion` | C: age ≥ 16 hoặc ≥65 ưu tiên | Không áp dụng tốt cho trẻ nhỏ; có thể nằm trong câu tri giác chung. |
| `caregiver_concern_level` | M1/H | Tín hiệu tốt, nhưng không nên bắt user luôn chấm 0-10 nếu đã có kết luận cao hơn. |
| `looks_very_unwell` | M1 | Quan trọng cho self-care, nhưng có thể bỏ nếu đã `EMERGENCY`/`EARLY_VISIT`. |
| `chest_pain` | C/P1 theo tuổi/người lớn hoặc khi có triệu chứng hô hấp | Cross-protocol, không nên là M toàn bộ fever. |
| `rash_present` | C nếu hỏi `non_blanching_rash` dương/mơ hồ | `non_blanching_rash` mới là red flag; `rash_present` chủ yếu định hướng. |
| `diarrhea` | M1 hoặc O | Chỉ đổi mức qua mất nước/bloody stool; không cần bắt buộc toàn bộ ca. |
| `urinary_symptoms` | C: trẻ <5 sốt không rõ ổ; người lớn hỏi khi triệu chứng gợi ý | Knowledge model đang nói bắt buộc ở trẻ <5, nhưng bảng lại để M toàn cục. |
| `travel_history_12m` | C/P1 rút gọn: đi vùng sốt rét trong 3 tháng hoặc đi rừng/biên giới/gần đây | 12 tháng quá rộng, gây hỏi dài và nhiễu. |
| `outbreak_exposure` | H/O hoặc C theo mùa/vùng/dấu dengue | Xác suất nền, không nên chặn kết luận mọi ca. |
| `mosquito_exposure` | C khi vùng dengue/lâm sàng nghi dengue hoặc trước khi tư vấn NSAID | Ở Việt Nam muỗi rất phổ biến, hỏi toàn bộ có giá trị phân biệt thấp. |
| `antibiotic_current` | H/O hoặc C nếu sốt ≥5 ngày / đã khám trước | Không nên bắt buộc mọi ca sốt 1 ngày. |
| `recent_surgery_30d` + `indwelling_device` | M1 hoặc C bằng câu sàng lọc chung | Quan trọng, nhưng có thể gom vào "có can thiệp y tế/ống dẫn nào gần đây không". |

---

## 5. Đề xuất cải thiện hội thoại để giảm số câu

### 5.1. Dùng "question clusters" thay vì field checklist

Thay vì coi mỗi field là một câu, nên chuẩn hóa 8-10 cụm:

1. Đối tượng + tuổi + giới.
2. Sốt: có sốt, đo bao nhiêu, đo ở đâu, bắt đầu khi nào.
3. Toàn trạng: tỉnh táo, hoạt động, ăn/uống/bú.
4. Hô hấp: khó thở, thở nhanh, tím, thở rít/chảy dãi.
5. Tuần hoàn/mất nước: tay chân lạnh ẩm, tiểu 6 giờ, nôn không giữ được nước.
6. Thần kinh: co giật, cứng gáy/đau đầu dữ dội, yếu liệt/nói khó.
7. Da/xuất huyết/bụng: ban không mất khi ấn, chảy máu, đau bụng nhiều.
8. Nhóm nguy cơ: <3 tháng tự biết từ tuổi; thai/hậu sản nếu nữ; miễn dịch/hóa trị; bệnh mạn nặng; phẫu thuật/thiết bị.
9. Dịch tễ/thuốc: đi vùng sốt rét gần đây; vùng/tiếp xúc dengue nếu relevant; NSAID.
10. Điều kiện self-care: có người theo dõi, quay lại được nếu xấu đi.

Một câu cụm có thể fill 3-5 field. Khi user trả lời phủ định rõ ràng cả cụm, có thể gán false cho các field trong cụm vì đã được hỏi rõ, không phải suy luận từ im lặng.

### 5.2. Áp dụng stopping rule theo triage direction

Nên đổi logic:

- Nếu có `EMERGENCY`: dừng ngay, không hỏi thêm để hoàn thiện model.
- Nếu đã có `EARLY_VISIT`: chỉ hỏi thêm field có thể nâng lên `EMERGENCY` hoặc thay đổi nơi đi khám/thời gian trong 4h; bỏ field làm giàu.
- Nếu muốn `SELF_CARE`: phải hoàn thành `M0 + M1 self-care checklist`, nhưng không cần hoàn thành toàn bộ Part 6.

### 5.3. Dùng route theo nguy cơ thay vì hỏi mọi người như nhau

Sau 2-3 câu đầu, xác định route:

- `ROUTE_INFANT_HIGH`: trẻ <3 tháng → gần như chốt `EMERGENCY`; hỏi rất ít.
- `ROUTE_HIGH_RISK`: thai, suy giảm miễn dịch, ≥75, phẫu thuật/thiết bị, bệnh nền nặng → mục tiêu là phát hiện có cần `EMERGENCY` không; không cố chứng minh `SELF_CARE`.
- `ROUTE_STANDARD`: không nguy cơ cao → scan red flags + self-care checklist rút gọn.
- `ROUTE_DENGUE_CONTEXT`: khi có muỗi/ổ dịch/đau bụng/chảy máu/worse after defervescence/NSAID → kích hoạt câu SXHD sâu hơn.
- `ROUTE_LOCALIZED_SOURCE`: có ổ hô hấp trên nhẹ, không red flag → giảm câu hỏi làm giàu, tập trung self-care safety.

### 5.4. Đề xuất ngân sách câu hỏi

- `EMERGENCY obvious`: 3-6 câu trước cảnh báo.
- `EARLY_VISIT obvious`: 8-12 câu, chỉ hỏi để loại trừ emergency.
- `SELF_CARE candidate`: 12-16 câu cụm, cộng điều kiện theo dõi.
- `High-risk but stable`: 8-12 câu, không cố hỏi đủ để self-care vì nhiều nhóm đã tối thiểu early visit.

Ngân sách hiện tại "20-25 câu tổng cộng" vẫn hơi cao nếu đa số câu là cụm dài. Nên đo theo **turns** và **fields covered**, ví dụ tối đa 12 turns cho ca thường, trừ khi user tự cung cấp nhiều thông tin hoặc có mâu thuẫn.

---

## 6. Các điểm cần sửa cụ thể trong knowledge model

1. **Part 3.1:** thay định nghĩa `Mandatory (M)` như đề xuất `M0/M1/C/H/O`.

2. **Part 3.2:** chuyển `patient_id` và `reporter_type` khỏi `M` lâm sàng. `patient_id` là metadata hệ thống, không phải câu hỏi người dùng.

3. **Part 3.2:** `lives_alone`, `caregiver_available` nên là `M1_SELF_CARE`, không phải hỏi bắt buộc trước mọi kết luận.

4. **Part 3.4:** `new_confusion` nên conditional theo tuổi/người lớn hoặc được gom vào tri giác; không cần hỏi trẻ em theo field riêng.

5. **Part 3.8:** `rash_present` nên là conditional/handoff. Field rule chính là `non_blanching_rash`.

6. **Part 3.9:** `urinary_symptoms` đang mô tả "bắt buộc ở trẻ <5 sốt không rõ ổ", nhưng cột lại là `M`. Nên đổi thành `C (<5 và chưa rõ ổ nhiễm khuẩn)`.

7. **Part 3.9:** `diarrhea` nên hạ từ `M` xuống `M1/O`, vì rule nặng nằm ở mất nước, nôn, tiểu ít, phân máu.

8. **Part 3.10:** `travel_history_12m` nên hạ thành câu sàng lọc ngắn về vùng sốt rét/đi rừng/biên giới/gần đây. 12 tháng quá rộng cho mandatory.

9. **Part 3.10:** `outbreak_exposure`, `mosquito_exposure` nên conditional theo route dengue/local epidemiology, không nên `M` toàn cục.

10. **Part 3.11:** `antibiotic_current` nên là `H/C`, không phải `M` toàn cục.

11. **Part 5.2:** tier logic có mâu thuẫn nhẹ: người ≥75 có "Tier 1-2" nhưng rule `R-V-13` chỉ `EARLY_VISIT / 24h`. Cần làm rõ khi nào ≥75 là tier 2, và nếu tier 2 thì output tối thiểu là gì.

12. **Part 6.1:** `R-G-02` chỉ chặn SELF_CARE khi `mandatory unknown AND tier ≥1`. Nhưng Part 5.4 lại yêu cầu không có mandatory unknown để SELF_CARE cho mọi người. Cần thống nhất:
    - hoặc `R-G-02` chặn SELF_CARE cho mọi tier nếu thiếu `M1_SELF_CARE`;
    - hoặc chỉ tier ≥1 thì chặn, còn tier 0 cho phép self-care với unknown không trọng yếu.

13. **Part 7 schema:** `associated_symptoms` không nằm trong root `required`, nhưng nhiều field trong Part 3/6 lại là `M`. Schema và KM đang lệch nhau.

14. **Part 7 schema:** root required không có `medications`, nhưng `nsaid_use`, `antibiotic_current` là `M` trong KM. Cần đồng bộ.

15. **Part 7 schema:** `obstetric` không root required, hợp lý nếu conditional, nhưng Part 6 cần phản ánh đúng là conditional chứ không bắt qua `sex` quá rộng.

---

## 7. Các điểm cần sửa cụ thể trong conversation spec

1. **Part 1.1:** không nên ghi "toàn bộ field M không phụ thuộc nhánh tuổi/quần thể". Thay bằng "core safety fields + self-care-required fields theo route".

2. **Part 3.3:** tách Stage 3 thành 2 lớp:
   - `Stage 3A Emergency scan`: tri giác nặng, co giật, khó thở/tím/thở rít, sốc/không tiểu, không uống/nôn tất cả, ban không mất khi ấn, xuất huyết nặng, đau bụng dữ/bụng cứng, <3 tháng.
   - `Stage 3B Early/self-care scan`: thở nhanh, ăn giảm, hoạt động giảm, lo lắng caregiver, đau đầu/cứng gáy mơ hồ, khớp/chi, UTI ở trẻ.

3. **Part 3.4:** Stage 4 nên hỏi "risk screen" ngắn trước, chỉ mở follow-up nếu dương tính. Ví dụ: "Có đang mang thai/hậu sản, hóa trị/suy giảm miễn dịch, bệnh mạn nặng, mới mổ hoặc đang có ống/catheter, hoặc vừa đi vùng rừng núi/biên giới/sốt rét không?"

4. **Part 3.5:** `Q5-05` nên tách NSAID và antibiotic. NSAID là safety advice; antibiotic là handoff/rule bổ trợ. Không nên ép chung làm một P0.

5. **Part 4.2:** cần định nghĩa "không được bỏ Stage 3" là không bỏ **emergency/self-care minimum scan**, chứ không phải hỏi đủ tất cả 14 câu y như bảng trong mọi ca.

6. **Part 6:** thêm chính sách `unknown` theo route:
   - Unknown ở field `M0` sau re-ask → không self-care, escalate/ask_more.
   - Unknown ở field `M1` khi đã có `EARLY_VISIT` → không cần hỏi tiếp nếu không thể nâng `EMERGENCY`.
   - Unknown ở `H/O` → ghi `unknown_fields`, không chặn.

---

## 8. Mô hình câu hỏi rút gọn đề xuất

### Ca thường, không nguy cơ cao, hướng self-care

1. Tuổi/giới/người khai.
2. Có sốt không, đo bao nhiêu, đo ở đâu, từ khi nào.
3. Có tỉnh táo, sinh hoạt/ăn uống gần bình thường không.
4. Có khó thở, thở nhanh, tím, thở rít/chảy dãi không.
5. Có co giật, cứng gáy/đau đầu dữ dội, yếu liệt/nói khó không.
6. Có tay chân lạnh ẩm, không tiểu >6h, nôn không giữ được nước không.
7. Có ban tím không mất khi ấn, chảy máu bất thường, đau bụng nhiều không.
8. Có sưng đau khớp/chi hoặc không chịu đi lại không.
9. Có nguy cơ đặc biệt: thai/hậu sản, hóa trị/suy giảm miễn dịch, bệnh mạn nặng, mới mổ/thiết bị, đi vùng sốt rét gần đây không.
10. Có dùng ibuprofen/aspirin/NSAID không; có bối cảnh sốt xuất huyết quanh nhà hoặc bị muỗi nhiều không.
11. Có người theo dõi và đi khám lại được nếu xấu đi không.

Đây là 10-11 turns, nhưng cover được phần lớn red flag và checklist self-care.

### Ca đã có amber rõ

Ví dụ sốt ≥5 ngày, trẻ 3-6 tháng sốt ≥39, người ≥75, thai phụ:

- Hỏi đủ để loại trừ emergency.
- Không cần hỏi hết ổ nhiễm khuẩn, dịch tễ, antibiotic, sore throat/ear/cough nếu không đổi mức.
- Kết luận `EARLY_VISIT` với safety-netting.

### Ca đã emergency

- Hiển thị cảnh báo ngay sau field kích hoạt.
- Sau cảnh báo chỉ hỏi tối đa 1-2 thông tin routing: tuổi nếu chưa biết, thai/suy giảm miễn dịch nếu ảnh hưởng nơi đến, thuốc đã dùng nếu người dùng còn tương tác.

---

## 9. Tác động dự kiến

Nếu giữ nguyên KM hiện tại:

- `SELF_CARE` cần quá nhiều câu hỏi.
- User dễ bỏ cuộc trước khi xong.
- Nhiều ca nhẹ bị `EARLY_VISIT` chỉ vì thiếu field ít giá trị, không phải vì nguy cơ thực sự.
- Rule engine khó giải thích vì `data_gap` bị kích hoạt bởi quá nhiều field.

Nếu phân lớp lại:

- Ít câu hỏi hơn nhưng vẫn không bỏ red flag.
- Dễ test hơn: test `M0`, `M1_SELF_CARE`, `C`, `H`, `O` riêng.
- Conversation spec có thể hỏi theo route, không bị ép đi hết matrix.
- HITL nhận được unknown_fields có ý nghĩa hơn, thay vì danh sách dài do chưa hỏi hết.

---

## 10. Ưu tiên sửa

1. **Sửa Part 3.1 và Part 6.2 của knowledge model trước.** Đây là nguồn gây phình hội thoại.
2. **Đồng bộ schema Part 7 với nhãn field mới.** Root `required` nên chỉ yêu cầu object nhóm và field kỹ thuật tối thiểu; requirement lâm sàng nên để rule engine kiểm tra theo route.
3. **Sửa Part 1.1 của conversation spec để không kế thừa `M` toàn cục.**
4. **Rút Stage 3 thành emergency scan + self-care scan.**
5. **Viết bộ test case theo số lượt hỏi:** emergency ≤6, early obvious ≤12, self-care ≤16 turns.

---

## 11. Kết luận

Hai tài liệu đang đi đúng hướng về an toàn y khoa và kiến trúc rule-based triage, nhưng hiện tại **đang quá bảo thủ ở tầng data requirement**. Bảo thủ y khoa là cần thiết; bảo thủ bằng cách bắt mọi field thành `M` lại làm hội thoại dài và có thể phản tác dụng.

Cách cải thiện tốt nhất không phải giảm độ an toàn, mà là **giảm độ bắt buộc toàn cục**: phân lớp lại field theo tác động tới quyết định, route theo nguy cơ, và chỉ bắt buộc hoàn thành checklist đầy đủ khi thật sự muốn trả `SELF_CARE`.

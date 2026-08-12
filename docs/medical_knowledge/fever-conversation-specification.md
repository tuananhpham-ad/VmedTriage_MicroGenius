# CONVERSATION SPECIFICATION — TRIỆU CHỨNG: SỐT (FEVER)

**Sản phẩm:** VMedTriage — AI Symptom Assessment & Triage
**Loại tài liệu:** Conversation Design Specification (thiết kế cách AI hội thoại), dựa trên **Medical Knowledge Model**
**Symptom group:** `FEVER`
**Phiên bản:** v1.0 — DRAFT
**Ngày soạn:** 2026-08-11
**Tài liệu nguồn tham chiếu:** `docs/medical_knowledge/fever-knowledge-model.md` (v1.0) — mọi field name, mã `RF-xx`, mã rule `R-x-xx`, ngưỡng số liệu trong tài liệu này **kế thừa** từ knowledge model.

> **Vai trò của tài liệu:** Knowledge model trả lời "cần biết gì và tại sao". Tài liệu này trả lời **"hỏi thế nào, hỏi khi nào, hỏi bao nhiêu là đủ"** — để AI agent hành xử như một điều dưỡng triage giàu kinh nghiệm (hỏi có trọng tâm, gộp câu hỏi liên quan, dừng đúng lúc) thay vì một bảng câu hỏi máy móc theo thứ tự cố định.

---

## PART 0 — NGUYÊN TẮC THIẾT KẾ HỘI THOẠI

| # | Nguyên tắc | Áp dụng |
|---|---|---|
| P0-1 | **An toàn > hiệu quả.** Không bao giờ bỏ qua một câu hỏi an toàn (P0) để hội thoại ngắn gọn hơn. | Xuyên suốt Part 3–4 |
| P0-2 | **Không chẩn đoán.** Câu hỏi và phản hồi của AI không bao giờ nêu tên bệnh, chỉ mô tả dấu hiệu. | Toàn bộ script mẫu |
| P0-3 | **Gộp câu hỏi có liên quan lâm sàng** thay vì hỏi từng field rời rạc — giống cách điều dưỡng thật hỏi "có sốt, ớn lạnh, mệt mỏi gì không" trong một câu. | Part 3 |
| P0-4 | **Tri-state luôn được tôn trọng ở tầng hội thoại:** AI không được diễn giải im lặng/né tránh thành "không có". Một câu chưa trả lời rõ = `unknown`, không phải `false`. | Part 5, 6 |
| P0-5 | **Đỏ (red flag EMERGENCY) ngắt hội thoại ngay** — hiển thị cảnh báo tức thì, không chờ hỏi hết checklist, không chờ duyệt HITL. | Part 4 |
| P0-6 | **Khi nghi ngờ giữa hai mức thận trọng, chọn mức thận trọng hơn** — cả ở việc diễn giải câu trả lời mơ hồ lẫn ở việc quyết định hỏi thêm hay dừng. | Part 5, 6 |
| P0-7 | **Ngôn ngữ hội thoại:** tiếng Việt, giọng điệu điều dưỡng — ấm áp, rõ ràng, không thuật ngữ y khoa khó hiểu, câu hỏi ngắn (≤2 ý/câu). | Toàn bộ script mẫu |

---

## PART 1 — MỤC TIÊU HỘI THOẠI

### 1.1. Thông tin luôn phải thu thập (trước khi kết luận triage)

Chia 5 tier: `M0`, `M1`/`M1_SELF_CARE`, `C`, `H`, `O` (xem KM §3.1 điểm 3). Ý nghĩa vận hành cho hội thoại:

- **Kết luận triage nói chung** (bất kỳ mức nào trong 3 mức) chỉ cần **`M0` đầy đủ** (+ quét red flag ở Stage 3A) — đây là điều kiện tối thiểu để hệ thống "biết nói gì".
- **Kết luận `SELF_CARE`** cần thêm **`M1`/`M1_SELF_CARE` đầy đủ** cho route đang áp dụng (xem Part 4/6 — routing). Thiếu `M1` không chặn `EARLY_VISIT`/`EMERGENCY`, chỉ chặn `SELF_CARE`.
- **`H` (handoff)** không bao giờ chặn kết luận — chỉ cần có trên phiếu bàn giao điều dưỡng trước khi đóng phiên.
- **`O` (optional)** không chặn gì, chỉ hỏi khi còn ngân sách.

Nếu một field `M0` còn `unknown` khi kết thúc hội thoại, hệ thống **không được kết luận triage nào cả**, phải đặt `data_gap = true`, `ask_more`, và tối thiểu nâng `EARLY_VISIT` nếu tier ≥1 (theo `R-G-02`, KM §6.1a). Nếu chỉ field `M1` còn `unknown`, hệ thống **vẫn có thể** kết luận `EARLY_VISIT`/`EMERGENCY` bình thường — chỉ riêng `SELF_CARE` bị chặn.

| Nhóm | Field `M0` (chặn mọi kết luận) | Field `M1`/`M1_SELF_CARE` (chỉ chặn `SELF_CARE`) |
|---|---|---|
| Định danh & tuổi | `age_value`, `age_unit`, `sex` | — |
| Cổng sốt | `fever_reported`, `fever_status`, `fever_onset_at`→`fever_duration_days` | — |
| Đặc điểm sốt an toàn | `rigors`, `antipyretic_taken`, `worse_after_defervescence` | — |
| Toàn trạng | `consciousness_level`, `feeding_intake` | `activity_vs_baseline`, `caregiver_concern_level`, `looks_very_unwell` |
| Hô hấp | `breathing_difficulty`, `cyanosis`, `stridor_or_drooling` | `rapid_breathing`; `chest_pain` là `C` (cross-protocol) |
| Tuần hoàn | `cold_clammy_skin`, `capillary_refill_ge_3s`, `urine_output`, `vomiting_severity` | `dizziness_on_standing` |
| Thần kinh | `seizure_occurred`, `neck_stiffness`, `severe_headache`, `focal_neuro_deficit` | — |
| Da/xuất huyết | `non_blanching_rash`, `mucosal_bleeding`, `gi_bleeding` | `rash_present` là `C` (chỉ khi `non_blanching_rash` dương/mơ hồ) |
| Triệu chứng kèm | `abdominal_pain_severity` | `diarrhea`, `joint_limb_swelling`; `urinary_symptoms` là `C` (<5 tuổi, không có ổ rõ) |
| Nguy cơ | — | `chronic_conditions`, `immunocompromised`, `recent_surgery_30d`+`indwelling_device` (có thể gộp 1 câu); `travel_history_12m`/`malaria_risk_area`, `outbreak_exposure`, `mosquito_exposure` là `C`/`H` (kích hoạt theo câu sàng lọc gộp — xem 3.4) |
| Thuốc an toàn | — | `nsaid_use` là `C`/`M1` (route dengue-context); `antibiotic_current` là `H`/`C` |
| Bối cảnh an toàn | — | `lives_alone`, `caregiver_available`, `can_return_for_followup` (hiệu lực `M1` khi hướng `SELF_CARE`) |

`reporter_type` là `H` (cho phiếu bàn giao, không chặn kết luận).

### 1.2. Thông tin tùy chọn (làm giàu, không chặn kết luận) — tier `O`, và `H` khi không kích hoạt điều kiện `C`

`fever_pattern`, `temp_device_type`, `temp_max_24h_c`, `antipyretic_total_24h_mg`, `antipyretic_response`, `dehydration_signs`, `hemoptysis`, `spo2_percent`, `jaundice_new`, `localized_infection_signs`, `abdominal_pain_location`, `bloody_stool`, `sore_throat`/`ear_pain`/`cough`, `myalgia_retroorbital_pain`, `obesity_or_malnutrition`, `current_medications`, `new_medication_6w`, `drug_allergies`, `anticoagulant_use`, `animal_water_exposure`, `sick_contact`, `access_to_care_minutes`, `weight_kg`, `reporter_type`(H), `outbreak_exposure`(H/O ngoài điều kiện `C`), `antibiotic_current`(H ngoài điều kiện `C`).

→ Chỉ hỏi nếu còn "ngân sách câu hỏi" (xem Part 6) và chưa có kết luận đủ căn cứ.

### 1.3. Khi nào dừng hỏi

Áp dụng **điều kiện nào đến trước thì dừng theo điều kiện đó**:

1. **Chốt đỏ:** một red flag `EMERGENCY` được xác nhận → dừng thu thập thường quy, chuyển thẳng Stage 6 (nhánh cấp cứu) — xem Part 4.
2. **Đủ căn cứ:** toàn bộ field `M0` (và `M1`/`M1_SELF_CARE` nếu đang hướng `SELF_CARE`), bao gồm field `C` được kích hoạt theo tuổi/quần thể, đã có giá trị xác định (không còn `unknown` ảnh hưởng rule) → dừng, sang Stage 6.
3. **Hết ngân sách câu hỏi** mà phần còn thiếu chỉ là field `O`: dừng, ghi nhận `unknown_fields`, sang Stage 6.
4. **Người dùng không thể tiếp tục** (mất kết nối, quá hoảng loạn, từ chối trả lời): dừng ngay, áp dụng mức thận trọng nhất có thể suy ra từ dữ liệu đã có, đặt `data_gap = true`, `hitl_status = ask_more`.

---

## PART 2 — CÁC GIAI ĐOẠN HỘI THOẠI (CONVERSATION STAGES)

| Stage | Tên | Mục tiêu | Field chính | Điều kiện thoát sớm |
|---|---|---|---|---|
| **0** | Xác định đối tượng | Biết đang hỏi cho ai, tuổi bao nhiêu — vì tuổi quyết định toàn bộ ngưỡng & nhánh hỏi phía sau | `age_value`, `age_unit`, `sex`, `reporter_type` | Không có — luôn chạy đủ, chỉ 1–2 câu |
| **1** | Phát hiện sốt | Xác nhận có sốt, sốt khách quan hay chủ quan, số đo/vị trí/thời điểm nếu có | `fever_reported`, `fever_status`, `temp_c`, `temp_site`, `temp_measured_at` | Nếu `fever_reported = false` → ra ngoài phạm vi protocol sốt (bàn giao sang luồng khác, không thuộc spec này) |
| **2** | Đặc điểm sốt | Thời gian sốt, rét run, đáp ứng hạ sốt, dấu hiệu "khó chịu hơn dù đã hạ sốt" | `fever_onset_at`, `rigors`, `antipyretic_*`, `worse_after_defervescence` | Không có — đây là input bắt buộc cho mọi rule |
| **3A** | Phát hiện red flag — Emergency scan | Quét các field `M0` red-flag: tri giác, co giật, khó thở/tím/thở rít, sốc/không tiểu, không uống/nôn tất cả, ban không mất khi ấn, xuất huyết nặng, đau bụng dữ/bụng cứng, tuổi <3 tháng | ~8-10 câu hỏi tổ hợp `P0`, xem Part 3.3A | **Dừng ngay** tại câu đầu tiên xác nhận 1 red flag `EMERGENCY` (Part 4) |
| **3B** | Phát hiện red flag — Early/self-care scan | Quét các field `M1`: thở nhanh, ăn giảm, hoạt động giảm, lo lắng caregiver, đau đầu/cứng gáy mơ hồ, khớp/chi | ~4-6 câu hỏi tổ hợp `P1`, xem Part 3.3B | Chỉ chạy nếu Stage 3A âm tính; bỏ qua nếu đã hướng `EARLY_VISIT`/`EMERGENCY` và các field này không thể đổi kết luận |
| **4** | Đánh giá quần thể nguy cơ | Thai kỳ, suy giảm miễn dịch, bệnh mạn tính, phẫu thuật/thiết bị, du lịch/sốt rét, dịch tễ SXHD, hoàn cảnh sống | Field nhóm RISK (§3.10 KM) | Bỏ các nhánh không áp dụng theo tuổi/giới (điều kiện `C` tự skip) |
| **5** | Thu thập phần còn lại | Triệu chứng kèm theo cơ quan, thuốc an toàn (NSAID), làm giàu thông tin | Field nhóm G, N (một phần), MEDICATION | Bỏ toàn bộ nếu đã vào nhánh cấp cứu ở Stage 3 |
| **6** | Kết thúc đánh giá | Rà soát mâu thuẫn, tóm tắt, hiển thị safety-netting (nếu `SELF_CARE`), bàn giao HITL hoặc escalate cấp cứu | `contradiction_flags`, `triage_level`, `hitl_status` | — |

**Lưu ý về Stage 0:** không phải là stage tách biệt, về mặt vận hành, tuổi phải được biết **trước** khi hỏi bất kỳ câu nào về sốt — vì ngưỡng nhiệt độ, cách diễn giải "trông mệt" đều lệ thuộc tuổi. Do đó Stage 0 được gộp làm **bước mở đầu của Stage 1** trong luồng thực tế, nhưng tách bảng riêng ở đây để rõ ràng.

---

## PART 3 — CÂU HỎI THÍCH ỨNG (ADAPTIVE QUESTIONING)

### Quy ước

- **Priority:** `P0` = an toàn tối khẩn, không được bỏ qua trừ khi đã chốt `EMERGENCY`; `P1` = bắt buộc cho triage; `P2` = bắt buộc có điều kiện (theo tuổi/giới/nhóm nguy cơ); `P3` = làm giàu, hỏi nếu còn ngân sách.
- Nhiều field liên quan lâm sàng được **gộp vào một câu hỏi tổ hợp** (giống cách điều dưỡng thật hỏi) — cột "Field" liệt kê tất cả field mà một câu trả lời có thể phủ.
- "Follow-up" là câu hỏi làm rõ được kích hoạt **chỉ khi** câu trả lời đầu mơ hồ hoặc dương tính cần chi tiết hơn — không phải hỏi mặc định.
- **Không hỏi lại field đã có giá trị xác định.** Nếu một câu trả lời tự do (kể cả trả lời cho câu hỏi khác, hoặc mô tả chủ động ngay từ đầu hội thoại) đã phủ được nhiều field cùng lúc — kể cả field thuộc câu hỏi ở stage sau — hệ thống phải **ghi nhận ngay các field đó** và **bỏ qua câu hỏi tương ứng** khi tới lượt, không hỏi lại để "xác nhận cho chắc". Chỉ hỏi lại nếu giá trị còn mơ hồ (theo Part 5) hoặc thuộc field an toàn `P0` cần xác nhận rõ ràng theo cách hỏi chuẩn (vd red flag ở Stage 3A vẫn hỏi đúng script dù đã có gợi ý, để tránh bỏ sót do suy diễn).
- **Khi người dùng chủ động sửa lại một câu trả lời trước đó** (vd "à không, không phải 3 ngày, là 5 ngày rồi"), hệ thống phải **lấy giá trị mới nhất** ghi đè giá trị cũ cho field đó, không giữ giá trị ban đầu và không hỏi lại các câu đã hỏi dựa trên giá trị cũ trừ khi giá trị mới làm thay đổi điều kiện kích hoạt của những câu đó (vd sửa tuổi từ người lớn thành trẻ nhũ nhi → phải chạy lại các nhánh `C` phụ thuộc tuổi).

### 3.0. Stage 0 — Xác định đối tượng

| ID | Câu hỏi (script) | Mục đích | Field | Priority | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|---|
| Q0-01 | "Cho em/mình hỏi, người đang cần tư vấn là bé hay người lớn ạ? Năm nay bao nhiêu tuổi (nếu là trẻ nhỏ thì bao nhiêu tháng) ạ?" | Xác định biến phân tầng nguy cơ chính, quyết định toàn bộ nhánh hỏi & ngưỡng sau này | `age_value`, `age_unit`, `reporter_type` | P0 | Luôn hỏi đầu tiên | Không bao giờ skip | Nếu trả lời mơ hồ ("cháu còn nhỏ lắm") → hỏi neo cụ thể: "bé được mấy tháng, hay đã hơn 1 tuổi rồi ạ?" | 1 |
| Q0-02 | "[Bé/Anh/chị] là nam hay nữ ạ?" | Điều hướng nhánh sản khoa/tiết niệu (Stage 4) | `sex` | P1 | Luôn hỏi | Không skip | — | 0 |

### 3.1. Stage 1 — Phát hiện sốt

| ID | Câu hỏi | Mục đích | Field | Priority | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|---|
| Q1-01 | "Hiện tại [bé/anh chị] có đang sốt hoặc cảm thấy nóng người không ạ?" | Cổng vào toàn bộ protocol sốt | `fever_reported` | P0 | Luôn hỏi ngay sau Stage 0 | Không skip | — | 0 |
| Q1-02 | "Đã đo nhiệt độ chưa ạ? Nếu có, đo được bao nhiêu độ, đo ở đâu (nách/miệng/tai/hậu môn), và đo cách đây bao lâu rồi?" | Phân loại sốt khách quan/chủ quan; đầu vào ngưỡng theo vị trí đo | `fever_status`, `temp_c`, `temp_site`, `temp_measured_at` | P0/P1 | Sau khi `fever_reported = true` | Không skip | Nếu thiếu vị trí đo → hỏi riêng ("đo ở nách hay ở đâu ạ?"); nếu đo đã lâu (>6h) → hỏi "hiện giờ sờ vẫn thấy nóng không?" | 1 |
| Q1-03 | "Hiện có nhiệt kế để đo thử ngay bây giờ không ạ? Nếu chưa có, mình tiếp tục các câu hỏi khác trước." | Cố gắng nâng `subjective` → `objective`; hướng dẫn đo tại nhà (bắt buộc theo §1.3 KM khi `SUBJECTIVE`) | `fever_status` (nâng cấp), `temp_device_type` | P2 | `fever_status = subjective` | Người dùng đã xác nhận không có nhiệt kế / đang trong tình huống gấp | — | 1 |

> **Không loại bỏ ca khi `fever_status = subjective`** — tiếp tục toàn bộ luồng bình thường, chỉ đánh dấu `measurement_confidence = subjective` để điều dưỡng biết (§1.3 KM).

### 3.2. Stage 2 — Đặc điểm sốt

| ID | Câu hỏi | Mục đích | Field | Priority | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|---|
| Q2-01 | "[Bé/Anh chị] bắt đầu sốt từ khi nào ạ — mấy ngày rồi?" | Tính `fever_duration_days` — mốc 5/7 ngày | `fever_onset_at` → `fever_duration_days` | P0 | Luôn hỏi | Không skip | Nếu mơ hồ ("mấy hôm nay", "lâu rồi") → neo mốc cụ thể (xem Part 5) | 2 |
| Q2-02 | "Sốt có kèm rét run dữ dội, người run bần bật, đắp chăn cũng không đỡ không ạ?" | Amber signal — gợi ý nhiễm khuẩn huyết/sốt rét | `rigors` | P1 | Luôn hỏi | Không skip | Phân biệt "rét run dữ dội" với "hơi ớn lạnh" nếu trả lời không chắc | 1 |
| Q2-03 | "Đã dùng thuốc hạ sốt chưa ạ? Nếu có, thuốc gì, uống lúc nào, và sau đó có đỡ sốt không?" | Sàng lọc NSAID (an toàn SXHD); đánh giá độ che lấp nhiệt độ | `antipyretic_taken`, `antipyretic_drug`, `antipyretic_response` | P1 (M vì an toàn) | Luôn hỏi | Không skip | Nếu không nhớ tên thuốc → gợi ý mô tả vỏ hộp/màu viên | 1 |
| Q2-04 | "Sau khi hạ sốt (hoặc hết sốt), [bé/anh chị] có thấy mệt hơn, lừ đừ hơn, hay là đỡ hơn hẳn ạ?" | **Dấu hiệu khám lại ngay theo QĐ 2760 — RF-29, có thể đơn độc đẩy thẳng lên `EMERGENCY`** | `worse_after_defervescence` | P0 | Sau khi đã có ít nhất 1 lần hạ sốt/cắt sốt; nếu đang sốt liên tục chưa từng hạ → đánh dấu N/A, không phải unknown | Chưa từng hạ sốt lần nào | Nếu câu trả lời chung chung ("cũng bình thường") → so sánh cụ thể mức hoạt động trước/sau | 1 |
| Q2-05 | "Có lúc nào đo hoặc cảm thấy người lạnh bất thường, dưới mức bình thường không?" | Hạ thân nhiệt = red flag tương đương sốt ở nhóm nguy cơ | `hypothermia_reported` | P1 | `age < 3 tháng` HOẶC `age ≥ 65` HOẶC `immunocompromised = true` (biết trước từ Stage 0/4) | Ngoài các điều kiện trên | — | 1 |

### 3.3A. Stage 3A — Emergency scan (field `M0`)

> **Toàn bộ câu hỏi trong bảng này có độ ưu tiên hỏi `P0`** (hỏi sớm nhất, không được hoãn) — phần lớn ánh xạ tới field tier `M0` trong KM §3, nhưng một số câu cũng gom kèm field tier `C` liên quan cùng cụm lâm sàng (vd `seizure_active_now`/`seizure_features`, `chest_indrawing`, `nasal_flaring_grunting`, `bulging_fontanelle`, `rash_present`/`rash_type`, `abdominal_pain_location`, `abdominal_guarding`) để tránh hỏi rời rạc. **`P0` là độ ưu tiên hỏi, không đồng nhất với tier `M0`** — field `C` trong bảng này vẫn chỉ bắt buộc khi điều kiện kích hoạt của nó đúng. Nguyên tắc vận hành: hỏi tuần tự Q3-01 → Q3-13; **ngay khi một câu trả lời xác nhận điều kiện `EMERGENCY`**, dừng bảng này lập tức và chuyển Part 4 (Optimization). Đây là "minimum scan" bắt buộc cho **mọi** route (kể cả `ROUTE_LOCALIZED_SOURCE`) — không được rút gọn thêm.

> **Kỹ thuật hỏi gộp-phủ-định-cả-cụm (batch negation), áp dụng cho cả Stage 3A và 3B:** để tiết kiệm lượt hỏi, mỗi câu tổ hợp trong hai bảng scan có thể diễn đạt dưới dạng liệt kê rồi hỏi phủ định gộp — ví dụ Q3-06 hỏi "Có khó thở không? Môi/đầu ngón tay có tím tái không? Ngực có rút lõm, cánh mũi phập phồng, thở rên không?" rồi chốt bằng "— có dấu hiệu nào trong số này không ạ?". Cách xử lý câu trả lời:
> - Nếu người dùng trả lời **phủ định tường minh cho cả cụm** ("không có gì cả", "không, hoàn toàn bình thường") → gán `false` cho **toàn bộ field trong cụm đó cùng lúc**, không hỏi lại từng field riêng. 
> - Nếu người dùng chọn **"có"** cho một hoặc vài ý trong cụm → chỉ hỏi làm rõ (follow-up) riêng cho (các) field đó, các field còn lại trong cụm mà người dùng phủ định vẫn gán `false` bình thường.
> - Nếu người dùng trả lời **"không chắc"/mơ hồ** cho một ý cụ thể trong cụm → chỉ field đó đi vào quy trình làm rõ mơ hồ (Part 5, tối đa 2 lần), các field khác trong cụm đã được phủ định rõ ràng vẫn gán `false`, không kéo cả cụm thành `unknown`.
> - Kỹ thuật này không áp dụng cho các câu hỏi bắt buộc phải xác nhận riêng lẻ theo script chuẩn dù đã có phủ định gộp trước đó (vd Q3-01 tri giác, Q3-03 co giật) — nếu ngữ cảnh cho thấy câu phủ định gộp có thể che lấp một dấu hiệu an toàn tối khẩn, vẫn hỏi lại đúng câu chuẩn thay vì suy diễn từ phủ định gộp.

| ID | Câu hỏi | Mục đích | Field | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|
| Q3-01 | "[Bé/Anh chị] hiện có tỉnh táo bình thường không — dễ đánh thức, phản ứng gọi hỏi bình thường không? [<5 tuổi: bé có cười, giao tiếp mắt, phản ứng khi gọi tên không?]" | Yếu tố tiên lượng mạnh nhất mọi thang triage (RF-01) | `consciousness_level`, `social_response_child`(C: <5t) | Luôn hỏi đầu Stage 3A | Không skip | Nếu "khó đánh thức" không rõ do mệt hay do lơ mơ bệnh lý → hỏi cụ thể "gọi to có mở mắt/phản ứng ngay không" | 2 |
| Q3-03 | "Trong đợt sốt này có bị co giật không — tay chân giật, mắt trợn, cứng người? Có đang co giật ngay lúc này không?" | IMCI general danger sign (RF-02); co giật đang diễn ra là cấp cứu tối khẩn | `seizure_occurred`, `seizure_active_now` | Luôn hỏi | Không skip | Nếu `occurred = true` và không active → hỏi đặc điểm cơn (khu trú một bên? kéo dài >5 phút? tái diễn trong 24h? chưa tỉnh hẳn sau cơn?) | 2 |
| Q3-04 | "Có bị cứng gáy (khó cúi cổ chạm cằm ngực), sợ ánh sáng, hoặc đau đầu dữ dội khác thường không? [trẻ nhũ nhi: thóp có phồng lên không?]" | Bộ ba nghi nhiễm khuẩn màng não — cửa sổ điều trị tính bằng giờ (RF-04) | `neck_stiffness`, `photophobia`, `severe_headache`, `bulging_fontanelle`(C: <18 tháng) | Luôn hỏi | Không skip | Nếu "đau đầu dữ dội" không rõ mức độ → so sánh với đau đầu thông thường của người đó (đau đầu **mơ hồ**, không dữ dội → không tính là dương tính ở đây, có thể ghi nhận thêm ở Stage 3B) | 1 |
| Q3-05 | "Có bị yếu tay/chân một bên, méo miệng, hoặc nói khó/nói ngọng mới xuất hiện không?" | Cross-protocol viêm não/đột quỵ (RF-06) | `focal_neuro_deficit` | Luôn hỏi | Không skip | — | 0 |
| Q3-06 | "Có khó thở không? Môi hoặc đầu ngón tay có tím tái không? [<5 tuổi: ngực có rút lõm khi thở, cánh mũi có phập phồng, có thở rên không?]" | Cấu phần red hô hấp (RF-07, 08, 09) | `breathing_difficulty`, `cyanosis`, `chest_indrawing`(C:<5t), `nasal_flaring_grunting`(C:<5t) | Luôn hỏi | Không skip | Nếu "khó thở nhẹ" mơ hồ → hỏi có ảnh hưởng nói chuyện/bú/ăn không | 1 |
| Q3-07 | "Có thở rít khi hít vào, chảy nước dãi liên tục không nuốt được, hoặc phải ngồi chồm người ra trước mới dễ thở không?" | Nghi tắc nghẽn đường thở trên — **không được yêu cầu người nhà há miệng khám họng** (RF-10) | `stridor_or_drooling` | Luôn hỏi (câu ngắn) | Đã xác nhận `cyanosis`/`breathing_difficulty=severe` (đã đủ căn cứ EMERGENCY, hỏi thêm không đổi kết luận) | — | 0 |
| Q3-08 | "Da có lạnh, ẩm, hoặc nổi vân tím (nổi bông) không? Nếu ấn vào đầu ngón tay/chân rồi thả ra, màu hồng trở lại có chậm hơn khoảng 3 giây không?" | Dấu hiệu sốc — tương ứng giai đoạn sốc trong SXHD (RF-13) | `cold_clammy_skin`, `capillary_refill_ge_3s` | Luôn hỏi | Không skip | Hướng dẫn cách tự đo CRT nếu chưa từng làm | 1 |
| Q3-09 | "Trong 6 giờ qua có đi tiểu không ạ? Có ăn uống/bú được bình thường không? Có nôn nhiều không — nôn xong có giữ được nước/sữa sau đó không?" | Chỉ dấu tưới máu thận (RF-14); IMCI danger sign "không uống được", "nôn tất cả" (RF-15) | `urine_output`, `feeding_intake`, `vomiting_severity` | Luôn hỏi | Không skip | Nếu "không nhớ"/"nôn vài lần" mơ hồ → hỏi cụ thể tần suất/thời điểm | 1 |
| Q3-11 | "Trên da có nổi ban đỏ/tím không ạ? Nếu có, lấy cốc thủy tinh (hoặc ngón tay) ấn vào vết ban — màu có mất đi không hay vẫn còn?" | **Ban không mất khi ấn kính = red flag kinh điển nghi não mô cầu** (RF-18); `rash_present` chỉ hỏi tiếp khi có ban để làm rõ | `non_blanching_rash`, `rash_present`(C), `rash_type`(C) | Luôn hỏi | Không skip | Hướng dẫn từng bước cách làm "glass test" nếu người dùng chưa hiểu | 2 |
| Q3-12 | "Có chảy máu bất thường không — chảy máu chân răng, chảy máu mũi không rõ nguyên nhân, nôn ra máu/dịch nâu, đi ngoài phân đen, hoặc [nữ] ra máu âm đạo bất thường?" | Dấu hiệu cảnh báo SXHD → chỉ định nhập viện (RF-19, 20) | `mucosal_bleeding`, `gi_bleeding` | Luôn hỏi | Không skip | — | 0 |
| Q3-13 | "Có đau bụng không ạ? Nếu có, đau mức nào — âm ỉ, hay đau nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào?" | Cảnh báo SXHD + nghi bụng ngoại khoa (RF-39) | `abdominal_pain_severity`, `abdominal_pain_location`(C), `abdominal_guarding` | Luôn hỏi | Không skip | Dùng thang so sánh nếu "đau bụng" mơ hồ (xem Part 5) | 2 |

Tuổi <3 tháng được biết từ Stage 0 và tự nâng `EMERGENCY` ngay (RF-22) mà không cần chờ hết Stage 3A.

### 3.3B. Stage 3B — Early/self-care scan (field `M1`)

> Chỉ chạy khi Stage 3A **âm tính toàn bộ**. Các câu hỏi trong bảng này là `P1`, ánh xạ tới field tier `M1` trong KM §3 — cần thiết để mở khả năng kết luận `SELF_CARE`, nhưng **không** chặn `EARLY_VISIT`/`EMERGENCY` nếu bị bỏ qua. Nếu đã có căn cứ `EARLY_VISIT` từ nơi khác (vd Stage 4) và các field này không thể đổi kết luận, có thể bỏ qua bảng này (xem Part 4.2/Part 6 routing).

| ID | Câu hỏi | Mục đích | Field | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|
| Q3-01b | "So với ngày thường, mức độ chơi/hoạt động có giảm nhiều không? Thở có nhanh hơn/gắng sức hơn bình thường không?" | Chuẩn hóa theo baseline (RF liên quan hoạt động) + dấu hiệu nặng hô hấp nhận biết từ xa (RF-11 nhẹ) | `activity_vs_baseline`, `rapid_breathing` | Sau Stage 3A âm tính | Đã chốt `EMERGENCY`/`EARLY_VISIT` từ nơi khác và câu này không đổi kết luận | — | 1 |
| Q3-08b | "Khi đứng dậy đột ngột có thấy choáng váng, hoa mắt, hoặc muốn ngất không?" | Dấu hiệu giảm thể tích tuần hoàn/tiền sốc, bổ sung cho cụm tuần hoàn ở Q3-08 (RF-13 mức nhẹ) | `dizziness_on_standing` | Sau Stage 3A âm tính; ưu tiên hỏi cùng cụm với Q3-01b | Đã chốt `EMERGENCY`/`EARLY_VISIT` từ nơi khác và câu này không đổi kết luận; hoặc bệnh nhân không tự đứng được (đã có căn cứ nặng hơn từ Q3-08/Q3-09) | — | 0 |
| Q3-02 | "Gần đây có ai nhận thấy [tên] nói lẫn, không nhận ra người quen, hoặc hành vi khác lạ hẳn không?" | Ở người lớn tuổi/suy giảm miễn dịch có thể là **biểu hiện duy nhất** của nhiễm khuẩn nặng (RF-05) | `new_confusion` | `age ≥ 16` (ưu tiên hỏi kỹ nếu `age ≥ 65`) | `age < 16` | — | 1 |
| Q3-13b | "Bé/anh chị có sưng, đau khớp hoặc chi nào không? Có chịu đi lại, dùng tay chân bình thường không?" | Amber NICE — nghi nhiễm khuẩn xương khớp, dễ bỏ sót (RF-41) | `joint_limb_swelling`, `non_weight_bearing`(C: <16t) | Sau Stage 3A âm tính | Không skip | — | 0 |
| Q3-14 | "Trên thang 0–10, [anh/chị] lo lắng đến mức nào về tình trạng hiện tại? Và so với ngày thường, [bé/anh chị] có trông khác hẳn, mệt rõ rệt hơn không?" | Tín hiệu độc lập có giá trị (NICE); proxy "ill-appearance" khi không khám trực tiếp được (RF-44) | `caregiver_concern_level`, `looks_very_unwell` | Đặt cuối Stage 3B như "gut-check" tổng kết | Có thể rút gọn thành câu quan sát ngắn (bỏ thang 0–10) nếu đã có kết luận cao hơn `SELF_CARE` — xem KM §3.4 field `caregiver_concern_level` | Nếu điểm lo lắng ≥8 nhưng chưa tìm ra RF nào khác → hỏi cụ thể "điều gì khiến anh/chị lo nhất" — có thể lộ ra chi tiết bị bỏ sót | 1 |

**Mọi tham chiếu "Stage 3" ở các phần khác của tài liệu này** (Part 2, Part 4, Part 6, Part 7 sơ đồ, Part 8 ví dụ) hiểu là **Stage 3A + Stage 3B**, trừ khi ghi rõ chỉ 3A hoặc chỉ 3B.

### 3.4. Stage 4 — Đánh giá quần thể nguy cơ

| ID | Câu hỏi | Mục đích | Field | Priority | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|---|
| Q4-00 | "Cho em hỏi thêm để đánh giá đầy đủ hơn: hiện có đang mang thai/mới sinh, đang hóa trị/dùng thuốc ức chế miễn dịch, có bệnh mạn tính nặng (tim/phổi/gan/thận/tiểu đường/máu), mới phẫu thuật hoặc đang có ống thông/catheter trên người, hoặc vừa đi vùng rừng núi/biên giới/sốt rét trong 1–3 tháng gần đây không?" | Câu sàng lọc rủi ro gộp — chỉ branch chi tiết khi dương tính, tránh hỏi 5-6 câu `M1` riêng lẻ cho ca nguy cơ thấp | Sơ bộ cho `is_pregnant`, `immunocompromised`, `chronic_conditions`, `recent_surgery_30d`/`indwelling_device`, `malaria_risk_area` | P1 | Luôn hỏi 1 lần, dạng câu hỏi kép | Không skip | Nếu **bất kỳ** ý nào được xác nhận dương tính/mơ hồ → hỏi tiếp câu chi tiết tương ứng (Q4-01…Q4-06 bên dưới) cho đúng nhóm đó; nếu toàn bộ âm tính rõ ràng → bỏ qua Q4-01…Q4-06, chỉ giữ Q4-07/Q4-08 | 1 |
| Q4-01 | "Hiện có đang mang thai không ạ? Nếu có, được khoảng bao nhiêu tuần rồi?" | Nhánh sản khoa riêng — sinh lý che lấp sốc (RF-32) | `is_pregnant`, `gestational_weeks` | P1 | `sex = female` AND `10 ≤ age ≤ 60` AND Q4-00 dương tính (ý thai kỳ) | Nam giới, ngoài khoảng tuổi, hoặc Q4-00 âm tính rõ ràng | Nếu `is_pregnant = true` → Q4-01b | 1 |
| Q4-01b | "Có ra máu/dịch bất thường ở âm đạo, đau bụng từng cơn, hoặc thấy thai cử động ít hơn hẳn không?" | Nâng mức khẩn cấp sản khoa | `obstetric_red_flags` | P0 | `is_pregnant = true` hoặc `postpartum_6w = true` | Ngoài điều kiện trên | — | 0 |
| Q4-02 | "Trong 6 tuần gần đây có sinh nở, sảy thai, hoặc nạo hút thai không?" | Nguy cơ nhiễm khuẩn hậu sản (RF-32) | `postpartum_6w` | P1 | `sex = female` AND `15 ≤ age ≤ 55` AND chưa xác nhận đang mang thai AND Q4-00 dương tính (ý thai kỳ/hậu sản) | Nam giới, đã xác nhận đang mang thai, hoặc Q4-00 âm tính rõ ràng | — | 0 |
| Q4-03 | "Có đang hóa trị ung thư, ghép tạng, dùng thuốc ức chế miễn dịch/corticoid kéo dài, hoặc biết mình bị suy giảm miễn dịch (HIV, đã cắt lách...) không?" | **Nhóm nguy cơ cao nhất — sốt giảm bạch cầu hạt là cấp cứu nội khoa** (RF-30, 31) | `immunocompromised`, `immunocompromise_cause`, `known_neutropenia` | P1 | Q4-00 dương tính (ý miễn dịch/hóa trị) hoặc mơ hồ | Q4-00 âm tính rõ ràng cho ý này | Nếu đang hóa trị → hỏi thời điểm gần nhất (≤6 tuần?) và có biết đang giảm bạch cầu hạt không | 2 |
| Q4-04 | "Có đang mắc bệnh mạn tính nào không — bệnh tim, phổi, gan, thận, tiểu đường, hoặc bệnh về máu như thalassemia?" | Lý do cân nhắc nhập viện theo BYT dù chưa có dấu hiệu cảnh báo (RF-36) | `chronic_conditions` | P1 | Q4-00 dương tính (ý bệnh mạn tính) hoặc mơ hồ | Q4-00 âm tính rõ ràng cho ý này | — | 1 |
| Q4-05 | "Trong 30 ngày gần đây có phẫu thuật, thủ thuật xâm lấn nào không? Hiện có đang mang ống thông tiểu, catheter, hay dẫn lưu nào trên người không?" | Đường vào nhiễm khuẩn trực tiếp (RF-33, 34) | `recent_surgery_30d`, `surgical_site_signs`(C), `indwelling_device` | P1 | Q4-00 dương tính (ý phẫu thuật/thiết bị) hoặc mơ hồ | Q4-00 âm tính rõ ràng cho ý này | Nếu có phẫu thuật → hỏi vết mổ hiện có sưng đỏ/chảy dịch không | 1 |
| Q4-06 | "Trong 1–3 tháng gần đây có đi đến vùng nào có sốt rét lưu hành không (vùng núi, biên giới, đi nước ngoài)?" | Sốt rét ác tính — cấp cứu tiềm tàng, không loại trừ được nếu không xét nghiệm (RF-35) | `travel_history_12m`, `malaria_risk_area` | P1 | Q4-00 dương tính (ý du lịch/sốt rét) hoặc mơ hồ | Q4-00 âm tính rõ ràng cho ý này | Hỏi ngày trở về cụ thể để phân định ≤1 tháng vs >1 tháng | 1 |
| Q4-07 | "Xung quanh nhà/nơi làm việc gần đây có ai bị sốt xuất huyết, cúm, sởi, tay chân miệng không? Gần đây có bị muỗi đốt nhiều, hoặc ở khu vực có sốt xuất huyết không?" | Thay đổi xác suất nền; kích hoạt bộ câu hỏi cảnh báo SXHD (§Nhóm K KM) | `outbreak_exposure`, `mosquito_exposure` | P1 | Luôn hỏi | Không skip | — | 0 |
| Q4-08 | "Hiện [bé/anh chị] sống một mình hay có người ở cùng theo dõi được? Từ nhà đến cơ sở y tế gần nhất mất khoảng bao lâu?" | Điều kiện an toàn tiên quyết của `SELF_CARE` — self-care an toàn phụ thuộc người theo dõi (RF-38) | `lives_alone`, `caregiver_available`, `access_to_care_minutes`(O) | P1 | Luôn hỏi trước khi có thể kết luận `SELF_CARE` | Có thể hoãn tới Stage 6 nếu đã xác định `EMERGENCY`/`EARLY_VISIT` ở Stage 3 (không ảnh hưởng kết luận nữa, chỉ cần cho phiếu bàn giao) | — | 0 |

### 3.5. Stage 5 — Thu thập phần còn lại

| ID | Câu hỏi | Mục đích | Field | Priority | Ask condition | Skip condition | Follow-up | Max follow-up |
|---|---|---|---|---|---|---|---|---|
| Q5-01 | "Có tiểu buốt, tiểu rắt, hoặc đau vùng hông lưng không?" | NICE: luôn cân nhắc nhiễm khuẩn tiết niệu ở trẻ sốt <5 tuổi không rõ ổ (RF-42) | `urinary_symptoms` | P1 (M nếu <5t, O nếu người lớn) | Luôn hỏi nếu `age < 5`; người lớn hỏi nếu còn ngân sách | Người lớn khi ngân sách hết và đã có ổ nhiễm khuẩn rõ ràng khác | — | 0 |
| Q5-02 | "Có sưng, đau khớp hoặc chi nào không? [trẻ] Bé có chịu đi lại, dùng tay chân bình thường không?" | Amber NICE — nghi nhiễm khuẩn xương khớp, dễ bỏ sót (RF-41) | `joint_limb_swelling`, `non_weight_bearing`(C: <16t) | P1 | Luôn hỏi (rẻ, giá trị cao) | Không skip | — | 0 |
| Q5-03 | "Có đau họng, đau tai, ho, sổ mũi không?" | Định hướng ổ nhiễm khuẩn lành tính hơn, hỗ trợ kết luận `SELF_CARE` | `sore_throat`, `ear_pain`, `cough` | P3 | Còn ngân sách VÀ chưa xác định rõ ổ nhiễm khuẩn | Đã chốt `EMERGENCY`/`EARLY_VISIT`, hoặc hết ngân sách | — | 0 |
| Q5-04 | "Có tiêu chảy không ạ? Phân có lẫn máu không?" | Mất nước, nguồn nhiễm; cảnh báo SXHD | `diarrhea`, `bloody_stool`(C) | P1 | Luôn hỏi | Không skip | — | 0 |
| Q5-05a | "Hiện có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không — ví dụ ibuprofen, aspirin?" | **Ràng buộc an toàn:** cấm gợi ý NSAID khi chưa loại trừ SXHD (§4.9 KM, R-G-03) — bản thân ràng buộc an toàn này **không đổi**, chỉ đổi cách/thời điểm hỏi | `nsaid_use` | C/M1 (route dengue-context, hoặc trước khi đưa lời khuyên hạ sốt) | Nếu `EMERGENCY` **đã** được xác nhận: **hoãn câu hỏi này tới sau khi đã hiển thị cảnh báo cấp cứu** — không bao giờ là bước chặn trước khi hiển thị cảnh báo; nếu chưa rõ EMERGENCY, hỏi bình thường trong Stage 5 | Route không phải dengue-context và không hướng tới tư vấn hạ sốt cụ thể → có thể rút gọn thành 1 câu ghi chú "nhớ nói với điều dưỡng thuốc đã dùng" thay vì hỏi trực tiếp | Nếu `nsaid_use = true` → hiển thị cảnh báo an toàn ngay trong hội thoại (nhưng không chặn/trì hoãn cảnh báo `EMERGENCY` nếu đã có) | 0 |
| Q5-05b | "Có đang dùng kháng sinh nào không ạ?" | Sốt dai dẳng dù dùng KS = tín hiệu cần khám; dùng cho phiếu bàn giao | `antibiotic_current` | H / C (sốt ≥5 ngày hoặc đã khám bác sĩ trước đó) | Còn ngân sách, hoặc điều kiện `C` kích hoạt | Đã chốt `EMERGENCY`, hoặc hết ngân sách và điều kiện `C` không kích hoạt | — | 0 |
| Q5-06 | "Bé đã tiêm chủng đầy đủ theo lịch chưa ạ? Có tiêm vắc-xin nào trong 48 giờ gần đây không?" | Nguy cơ bệnh phòng ngừa được; vắc-xin gần đây là yếu tố nhiễu khi diễn giải sốt | `immunization_status`, `recent_vaccination_48h` | P2 | `age < 5` VÀ còn ngân sách | `age ≥ 5` | — | 0 |
| Q5-07 | "Có đau nhức người, đau cơ, hoặc đau nhức phía sau hốc mắt không?" | Bộ triệu chứng gợi ý bệnh virus lưu hành tại VN; hỗ trợ ghi chú cho điều dưỡng | `myalgia_retroorbital_pain` | P3 | Còn ngân sách, đặc biệt nếu `outbreak_exposure` chứa `dengue` | Đã chốt `EMERGENCY`/`EARLY_VISIT`, hoặc hết ngân sách | — | 0 |

### 3.6. Stage 6 — Kết thúc đánh giá

Không sinh field mới; thực hiện: (a) kiểm tra `contradiction_flags`, chạy 1 vòng làm rõ nếu có (Part 6); (b) tóm tắt lại các điểm chính cho người dùng xác nhận; (c) nếu kết luận `SELF_CARE` → hiển thị **đầy đủ, không rút gọn** danh sách safety-netting (§5.5 KM); (d) đặt `hitl_status = pending` (hoặc giữ trạng thái escalate đã có nếu là nhánh cấp cứu) và kết thúc phiên.

---

## PART 4 — TỐI ƯU HÓA HỘI THOẠI

### 4.1. Khi đã xác định được `EMERGENCY` — bỏ những câu hỏi nào?

Ngay khi **một** điều kiện `EMERGENCY` được xác nhận (bất kỳ rule `R-E-xx` nào trong KM §6.1, ví dụ: `consciousness_level` giảm, co giật đang diễn ra, cứng gáy/thóp phồng, khó thở nặng/tím tái/thở rít, dấu hiệu sốc, không tiểu >6h, không uống được/nôn tất cả, ban không mất khi ấn kính, xuất huyết niêm mạc/tiêu hóa, trẻ <3 tháng có sốt, hạ thân nhiệt ở nhóm nguy cơ, nghi hyperthermia, khó chịu hơn dù đã hạ sốt, sốt giảm bạch cầu hạt, sốt rét vùng dịch ≤1 tháng, đau bụng dữ dội/bụng cứng, hoặc sản khoa có red flag):

1. **Dừng ngay bảng Stage 3A/3B** — không cần hỏi hết các câu còn lại, vì theo nguyên tắc bất biến của KM (§0.2): mức triage = mức cao nhất trong các rule khớp, **không rule nào được hạ mức đã đặt**. Hỏi thêm red flag khác không thay đổi kết luận `EMERGENCY`.
2. **Hiển thị cảnh báo cấp cứu ngay lập tức**, không chờ hỏi hết, không chờ duyệt HITL (kế thừa §0.5 KM).
3. **Bỏ toàn bộ Stage 4 (trừ những gì thay đổi cách hướng dẫn escalate):** vẫn hỏi nhanh `immunocompromised`/`known_neutropenia` nếu chưa biết (ảnh hưởng thông điệp "cần kháng sinh trong giờ đầu" cho điều dưỡng), và `is_pregnant` nếu là nữ trong độ tuổi sinh sản (ảnh hưởng việc hướng tới cơ sở có sản khoa) — còn lại (du lịch, dịch tễ, sống một mình...) **bỏ hoàn toàn**, điều dưỡng sẽ đánh giá trực tiếp.
4. **Bỏ toàn bộ Stage 5** — triệu chứng kèm theo, làm giàu thông tin không còn giá trị khi đã cần cấp cứu ngay.
5. **Q5-05a (NSAID) không bao giờ chặn bước hiển thị cảnh báo cấp cứu.** Nếu chưa biết `nsaid_use`, có thể hỏi nhanh 1 câu **sau khi** cảnh báo đã hiển thị, hoặc rút gọn thành ghi chú "nhớ nói với điều dưỡng thuốc đã dùng" trên phiếu bàn giao. **Q5-05b (kháng sinh) là `H`, bỏ qua hoàn toàn** ở nhánh cấp cứu — không có giá trị thay đổi hành động cấp cứu.
6. Chuyển thẳng Stage 6 — nhánh cấp cứu: thông điệp an toàn (theo §0.4 KM, không nêu tên bệnh), hướng dẫn gọi 115/đến cấp cứu, escalate cho điều dưỡng ngay lập tức.

### 4.2. Khi `SELF_CARE` đã "có vẻ" rõ ràng — bỏ những câu hỏi nào?

**Không được bỏ "minimum scan" an toàn — tức Stage 3A (toàn bộ field `M0`) cộng với các field `M1` liên quan tới route đang áp dụng.** Điều này **không** có nghĩa là phải hỏi đủ toàn bộ danh sách câu hỏi trong bảng Part 3/ma trận Part 6 KM cho mọi ca — với route nguy cơ thấp (`ROUTE_LOCALIZED_SOURCE`), phần enrichment (`H`/`O`) có thể bỏ qua ngay cả khi đang hướng `SELF_CARE`. `SELF_CARE` chỉ được kết luận khi Stage 3A âm tính toàn bộ **và** các field `M1`/`M1_SELF_CARE` liên quan tới route đã có giá trị xác định (không `unknown` ảnh hưởng rule) — không thể suy luận tắt "chắc là nhẹ" mà bỏ qua câu hỏi `M0`/`M1` an toàn. Đây là khác biệt cốt lõi so với việc rút ngắn khi `EMERGENCY`: rút ngắn vì đã đủ căn cứ nâng mức là an toàn; rút ngắn để hạ mức xuống `SELF_CARE` mà bỏ qua `M0`/`M1` là **không bao giờ được phép**.

Những gì **có thể** bỏ khi xu hướng đang rất rõ là lành tính (đã qua hết Stage 3 sạch, không red flag, `caregiver_concern_level` thấp):

- Toàn bộ field `P3` ở Stage 5: `fever_pattern`, `myalgia_retroorbital_pain`, `sore_throat`/`ear_pain`/`cough` (nếu đã xác định ổ nhiễm khuẩn lành tính rõ qua câu khác), `temp_device_type`, `antipyretic_total_24h_mg` (trừ khi có dấu hiệu nghi quá liều), `animal_water_exposure`, `sick_contact`, `drug_allergies`, chi tiết `current_medications`.
- Các nhánh điều kiện `C` tự nhiên không áp dụng (ví dụ hỏi sản khoa cho nam giới) — đây không phải "tối ưu" mà là skip condition mặc định.
- Một khi checklist §5.4 đã **toàn bộ xanh** và không còn `unknown` ảnh hưởng rule → dừng ngay, không cố hỏi thêm cho "chắc" — sang Stage 6 hiển thị safety-netting.

### 4.3. Routing theo mức nguy cơ (named routes) — quy tắc dừng/hỏi theo route

Để tránh hỏi đều một bộ câu hỏi cho mọi ca, hội thoại xác định "route" ngay khi đủ dữ liệu (thường sau Stage 0 + đầu Stage 4) và áp quy tắc dừng tương ứng:

| Route | Điều kiện kích hoạt | Mục tiêu hỏi |
|---|---|---|
| `ROUTE_INFANT_HIGH` | Tuổi < 3 tháng | Xác nhận tuổi + sốt là đủ để `EMERGENCY` (RF-22); hỏi thêm 1–2 câu tối thiểu cho phiếu bàn giao, không cố "chứng minh" mức nào khác |
| `ROUTE_HIGH_RISK` | `conservatism_tier ≥ 1` (thai kỳ/hậu sản, suy giảm miễn dịch/hóa trị, ≥75 tuổi kèm yếu tố khác, bệnh mạn nặng, sốt rét vùng dịch, sống một mình…) | **Mục tiêu là loại trừ `EMERGENCY`, không phải chứng minh `SELF_CARE`** — `SELF_CARE` không tồn tại ở tier 2 theo KM §5.2/§6.3 |
| `ROUTE_STANDARD` | Không thuộc route trên, tuổi ≥6 tháng, không dấu hiệu định hướng ổ nhiễm khuẩn rõ | Hỏi đủ Stage 3A + 3B + Q4-00 sàng lọc; hướng tới `SELF_CARE` nếu đủ điều kiện §5.4 KM |
| `ROUTE_DENGUE_CONTEXT` | `mosquito_exposure`/`outbreak_exposure` (dengue) dương tính, hoặc có ≥1 trong: đau bụng, xuất huyết, `worse_after_defervescence`, đang dùng/định dùng NSAID | Đào sâu bộ câu hỏi cảnh báo SXHD (Nhóm K, Nhóm P — đặc biệt `nsaid_use`) trước khi tư vấn hạ sốt |
| `ROUTE_LOCALIZED_SOURCE` | Stage 3A âm tính, có ổ nhiễm khuẩn lành tính rõ (vd viêm họng) qua các field `O` đã trả lời tự nhiên | Bỏ qua toàn bộ enrichment (`H`/`O`) còn lại, chỉ tập trung xác nhận an toàn `SELF_CARE` (`M0` + `M1` liên quan) |

**Quy tắc dừng theo route (kế thừa Part 4.1/4.2, áp dụng cụ thể theo route):**

1. **`EMERGENCY` đã xác nhận** → dừng hỏi thường quy ngay, hiển thị cảnh báo ngay lập tức (bất kể route nào).
2. **`EARLY_VISIT` đã đạt được** → chỉ tiếp tục hỏi các field còn có thể **nâng** lên `EMERGENCY` hoặc **đổi** cơ sở/khung thời gian trong vòng 4 giờ; bỏ qua toàn bộ field `H`/`O` thuần làm giàu.
3. **Đang hướng `SELF_CARE`** → phải hoàn thành `M0` + `M1`/`M1_SELF_CARE` cho route đang áp dụng, nhưng **không** cần hỏi hết ma trận đầy đủ ở Part 6 KM — chỉ phần liên quan route đó (vd `ROUTE_LOCALIZED_SOURCE` bỏ qua gần hết Stage 4 chi tiết vì Q4-00 đã âm tính).

---

## PART 5 — XỬ LÝ CÂU TRẢ LỜI MƠ HỒ

### Nguyên tắc chung

1. **Không bao giờ tự suy diễn con số/giá trị cụ thể** từ một mô tả định tính cho field numeric (`temp_c`, `fever_duration_days`...). Khi mơ hồ, hỏi lại bằng **mốc neo cụ thể** (anchored multiple-choice) — con người trả lời chính xác hơn khi được cho các lựa chọn cụ thể so với câu hỏi mở lặp lại.
2. Với field tri-state ảnh hưởng red flag: câu trả lời mơ hồ **không được** map thành `false`. Tối đa 2 lần làm rõ; nếu vẫn mơ hồ → `unknown`, áp dụng §3.1.2 KM (unknown + nhóm nguy cơ cao → nâng `EARLY_VISIT` tối thiểu).
3. **Khi buộc phải chọn giữa hai giá trị neo vì người dùng lưỡng lự, luôn chọn giá trị làm tăng thận trọng** (ví dụ lưỡng lự giữa 5–10 ngày sốt → dùng 7 ngày để kích hoạt đúng rule `≥7 ngày` thay vì bỏ qua).

### Bảng xử lý theo ví dụ

| Câu trả lời mơ hồ | Rủi ro nếu diễn giải sai | Chiến lược làm rõ | Ví dụ câu hỏi lại |
|---|---|---|---|
| **"Tôi thấy nóng"** | Nhầm cảm giác nóng do môi trường/vận động với sốt thật | Hỏi dấu hiệu đi kèm sốt thật (ớn lạnh, mệt mỏi khác thường) + mời đo nếu có nhiệt kế; nếu không đo được → `fever_status = subjective`, **không loại bỏ ca** | "Anh/chị cảm thấy nóng người có kèm ớn lạnh, rét run, hay mệt khác thường không ạ? Nhà có nhiệt kế để đo thử không?" |
| **"Chắc là bị sốt" / "hình như sốt"** | Hạ thấp độ tin cậy dẫn tới bỏ sót ca — nhưng KHÔNG được hạ mức nghi ngờ | Chấp nhận `fever_reported = true`, `fever_status = subjective`, tiếp tục hỏi bình thường như đã có sốt (đúng nguyên tắc §1.3 KM: coi trọng báo cáo của người khai dù không có số đo) | Không cần hỏi lại để "chắc chắn hơn" — tiếp tục sang câu tiếp theo bình thường |
| **"Có lẽ"** (trả lời cho câu hỏi có/không an toàn, vd "có lẽ có co giật") | Đây có thể là red-flag field — "có lẽ" không được map thành `false`; bỏ sót co giật là nguy hiểm | Chuyển câu hỏi có/không thành **mô tả hành vi quan sát được** để người trả lời tự đối chiếu | "Tay chân có giật liên tục, mắt có trợn ngược không, việc đó kéo dài khoảng bao lâu ạ?" — nếu sau 2 lần vẫn mơ hồ → `unknown`, không phải `false` |
| **"Khá cao"** (trả lời cho câu hỏi nhiệt độ) | `temp_c` là field số, không được suy diễn con số cụ thể | Hỏi lại có số đo cụ thể không; nếu không có, dùng mốc quen thuộc chỉ để ghi chú định tính cho điều dưỡng, **không** gán vào `temp_c` — giữ `fever_status = subjective` | "Có số đo cụ thể không ạ? Nếu chưa đo, so với những lần sốt trước, lần này có vẻ cao hơn hay tương đương ạ?" |
| **"Lâu rồi"** (trả lời cho câu hỏi số ngày sốt) | `fever_duration_days` là mốc rule quan trọng (≥5, ≥7 ngày) | Hỏi lại bằng mốc neo cụ thể; nếu vẫn lưỡng lự giữa hai mốc, **chọn mốc cao hơn** (an toàn hơn) | "Lâu rồi là khoảng 3–4 ngày, gần một tuần, hay đã hơn 10 ngày rồi ạ?" |
| **"Cũng bình thường" / im lặng kéo dài** | Có thể là né tránh, không hiểu câu hỏi, hoặc thực sự bình thường — ba trường hợp khác nhau | Hỏi lại theo cách khác (paraphrase), không lặp y nguyên câu cũ; nếu vẫn không rõ sau 1 lần → `unknown` | Đổi cách hỏi cụ thể hơn thay vì lặp lại câu tổng quát |

---

## PART 6 — XỬ LÝ THÔNG TIN THIẾU

| Tình huống | Quyết định | Điều kiện áp dụng |
|---|---|---|
| **Hỏi lại (re-ask)** | Field `M0`/`M1`/`C` (đã kích hoạt) còn `unknown` sau lượt hỏi đầu, VÀ field đó cấp dữ liệu trực tiếp cho 1 rule có thể thay đổi mức triage | Field `M0`: tối đa **2 lần** làm rõ (hậu quả bỏ sót cao hơn giá trị rút ngắn hội thoại); field `M1`/`C`: tối đa 1 lần — nếu vẫn `unknown` và đã có `EARLY_VISIT`/`EMERGENCY` từ nơi khác thì dừng, chỉ chặn riêng kết luận `SELF_CARE` (xem KM §6.1a) |
| **Ước lượng (estimate)** | **Chỉ** áp dụng cho field **derived** đã khai báo rõ trong KM (`fever_duration_days` tính từ `fever_onset_at`; `measurement_confidence` suy ra từ `temp_device_type` + `temp_site` + thời điểm đo) | Không bao giờ ước lượng thay người dùng cho field `*_reported`/tri-state gốc — cấm tuyệt đối theo §3.1 KM (`unknown ≠ false`) |
| **Tiếp tục (không hỏi lại)** | Field `O`, hoặc field `C` mà điều kiện kích hoạt không thỏa, hoặc field đã bị field khác "bao hàm" (vd đã xác nhận `non_blanching_rash = true` thì không cần hỏi riêng `rash_present`) | Ghi vào `unknown_fields` nếu có, không chặn tiến trình |
| **Dừng hẳn** | (a) Đã chốt 1 red flag `EMERGENCY` (Part 4); (b) đạt giới hạn ngân sách câu hỏi mà phần còn lại chỉ là field `O`/`H`; (c) người dùng không thể tiếp tục (mất kết nối, quá hoảng loạn, từ chối) | (b) Ngân sách theo route/kết luận (thay cho ngân sách phẳng "20–25 câu tổng cộng" của bản thiết kế trước — xem bảng ngân sách §6.5 bên dưới). (c) Áp dụng ngay mức thận trọng nhất suy ra được từ dữ liệu đã có, đặt `data_gap = true`, `hitl_status = ask_more` — **không bao giờ mặc định về `SELF_CARE`** khi dừng giữa chừng |

**Trường hợp đặc biệt — mâu thuẫn (`contradiction_flags`):** không thuộc 4 nhánh trên. Khi phát hiện hai câu trả lời trái ngược (ví dụ: "bé vẫn chơi ngoan" ở Q3-01 nhưng "bé li bì khó đánh thức" ở chỗ khác), **không kết luận vội** — chạy đúng 1 vòng câu hỏi làm rõ trực tiếp nêu rõ điểm mâu thuẫn, rồi mới tiếp tục hoặc dừng theo bảng trên.

### 6.5. Ngân sách câu hỏi theo route/kết luận **[EN]** 

| Tình huống | Ngân sách câu hỏi (cụm câu hỏi tổ hợp, không phải field đơn lẻ) |
|---|---|
| `EMERGENCY` rõ ràng (chốt sớm ở Stage 3A hoặc do tuổi/ngưỡng riêng — `ROUTE_INFANT_HIGH`) | **3–6 câu** |
| `EARLY_VISIT` rõ ràng | **8–12 câu** |
| `SELF_CARE` — ứng viên (`ROUTE_STANDARD`/`ROUTE_LOCALIZED_SOURCE`) | **12–16 câu** |
| Nguy cơ cao nhưng ổn định (`ROUTE_HIGH_RISK`, mục tiêu loại trừ `EMERGENCY`) | **8–12 câu** |

Vượt ngân sách mà phần còn thiếu chỉ là field `O`/`H` → dừng theo bảng Part 6 (mục "Dừng hẳn").

---

## PART 7 — SƠ ĐỒ LUỒNG HỘI THOẠI

### 7.1. Decision flow (luồng quyết định cấp cao)

```mermaid
flowchart TD
    A[Bắt đầu phiên] --> B[Stage 0: Tuổi, giới, người khai]
    B --> C[Stage 1: Có sốt không?]
    C -->|Không sốt| Z1[Ngoài phạm vi protocol Sốt]
    C -->|Có sốt| D[Stage 2: Thời gian sốt, rét run,\nđáp ứng hạ sốt, khó chịu hơn sau hạ sốt]
    D --> E{worse_after_defervescence\nHOẶC dưới 3 tháng tuổi có sốt?}
    E -->|Có| F[EMERGENCY ngay -\nkhông cần Stage 3 đầy đủ]
    E -->|Chưa rõ| G[Stage 3: Quét red flag theo cụm\nQ3-01 .. Q3-14]
    G --> H{Bất kỳ red flag\nEMERGENCY nào dương tính?}
    H -->|Có, tại bất kỳ câu nào| F
    H -->|Không, hết Stage 3| I[Stage 4: Quần thể nguy cơ\nthai kỳ / suy giảm miễn dịch /\nmạn tính / sốt rét / dịch tễ]
    I --> J{Bất kỳ điều kiện\nEARLY_VISIT nào dương tính?}
    J -->|Có| K[EARLY_VISIT]
    J -->|Không| L[Stage 5: Triệu chứng kèm theo\n+ an toàn thuốc NSAID]
    L --> M{Bất kỳ điều kiện\nEARLY_VISIT nào dương tính?}
    M -->|Có| K
    M -->|Không| N{Checklist SELF_CARE\n5.4 KM đủ điều kiện?}
    N -->|Đủ| O[SELF_CARE + safety-netting đầy đủ]
    N -->|Thiếu dữ liệu ảnh hưởng rule| K
    F --> P[Stage 6: Cảnh báo ngay,\nescalate, bỏ qua chờ HITL]
    K --> Q[Stage 6: Tóm tắt, chờ duyệt HITL]
    O --> Q
```

### 7.2. State machine (trạng thái phiên hội thoại)

```mermaid
stateDiagram-v2
    [*] --> IdentifySubject: Stage 0
    IdentifySubject --> DetectFever: Stage 1
    DetectFever --> OutOfScope: fever_reported = false
    DetectFever --> CharacterizeFever: fever_reported = true, Stage 2
    CharacterizeFever --> EmergencyExit: worse_after_defervescence = true\nHOẶC age<3m có sốt\nHOẶC hyperthermia nghi ngờ
    CharacterizeFever --> RedFlagScreen: Stage 3
    RedFlagScreen --> EmergencyExit: bất kỳ RF EMERGENCY nào dương tính\n(dừng quét ngay tại câu đó)
    RedFlagScreen --> RiskPopulation: hết 14 câu, không RF đỏ, Stage 4
    RiskPopulation --> EmergencyExit: RF đỏ mới lộ ra\n(vd sản khoa + RF nhóm A-E)
    RiskPopulation --> EarlyVisitPending: điều kiện EARLY_VISIT dương tính
    RiskPopulation --> RemainingInfo: không có RF, Stage 5
    RemainingInfo --> EarlyVisitPending: điều kiện EARLY_VISIT dương tính
    RemainingInfo --> ChecklistSelfCare: không có RF, kiểm tra §5.4
    ChecklistSelfCare --> EarlyVisitPending: thiếu dữ liệu ảnh hưởng rule\nHOẶC không đủ điều kiện an toàn
    ChecklistSelfCare --> SelfCarePending: đủ điều kiện, Stage 6
    EmergencyExit --> Finish: hiển thị cảnh báo ngay,\nescalate không chờ HITL
    EarlyVisitPending --> Finish: Stage 6, chờ duyệt HITL
    SelfCarePending --> Finish: Stage 6, safety-netting đầy đủ,\nchờ duyệt HITL
    Finish --> [*]
    OutOfScope --> [*]
```

### 7.3. Conversation graph (định tuyến câu hỏi thích ứng)

```mermaid
graph TD
    Q0["Q0-01/02: Tuổi, giới"] --> Q1["Q1-01: Có sốt?"]
    Q1 --> Q1b["Q1-02: Đo được bao nhiêu,\nvị trí, thời điểm"]
    Q1b -->|subjective| Q1c["Q1-03: Có thể đo ngay không"]
    Q1b --> Q2a["Q2-01: Bao nhiêu ngày"]
    Q1c --> Q2a
    Q2a --> Q2b["Q2-02..04: Rét run,\nthuốc hạ sốt, khó chịu\nhơn sau hạ sốt"]
    Q2b -->|worse_after_defervescence=true| STOP1(["DỪNG → EMERGENCY"])
    Q2b --> Q3a["Q3-01: Tri giác + hoạt động"]
    Q3a -->|difficult_to_rouse/unresponsive| STOP1
    Q3a --> Q3b["Q3-02..05: Lú lẫn, co giật,\ncứng gáy, dấu TK khu trú"]
    Q3b -->|bất kỳ dương tính| STOP1
    Q3b --> Q3c["Q3-06..08: Hô hấp, sốc"]
    Q3c -->|bất kỳ dương tính| STOP1
    Q3c --> Q3d["Q3-09..13: Tiểu, ăn uống/nôn,\nban, xuất huyết, bụng"]
    Q3d -->|bất kỳ dương tính| STOP1
    Q3d --> Q3e["Q3-14: Mức lo lắng người chăm sóc"]
    Q3e -->|concern≥8 hoặc looks_very_unwell| EARLY(["→ tối thiểu EARLY_VISIT"])
    Q3e --> Q4["Stage 4: Thai kỳ, miễn dịch,\nmạn tính, sốt rét, dịch tễ,\nhoàn cảnh sống"]
    Q4 -->|điều kiện EARLY_VISIT| EARLY
    Q4 --> Q5["Stage 5: Tiết niệu, khớp,\nhô hấp trên, tiêu chảy, NSAID"]
    Q5 -->|điều kiện EARLY_VISIT| EARLY
    Q5 --> CHECK{"Checklist\nSELF_CARE §5.4"}
    CHECK -->|đủ| SELFCARE(["→ SELF_CARE + safety-netting"])
    CHECK -->|thiếu| EARLY
```

> **Áp dụng trong các cụm Q3a–Q3d (Stage 3A) và Q3e/nhánh Stage 3B ở trên:** mỗi cụm là một câu hỏi tổ hợp theo kỹ thuật batch negation (§3.3A) — "không có dấu hiệu nào" đưa toàn bộ field trong cụm về `false` cùng lúc và đi thẳng sang cụm kế tiếp; chỉ khi có ít nhất 1 ý "có"/"không chắc" mới rẽ vào follow-up riêng cho (các) field đó trước khi sang cụm kế tiếp. Đồng thời, tại **bất kỳ điểm nào** trên đồ thị, nếu field của một node phía sau đã được suy ra từ câu trả lời tự do trước đó (§3, quy ước "không hỏi lại field đã có giá trị xác định") thì node đó được **bỏ qua**, đi thẳng tới node kế tiếp còn field `unknown`; nếu người dùng sửa lại giá trị đã cho ở một node đã đi qua, hệ thống ghi đè giá trị tại node đó và chỉ quay lại các node có điều kiện kích hoạt phụ thuộc giá trị vừa đổi (vd sửa tuổi ở Q0 buộc đánh giá lại các nhánh `C` theo tuổi dọc theo đồ thị).

---

## PART 8 — HỘI THOẠI MẪU

> Mỗi ca gồm: hội thoại rút gọn (User/Assistant), JSON trích xuất (chỉ các field liên quan trực tiếp tới kết luận, không liệt kê toàn schema), và lập luận (rule/RF nào khớp). Tên bệnh **không bao giờ** xuất hiện trong lời thoại của Assistant, chỉ có thể xuất hiện trong phần "Reasoning" để giải thích cho mục đích thiết kế.

### 8.1. EMERGENCY — 5 ca

#### E1 — Trẻ sơ sinh < 3 tháng có sốt

**User:** "Con em được 2 tháng, sáng nay sờ thấy nóng, đo nách 37,8 độ."
**Assistant:** "Dạ em cảm ơn chị. Với bé dưới 3 tháng tuổi, sốt dù chỉ nhẹ cũng cần được bác sĩ khám ngay, kể cả khi bé vẫn có vẻ chơi ngoan bình thường. Chị cho em hỏi nhanh: bé bú có bình thường không, và bé có đang khó đánh thức hay li bì không ạ?" *(vẫn hỏi 1–2 câu tối thiểu để hỗ trợ thông điệp bàn giao, không trì hoãn cảnh báo)*
**User:** "Bé vẫn bú bình thường, tỉnh táo, chỉ hơi quấy."
**Assistant:** "Dạ, dù bé vẫn tỉnh táo và bú tốt, đây vẫn là tình huống **cần đưa bé đến cơ sở y tế/khoa cấp cứu nhi ngay bây giờ** — không cần chờ thêm dấu hiệu khác, vì trẻ dưới 3 tháng có nguy cơ nhiễm khuẩn nặng dù bề ngoài vẫn ổn. Em đã ghi nhận và chuyển thông tin cho điều dưỡng ngay."

```json
{
  "patient": {"age_value": 2, "age_unit": "month"},
  "fever": {"fever_reported": true, "fever_status": "objective", "temp_c": 37.8, "temp_site": "axillary"},
  "general": {"consciousness_level": "alert", "feeding_intake": "normal"},
  "session": {"triage_level": "EMERGENCY", "time_target": "now", "reason_codes": ["RF-22"], "triggered_rules": ["R-E-14"]}
}
```

**Reasoning:** `age = 2 tháng < 3 tháng` AND sốt khách quan (37,8°C nách ≥ ngưỡng 37,5°C) → `R-E-14` khớp ngay lập tức. Theo KM §1.6/§5.2, guideline AAP chỉ áp dụng cho trẻ "trông khỏe" nhưng vẫn yêu cầu đánh giá y tế — vẻ ngoài bình thường **không loại trừ**. Không tồn tại nhánh `SELF_CARE` cho tier 2. Stage 3 không cần chạy đầy đủ vì tuổi đã quyết định mức tối thiểu.

---

#### E2 — Co giật đang diễn ra

**User:** "Con em đang sốt cao, giờ tay chân đang giật, mắt trợn lên, em không biết làm sao."
**Assistant:** "Chị bình tĩnh, đặt bé nằm nghiêng an toàn, không đút bất cứ thứ gì vào miệng bé, không cố giữ chặt tay chân. **Đây là tình huống cấp cứu — gọi 115 hoặc đưa bé đến cấp cứu gần nhất ngay bây giờ.** Em đã chuyển thông tin cho điều dưỡng để hỗ trợ chị ngay."

```json
{
  "neurological": {"seizure_occurred": true, "seizure_active_now": true},
  "session": {"triage_level": "EMERGENCY", "time_target": "now", "reason_codes": ["RF-02"], "triggered_rules": ["R-E-02"]}
}
```

**Reasoning:** `seizure_active_now = true` → `R-E-02`, red flag tuyệt đối theo IMCI general danger sign. Theo Part 4, đây là trường hợp **dừng hỏi ngay lập tức**, không tiếp tục Q3-04 trở đi — chỉ hướng dẫn an toàn tức thời và escalate.

---

#### E3 — Ban không mất khi ấn

**User:** "Cháu sốt 2 ngày nay, sáng nay thấy nổi mấy chấm tím ở chân, ấn vào không mất."
**Assistant:** "Dạ em ghi nhận. Dấu hiệu ban tím không mất khi ấn là dấu hiệu **cần đưa cháu đi cấp cứu ngay bây giờ**, không chờ thêm. Trong lúc di chuyển, cô/chú theo dõi thêm giúp em: cháu có tỉnh táo, có cứng gáy hay sợ ánh sáng không ạ?"
**User:** "Cháu hơi mệt nhưng vẫn nói chuyện được, chưa thấy cứng gáy."
**Assistant:** "Dạ em đã ghi nhận đầy đủ và chuyển ngay cho điều dưỡng. Đề nghị gia đình đưa cháu đến cấp cứu ngay, không đợi thêm ạ."

```json
{
  "skin": {"rash_present": true, "non_blanching_rash": true, "rash_type": "petechial"},
  "neurological": {"neck_stiffness": false, "photophobia": false},
  "session": {"triage_level": "EMERGENCY", "time_target": "now", "reason_codes": ["RF-18"], "triggered_rules": ["R-E-12"]}
}
```

**Reasoning:** `non_blanching_rash = true` → `R-E-12`, red flag kinh điển nghi nhiễm khuẩn huyết do não mô cầu, tử vong trong vài giờ nếu chậm trễ. Việc hỏi thêm 1–2 câu ở đây (cứng gáy, tri giác) chỉ nhằm làm giàu phiếu bàn giao, **không** trì hoãn thông điệp cấp cứu đã hiển thị trước đó — đúng nguyên tắc Part 4.1.

---

#### E4 — Sốt sau du lịch vùng sốt rét, về trong 1 tháng, kèm rét run

**User:** "Em vừa đi công tác ở Bình Phước về được 2 tuần, giờ sốt kèm rét run dữ dội."
**Assistant:** "Dạ em hỏi thêm: anh sốt được mấy ngày rồi, và hiện có tỉnh táo bình thường không ạ?"
**User:** "Sốt 1 ngày nay thôi, vẫn tỉnh táo."
**Assistant:** "Dạ, sốt kèm rét run dữ dội sau khi trở về từ khu vực có sốt rét lưu hành trong vòng 1 tháng gần đây là tình huống **cần được khám và xét nghiệm ngay hôm nay, không trì hoãn** — vì đây là loại sốt có thể diễn tiến rất nhanh và không thể loại trừ nếu không xét nghiệm máu. Anh nên đến cơ sở y tế gần nhất càng sớm càng tốt."

```json
{
  "risk_factors": {"travel_history_12m": [{"place": "Bình Phước", "return_date": "2026-07-28"}], "malaria_risk_area": true},
  "fever": {"rigors": true, "fever_duration_days": 1},
  "general": {"consciousness_level": "alert"},
  "session": {"triage_level": "EMERGENCY", "time_target": "now", "reason_codes": ["RF-35", "RF-28"], "triggered_rules": ["R-E-19"]}
}
```

**Reasoning:** `malaria_risk_area = true` AND trở về ≤1 tháng → `R-E-19` khớp ngay theo KM §4.7/§6.1, bất kể tỉnh táo và chưa có red flag khác — vì sốt rét ác tính có thể tử vong trong vài ngày và không loại trừ được qua khai thác từ xa. `rigors = true` càng củng cố lập luận (RF-28) nhưng bản thân yếu tố du lịch đã đủ để chốt `EMERGENCY`.

---

#### E5 — Xuất huyết niêm mạc (cảnh báo SXHD)

**User:** "Cháu sốt 4 ngày rồi, hôm nay hết sốt nhưng sáng nay chải răng thấy chảy máu chân răng nhiều, cháu cũng mệt hơn hôm qua."
**Assistant:** "Dạ em ghi nhận hai điểm quan trọng: chảy máu chân răng bất thường và mệt hơn dù đã hết sốt — đây là **dấu hiệu cần đưa cháu đi khám ngay bây giờ**, không chờ thêm. Trong lúc chuẩn bị đi, cô/chú cho em hỏi thêm cháu có đau bụng nhiều hay nôn nhiều không ạ?"
**User:** "Có, cháu kêu đau bụng từ tối qua, hơi nôn 2 lần."
**Assistant:** "Dạ em đã ghi nhận đầy đủ và chuyển ngay cho điều dưỡng ưu tiên xử lý. Đề nghị đưa cháu đến cơ sở y tế ngay."

```json
{
  "fever": {"fever_duration_days": 4, "worse_after_defervescence": true},
  "skin": {"mucosal_bleeding": true},
  "associated": {"abdominal_pain_severity": "moderate", "vomiting_severity": "occasional"},
  "session": {"triage_level": "EMERGENCY", "time_target": "now", "reason_codes": ["RF-19", "RF-29"], "triggered_rules": ["R-E-13", "R-E-17"]}
}
```

**Reasoning:** Hai rule độc lập cùng khớp: `mucosal_bleeding = true` → `R-E-13` (xuất huyết niêm mạc = dấu hiệu cảnh báo SXHD theo QĐ 2760); `worse_after_defervescence = true` → `R-E-17`. Đây đúng là kịch bản LOCAL quan trọng nhất mà KM nhấn mạnh (§1.5, §4.6): "khó chịu hơn dù đã hạ sốt" trùng thời điểm chuyển sang giai đoạn nguy hiểm của sốt xuất huyết — ngày 3–7 của bệnh (ở đây là ngày 4).

### 8.2. EARLY_VISIT — 5 ca

#### V1 — Trẻ 3–6 tháng, sốt ≥39°C, không red flag khác

**User:** "Bé nhà em 4 tháng, sốt 39,2 độ đo ở tai, bé vẫn bú và chơi bình thường."
**Assistant:** *(hỏi đủ Stage 3, tất cả âm tính)* "Dạ em cảm ơn chị đã cung cấp đầy đủ thông tin. Với mức nhiệt độ này ở bé 4 tháng tuổi, dù hiện tại bé vẫn chơi và bú tốt, em vẫn khuyên gia đình cho bé đi khám **trong vòng 24 giờ** để bác sĩ kiểm tra kỹ hơn, không cần cấp cứu ngay nhưng không nên để quá lâu ạ."

```json
{
  "patient": {"age_value": 4, "age_unit": "month"},
  "fever": {"temp_c": 39.2, "temp_site": "tympanic"},
  "general": {"consciousness_level": "alert", "feeding_intake": "normal", "activity_vs_baseline": "normal"},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_24h", "reason_codes": ["RF-23"], "triggered_rules": ["R-V-01"]}
}
```

**Reasoning:** `age 3–6 tháng` AND `temp_c ≥ 39.0` → `R-V-01`, amber theo NICE NG143 dù không có red flag toàn thân nào khác. Toàn bộ Stage 3 vẫn được hỏi đủ vì đây không phải nhánh EMERGENCY tự động theo tuổi (khác với <3 tháng).

---

#### V2 — Sốt kéo dài ≥5 ngày, người lớn, không red flag

**User:** "Em sốt 5 ngày nay rồi, uống hạ sốt có đỡ nhưng lại sốt lại, không có triệu chứng gì khác đặc biệt."
**Assistant:** *(Stage 3 âm tính toàn bộ)* "Dạ, sốt kéo dài từ 5 ngày trở lên, dù hiện chưa có dấu hiệu nguy hiểm nào khác, vẫn cần bác sĩ khám trực tiếp để tìm nguyên nhân, tốt nhất là **trong hôm nay**. Trong lúc chờ, nếu xuất hiện bất kỳ dấu hiệu nào như mệt hơn dù đã hạ sốt, đau bụng nhiều, chảy máu bất thường thì cần đi cấp cứu ngay, không chờ thêm."

```json
{
  "fever": {"fever_duration_days": 5, "antipyretic_response": "partial"},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_24h", "reason_codes": ["RF-26"], "triggered_rules": ["R-V-02"]}
}
```

**Reasoning:** `fever_duration_days ≥ 5` → `R-V-02`. Theo KM §1.2, độ cao/thời gian sốt đơn thuần không dự đoán độ nặng, **trừ** mốc ≥5 ngày (cân nhắc Kawasaki) — nên rule chỉ nâng lên `EARLY_VISIT`, không lên `EMERGENCY`, vì không có red flag chức năng đi kèm.

---

#### V3 — Người ≥75 tuổi, sốt nhẹ, tỉnh táo hoàn toàn

**User:** "Bà tôi 78 tuổi, sốt nhẹ 37,9 độ từ chiều qua, vẫn tỉnh táo, ăn uống bình thường, không ho, không đau ở đâu cả."
**Assistant:** *(Stage 3 âm tính)* "Dạ em cảm ơn. Dù bà vẫn tỉnh táo và ăn uống tốt, ở người từ 75 tuổi trở lên, phản ứng sốt của cơ thể thường yếu hơn nên dấu hiệu bên ngoài có thể không phản ánh đúng mức độ — vì vậy em vẫn khuyên nên cho bà khám **trong vòng 24 giờ** để chắc chắn, dù không cần đi cấp cứu ngay."

```json
{
  "patient": {"age_value": 78, "age_unit": "year"},
  "fever": {"temp_c": 37.9},
  "general": {"consciousness_level": "alert", "new_confusion": false, "feeding_intake": "normal"},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_24h", "reason_codes": ["RF-37"], "triggered_rules": ["R-V-13"]}
}
```

**Reasoning:** `age ≥ 75` → `R-V-13` áp dụng mặc định (tier 1–2 theo §5.2 KM) do đáp ứng sốt bị cùn — không thể dùng "hiện đang ổn" để hạ mức xuống `SELF_CARE`, vì giá trị tiên đoán âm thấp hơn ở nhóm tuổi này.

---

#### V4 — Phụ nữ mang thai, không red flag sản khoa

**User:** "Em đang mang thai 28 tuần, sốt 38 độ từ sáng, hơi mệt nhưng không đau bụng, không ra máu, thai vẫn máy bình thường."
**Assistant:** *(Stage 3 + Q4-01/01b âm tính)* "Dạ em cảm ơn chị đã cho biết. Với phụ nữ mang thai, dù chưa có dấu hiệu nguy hiểm rõ ràng, sinh lý cơ thể lúc mang thai có thể che lấp các dấu hiệu trở nặng nên xuất hiện muộn hơn bình thường — vì vậy em khuyên chị nên đến khám tại cơ sở **có chuyên khoa sản trong vòng 4-6 giờ tới** để được kiểm tra kỹ, không cần quá gấp nhưng không nên để quá lâu."

```json
{
  "risk_factors": {"is_pregnant": true, "gestational_weeks": 28, "obstetric_red_flags": []},
  "fever": {"temp_c": 38.0},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_4h", "reason_codes": ["RF-32"], "triggered_rules": ["R-V-10"]}
}
```

**Reasoning:** `is_pregnant = true` không kèm `obstetric_red_flags` hay red flag nhóm A–E → `R-V-10`, mức tối thiểu `EARLY_VISIT` với khung `within_4h` theo NICE NG51 (nhánh riêng cho thai phụ, vì dấu hiệu sốc xuất hiện muộn hơn theo KM §1.6/§5.2).

---

#### V5 — Sưng đau khớp gối ở trẻ, không red flag khác

**User:** "Bé 6 tuổi sốt 2 ngày, hôm nay kêu đau gối phải, hơi sưng, không chịu đi lại bằng chân đó."
**Assistant:** *(Stage 3 các mục khác âm tính)* "Dạ em ghi nhận. Sưng đau khớp kèm không chịu đi lại là dấu hiệu cần bác sĩ khám trực tiếp **trong vòng 24 giờ** để loại trừ nhiễm khuẩn ở khớp — tình trạng này nếu chậm trễ có thể ảnh hưởng lâu dài, dù hiện bé vẫn tỉnh táo."

```json
{
  "associated": {"joint_limb_swelling": true, "non_weight_bearing": true},
  "general": {"consciousness_level": "alert"},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_24h", "reason_codes": ["RF-41"], "triggered_rules": ["R-V-15"]}
}
```

**Reasoning:** `joint_limb_swelling = true` AND `non_weight_bearing = true` → `R-V-15`, amber NICE dễ bị bỏ sót nếu chỉ tập trung vào bộ ba tri giác/hô hấp/tuần hoàn — đúng lý do KM liệt kê riêng nhóm G (§Nhóm G) để không bỏ sót ổ nhiễm khuẩn xương khớp.

### 8.3. SELF_CARE — 5 ca

#### H1 — Trẻ 2 tuổi, sốt nhẹ 2 ngày, hoàn toàn bình thường

**User:** "Con em 2 tuổi, sốt 38,3 độ 2 ngày nay, vẫn chơi đùa, ăn uống bình thường, không ho không sổ mũi gì đặc biệt."
**Assistant:** *(toàn bộ Stage 3–5 âm tính, checklist §5.4 đủ)* "Dạ em cảm ơn chị. Với các thông tin chị cung cấp, hiện chưa thấy dấu hiệu đáng lo — bé có thể được **theo dõi và chăm sóc tại nhà**. Tuy nhiên em vẫn cần thông tin: nhà mình có ai ở cùng theo dõi bé được không, và nếu bé trở nặng có thể đưa đi khám kịp không ạ?"
**User:** "Có, em ở nhà cả ngày, cách bệnh viện 10 phút."
**Assistant:** "Dạ em đã ghi nhận đầy đủ. Đây là danh sách các dấu hiệu **cần đưa bé đi khám ngay** nếu xuất hiện: li bì khó đánh thức, co giật, ban tím không mất khi ấn, khó thở/tím môi, tay chân lạnh ẩm, nôn nhiều không ăn uống được, đau bụng nhiều, chảy máu bất thường, không đi tiểu trên 6 giờ, mệt hơn dù đã hạ sốt, sốt kéo dài từ 5 ngày trở lên, cứng gáy/đau đầu dữ dội. Ngoài ra nhớ kiểm tra bé cả ban đêm và cho uống đủ nước ạ. Thông tin đã được gửi cho điều dưỡng xác nhận trước khi hoàn tất."

```json
{
  "patient": {"age_value": 2, "age_unit": "year", "lives_alone": false, "caregiver_available": true, "can_return_for_followup": true},
  "fever": {"temp_c": 38.3, "fever_duration_days": 2},
  "general": {"consciousness_level": "alert", "activity_vs_baseline": "normal", "feeding_intake": "normal"},
  "session": {"triage_level": "SELF_CARE", "time_target": "monitor", "reason_codes": [], "triggered_rules": ["R-S-01"], "safety_netting_items": ["li_bi", "co_giat", "ban_khong_mat", "kho_tho", "tay_chan_lanh", "non_nhieu", "dau_bung_nhieu", "chay_mau", "khong_tieu_6h", "met_hon_sau_ha_sot", "sot_5_ngay", "cung_gay"]}
}
```

**Reasoning:** Không rule `R-E-xx`/`R-V-xx` nào khớp; checklist §5.4 đủ điều kiện (age ≥6 tháng, duration <5 ngày, tỉnh táo, ăn uống/tiểu bình thường, có người theo dõi, có thể tái khám) → `R-S-01` mặc định. Danh sách safety-netting hiển thị **đầy đủ 13 mục** theo §5.5 KM, không rút gọn.

---

#### H2 — Người lớn, sốt cảm cúm thông thường

**User:** "Em sốt 38 độ 1 ngày nay, đau họng, hơi mệt nhưng vẫn đi làm việc nhà được, không có gì bất thường khác."
**Assistant:** *(Stage 3–5 âm tính)* "Dạ, các dấu hiệu chị mô tả phù hợp với sốt do viêm họng/cảm thông thường, hiện chưa thấy dấu hiệu cần khám gấp — chị có thể **theo dõi và chăm sóc tại nhà**. Chị hiện sống một mình hay có người ở cùng ạ?"
**User:** "Em ở cùng chồng."
**Assistant:** "Dạ em đã ghi nhận. Đây là các dấu hiệu cần đi khám ngay nếu xuất hiện: [danh sách đầy đủ 13 mục theo §5.5]. Chị nhớ uống đủ nước và nghỉ ngơi. Thông tin đã chuyển điều dưỡng xác nhận."

```json
{
  "fever": {"temp_c": 38.0, "fever_duration_days": 1},
  "associated": {"sore_throat": true},
  "patient": {"lives_alone": false, "caregiver_available": true},
  "session": {"triage_level": "SELF_CARE", "time_target": "monitor", "reason_codes": [], "triggered_rules": ["R-S-01"]}
}
```

**Reasoning:** Không có red flag; có ổ nhiễm khuẩn lành tính rõ (đau họng) hỗ trợ diễn giải nhưng **không phải căn cứ hạ mức** — bản thân việc không có bất kỳ RF nào mới là căn cứ chính (đúng nguyên tắc "không rule nào hạ mức", chỉ là ở đây không có rule nào kích hoạt để nâng). Field `O` như `cough`, `ear_pain` được bỏ qua vì đã đủ căn cứ và ngân sách ưu tiên dừng đúng lúc (Part 4.2).

---

#### H3 — Trẻ sốt nhẹ sau tiêm chủng 24 giờ trước

**User:** "Bé nhà em tiêm phòng hôm qua, tối nay sốt 37,8 độ, hơi quấy nhưng vẫn bú được."
**Assistant:** *(Stage 3–5 âm tính)* "Dạ, sốt nhẹ sau tiêm chủng trong vòng 48 giờ là phản ứng khá thường gặp và thường tự hết — hiện chưa thấy dấu hiệu đáng lo, gia đình có thể **theo dõi bé tại nhà**. Mình có thể chườm ấm, cho bé bú/uống đủ nước ạ."

```json
{
  "fever": {"temp_c": 37.8, "fever_duration_days": 0},
  "risk_factors": {"recent_vaccination_48h": true},
  "general": {"consciousness_level": "alert", "feeding_intake": "normal"},
  "session": {"triage_level": "SELF_CARE", "time_target": "monitor", "reason_codes": [], "triggered_rules": ["R-S-01"]}
}
```

**Reasoning:** `recent_vaccination_48h = true` được ghi nhận như yếu tố nhiễu khi diễn giải sốt (không phải rule triage), không thay đổi kết luận nhưng hiển thị trên phiếu bàn giao để điều dưỡng biết bối cảnh. Không có RF nào khớp → `R-S-01`.

---

#### H4 — Sốt chủ quan, không đo, không red flag

**User:** "Em sờ trán thấy hơi nóng, không có nhiệt kế đo, người hơi mệt nhưng vẫn tỉnh táo bình thường."
**Assistant:** "Dạ, nếu có thể, chị nên tìm nhiệt kế đo lại giúp em để theo dõi chính xác hơn nhé. Trong lúc đó em vẫn tiếp tục hỏi thêm vài câu để đánh giá đầy đủ." *(tiếp tục Stage 2–5, tất cả âm tính)* "Dạ với các thông tin hiện có, chưa thấy dấu hiệu đáng lo, chị có thể theo dõi tại nhà, nhưng em lưu ý điều dưỡng là **chưa có số đo cụ thể** để tiện đối chiếu sau này."

```json
{
  "fever": {"fever_reported": true, "fever_status": "subjective", "temp_c": null, "measurement_confidence": "subjective"},
  "general": {"consciousness_level": "alert"},
  "session": {"triage_level": "SELF_CARE", "time_target": "monitor", "reason_codes": [], "triggered_rules": ["R-S-01"], "data_gap": false}
}
```

**Reasoning:** `fever_status = subjective` không loại bỏ ca và không tự động hạ/nâng mức (§1.3 KM) — rule engine vẫn chạy đầy đủ dựa trên red flag + nhóm nguy cơ; ở đây tất cả âm tính nên vẫn ra `SELF_CARE`, nhưng `measurement_confidence = subjective` được gắn cờ để điều dưỡng biết độ tin cậy số đo thấp.

---

#### H5 — Trẻ 8 tháng sốt nhẹ, nghi viêm họng nhẹ, ăn uống bình thường

**User:** "Bé 8 tháng, sốt 38,1 độ từ hôm qua, hơi chảy nước dãi nhiều hơn (chắc mọc răng), vẫn bú và chơi bình thường, không sưng khớp, không tiêu chảy."
**Assistant:** *(Stage 3 kỹ hơn về `stridor_or_drooling` để loại trừ nhầm lẫn với chảy dãi do mọc răng — hỏi rõ có kèm thở rít/khó nuốt không, xác nhận không)* "Dạ chảy dãi khi mọc răng là bình thường, không phải dấu hiệu nguy hiểm khi không kèm khó thở hay khó nuốt. Với các thông tin đã có, bé có thể được theo dõi tại nhà." *(tiếp tục hết Stage 4–5, âm tính, checklist đủ)* "Danh sách dấu hiệu cần đưa bé đi khám ngay: [đầy đủ 13 mục §5.5]."

```json
{
  "patient": {"age_value": 8, "age_unit": "month"},
  "fever": {"temp_c": 38.1, "fever_duration_days": 1},
  "respiratory": {"stridor_or_drooling": false},
  "general": {"consciousness_level": "alert", "feeding_intake": "normal"},
  "session": {"triage_level": "SELF_CARE", "time_target": "monitor", "reason_codes": [], "triggered_rules": ["R-S-01"]}
}
```

**Reasoning:** Đây là ví dụ về **làm rõ chủ động** (Part 5) khi một mô tả ("chảy dãi nhiều") trùng từ khóa với field red-flag (`stridor_or_drooling`, RF-10) nhưng bản chất lâm sàng khác — AI không được tự loại trừ mà phải hỏi thêm để xác nhận không kèm thở rít/khó nuốt trước khi gán `false`. Sau khi loại trừ, không còn RF nào khác → `R-S-01`.

---

### 8.4. Minh hoạ tối ưu hoá hội thoại (batch negation, không hỏi lại field đã có, xử lý sửa câu trả lời)

#### O1 — Batch negation ở Stage 3A + không hỏi lại field đã trả lời sớm

**User:** "Con em 3 tuổi, sốt 2 ngày 38,5 độ, bé vẫn tỉnh táo, chơi đùa bình thường, ăn uống tốt, không có gì bất thường khác cả."
**Assistant:** *(đã ghi nhận `consciousness_level = alert`, `feeding_intake = normal`, `fever_duration_days = 2`, `temp_c = 38.5` ngay từ câu mô tả tự do đầu tiên — bỏ qua lại Q3-01 phần tri giác và Q3-09 phần ăn uống khi tới lượt)* "Dạ em cảm ơn chị. Cho em hỏi thêm một loạt để chắc chắn an toàn cho bé: bé có bị co giật, cứng gáy, sợ ánh sáng, hay yếu tay chân/méo miệng không ạ? Có khó thở, tím môi, ngực rút lõm không? Da có lạnh ẩm, nổi vân tím không? Có nổi ban tím không mất khi ấn, hay chảy máu bất thường không? — chị thấy có dấu hiệu nào trong số này không ạ?"
**User:** "Dạ không, không có gì trong số đó cả."
**Assistant:** *(gán `false` cho toàn bộ field trong cụm vừa hỏi: `seizure_occurred`, `neck_stiffness`, `photophobia`, `focal_neuro_deficit`, `breathing_difficulty`, `cyanosis`, `chest_indrawing`, `cold_clammy_skin`, `capillary_refill_ge_3s`, `non_blanching_rash`, `mucosal_bleeding`, `gi_bleeding` — không hỏi lại từng ý) — chuyển sang cụm Stage 3A còn lại (đau bụng, tiểu tiện)* "Dạ, bé có đau bụng nhiều hay đi tiểu ít hơn bình thường trong 6 giờ qua không ạ?"

```json
{
  "patient": {"age_value": 3, "age_unit": "year"},
  "fever": {"temp_c": 38.5, "fever_duration_days": 2},
  "general": {"consciousness_level": "alert", "feeding_intake": "normal"},
  "neurological": {"seizure_occurred": false, "neck_stiffness": false, "photophobia": false, "focal_neuro_deficit": false},
  "respiratory": {"breathing_difficulty": false, "cyanosis": false, "chest_indrawing": false},
  "circulatory": {"cold_clammy_skin": false, "capillary_refill_ge_3s": false},
  "skin": {"non_blanching_rash": false, "mucosal_bleeding": false, "gi_bleeding": false}
}
```

**Reasoning:** Hai nguyên tắc tối ưu hoá cùng áp dụng: (1) `consciousness_level`/`feeding_intake`/`fever_duration_days`/`temp_c` đã có giá trị xác định từ câu mô tả mở đầu → Q3-01 (phần tri giác) và Q3-09 (phần ăn uống) không được hỏi lại, đúng quy ước §3; (2) câu phủ định tường minh "không, không có gì trong số đó cả" cho cả cụm hỏi gộp → gán `false` đồng loạt cho toàn bộ field trong cụm, không lặp lại từng ý — đúng kỹ thuật batch negation §3.3A. Đây **không** vi phạm `unknown ≠ false` vì là phủ định rõ ràng cho câu hỏi đã hỏi tường minh, không phải suy diễn từ im lặng.

---

#### O2 — Người dùng sửa lại câu trả lời giữa hội thoại

**User:** "Bé nhà em 2 tuổi, sốt 3 ngày rồi."
**Assistant:** *(ghi `age_value=2, age_unit=year`, `fever_duration_days=3`)* "Dạ em cảm ơn chị. Bé có bị co giật, cứng gáy, khó thở, tím tái, hay nổi ban tím không mất khi ấn không ạ?"
**User:** "À khoan, em nhớ nhầm, không phải 3 ngày, là 6 ngày rồi mới đúng. Còn mấy cái chị hỏi thì không có."
**Assistant:** *(ghi đè `fever_duration_days = 6` thay cho 3, đồng thời gán `false` cho cụm red flag vừa hỏi theo batch negation; vì thay đổi thời gian sốt không đổi điều kiện kích hoạt của các câu đã hỏi ở Stage 0/3A nên không cần hỏi lại các câu đó, chỉ ghi nhận mốc mới cho rule ngưỡng ≥5 ngày)* "Dạ em đã cập nhật lại là bé sốt 6 ngày rồi ạ. Với thời gian sốt kéo dài như vậy, dù các dấu hiệu khác hiện chưa thấy, em vẫn khuyên nên cho bé đi khám sớm để tìm nguyên nhân."

```json
{
  "patient": {"age_value": 2, "age_unit": "year"},
  "fever": {"fever_duration_days": 6},
  "neurological": {"seizure_occurred": false, "neck_stiffness": false},
  "respiratory": {"breathing_difficulty": false, "cyanosis": false},
  "skin": {"non_blanching_rash": false},
  "session": {"triage_level": "EARLY_VISIT", "time_target": "within_24h", "reason_codes": ["RF-26"], "triggered_rules": ["R-V-02"]}
}
```

**Reasoning:** `fever_duration_days` bị ghi đè từ 3 → 6 theo giá trị mới nhất người dùng cung cấp, đúng quy ước "lấy giá trị sửa lại" ở §3. Vì `age_value/age_unit` không đổi, không có nhánh `C` phụ thuộc tuổi nào cần chạy lại. Mốc mới `≥5 ngày` kích hoạt `R-V-02` → `EARLY_VISIT`, khác với kết luận đáng lẽ có nếu vẫn dùng giá trị cũ (3 ngày, chưa đạt ngưỡng) — minh hoạ vì sao bắt buộc phải dùng giá trị đã sửa, không giữ giá trị ban đầu.

---

## PHỤ LỤC — NGUỒN

Tài liệu này không tự tạo field, ngưỡng, hay rule mới — mọi tham chiếu `RF-xx`, `R-x-xx`, field name đều trỏ về `fever-knowledge-model.md` v1.0. 
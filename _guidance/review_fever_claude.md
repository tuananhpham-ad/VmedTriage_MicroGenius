# REVIEW — Fever Knowledge Model & Conversation Specification

**Người review:** Claude (Sonnet 5)
**Tài liệu được review:**
- `fever-knowledge-model.md` (v1.0 DRAFT, 2026-08-10) — sau đây gọi tắt **KM**
- `fever-conversation-specification.md` (v1.0 DRAFT, 2026-08-11) — sau đây gọi tắt **CS**

**Ngày review:** 2026-08-11
**Phạm vi:** đọc toàn bộ hai tài liệu (KM: Part 0–7 + Phụ lục JSON Schema; CS: Part 0–8). Trọng tâm theo yêu cầu: (1) tính đúng đắn/nhất quán, (2) các đoạn chưa hợp lý, (3) **vấn đề số lượng câu hỏi bắt buộc (M) quá nhiều gây hội thoại dài** — đây là phần được đào sâu nhất, có phân tích định lượng và đề xuất cụ thể.

---

## 0. Kết luận nhanh (executive summary)

Hai tài liệu có chất lượng thiết kế lâm sàng tốt: red flag được ánh xạ rõ ràng tới nguồn (NICE/IMCI/AAP/QĐ 2760), nguyên tắc an toàn (tri-state, không hạ mức, không chẩn đoán) được giữ nhất quán xuyên suốt, và CS đã áp dụng đúng ý tưởng "gộp câu hỏi theo cụm lâm sàng" ở Stage 3. Đây là nền tảng tốt.

Nhưng phần **user quan tâm nhất — số câu hỏi bắt buộc (M) và độ dài hội thoại — là vấn đề thật, không phải cảm giác**. Bằng chứng định lượng ở §2 dưới đây: tổng số lượt hỏi tối thiểu theo thiết kế hiện tại là **~33–38 lượt** (Stage 0–5), trong khi chính KM và CS tự đặt ngân sách **≤20–25 câu** (CS Part 6, KM không nêu con số nhưng CS kế thừa). Nguyên nhân gốc không nằm ở Stage 3 (đã gộp cụm khá tốt) mà nằm ở **Stage 4** và một phần **Stage 5**, nơi gần như mọi field được đánh dấu **M nhưng lại hỏi rời từng field một, "luôn hỏi" không điều kiện** — ngược với chính nguyên tắc P0-3 (gộp câu hỏi liên quan) mà tài liệu đề ra.

Ngoài ra có một số điểm **không nhất quán giữa hai tài liệu** cần chốt lại trước khi implement (liệt kê ở §3), và một vài điểm câu chữ/logic trong KM cần làm rõ (§4).

---

## 1. Điểm làm tốt (giữ nguyên)

| # | Điểm tốt | Vị trí |
|---|---|---|
| 1 | Nguyên tắc tri-state (`unknown ≠ false`) được giữ nhất quán từ KM §3.1 xuống tới CS Part 5–6, không có chỗ nào vi phạm khi đọc lại toàn bộ script mẫu Part 8 | KM §3.1, CS P0-4, Part 5, 6 |
| 2 | Nguyên tắc "không rule nào được hạ mức" (invariant) được tôn trọng nhất quán ở cả rule catalog (§6.1 KM) lẫn flow hội thoại (CS Part 4.2, Part 7 flowchart) | KM §0.2, §6.3; CS 4.2 |
| 3 | Stage 3 (quét red flag) là ví dụ tốt về gộp câu hỏi theo cụm lâm sàng — 14 câu bao phủ ~30 field, đúng tinh thần "hỏi như điều dưỡng thật" | CS Part 3.3 |
| 4 | Ràng buộc an toàn NSAID (R-G-03) được thiết kế để **không bao giờ bị bỏ qua kể cả khi đã escalate cấp cứu** — đúng logic vì đây là rủi ro do chính hệ thống gây ra (gợi ý sai thuốc), khác với các field làm giàu thông tin khác | KM §4.9; CS Q5-05, Part 4.1 mục 5 |
| 5 | Cơ chế `conservatism_tier` (0/1/2) là thiết kế đúng hướng để mô hình hóa các quần thể nguy cơ cao thay vì rải rule riêng lẻ | KM §5.1 |
| 6 | Ví dụ H5 (CS Part 8.3) — phân biệt "chảy dãi do mọc răng" với `stridor_or_drooling` — là minh chứng tốt cho việc AI phải làm rõ trước khi gán `false` cho field red-flag, đúng nguyên tắc Part 5 | CS 8.3-H5 |

---

## 2. VẤN ĐỀ TRỌNG TÂM — Quá nhiều field M → hội thoại quá dài

### 2.1. Đếm định lượng: bao nhiêu field thực sự là M?

Đếm trực tiếp từ ma trận đối soát KM §6.2 (bỏ qua field session/meta không được hỏi trực tiếp): có khoảng **46 field được đánh dấu M** (không tính field C/O). Đối chiếu với CS Part 1.1 — bảng "Thông tin luôn phải thu thập" liệt kê đúng ngần ấy field, chia theo 11 nhóm.

Điều đáng chú ý: **KM không có tầng phân loại nào giữa "M tuyệt đối" và "M nhưng có thể hỏi gộp/hỏi nhanh"**. Một field như `mosquito_exposure` (muỗi đốt) được xếp M ngang hàng với `consciousness_level` (tri giác) — cả hai đều "không được kết luận triage nếu thiếu" theo KM §3.1 mục 3. Về mặt an toàn điều đó không sai (thiếu field nào cũng phải xử lý bằng `data_gap`), nhưng về mặt **thiết kế hội thoại, nó xóa mất mọi tín hiệu để phân biệt "field cần hỏi kỹ, từng cái" với "field có thể hỏi gộp/hỏi nhanh dạng sàng lọc"**. Đây là gốc rễ của vấn đề, không phải triệu chứng.

### 2.2. Đếm số lượt hỏi thực tế theo CS Part 3

| Stage | Số câu hỏi trong bảng | Ghi chú "ask condition" |
|---|---|---|
| 0 | 2 (Q0-01, Q0-02) | Cả 2 "luôn hỏi" |
| 1 | 2–3 (Q1-01..03) | Q1-03 chỉ khi subjective |
| 2 | 4–5 (Q2-01..05) | Q2-05 chỉ nhóm nguy cơ |
| 3 | **14** (Q3-01..14) | Toàn bộ "luôn hỏi", chỉ dừng khi có EMERGENCY |
| 4 | **8** (Q4-01..08) | **7/8 câu ghi "Luôn hỏi" không điều kiện** (trừ Q4-01/01b/02 có gate theo sex/age, nhưng Q4-03..08 đều "Luôn hỏi") |
| 5 | 7 (Q5-01..07) | Trộn lẫn: một số P1 "luôn hỏi" (Q5-01 nếu <5t, Q5-02, Q5-04, Q5-05), một số P2/P3 có gate ngân sách |

**Tổng lượt hỏi tối thiểu (không tính follow-up khi mơ hồ) nếu không có EMERGENCY sớm và không rơi vào nhánh skip theo tuổi/giới:**

```
Stage 0: 2
Stage 1: 2–3
Stage 2: 4–5   (Q2-05 chỉ nhóm nguy cơ, bỏ qua với đa số → tính 4)
Stage 3: 14
Stage 4: 6–8   (Q4-01/01b/02 phụ thuộc giới, còn lại 5 câu luôn hỏi + risk-nhóm)
Stage 5: 5–7
──────────────────────────
TỔNG: ~33–38 lượt hỏi
```

So với ngân sách CS tự đặt ra ở Part 6: **"nhóm chung ≤ 20–25 câu tổng cộng qua các stage"**. Riêng Stage 0–3 (trước khi vào Stage 4) đã tiêu tốn **20–22 lượt** — tức là **đã chạm hoặc vượt trần ngân sách trước khi Stage 4 kịp bắt đầu**. Đây là một mâu thuẫn nội tại giữa Part 6 (ngân sách) và Part 3 (thiết kế câu hỏi thực tế) mà tài liệu chưa tự phát hiện ra.

Đây chính xác là điều user quan sát được: hội thoại "đang bị nhiều quá" không phải ảo giác — nó là hệ quả tất yếu của cách CS hiện tại thiết kế Stage 4/5.

### 2.3. Vì sao Stage 4 là thủ phạm chính (không phải Stage 3)

Stage 3 tuy có 14 câu nhưng **đã gộp đúng cách** — mỗi câu bao phủ 1–4 field liên quan lâm sàng (vd Q3-06 gộp 5 field hô hấp trong 1 câu). Đây là thiết kế nên giữ.

Stage 4 thì ngược lại: **8 câu cho 8 nhóm nguy cơ gần như tách biệt hoàn toàn, mỗi câu hỏi kỹ một chủ đề (thai kỳ, miễn dịch, mạn tính, phẫu thuật/thiết bị, sốt rét, dịch tễ, hoàn cảnh sống)**, và **hầu hết đều "luôn hỏi"** dù xác suất một ca cụ thể rơi vào từng nhóm nguy cơ là thấp (vd một người lớn khỏe mạnh, không đi đâu xa, không có bệnh nền — vẫn phải trả lời đủ 8 câu để hệ thống "loại trừ" từng nguy cơ một). Đây vi phạm chính nguyên tắc P0-3 (gộp câu hỏi liên quan) mà CS đặt ra cho Stage 3 nhưng không áp dụng cho Stage 4.

CS Part 4.2 (mục "khi SELF_CARE có vẻ rõ ràng — bỏ câu hỏi nào") chỉ cho phép bỏ field **P3 ở Stage 5**, không cho phép rút gọn bất cứ gì ở Stage 4 — nghĩa là theo đúng thiết kế hiện tại, **không có ca nào (kể cả ca lành tính rõ ràng nhất) tránh được đủ 8 câu Stage 4**.

### 2.4. Đề xuất cải thiện — 3 lựa chọn, có thể kết hợp

**A. Gộp cụm Stage 4 theo chủ đề (áp dụng đúng pattern đã thành công ở Stage 3)**

Thay vì 8 câu tách biệt, gộp thành 3 câu sàng lọc đa lựa chọn (multi-select), tương tự cách người thật hỏi nhanh trong khai thác tiền sử:

- **Câu sàng lọc nguy cơ nhiễm khuẩn nặng** (gộp Q4-03 + Q4-04 + Q4-05): *"Anh/chị hiện có đang gặp trường hợp nào sau đây không: đang hóa trị/dùng thuốc ức chế miễn dịch, có bệnh mạn tính (tim/phổi/gan/thận/tiểu đường/bệnh máu), hoặc mới phẫu thuật/đang mang ống thông trong người?"* — 1 lượt thay vì 3, chỉ hỏi chi tiết tiếp (thời điểm hóa trị, loại bệnh, vết mổ) cho **nhánh nào trả lời có**.
- **Câu sàng lọc dịch tễ** (gộp Q4-06 + Q4-07): *"Gần đây anh/chị có đi vùng nào có sốt rét, hoặc xung quanh có ai bị sốt xuất huyết/dịch bệnh, hoặc bị muỗi đốt nhiều không?"* — 1 lượt thay vì 2.
- **Câu hoàn cảnh sống** (giữ Q4-08 riêng vì không cùng chủ đề lâm sàng): 1 lượt.
- Thai kỳ (Q4-01/01b/02): giữ nguyên vì đã có gate theo giới/tuổi, không phải thủ phạm.

Kết quả: Stage 4 từ 6–8 lượt còn **~4 lượt** cho đa số ca, chỉ tăng lên khi có nhánh dương tính cần làm rõ — đúng nguyên tắc "hỏi sâu khi cần, không hỏi sâu khi không cần".

**B. Tách "M-sàng lọc" khỏi "M-chi tiết" trong bản thân KM (thay đổi cấu trúc M/C)**

Đây là thay đổi ở tầng KM, không chỉ CS. Hiện tại KM §3.1 mục 3 chỉ có 3 mức M/C/O. Đề xuất bổ sung một thuộc tính thứ hai độc lập với M/C/O: **"question footprint"** — field nào có thể được **suy ra gián tiếp từ 1 câu hỏi gộp** (vd `chronic_conditions`, `recent_surgery_30d`, `indwelling_device` đều có thể trả lời qua 1 câu sàng lọc đa lựa chọn) và field nào **bắt buộc phải là câu hỏi riêng vì cần độ chính xác cao** (vd `consciousness_level`, `seizure_active_now` — không thể gộp vì sai lệch ở đây trực tiếp đổi mức triage nghiêm trọng nhất).

Việc này giúp Engineering/Conversation Designer nhìn vào KM là biết field nào **được phép** thiết kế thành multi-select gộp, thay vì phải tự suy luận như CS đang làm (và làm chưa nhất quán — Stage 3 gộp tốt, Stage 4 thì không).

**C. Siết lại ngân sách theo stage thay vì ngân sách tổng**

CS Part 6 hiện chỉ có ngân sách tổng (~20–25 câu) và ngân sách riêng cho tier 2 (≤6 câu). Đề xuất thêm **trần cứng theo từng stage** ngay trong CS Part 2 (bảng stage), ví dụ Stage 4 ≤ 4 lượt, Stage 5 ≤ 4 lượt — buộc thiết kế câu hỏi phải tuân theo, thay vì để ngân sách tổng là con số "hy vọng" không ràng buộc thiết kế cụ thể. Nếu không có trần theo stage, ngân sách tổng chỉ là khẩu hiệu.

**Khuyến nghị:** làm cả A và C ngay (không đổi cấu trúc KM), B là cải thiện dài hạn nếu nhóm muốn tài liệu hóa rõ ràng hơn cho các symptom group tiếp theo (không chỉ riêng sốt).

### 2.5. Một điểm cần cân nhắc thêm: phân biệt "hỏi hết M" và "kết luận được"

KM §3.1 mục 3 định nghĩa M = "không được kết luận triage nếu thiếu". Điều này **không bắt buộc phải hỏi M bằng một câu hỏi riêng** — nó chỉ yêu cầu field đó có giá trị (kể cả suy ra được từ ngữ cảnh, vd nếu Stage 0 đã biết là nam giới thì toàn bộ field sản khoa M "coi như đã trả lời" bằng `not_applicable`, không phải "unknown"). CS đã áp dụng đúng logic này cho field điều kiện theo giới/tuổi, nhưng **chưa áp dụng logic tương tự cho các field nguy cơ dịch tễ/mạn tính/phẫu thuật** — những field này không có "auto-skip" nào, luôn cần một câu hỏi tường minh. Đây là cơ hội cải thiện lớn nhất: nếu coi các câu sàng lọc gộp (đề xuất A) là "một câu hỏi = nhiều field", thì per-field M vẫn được tôn trọng (mỗi field vẫn có giá trị xác định `true/false/unknown`) mà **số lượt hội thoại giảm mạnh** — đây là hướng giải đúng: không giảm độ an toàn (không hạ M xuống O), chỉ giảm **số lượt tương tác cần thiết để thu thập cùng một lượng field**.

---

## 3. Điểm KHÔNG NHẤT QUÁN giữa hai tài liệu (cần chốt trước khi implement)

| # | Vấn đề | Vị trí | Mức độ |
|---|---|---|---|
| 1 | **Ngưỡng thời gian du lịch vùng sốt rét không nhất quán giữa 4 chỗ khác nhau:** tiêu đề RF-35 trong KM ghi "**≤3 tháng**" (§4.7); rule `R-E-19`/`R-V-20` (§6.1) lại dùng mốc **≤1 tháng vs >1 tháng**; bảng quần thể §5.2 ghi lại "**≤3 tháng**"; còn CS Q4-06 hỏi khoảng "**1–3 tháng**" và field `travel_history_12m` (KM §3.10, Nhóm L) định nghĩa cửa sổ **12 tháng**. Bốn con số khác nhau (1 tháng / 3 tháng / 1–3 tháng / 12 tháng) cho cùng một khái niệm nguy cơ sốt rét. | KM §4.7 (RF-35), §5.2, §6.1 (R-E-19, R-V-20); CS Q4-06 | **Cao** — đây là rule ảnh hưởng trực tiếp tới mức `EMERGENCY`, cần chốt lại đúng 1 con số trước khi engineering implement, nếu không rule sẽ không nhất quán giữa các phiên bản đọc tài liệu khác nhau |
| 2 | **Ngưỡng sốt đường miệng (oral) mơ hồ:** bảng §1.2 KM ghi ngưỡng oral là "**≥ 37,8 – 38,0 °C**" (trình bày như một khoảng, không rõ ngưỡng vận hành là bao nhiêu), nhưng công thức `is_fever_objective` ngay bên dưới lại gộp `oral` chung nhóm với `rectal`/`tympanic` ở ngưỡng **≥38.0** — tức bỏ qua khả năng 37.8–37.9°C oral cũng được tính là sốt theo chính bảng phía trên. | KM §1.2 | Trung bình — ảnh hưởng ngưỡng phân loại `fever_status`/`temp_c` cho nhóm đo ở miệng, cần chốt 1 số duy nhất (khuyến nghị dùng 37.8 nếu muốn nhạy hơn, hoặc xóa khoảng mơ hồ và chỉ để 38.0 nếu muốn nhất quán với công thức hiện tại) |
| 3 | Field `known_neutropenia` được đánh dấu **C** trong bảng field (§3.10) nhưng logic rule R-E-18 coi nó ngang hàng điều kiện kích hoạt EMERGENCY tuyệt đối (cùng cấp với `chemotherapy_6w`) — về bản chất đây gần như M cho nhóm đang hóa trị (tier 2), không phải C thường. Không sai nhưng dễ gây hiểu lầm khi đọc riêng bảng field mà không đọc kèm rule. | KM §3.10, §6.1 (R-E-18) | Thấp — chỉ là vấn đề trình bày, nên chú thích rõ "C nhưng trở thành M-hiệu-lực khi `immunocompromise_cause` chứa hóa trị" |
| 4 | CS Part 4.1 mục 3 khi đã EMERGENCY: giữ lại 2 câu Stage 4 (immunocompromised, is_pregnant) nhưng **bỏ hoàn toàn** câu về sốt rét (`malaria_risk_area`) — trong khi chính KM liệt kê sốt rét là 1 trong các nguyên nhân EMERGENCY độc lập (`R-E-19`) có thể **cùng tồn tại** với một EMERGENCY khác (vd co giật + vừa đi vùng sốt rét). Việc bỏ hẳn câu này khi đã EMERGENCY do lý do khác là hợp lý về mặt tốc độ (không đổi kết luận nữa), nhưng tài liệu nên nói rõ lý do (đã đủ EMERGENCY, thông tin sốt rét chỉ ảnh hưởng lựa chọn tuyến điều trị chứ không đổi time_target) để tránh đọc nhầm là "quên" — hiện CS không giải thích tại sao bỏ đúng câu này mà không phải câu khác. | CS Part 4.1 mục 3 | Thấp — chỉ cần thêm 1 câu giải thích |

---

## 4. Điểm cần làm rõ thêm trong KM (không phải lỗi, nhưng chưa đủ rõ)

1. **§5.2, dòng "Trẻ 3–6 tháng":** ghi tier **"1"**, nhưng dòng "Trẻ 6 tháng – 5 tuổi" ghi tier **"0–1"**. Không có bảng nào giải thích khi nào nhóm 6 tháng–5 tuổi rơi vào tier 1 thay vì tier 0 — nên bổ sung điều kiện cụ thể (có lẽ là khi có thêm yếu tố khác như bệnh mạn tính đi kèm?), nếu không rule engine không biết khi nào áp `tier=1` cho nhóm tuổi này.
2. **RF-11 / R-E-08 / R-V-05 (SpO₂):** KM tự nhận field `spo2_percent` là **O** (optional, §3.5) vì đây là remote assessment không phải ai cũng đo được — nhưng đồng thời rule `R-E-08` (SpO₂ ≤92 → EMERGENCY) là một trong các điều kiện EMERGENCY độc lập. Nên ghi rõ trong §4.3 rằng rule này **chỉ kích hoạt khi có SpO₂ đo được**, không phải "thiếu SpO₂ = không loại trừ được EMERGENCY qua đường này" — hiện đọc lướt dễ hiểu nhầm SpO₂ là bắt buộc phải hỏi.
3. **KM §6.3 "Coverage checks":** liệt kê "44/44 RF được ánh xạ ✔" nhưng đếm thủ công trong Part 4 thấy RF đánh số tới **RF-44**, tức đúng 44 mã — con số này đúng, chỉ nên lưu ý đây là **tổng kiểm tra thủ công chưa có công cụ tự động**, nếu KM còn sửa (rất có thể, vì đang DRAFT) thì con số "44/44" dễ lỗi thời mà không ai cập nhật — nên thay bằng câu "chạy script coverage-check trước mỗi lần merge" thay vì con số tĩnh.

---

## 5. Điểm cần làm rõ thêm trong CS (không phải lỗi, nhưng chưa đủ rõ)

1. **Q3-14 (mức lo lắng 0–10) đặt cuối Stage 3** — hợp lý vì là "gut-check" tổng kết, nhưng vì đây cũng là một trong các điều kiện có thể tự đẩy lên `EARLY_VISIT` (RF-44, khi `caregiver_concern_level ≥ 8`), nên cân nhắc: nếu người dùng trả lời 9–10 ngay từ đầu hội thoại (vd trong câu mở đầu tự nhiên "tôi rất lo, cháu có vẻ mệt lắm"), CS không có cơ chế nào bắt tín hiệu này sớm để rút ngắn Stage 3–5 — hiện tại CS chỉ hỏi lo lắng ở cuối, nghĩa là bỏ lỡ cơ hội dùng nó như tín hiệu ưu tiên hỏi kỹ hơn thay vì hỏi ít hơn. Gợi ý: nếu người dùng tự phát biểu mức độ lo lắng cao trong lời mở đầu tự do, hệ thống nên ghi nhận ngay (không đợi tới Q3-14) — đây là điểm NLU/parsing tự do cần lưu ý khi implement, không chỉ là thứ tự script.
2. **Max follow-up = 0 cho nhiều câu P0/P1** (vd Q3-05, Q3-07, Q3-12, Q5-02...) — hợp lý cho câu ngắn/rõ ràng, nhưng nên có một câu giải thích tường minh trong Part 3 "Quy ước" rằng `Max follow-up = 0` không có nghĩa là không được làm rõ khi mơ hồ, mà nghĩa là **không có follow-up kịch bản sẵn — vẫn áp dụng nguyên tắc chung Part 5** (paraphrase 1 lần). Hiện đọc bảng dễ hiểu nhầm "0 follow-up" = "chấp nhận câu trả lời mơ hồ luôn", trái với P0-4.

---

## 6. Tổng kết ưu tiên xử lý

| Ưu tiên | Việc cần làm | Vì sao |
|---|---|---|
| 1 | Gộp cụm Stage 4 (đề xuất A ở §2.4) — biến 8 câu rời thành ~3–4 câu sàng lọc + follow-up có điều kiện | Đây là nguyên nhân lớn nhất khiến hội thoại vượt ngân sách; sửa không cần đổi field/rule nào trong KM, chỉ đổi cách CS hỏi |
| 2 | Thêm trần cứng theo stage vào CS Part 2/6 (đề xuất C) | Biến ngân sách tổng từ khẩu hiệu thành ràng buộc thiết kế thực sự |
| 3 | Chốt lại ngưỡng thời gian du lịch sốt rét (mục 1, §3) — chọn 1 trong 4 con số đang mâu thuẫn | Ảnh hưởng trực tiếp kết luận EMERGENCY, rủi ro implement sai nếu không chốt trước |
| 4 | Làm rõ ngưỡng oral fever (mục 2, §3) | Ảnh hưởng phân loại `fever_status`, dễ sai khi code hóa công thức |
| 5 | (Dài hạn, không gấp) Cân nhắc thêm thuộc tính "question footprint" vào KM §3.1 (đề xuất B) nếu nhóm sẽ làm thêm nhiều symptom group khác — giúp chuẩn hóa cách CS tương lai gộp câu hỏi thay vì tự suy luận từng lần | Giá trị dài hạn cho toàn bộ hệ thống, không chỉ riêng FEVER |

**Trạng thái đề xuất:** đây là review kỹ thuật, chưa phải phê duyệt lâm sàng — mọi thay đổi ngưỡng số liệu (mục 3.1 và 3.2) vẫn cần hội đồng chuyên môn xác nhận trước khi chỉnh sửa KM, đúng như ghi chú DRAFT ở cả hai tài liệu.

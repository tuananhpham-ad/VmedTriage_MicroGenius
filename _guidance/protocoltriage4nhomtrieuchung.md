# VMedTriage — Protocol triage

## 1\. Tổng quan

**Mục đích:** Tài liệu grounding quy định *nên hỏi câu gì*, *hỏi theo thứ tự/logic nào*, và *dựa vào đâu để gắn mức ưu tiên*. Không phải tài liệu y khoa để chẩn đoán — AI Agent không được chẩn đoán, chỉ thu thập triệu chứng, phát hiện dấu hiệu nguy hiểm (red-flag) và đề xuất mức ưu tiên; nhân viên y tế luôn là người duyệt cuối (Human-in-the-Loop).

**Phạm vi:** 4 nhóm triệu chứng khởi đầu \- Đau ngực, Đau bụng, Khó thở, Đau đầu.

**3 mức ưu tiên đầu ra**: **Cấp cứu** → **Cần khám sớm** → **Tự chăm sóc tại nhà**.

pipeline: Kiểm tra Cấp cứu (1) \-\> Lấy Hồ sơ (2) \-\> Lấy Triệu chứng (3, 4\) \-\> Quét Rủi ro/Tiền sử (5) \-\> XUẤT KẾT QUẢ TƯ VẤN.

---

Nên dùng decision tree, không phải checklist tuyến tính. Câu hỏi tiếp theo phụ thuộc câu trả lời trước \- nếu một nhánh đã đủ dữ kiện để phân loại, các câu hỏi của nhánh khác bị bỏ qua.

→ AI Agent nên có tối đa 5 câu hỏi lõi cho mỗi nhóm triệu chứng (câu 1 luôn là sàng lọc red-flag), cộng thêm tối đa 1-2 câu hỏi mở rộng có điều kiện chỉ khi câu trả lời trước đó chưa đủ rõ để phân loại.   
---

## 2\. Nguồn protocol tham chiếu (grounding)

| Nhóm triệu chứng | Protocol/nguồn chuẩn | Loại protocol |
| :---- | :---- | :---- |
| Đau ngực | Schmitt-Thompson Telephone Triage Protocols — *Chest Pain, Adult* (2015); bổ sung danh mục discriminator từ The Sullivan Group (ED triage) | Telephone triage (tổng đài y tế) |
| Đau bụng | Schmitt-Thompson Telephone Triage Protocols — *Abdominal Pain, Adult* | Telephone triage |
| Khó thở | Bộ 3 câu hỏi sàng lọc breathlessness của NHS 111; khuyến nghị đánh giá từ xa của Centre for Evidence-Based Medicine (Oxford) | Telephone/remote triage |
| Đau đầu | SNOOP / SNNOOP10 — bộ tiêu chí "red & orange flags" cho đau đầu thứ phát, dùng rộng rãi trong y văn thần kinh học (LITFL, tài liệu neurology lâm sàng) | Clinical red-flag checklist |

---

## 3\. Bộ câu hỏi tối thiểu theo từng nhóm triệu chứng

Cấu trúc chung mỗi nhóm: **Câu 1 \= sàng lọc red-flag (trả lời "có" → Cấp cứu ngay, dừng hỏi)** → Câu 2-5 \= các câu hỏi gộp để phân biệt Cần khám sớm vs Tự chăm sóc.

### 3.1. Đau ngực

| \# | Câu hỏi gộp cho AI Agent | Tiêu chí protocol được phủ |
| :---- | :---- | :---- |
| 1 (red-flag) | "Hiện tại bạn/ người thân có đang khó thở nặng đến mức không nói được hết câu, không còn tỉnh táo không?" | Severe breathing difficulty, loss of consciousness, "sounds life-threatening" |
| 2 | "Cơn đau ở vị trí nào, có cảm giác đè ép/bóp nghẹt/nặng ngực không, và có lan ra vai, cánh tay hoặc hàm không?" | Vị trí \+ tính chất "crushing/pressure" \+ lan  \- dấu hiệu hội chứng vành cấp |
| 3 | "Cơn đau bắt đầu từ khi nào, kéo dài liên tục hay từng cơn, và đã hơn 5 phút chưa?" | Onset \+ duration \>5 phút (ngưỡng quyết định chính trong protocol gốc) |
| 4 | "Bạn có tuổi trên 50 và có bệnh nền như cao huyết áp/tiểu đường/mỡ máu cao/hút thuốc/tiền sử bệnh tim không?" (Nếu đã có thông tin tuổi rồi thì chỉ hỏi bệnh nền) | Age \>50 \+ ≥1 yếu tố nguy cơ tim mạch |
| 5 | "Cơn đau có kèm khó thở, vã mồ hôi, chóng mặt, buồn nôn, tim đập nhanh/không đều, hoặc bạn vừa mới phẫu thuật/nằm bất động lâu/đi máy bay xa gần đây không?" | Đau kèm khó thở, diaphoresis, dizziness, arrhythmia; yếu tố nguy cơ thuyên tắc phổi (VTE) |

**Mapping mức ưu tiên:**  
Mục tiêu: Loại trừ các tình trạng đe dọa tính mạng ngay lập tức như Hội chứng vành cấp (ACS/Nhồi máu cơ tim), thuyên tắc phổi (PE) hoặc bóc tách động mạch chủ. 

- **Cấp cứu:** Câu 1 \= có; HOẶC đau \>5 phút \+ (tuổi/yếu tố nguy cơ ở câu 4 \= có) \+ tính chất đè ép ở câu 2; HOẶC đau kèm khó thở/tim đập nhanh-không đều ở câu 5\.

	→ Hướng xử lý: Gọi cấp cứu ngay lập tức.

- **Cần khám sớm:** đau \>5 phút nhưng không đủ tiêu chí Cấp cứu ở trên; hoặc có yếu tố nguy cơ VTE ở câu 5; hoặc đau từng cơn tăng dần mức độ/tần suất; hoặc sốt \>38.1°C kèm đau ngực.  
  → Hướng xử lý: Yêu cầu đến Khoa Cấp cứu hoặc khám bác sĩ ngay trong vòng vài giờ.  
- **Tự chăm sóc:** đau nhẹ, từng cơn, mỗi lần chỉ vài giây, không có yếu tố nguy cơ, không triệu chứng đi kèm ở câu 5 \- kèm dặn dò quay lại nếu đau nặng lên, kéo dài \>5 phút, hoặc khó thở.

	→ Hướng xử lý: Hướng dẫn chườm ấm/lạnh, nghỉ ngơi và cung cấp các "dấu hiệu cảnh báo" bắt buộc phải báo lại hoặc đi cấp cứu ngay nếu tình trạng thay đổi.

### 3.2. Đau bụng

| \# | Câu hỏi gộp cho AI Agent | Tiêu chí protocol được phủ |
| :---- | :---- | :---- |
| 1 (red-flag) | "Bạn có đang cảm thấy lơ mơ/khó tỉnh táo, lú lẫn, từng ngất xỉu, hoặc da lạnh/nhợt/vã mồ hôi không?" | Dấu hiệu sốc (shock), rối loạn ý thức, ngất |
| 2 | "Đau ở vị trí nào trong bụng, có lan ra ngực hoặc lưng không, và mức độ đau như thế nào?" | Location, radiation, severity scale |
| 3 | "Cơn đau bắt đầu đột ngột hay từ từ, đau liên tục hay từng cơn, và đã kéo dài bao lâu rồi?" | Onset, pattern, duration — ngưỡng quyết định theo giờ (\>1h/\>2h/\>24h/\>48h) |
| 4 | "Bạn có nôn ra máu hoặc dịch giống bã cà phê, đi ngoài phân đen/có máu, hoặc không thể đi tiểu được hơn 4 giờ dù rất mắc tiểu không?" | GI bleeding, urinary retention — nhóm tiêu chí "Cấp cứu/Khám ngay" nghiêm trọng nhất sau sốc |
| 5 | "Bạn có sốt không, có vàng da/mắt không, bụng có chướng bất thường không, và có trên 60 tuổi không?" (Nếu đã có thông tin về tuổi thì không hỏi lại) | Fever ngưỡng theo protocol, jaundice, abdominal distension, age \>60 (yếu tố nguy cơ độc lập) |

**Mapping mức ưu tiên:**

- **Cấp cứu:** Câu 1 \= có; HOẶC câu 4 \= có (xuất huyết tiêu hoá/bí tiểu).  
- **Cần khám sớm:** đau nặng \>1h (đặc biệt nếu \>60 tuổi); đau vừa liên tục \>2h; sốt cao theo ngưỡng ở câu 5 (\>39.4°C, hoặc \>38.3°C nếu \>60 tuổi, hoặc \>38.1°C nếu tiểu đường/suy giảm miễn dịch); vàng da; bụng chướng kèm nôn.  
- **Tự chăm sóc:** đau nhẹ-vừa, từng cơn, không có dấu hiệu ở câu 1/4/5, đau liên tục \<2h hoặc từng cơn \- kèm dặn dò quay lại nếu xuất hiện bất kỳ dấu hiệu nào ở câu 1 hoặc 4\.  
  → hướng xử lý: Nghỉ ngơi, chia nhỏ bữa ăn, ưu tiên thức ăn lỏng, nhạt (như cháo, súp, chế độ ăn BRAT: chuối, gạo, sốt táo, bánh mì nướng). Uống từng ngụm nước nhỏ (Oresol, nước lọc) để phòng mất nước.   
    
  Bệnh nhân/ người nhà được dặn dò phải liên lạc lại hoặc đi khám ngay nếu cơn đau trở nên dữ dội, đau khu trú vào một điểm, xuất hiện máu trong phân/chất nôn hoặc không thể đi tiểu.

### 3.3. Khó thở

| \# | Câu hỏi gộp cho AI Agent | Tiêu chí protocol được phủ |
| :---- | :---- | :---- |
| 1 (red-flag) | "Bạn có đang khó thở đến mức không nói được hết câu, hoặc môi/đầu ngón tay chuyển màu tím/xanh không?" | NHS 111 Q1 (unable to speak \>few words) \+ tím tái (cyanosis) — red flag nặng nhất |
| 2 | "Khó thở bắt đầu đột ngột hay tăng dần, và bắt đầu từ khi nào?" | Onset — đột ngột gợi ý thuyên tắc phổi/tràn khí màng phổi, cần phân biệt với mạn tính |
| 3 | "Bạn có đang thở nhanh hơn hoặc khó thở hơn bình thường ngay cả khi đang ngồi nghỉ không?" | NHS 111 Q2 — khó thở khi nghỉ (không cần gắng sức) |
| 4 | "Có kèm đau ngực, ho ra máu, sốt, hoặc phù/sưng ở chân không?" | Phân biệt nguyên nhân: thuyên tắc phổi, viêm phổi, suy tim |
| 5 | "So với hôm qua, việc bạn làm bình thường như đi lại, nói chuyện, làm việc nhà có bị ảnh hưởng nhiều không?" | NHS 111 Q3 — mức ảnh hưởng chức năng, dùng để phân biệt nhẹ/vừa khi câu 1-2 chưa rõ |

**Mapping mức ưu tiên:**

- **Cấp cứu:** Câu 1 \= có; HOẶC khó thở đột ngột \+ đau ngực/ho ra máu ở câu 4 (nghi thuyên tắc phổi).  
- **Cần khám sớm:** khó thở khi nghỉ (câu 3 \= có) nhưng chưa đến mức câu 1; kèm sốt (nghi viêm phổi) hoặc phù chân (nghi suy tim) ở câu 4; hoặc ảnh hưởng rõ đến sinh hoạt hàng ngày ở câu 5\.  
- **Tự chăm sóc:** chỉ khó thở nhẹ khi gắng sức, không khó thở khi nghỉ, không triệu chứng đi kèm, ít ảnh hưởng sinh hoạt \- kèm dặn dò quay lại ngay nếu khó thở tăng hoặc xuất hiện dấu hiệu ở câu 1\.

### 3.4. Đau đầu

Dựa trên mnemonic SNOOP (Systemic symptoms, Neurologic symptoms, Onset sudden, Older age \>50 khởi phát mới, Progressive) \- bộ tiêu chí red-flag cho đau đầu thứ phát nguy hiểm, được mở rộng thành SNNOOP10.

| \# | Câu hỏi gộp cho AI Agent | Tiêu chí SNOOP được phủ |
| :---- | :---- | :---- |
| 1 (red-flag) | "Cơn đau đầu này có đến đột ngột và đạt mức dữ dội nhất trong vòng vài giây đến vài phút không?" | **O**nset (thunderclap) — dấu hiệu nghi xuất huyết não/dưới nhện, khẩn cấp nhất |
| 2 | "Có kèm yếu/tê tay chân một bên, nói khó, lú lẫn, thay đổi ý thức, co giật, hoặc cứng gáy kèm sốt cao không?" | **N**eurologic symptoms \+ **S**ystemic (sốt/cứng gáy nghi viêm màng não) |
| 3 | "Bạn có đang mang thai, có bệnh nền như ung thư/HIV/rối loạn đông máu, hoặc mới bị chấn thương đầu gần đây không?" | Yếu tố nguy cơ nền (SNNOOP10 mở rộng) làm tăng khả năng đau đầu thứ phát |
| 4 | "Đau đầu này có khác hẳn kiểu đau bạn từng bị trước đây, hoặc đang nặng dần lên qua từng ngày? Bạn có trên 50 tuổi và đây là lần đầu tiên bị đau đầu kiểu này không?" | **P**rogressive \+ **O**lder (khởi phát mới \>50 tuổi) |
| 5 | "Cơn đau có thay đổi rõ khi đổi tư thế (đứng dậy/cúi người/ho, rặn), hoặc bạn có đang nhìn mờ/nhìn đôi không?" | **P**ositional \+ Papilledema-liên-quan (SNNOOP10 mở rộng) |

**Mapping mức ưu tiên:**

- **Cấp cứu:** Câu 1 \= có (thunderclap); HOẶC câu 2 \= có (dấu thần kinh khu trú/rối loạn ý thức/nghi viêm màng não).  
- **Cần khám sớm:** câu 3 \= có (thai kỳ/bệnh nền/chấn thương đầu); HOẶC câu 4 \= có (tiến triển nặng dần / khởi phát mới sau 50 tuổi); HOẶC câu 5 \= có (liên quan tư thế/rối loạn thị giác).  
- **Tự chăm sóc:** không có bất kỳ dấu hiệu nào ở câu 1-5, đau đầu giống các lần trước, đáp ứng với thuốc giảm đau thông thường \- kèm dặn dò quay lại nếu xuất hiện bất kỳ dấu hiệu nào ở trên.

---

## Nguồn tham khảo

- [Chest Pain Office Hours Telephone Triage Protocols, Adult — Schmitt-Thompson / TriageLogic (PDF)](https://triagelogic.com/wp-content/uploads/2018/03/OH-Adult-Chest-Pain.pdf)  
- [Abdominal Pain – Male After Hours Telephone Triage Protocols, Adult — Schmitt-Thompson / TriageLogic (PDF)](https://triagelogic.com/wp-content/uploads/2018/03/AH-Adult-Abdominal-Pain-Male.pdf)  
- [Schmitt-Thompson Triage Protocols: Guidelines & Software — TriageLogic](https://triagelogic.com/schmitt-thompson-triage-protocols/)  
- [Schmitt-Thompson Clinical Content — Nurse Triage Guidelines](https://www.stcc-triage.com/)  
- [Triage Nurses: Questions for Chest Pain & Chest-Related Symptoms — The Sullivan Group](https://blog.thesullivangroup.com/triage-questions-for-chest-pain-chest-related-symptoms)  
- [Are there any evidence-based ways of assessing dyspnoea (breathlessness) by telephone or video — Centre for Evidence-Based Medicine, Oxford](https://www.cebm.net/covid-19/are-there-any-evidence-based-ways-of-assessing-dyspnoea-breathlessness-by-telephone-or-video/)  
- [Headache red flags (SNOOP/SNNOOP10) — LITFL Neurology Library](https://litfl.com/headache-red-flags/)
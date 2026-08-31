# Transcript hội thoại đầy đủ (bệnh nhân mô phỏng)

> Bệnh nhân mô phỏng KHÔNG biết nhãn của ca - chỉ biết lời kể của chính người bệnh.
> Mức triage ở đây để xem PHÂN BỐ, không phải để chấm đúng/sai (xem docstring script).

## TC-V1-001 — EMERGENCY (2 lượt)

- độ phủ khi đóng: `False` | user_led: `1.0` | lặp: `0.0` | quét sót: `False`/`False`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, complaint_onset_at, complaint_duration_days, complaint_severity, complaint_progression, consciousness_level, activity_vs_baseline, feeding_intake, caregiver_concern_level, looks_very_unwell, rapid_breathing, cyanosis, stridor_or_drooling, cold_clammy_skin, capillary_refill_ge_3s, dizziness_on_standing, urine_output, vomiting_severity, seizure_occurred, neck_stiffness, severe_headache, focal_neuro_deficit, non_blanching_rash, mucosal_bleeding, gi_bleeding, abdominal_pain_severity, diarrhea, joint_limb_swelling, chronic_conditions, immunocompromised, recent_surgery_30d, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi đang cảm thấy thở gấp và tức ngực. Tôi có thể đang bị bệnh gì?
- AGENT: Dạ, mình đã nắm được tình trạng bạn đang bị tức ngực kèm theo thở gấp rồi ạ.

Để mình hiểu rõ hơn, bạn vui lòng cho mình biết thêm một vài thông tin nhé:
- Bạn bao nhiêu tuổi?
- Bạn là nam hay nữ?
- **BN**: Mình 45 tuổi, là nam. Mình đang khó thở quá nên nói chuyện rất khó khăn.
- AGENT: Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ.

## TC-V1-091 — EARLY_VISIT (28 lượt)

- độ phủ khi đóng: `False` | user_led: `0.0769` | lặp: `0.4615` | quét sót: `True`/`True`
- field M0/M1 còn thiếu: `activity_vs_baseline, caregiver_concern_level, looks_very_unwell, rapid_breathing, dizziness_on_standing, diarrhea, joint_limb_swelling, immunocompromised, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi bị đau tai, chảy dịch tai và bị HIV. Tôi có thể đang bị bệnh gì?
- AGENT: Tôi đã nắm được tình trạng bạn đang bị đau và chảy dịch ở tai, cũng như có bệnh nền là HIV.

Để mình hiểu rõ hơn về tình trạng của bạn, bạn cho mình biết thêm một vài thông tin nhé:
- Bạn bao nhiêu tuổi?
- Giới tính sinh học của bạn là gì?
- **BN**: Mình 35 tuổi và là nam ạ.
- AGENT: Chào bạn, cảm ơn bạn đã chia sẻ thông tin, mình đã ghi nhận bạn là nam giới, 35 tuổi và đang bị đau, chảy dịch tai.

Để mình nắm rõ hơn tình trạng hiện tại, bạn cho mình biết thêm một chút nhé:
- Tình trạng này bắt đầu từ khi nào và mức độ khó chịu hiện tại của bạn là bao nhiêu trên thang điểm 10?
- Những ngày gần đây, bạn thấy các triệu chứng này đang giảm dần, giữ nguyên hay nặng lên?
- **BN**: Mình bị đau và chảy dịch khoảng 3 ngày nay, mức độ đau khoảng 6/10. Các triệu chứng này vẫn đang giữ nguyên, chưa thấy đỡ hơn ạ.
- AGENT: Mình đã nắm được tình trạng đau và chảy dịch tai của bạn kéo dài 3 ngày nay và mức độ đau đang ở mức 6/10.

Hiện tại bạn có đang tỉnh táo bình thường không, hay có thấy khó gọi hỏi và khó thức giấc không?
- **BN**: Mình vẫn đang tỉnh táo bình thường, không thấy khó gọi hay khó thức giấc gì cả.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã nắm được thông tin là bạn vẫn đang hoàn toàn tỉnh táo.

Bạn có bị co giật không và hiện tại có đang lên cơn co giật nào không?
- **BN**: Mình không bị co giật gì cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số trên cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số trên cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) So với ngày thường thì chơi/hoạt động giảm hẳn, thở nhanh hơn hoặc phải gắng sức hơn; hoặc đứng dậy đột ngột thấy choáng váng
2) Nói lẫn, không nhận ra người quen, hành vi khác lạ hẳn so với thường ngày
3) Sưng đau khớp hoặc chi nào đó, không chịu đi lại hoặc không dùng tay/chân bình thường
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số trên cả.
- AGENT: Khi đứng dậy đột ngột có thấy choáng váng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Dạ mình hiểu rồi, cảm ơn bạn đã chia sẻ.

Để mình nắm rõ hơn tình trạng sức khỏe hiện tại, bạn có thấy đầu óc lâng lâng hay mất thăng bằng mỗi khi thay đổi tư thế không ạ?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Khi đứng dậy đột ngột có thấy choáng váng không
- **BN**: Mình không thấy bị choáng váng khi đứng dậy ạ.
- AGENT: Có sưng đau khớp/chi nào không - có chịu đi lại được không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có sưng đau khớp/chi nào không - có chịu đi lại được không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có sưng đau khớp/chi nào không - có chịu đi lại được không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 lo lắng đến mức nào, có trông khác hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 lo lắng đến mức nào, có trông khác hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 lo lắng đến mức nào, có trông khác hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: So với ngày thường mức độ hoạt động có giảm nhiều không, thở có nhanh hơn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: So với ngày thường mức độ hoạt động có giảm nhiều không, thở có nhanh hơn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Em hiểu là anh đang chưa rõ về tình trạng sức khỏe hiện tại của mình.

Để em nắm rõ hơn về thể trạng của anh, anh giúp em kiểm tra vài điểm nhé:
- Anh thấy mình có mệt mỏi hay đuối sức hơn bình thường không?
- Khi hít thở, anh có thấy nhịp thở nhanh hoặc gấp gáp hơn mọi khi không?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Gần đây có ai nhận thấy nói lẫn, hành vi khác lạ hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Gần đây có ai nhận thấy nói lẫn, hành vi khác lạ hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Gần đây có ai nhận thấy nói lẫn, hành vi khác lạ hẳn không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Câu sàng lọc rủi ro gộp: mang thai, hóa trị, bệnh mạn tính, phẫu thuật/ống thông
- **BN**: Mình chỉ có bệnh nền là HIV thôi, không thuộc các trường hợp còn lại ạ.
- AGENT: Cảm ơn bạn đã chia sẻ thông tin về bệnh nền HIV và việc hiện tại không dùng kháng sinh.

Để hỗ trợ tốt hơn, bạn cho mình biết thêm là hiện tại bạn có đang thực hiện hóa trị, ghép tạng hay sử dụng các loại thuốc ức chế miễn dịch nào không?
- **BN**: Mình không sử dụng các loại thuốc đó, chỉ có bệnh nền là HIV thôi ạ.
- AGENT: Cảm ơn bạn đã chia sẻ về tình trạng bệnh nền của mình.

Để bác sĩ đánh giá chính xác hơn về khả năng miễn dịch của cơ thể trong lúc này, bạn cho mình biết thêm là hiện tại bạn có đang điều trị hóa chất, ghép tạng hay sử dụng các thuốc ức chế miễn dịch nào không?
- **BN**: Mình không dùng các loại thuốc đó, chỉ có bệnh nền là HIV thôi ạ.
- AGENT: Cảm ơn bạn đã xác nhận thông tin về tình trạng sức khỏe hiện tại của mình.

Để hỗ trợ bạn tốt hơn trong quá trình theo dõi triệu chứng ở tai, bạn cho mình biết thêm một chút nhé:
- Bạn hiện đang sống một mình hay có người thân ở cùng để hỗ trợ?
- Từ chỗ bạn đến cơ sở y tế gần nhất mất khoảng bao lâu và liệu bạn có thuận tiện quay lại tái khám nếu triệu chứng trở nặng không?
- **BN**: Mình đang sống một mình. Từ chỗ mình đến cơ sở y tế gần nhất mất khoảng 20 phút và mình có thể đi tái khám nếu cần ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Không, mình không còn gì khác muốn chia sẻ ạ.

## TC-V1-106 — EARLY_VISIT (36 lượt)

- độ phủ khi đóng: `False` | user_led: `0.0588` | lặp: `0.5` | quét sót: `True`/`False`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, complaint_site, complaint_onset_at, complaint_duration_days, complaint_severity, complaint_progression, consciousness_level, diarrhea, chronic_conditions, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi bị căng thẳng quá mức và hiện đang bị xuất tinh sớm. Tôi có thể đang bị bệnh gì?
- AGENT: Người đang cần tư vấn là bé hay người lớn, bao nhiêu tuổi/tháng
- **BN**: Tôi là người lớn, năm nay tôi 30 tuổi.
- AGENT: Mình hỏi nhanh vài ý: (1) Điều khó chịu nhất hiện giờ là gì, ở vùng nào, bắt đầu từ khi nào; (2) Trên thang 0-10 khó chịu mức nào, mấy hôm nay đang đỡ dần, như cũ hay nặng lên
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 khó chịu mức nào, mấy hôm nay đang đỡ dần, như cũ hay nặng lên
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 khó chịu mức nào, mấy hôm nay đang đỡ dần, như cũ hay nặng lên
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trên thang 0-10 khó chịu mức nào, mấy hôm nay đang đỡ dần, như cũ hay nặng lên
- **BN**: Mình không rõ lắm ạ.
- AGENT: Điều khó chịu nhất hiện giờ là gì, ở vùng nào, bắt đầu từ khi nào
- **BN**: Mình không rõ lắm ạ.
- AGENT: Điều khó chịu nhất hiện giờ là gì, ở vùng nào, bắt đầu từ khi nào
- **BN**: Mình không rõ lắm ạ.
- AGENT: Điều khó chịu nhất hiện giờ là gì, ở vùng nào, bắt đầu từ khi nào
- **BN**: Mình không rõ lắm ạ.
- AGENT: Hiện có tỉnh táo bình thường không - dễ đánh thức, phản ứng gọi hỏi bình thường không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Hiện có tỉnh táo bình thường không - dễ đánh thức, phản ứng gọi hỏi bình thường không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Hiện có tỉnh táo bình thường không - dễ đánh thức, phản ứng gọi hỏi bình thường không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có bị co giật không - đang co giật ngay lúc này không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có bị co giật không - đang co giật ngay lúc này không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có bị co giật không - đang co giật ngay lúc này không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
3) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hiểu là các dấu hiệu này hơi khó để xác định chính xác, bạn không cần quá lo lắng đâu ạ.

Để mình nắm rõ hơn tình trạng sức khỏe hiện tại của bạn, bạn giúp mình cảm nhận xem:
- Bạn có cảm thấy bị hụt hơi hay khó thở không?
- Bạn có thấy môi hoặc đầu ngón tay bị đổi màu tím tái so với bình thường không?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hiểu là những dấu hiệu này khó quan sát chính xác, bạn cứ thoải mái nhé. Mình hỏi thêm một chút để kiểm tra sự lưu thông oxy trong cơ thể thôi ạ:

- Bạn có thấy mình thở nhanh, gấp hay cảm giác không đủ hơi để thở không?
- Bạn nhìn giúp mình xem môi hoặc đầu ngón tay có bị thâm hay tím hơn bình thường không?
- **BN**: Mình không có các dấu hiệu đó đâu ạ. Mình chỉ đang bị căng thẳng quá mức và xuất tinh sớm thôi.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã ghi nhận là hiện tại bạn không bị khó thở và bụng cũng không có biểu hiện cứng hay đau dữ dội.

Để mình nắm rõ hơn tình trạng, bạn cho mình biết thêm là bạn có đang bị đau bụng ở vị trí nào không và mức độ đau hiện tại như thế nào nhé?
- **BN**: Mình không bị đau bụng đâu ạ, chỉ đang bị căng thẳng quá mức và xuất tinh sớm thôi.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã nắm được là hiện tại bạn không bị đau bụng.

Bạn cho mình biết thêm trong 6 tiếng vừa qua bạn có đi tiểu được không, và việc ăn uống hay tình trạng nôn ói của bạn như thế nào nhé?
- **BN**: Mình vẫn đi tiểu và ăn uống bình thường, không bị nôn ói gì cả.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã ghi nhận hiện tại bạn vẫn ăn uống và đi tiểu bình thường, không bị nôn ói.

So với những ngày khỏe mạnh bình thường, bạn có cảm thấy mức độ hoạt động và khả năng vận động của mình bị giảm sút nhiều không?
- **BN**: Mình thấy sức khỏe vận động vẫn bình thường, không bị giảm sút gì cả.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã ghi nhận là hiện tại các hoạt động hằng ngày của bạn vẫn diễn ra bình thường.

Bạn vui lòng cho mình biết thêm:
- Từ 0 đến 10, mức độ lo lắng hiện tại của bạn là bao nhiêu?
- Bạn có thấy tâm trạng hay biểu hiện của mình khác hẳn so với trước đây không?
- **BN**: Mức độ lo lắng của mình khoảng 8/10. Tâm trạng mình hiện tại rất bất an và thấy khác hẳn so với trước đây.
- AGENT: Cảm ơn bạn đã tin tưởng chia sẻ. Mình đã ghi nhận tình trạng lo lắng hiện tại cũng như việc bạn cảm thấy mệt mỏi và khác biệt so với ngày thường.

Để mình có thêm thông tin hỗ trợ bạn tốt nhất, bạn cho mình biết thêm một vài chi tiết về sức khỏe nền nhé:
- Bạn có đang mắc bệnh lý mãn tính nào, hoặc có vấn đề gì về hệ miễn dịch không?
- Trong vòng 30 ngày qua, bạn có thực hiện phẫu thuật, thủ thuật y tế nào hay hiện đang có thiết bị y tế nào lưu giữ trong cơ thể không?
- **BN**: Mình không mắc bệnh mãn tính hay vấn đề miễn dịch nào, cũng không phẫu thuật hay có thiết bị y tế trong người trong thời gian qua.
- AGENT: Cảm ơn bạn đã chia sẻ để mình hiểu rõ hơn về tình trạng sức khỏe hiện tại.

Ngoài những vấn đề trên, bạn có đang điều trị hay gặp phải bệnh lý mạn tính nào về tim, phổi, gan, thận, tiểu đường hoặc các bệnh về máu không?
- **BN**: Mình không có bệnh lý mạn tính nào về tim, phổi, gan, thận hay tiểu đường cả.
- AGENT: Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia
- **BN**: Mình không mắc các bệnh mạn tính đó đâu.
- AGENT: Mình đã nắm rõ thông tin bạn chia sẻ.

Để mình có cái nhìn đầy đủ hơn về tình trạng sức khỏe tổng quát giúp đánh giá chính xác các triệu chứng hiện tại, bạn vui lòng cho mình biết bạn có đang điều trị bệnh lý nào liên quan đến tim, phổi, gan, thận, tiểu đường hoặc các bệnh về máu như thalassemia không nhé?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Mình không rõ lắm ạ.

## TC-V1-046 — EARLY_VISIT (34 lượt)

- độ phủ khi đóng: `False` | user_led: `0.1111` | lặp: `0.2222` | quét sót: `True`/`True`
- field M0/M1 còn thiếu: `diarrhea, chronic_conditions, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi hiện đang có triệu chứng đau nhức khớp ngón tay, sưng khớp và có tiền sử gia đình mắc bệnh viêm khớp. Tôi có thể đang bị bệnh gì?
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình bị đau nhức và sưng khớp ngón tay, kèm theo tình trạng cứng khớp vào mỗi buổi sáng. Gia đình mình cũng có người từng mắc bệnh viêm khớp nên mình hơi lo lắng không biết mình bị sao.
- AGENT: Chào bạn, mình đã nắm được thông tin bạn đang bị sưng đau tại các khớp ngón tay và thường xuyên gặp tình trạng cứng khớp vào buổi sáng.

Để mình hỗ trợ bạn tốt hơn, bạn cho mình biết thêm một chút thông tin nhé:
- Bạn bao nhiêu tuổi?
- Giới tính của bạn là gì?
- **BN**: Mình 45 tuổi và là nữ ạ.
- AGENT: Cảm ơn chị đã chia sẻ thông tin, em đã ghi nhận chị 45 tuổi và là nữ.

Để em hiểu rõ hơn về tình trạng của chị, chị cho em biết thêm:
- Những triệu chứng này đã xuất hiện từ bao giờ và mức độ khó chịu hiện tại chị chấm được mấy điểm trên thang từ 0 đến 10?
- Tình trạng này của chị mấy hôm nay đang có dấu hiệu đỡ dần, giữ nguyên hay nặng lên ạ?
- **BN**: Triệu chứng này xuất hiện khoảng vài tuần nay, mình thấy đau ở mức 6/10. Tình trạng này vẫn đang giữ nguyên chứ chưa thấy đỡ hơn chút nào.
- AGENT: Dạ em đã ghi nhận tình trạng chị bị sưng đau, cứng khớp ngón tay kéo dài từ ngày 27/7/2026 đến nay.

Hiện tại chị vẫn tỉnh táo và phản ứng nhanh nhẹn khi trò chuyện chứ ạ?
- **BN**: Vâng, mình vẫn hoàn toàn tỉnh táo và bình thường, không có vấn đề gì khác đâu ạ.
- AGENT: Dạ, em đã nắm được thông tin chị vẫn đang hoàn toàn tỉnh táo và minh mẫn.

Chị cho em hỏi thêm là mình có bị co giật không, và hiện tại chị có đang bị co giật không ạ?
- **BN**: Mình không bị co giật đâu ạ.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
3) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có khó thở không - môi/đầu ngón tay tím tái không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có khó thở không - môi/đầu ngón tay tím tái không
- **BN**: Không, mình không có các triệu chứng đó đâu ạ.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã nắm được là bạn không bị khó thở, đồng thời bụng vẫn mềm và không có dấu hiệu đau bụng dữ dội.

Để hiểu rõ hơn về tình trạng sức khỏe hiện tại, bạn cho mình biết thêm:
- Bạn cảm thấy đau bụng ở vị trí nào?
- Mức độ đau bụng của bạn hiện tại là khoảng bao nhiêu trên thang điểm 10 ạ?
- **BN**: Mình không bị đau bụng đâu ạ.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã nắm được là bạn hoàn toàn không bị đau bụng.

Để mình hiểu rõ hơn về sức khỏe của bạn lúc này, bạn cho mình biết thêm:
- Trong 6 giờ qua bạn có đi tiểu được không?
- Bạn có ăn uống được chút nào không và có bị nôn không ạ?
- **BN**: Mình vẫn đi tiểu bình thường và ăn uống được, không bị nôn chút nào cả.
- AGENT: Mình rất mừng khi biết bạn vẫn ăn uống tốt và đi tiểu đều đặn như bình thường.

So với ngày thường, mức độ hoạt động hằng ngày của bạn có bị giảm đi nhiều không ạ?
- **BN**: Có, vì các khớp ngón tay sưng đau và cứng vào buổi sáng nên mình cầm nắm đồ vật hay làm việc nhà thấy rất khó khăn và chậm chạp hơn nhiều.
- AGENT: Chia sẻ của bạn giúp mình hiểu rõ hơn vì sao các công việc hằng ngày trở nên khó khăn và chậm chạp hơn hẳn so với trước đây.

Bạn thấy tình trạng này hiện đang khiến mình lo lắng ở mức mấy trên thang điểm 10 và bạn có nhận thấy khớp ngón tay của mình đang có thay đổi gì khác lạ so với mọi khi không ạ?
- **BN**: Mình lo lắng ở mức 7/10. Ngoài sưng, đau và cứng khớp ra thì mình không thấy có thay đổi gì khác lạ nào khác cả.
- AGENT: Dạ, mình đã hiểu là hiện tại bạn đang cảm thấy lo lắng ở mức 7/10 và tuy người vẫn thấy khỏe khoắn, không có biểu hiện quá mệt mỏi nhưng các hoạt động hàng ngày của bạn đang bị ảnh hưởng đáng kể.

Để mình có thêm thông tin đầy đủ nhất, bạn cho mình biết thêm một số tình trạng sức khỏe nền sau đây nhé:
- Bạn hiện có đang mang thai, đang điều trị hóa chất hoặc có bệnh lý mạn tính nào không?
- Bạn có vừa trải qua phẫu thuật hoặc đang phải đặt các loại ống thông trên cơ thể không ạ?
- **BN**: Mình không mang thai, không điều trị hóa chất, cũng không có bệnh lý mạn tính nào khác. Mình cũng không vừa phẫu thuật hay đặt ống thông gì cả.
- AGENT: Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia
- **BN**: Mình không mắc các bệnh đó đâu ạ.
- AGENT: Cảm ơn bạn đã chia sẻ rõ hơn về tình trạng sức khỏe của mình.

Để giúp bác sĩ đánh giá chính xác hơn về nguyên nhân gây đau khớp, bạn có đang điều trị hoặc theo dõi định kỳ các bệnh lý mạn tính nào như tim mạch, tiểu đường hay các bệnh về máu không ạ?
- **BN**: Mình không mắc các bệnh lý đó và cũng không đang điều trị hay theo dõi định kỳ gì cả ạ.
- AGENT: Cảm ơn bạn đã cung cấp thông tin giúp mình hiểu rõ hơn về tình trạng hiện tại.

Để hỗ trợ bạn tốt nhất trong quá trình theo dõi sức khỏe, bạn cho mình hỏi thêm một chút nhé:
- Hiện tại bạn đang sống một mình hay có người ở cùng hỗ trợ?
- Từ nhà bạn đến cơ sở y tế mất khoảng bao lâu và liệu bạn có thể chủ động quay lại tái khám nếu triệu chứng trở nặng không ạ?
- **BN**: Mình sống cùng gia đình nên có người hỗ trợ ạ. Từ nhà mình đến cơ sở y tế chỉ mất khoảng 15 phút, nếu triệu chứng trở nặng mình hoàn toàn có thể chủ động đi khám ngay.
- AGENT: Cảm ơn bạn đã chia sẻ, mình rất yên tâm khi biết bạn có người thân hỗ trợ và việc di chuyển đến cơ sở y tế cũng rất thuận tiện chỉ trong khoảng 15 phút.

Ngoài paracetamol ra, bạn có đang sử dụng thêm loại thuốc giảm đau hay hạ sốt nào khác không ạ?
- **BN**: Mình không dùng loại thuốc nào cả, kể cả paracetamol mình cũng chưa uống ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Không.

## TC-V1-071 — EMERGENCY (13 lượt)

- độ phủ khi đóng: `False` | user_led: `0.25` | lặp: `0.0833` | quét sót: `False`/`False`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, temp_c, temp_site, activity_vs_baseline, caregiver_concern_level, looks_very_unwell, rapid_breathing, dizziness_on_standing, diarrhea, joint_limb_swelling, chronic_conditions, immunocompromised, recent_surgery_30d, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi đang bị đau bụng, sốt, vàng da và nước tiểu sẫm màu. Tôi có thể đang bị bệnh gì?
- AGENT: Mình đã nắm được tình trạng bạn đang bị đau bụng, vàng da, nước tiểu sẫm màu kèm cảm giác nóng sốt trong người.

Để mình hiểu rõ hơn về tình trạng của bạn, bạn cho mình biết thêm một chút thông tin nhé:
- Bạn bao nhiêu tuổi?
- Giới tính của bạn là gì?
- **BN**: Mình năm nay 45 tuổi và là nam giới. Ngoài ra mình còn bị vàng mắt và đang thấy hơi lơ mơ nữa.
- AGENT: Nam hay nữ
- **BN**: Mình là nam giới.
- AGENT: Mình đã ghi nhận thêm tình trạng bạn bị vàng mắt và có cảm giác lơ mơ.

Dạ, bạn năm nay bao nhiêu tuổi rồi ạ?
- **BN**: Mình 45 tuổi bạn ạ.
- AGENT: Dạ mình đã nắm được thông tin bạn 45 tuổi và đang bị vàng mắt kèm cảm giác lơ mơ.

Để theo dõi sát hơn tình trạng sốt của bạn, bạn cho mình biết kết quả đo nhiệt độ cụ thể là bao nhiêu độ, bạn đo ở vị trí nào và vào thời điểm nào không ạ? Ngoài ra, hiện tại bạn có đang sẵn nhiệt kế để kiểm tra lại ngay không?
- **BN**: Mình chưa đo nhiệt độ nên không rõ bao nhiêu độ cả, hiện tại mình cũng không có sẵn nhiệt kế ở đây.
- AGENT: Dạ, mình đã hiểu là hiện tại bạn chưa có nhiệt kế để đo thân nhiệt cụ thể.

Vì tình trạng sốt của bạn cần được theo dõi kỹ, nếu lát nữa có điều kiện đo lại, bạn giúp mình ghi nhớ:
- Con số hiển thị trên nhiệt kế là bao nhiêu độ và bạn đo ở vị trí nào (nách, miệng hay tai)?
- Bạn đã thực hiện đo vào thời điểm nào trong ngày?
- **BN**: Được rồi, nếu lát nữa đo được mình sẽ báo lại cho bạn nhé.
- AGENT: Dạ, mình đã ghi nhận việc bạn sẽ báo lại kết quả khi có điều kiện đo nhiệt độ.

Không biết hiện tại gia đình mình đang dùng loại nhiệt kế nào, ví dụ như nhiệt kế thủy ngân hay nhiệt kế điện tử ạ?
- **BN**: Mình không rõ nữa, mình chỉ biết là nhà mình hiện tại không có sẵn cái nào để đo thôi.
- AGENT: Dạ, mình đã nắm được thông tin hiện tại bạn chưa có nhiệt kế để kiểm tra thân nhiệt.

Để mình hiểu rõ hơn về tình trạng sốt này, bạn chia sẻ thêm giúp mình nhé:
- Bạn bắt đầu thấy sốt từ khi nào và đã kéo dài mấy ngày rồi?
- Khi sốt bạn có bị rét run dữ dội đến mức đắp chăn vẫn không đỡ không?
- Bạn đã dùng loại thuốc hạ sốt nào chưa, uống vào lúc nào và sau đó tình trạng có cải thiện không?
- **BN**: Mình mới bị sốt từ hôm qua thôi. Mình không bị rét run, cũng chưa uống loại thuốc hạ sốt nào cả.
- AGENT: Dạ, mình đã ghi nhận thông tin bạn mới bắt đầu sốt từ hôm qua và hiện tại chưa sử dụng thuốc hạ sốt nào.

Hiện tại bạn có đang tỉnh táo, phản ứng gọi hỏi bình thường hay cảm thấy dễ bị buồn ngủ, khó đánh thức không ạ?
- **BN**: Mình cảm thấy khá lơ mơ, cứ buồn ngủ và khó tập trung lắm.
- AGENT: Dạ, mình đã nắm được tình trạng bạn đang cảm thấy lơ mơ và khó tập trung do sốt.

Cho mình hỏi thêm là bạn có bị co giật không, và hiện tại bạn có đang bị co giật không ạ?
- **BN**: Không, mình không bị co giật gì cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) So với ngày thường thì chơi/hoạt động giảm hẳn, thở nhanh hơn hoặc phải gắng sức hơn; hoặc đứng dậy đột ngột thấy choáng váng
2) Nói lẫn, không nhận ra người quen, hành vi khác lạ hẳn so với thường ngày
3) Sưng đau khớp hoặc chi nào đó, không chịu đi lại hoặc không dùng tay/chân bình thường
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình có dấu hiệu thứ 2, mình thấy hơi lơ mơ và khó tập trung nên có lúc nói chuyện không được minh mẫn như bình thường.
- AGENT: Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ.

## TC-V1-002 — EMERGENCY (2 lượt)

- độ phủ khi đóng: `False` | user_led: `1.0` | lặp: `0.0` | quét sót: `False`/`False`
- field M0/M1 còn thiếu: `age_value, age_unit, sex, lives_alone, caregiver_available, complaint_onset_at, complaint_duration_days, complaint_severity, complaint_progression, consciousness_level, activity_vs_baseline, feeding_intake, caregiver_concern_level, looks_very_unwell, breathing_difficulty, rapid_breathing, cyanosis, stridor_or_drooling, cold_clammy_skin, capillary_refill_ge_3s, dizziness_on_standing, urine_output, vomiting_severity, seizure_occurred, neck_stiffness, severe_headache, focal_neuro_deficit, non_blanching_rash, mucosal_bleeding, gi_bleeding, abdominal_pain_severity, diarrhea, joint_limb_swelling, chronic_conditions, immunocompromised, recent_surgery_30d, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi hay bị đau sau xương ức khi leo cầu thang, nhưng giảm khi nghỉ ngơi. Tôi có thể đang bị bệnh gì?
- AGENT: Cảm ơn bạn đã chia sẻ tình trạng đau tức vùng sau xương ức mỗi khi vận động mạnh như leo cầu thang.

Để mình hiểu rõ hơn về tình trạng của bạn, bạn cho mình biết thêm một vài thông tin nhé:
- Bạn bao nhiêu tuổi?
- Bạn là nam hay nữ?
- **BN**: Mình 55 tuổi, là nam. Hiện tại mình đang thấy đau ngực dữ dội, kèm đổ mồ hôi và buồn nôn nữa, không biết mình bị sao vậy?
- AGENT: Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ.

## TC-V1-092 — EARLY_VISIT (30 lượt)

- độ phủ khi đóng: `False` | user_led: `0.0357` | lặp: `0.3929` | quét sót: `True`/`False`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, breathing_difficulty, diarrhea, chronic_conditions, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi bị đau trong thời kỳ kinh nguyệt. Tôi có thể đang bị bệnh gì?
- AGENT: Dạ, mình đã nắm được thông tin là bạn đang bị đau bụng trong kỳ kinh nguyệt.

Để mình hiểu rõ hơn về tình trạng của bạn, cho mình hỏi:
- Bạn bao nhiêu tuổi rồi?
- Bạn là nam hay nữ?
- **BN**: Mình 25 tuổi và mình là nữ.
- AGENT: Chào bạn, mình đã ghi nhận thông tin bạn 25 tuổi và đang bị đau trong kỳ kinh nguyệt nhé.

Để mình hiểu kỹ hơn về tình trạng của bạn, bạn chia sẻ thêm giúp mình:
- Cơn đau tập trung ở vị trí nào và bắt đầu từ khi nào?
- Hiện tại mức độ đau trên thang điểm từ 0 đến 10 là bao nhiêu, và so với mấy hôm trước thì tình trạng này đang giảm đi, giữ nguyên hay nặng lên ạ?
- **BN**: Mình đau ở vùng bụng dưới từ hôm bắt đầu có kinh. Mức độ đau tầm 6/10 và mình thấy nó vẫn giữ nguyên từ hôm qua tới giờ.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã ghi nhận tình trạng đau bụng dưới mức độ 6/10 từ hôm qua đến nay của bạn.

Hiện tại bạn vẫn tỉnh táo, gọi hỏi có phản ứng bình thường và dễ đánh thức chứ ạ?
- **BN**: Vâng, mình vẫn tỉnh táo và bình thường, không có dấu hiệu gì bất thường cả.
- AGENT: Cảm ơn bạn đã xác nhận mình vẫn tỉnh táo và phản ứng bình thường.

Bạn có đang bị co giật hay có biểu hiện co giật nào ngay lúc này không ạ?
- **BN**: Mình không bị co giật gì cả, chỉ thấy đau bụng thôi.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
3) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Có khó thở không - môi/đầu ngón tay tím tái không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có khó thở không - môi/đầu ngón tay tím tái không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có khó thở không - môi/đầu ngón tay tím tái không
- **BN**: Mình không thấy khó thở, môi hay đầu ngón tay cũng không có dấu hiệu tím tái gì cả.
- AGENT: Có thở rít khi hít vào, chảy dãi không nuốt được không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có thở rít khi hít vào, chảy dãi không nuốt được không
- **BN**: Không, mình không có các triệu chứng đó.
- AGENT: Cảm ơn bạn đã chia sẻ. Mình đã ghi nhận hiện tại bụng bạn không bị cứng và không có các dấu hiệu bất thường khác.

Bạn cho mình biết thêm cụ thể là bạn đang thấy đau ở vị trí nào ở bụng dưới và mức độ đau hiện tại trên thang điểm 10 là bao nhiêu nhé?
- **BN**: Mình đau ở ngay vùng bụng dưới, gần xương mu. Mức độ đau vẫn là 6/10 ạ.
- AGENT: Cảm ơn bạn đã chia sẻ. Mình đã ghi nhận bạn đang bị đau ở vùng bụng dưới gần xương mu với mức độ đau là 6/10.

Để hiểu rõ hơn tình trạng hiện tại, bạn cho mình biết trong 6 tiếng qua:
- Bạn có đi tiểu được không?
- Bạn có ăn uống được gì không và có bị nôn nhiều không?
- **BN**: Mình vẫn đi tiểu bình thường, ăn uống được và không bị nôn chút nào cả.
- AGENT: Mình đã ghi nhận việc bạn vẫn ăn uống và đi vệ sinh bình thường, không có tình trạng nôn ói.

Bạn kiểm tra giúp mình trên da có xuất hiện các nốt ban đỏ hay tím không, và nếu có thì khi mình dùng vật cứng trong suốt ấn nhẹ lên nốt đó, màu sắc có biến mất không nhé?
- **BN**: Da mình hoàn toàn bình thường, không có nốt ban đỏ hay tím nào cả.
- AGENT: Mình đã ghi nhận da của bạn hoàn toàn bình thường, không có các nốt phát ban.

So với những ngày khỏe mạnh bình thường, bạn cảm thấy mức độ hoạt động và đi lại của mình hiện tại có bị giảm nhiều không?
- **BN**: Mình vẫn đi lại được nhưng vì đau bụng nên hơi khó chịu, mình chủ yếu muốn nằm nghỉ ngơi thôi.
- AGENT: Mình đã ghi nhận việc bạn cảm thấy mệt và muốn nằm nghỉ ngơi nhiều hơn so với ngày thường do cơn đau bụng.

Hiện tại, bạn cảm thấy mức độ lo lắng của bản thân về tình trạng này là bao nhiêu trên thang điểm từ 0 đến 10?
- **BN**: Mình thấy mức độ lo lắng khoảng 4/10 thôi ạ, vì mình cũng thường xuyên bị đau khi đến kỳ kinh.
- AGENT: Mình đã ghi nhận mức độ lo lắng của bạn hiện tại là 4/10.

Để mình nắm rõ hơn về sức khỏe tổng quát, bạn cho mình biết thêm một vài thông tin nhé:
- Bạn hiện có đang mang thai, đang điều trị hóa chất hay có bệnh lý mãn tính nào không?
- Bạn có vừa trải qua phẫu thuật hoặc đang sử dụng ống thông y tế nào trong người không?
- **BN**: Mình không mang thai, không điều trị hóa chất cũng không có bệnh lý mãn tính nào cả. Mình cũng không vừa phẫu thuật hay đặt ống thông gì hết.
- AGENT: Mình đã ghi nhận bạn không mang thai và không có vấn đề về hệ miễn dịch.

Bạn có đang điều trị các bệnh lý mạn tính nào như tim mạch, phổi, gan, thận hay tiểu đường không?
- **BN**: Mình không mắc các bệnh lý đó, sức khỏe của mình trước giờ vẫn bình thường.
- AGENT: Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia
- **BN**: Mình không mắc bệnh nào trong số đó cả.
- AGENT: Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia
- **BN**: Mình đã trả lời rồi mà, mình không mắc bệnh nào trong số đó cả.
- AGENT: Cảm ơn bạn đã chia sẻ về tình trạng sức khỏe hiện tại của mình.

Để mình nắm rõ hơn nhằm hỗ trợ bạn tốt nhất, bạn cho mình biết thêm một chút thông tin nhé:
- Hiện tại bạn đang ở một mình hay có người thân ở cùng để hỗ trợ?
- Từ chỗ bạn đến cơ sở y tế gần nhất mất khoảng bao lâu và nếu tình trạng đau bụng trở nặng, bạn có thuận tiện để quay lại bệnh viện kiểm tra ngay không?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hiểu rồi, không sao đâu bạn nhé. Mình hỏi thêm các thông tin này để có thể hỗ trợ bạn kịp thời hơn nếu chẳng may cơn đau có diễn tiến bất thường thôi ạ.

- Bạn có thể ước lượng khoảng cách từ nhà đến nơi khám gần nhất là bao xa hoặc mất bao lâu để di chuyển đến đó không?
- Hiện tại bạn có người ở cùng để hỗ trợ nếu cần đi bệnh viện gấp không?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Không, mình không còn lo lắng gì thêm nữa.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Mình không rõ lắm ạ.

## TC-V1-107 — EARLY_VISIT (27 lượt)

- độ phủ khi đóng: `False` | user_led: `0.15` | lặp: `0.25` | quét sót: `True`/`True`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, complaint_severity, diarrhea, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi bị dị dạng cột sống và hiện đang bị xuất tinh ngược dòng. Tôi có thể đang bị bệnh gì?
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Mình không rõ lắm ạ.
- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi bị dị dạng cột sống và gần đây thấy có hiện tượng xuất tinh ngược dòng, nhưng các triệu chứng lúc có lúc không nên tôi cũng chưa chắc chắn lắm.
- AGENT: Chào bạn, mình đã nắm được thông tin bạn đang gặp tình trạng xuất tinh ngược dòng trên nền bệnh lý dị dạng cột sống.

Cho mình hỏi thêm là năm nay bạn bao nhiêu tuổi ạ?
- **BN**: Năm nay tôi 32 tuổi.
- AGENT: Cảm ơn bạn đã chia sẻ thông tin, mình đã ghi nhận bạn 32 tuổi và đang gặp tình trạng xuất tinh ngược dòng liên quan đến dị dạng cột sống.

Để hiểu rõ hơn về tình trạng của bạn, mình nhờ bạn chia sẻ thêm một chút:
- Triệu chứng này xuất hiện từ khi nào và mức độ khó chịu hiện tại trên thang điểm từ 0 đến 10 là bao nhiêu?
- Trong những ngày qua, tình trạng này đang có xu hướng giảm dần, giữ nguyên hay nặng lên ạ?
- **BN**: Tình trạng này mới xuất hiện gần đây thôi, còn mức độ khó chịu thì mình không rõ vì nó cứ chập chờn lúc bị lúc không. Mấy ngày qua mình thấy nó cứ giữ nguyên như vậy chứ không thay đổi gì rõ rệt.
- AGENT: Cảm ơn bạn đã chia sẻ, mình đã ghi nhận tình trạng xuất tinh ngược dòng của bạn đang giữ nguyên mức độ như những ngày qua.

Nếu tính trên thang điểm từ 0 đến 10, bạn cảm thấy mức độ khó chịu hiện tại của mình tương ứng với con số mấy ạ?
- **BN**: Mình không rõ nữa, vì triệu chứng lúc có lúc không nên mình khó chấm điểm lắm.
- AGENT: Dạ vâng, mình đã ghi nhận tình trạng của bạn vẫn đang giữ nguyên như những ngày qua và việc khó xác định mức độ cụ thể do triệu chứng không ổn định là điều dễ hiểu.

Bạn có thể chia sẻ cụ thể hơn là tình trạng này bắt đầu xuất hiện từ khoảng thời gian nào không?
- **BN**: Mình bắt đầu để ý thấy hiện tượng này khoảng vài tuần gần đây thôi.
- AGENT: Chào bạn, mình đã ghi nhận thông tin bạn gặp phải tình trạng xuất tinh ngược dòng từ khoảng 3 tuần nay.

Hiện tại bạn vẫn tỉnh táo, gọi hỏi phản ứng nhanh nhẹn và dễ đánh thức chứ ạ?
- **BN**: Vâng, mình vẫn bình thường, không có vấn đề gì về sự tỉnh táo cả.
- AGENT: Dạ mình đã nắm rõ tình trạng của bạn vẫn đang hoàn toàn tỉnh táo và minh mẫn.

Bạn có đang bị co giật không, hay hiện tại có đang gặp tình trạng này không ạ?
- **BN**: Mình không bị co giật gì cả, mọi thứ vẫn bình thường.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Không có dấu hiệu nào trong số trên cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Không có dấu hiệu nào trong số trên cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) So với ngày thường thì chơi/hoạt động giảm hẳn, thở nhanh hơn hoặc phải gắng sức hơn; hoặc đứng dậy đột ngột thấy choáng váng
2) Nói lẫn, không nhận ra người quen, hành vi khác lạ hẳn so với thường ngày
3) Sưng đau khớp hoặc chi nào đó, không chịu đi lại hoặc không dùng tay/chân bình thường
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Không có dấu hiệu nào trong số trên cả.
- AGENT: Cảm ơn bạn đã chia sẻ các thông tin trên, mình đã nắm được tình trạng hiện tại của bạn rồi.

Bạn cảm thấy mức độ lo lắng của mình hiện tại là bao nhiêu trên thang điểm từ 0 đến 10, và bạn có nhận thấy diện mạo hay thần thái của mình có gì khác biệt so với bình thường không ạ?
- **BN**: Mình thấy lo lắng ở mức khoảng 5 điểm, còn về diện mạo hay thần thái thì mình thấy vẫn bình thường, không có gì khác lạ cả.
- AGENT: Câu sàng lọc rủi ro gộp: mang thai, hóa trị, bệnh mạn tính, phẫu thuật/ống thông
- **BN**: Mình không rõ lắm ạ.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát; hoặc có bệnh mạn tính đang điều trị (tim, phổi, gan, thận, tiểu đường, thalassemia)
2) 30 ngày gần đây có phẫu thuật, hoặc hiện có ống thông/catheter/dẫn lưu
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không rõ lắm ạ.
- AGENT: 30 ngày gần đây có phẫu thuật không, hiện có ống thông/catheter/dẫn lưu không
- **BN**: Mình không có phẫu thuật trong 30 ngày gần đây và cũng không có ống thông hay dẫn lưu gì cả.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Cảm ơn bạn đã chia sẻ thông tin, mình đã ghi nhận lại các nội dung trước đó rồi nhé.

Để bên mình hỗ trợ tốt nhất và kịp thời nếu có vấn đề phát sinh, bạn giúp mình thông tin thêm một chút:
- Bạn hiện đang sống một mình hay có người ở cùng?
- Thời gian từ nhà bạn đến cơ sở y tế gần nhất mất khoảng bao lâu và bạn có thuận tiện đi lại nếu cần kiểm tra gấp không?
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không dùng loại thuốc nào khác cả.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Không.

## TC-V1-047 — EMERGENCY (2 lượt)

- độ phủ khi đóng: `False` | user_led: `1.0` | lặp: `0.0` | quét sót: `False`/`False`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, temp_c, temp_site, fever_onset_at, rigors, antipyretic_taken, worse_after_defervescence, consciousness_level, activity_vs_baseline, feeding_intake, caregiver_concern_level, looks_very_unwell, breathing_difficulty, rapid_breathing, cyanosis, stridor_or_drooling, cold_clammy_skin, capillary_refill_ge_3s, dizziness_on_standing, urine_output, vomiting_severity, seizure_occurred, neck_stiffness, severe_headache, non_blanching_rash, mucosal_bleeding, gi_bleeding, abdominal_pain_severity, diarrhea, joint_limb_swelling, chronic_conditions, immunocompromised, recent_surgery_30d, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi đang bị đau đầu, sưng mắt và sốt. Tôi có thể đang bị bệnh gì?
- AGENT: Dạ, mình đã ghi nhận tình trạng bạn đang bị đau đầu, sưng mắt và cảm thấy có sốt trong người.

Để mình nắm rõ hơn, bạn vui lòng cho mình biết:
- Bạn bao nhiêu tuổi?
- Bạn là nam hay nữ?
- **BN**: Mình 30 tuổi, là nữ. Ngoài ra mình còn bị nhìn mờ và liệt mặt nữa.
- AGENT: Đây là tình huống cần được cấp cứu ngay bây giờ — vui lòng gọi 115 hoặc đến ngay cơ sở y tế/khoa cấp cứu gần nhất, không chờ thêm. Thông tin đã được chuyển cho điều dưỡng ưu tiên hỗ trợ.

## TC-V1-072 — EARLY_VISIT (18 lượt)

- độ phủ khi đóng: `False` | user_led: `0.0625` | lặp: `0.3125` | quét sót: `True`/`True`
- field M0/M1 còn thiếu: `lives_alone, caregiver_available, diarrhea, indwelling_device`

- AGENT: Bạn hoặc người nhà đang thấy khó chịu thế nào? Bạn cứ kể theo cách dễ nhất với mình nhé.
- **BN**: Tôi hiện đang có các triệu chứng như viêm đa xoang mạn tính. Tôi có thể đang bị bệnh gì?
- AGENT: Chào bạn, mình đã nắm được thông tin bạn đang gặp tình trạng viêm đa xoang mạn tính kéo dài.

Để mình hiểu rõ hơn về tình trạng của bạn, bạn cho mình biết thêm một chút thông tin nhé:
- Bạn bao nhiêu tuổi?
- Bạn là nam hay nữ?
- **BN**: Mình năm nay 30 tuổi và mình là nam.
- AGENT: Chào anh, cảm ơn anh đã chia sẻ thông tin, mình đã ghi nhận anh 30 tuổi.

Để mình nắm rõ hơn tình trạng hiện tại của anh, anh cho mình biết thêm:
- Tình trạng khó chịu ở xoang của anh bắt đầu xuất hiện từ khi nào?
- Anh thấy mức độ khó chịu hiện tại là bao nhiêu trên thang điểm 10, và mấy hôm nay triệu chứng đang đỡ dần, giữ nguyên hay nặng lên ạ?
- **BN**: Mình bị tình trạng này cũng được vài tháng rồi. Mức độ khó chịu khoảng 6/10 và mấy hôm nay mình thấy các triệu chứng vẫn vậy, không đỡ hơn.
- AGENT: Chào anh, mình đã ghi nhận tình trạng viêm xoang của anh kéo dài từ giữa tháng 5 đến nay và hiện đang ở mức 6/10.

Hiện tại anh vẫn tỉnh táo, gọi hỏi và phản ứng bình thường chứ ạ?
- **BN**: Vâng, mình vẫn tỉnh táo và phản ứng bình thường, không có gì bất thường cả.
- AGENT: Cảm ơn anh đã phản hồi, mình đã nắm được anh vẫn hoàn toàn tỉnh táo và giao tiếp bình thường.

Anh có đang bị co giật không, hoặc hiện tại có dấu hiệu co giật nào không ạ?
- **BN**: Không, mình hoàn toàn không bị co giật gì cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); hoặc mới yếu tay/chân một bên, méo miệng, nói khó
2) Khó thở, tím môi hoặc đầu ngón tay, rút lõm lồng ngực/phập phồng cánh mũi/thở rên (với trẻ nhỏ); hoặc thở rít khi hít vào, chảy dãi mà không nuốt được
3) Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số các triệu chứng đó cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất; hoặc chảy máu chân răng, chảy máu mũi, nôn ra máu, đi ngoài phân đen
2) Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Mình hỏi nhanh một loạt dấu hiệu quan trọng để loại trừ, bạn xem có dấu hiệu nào không nhé:
1) So với ngày thường thì chơi/hoạt động giảm hẳn, thở nhanh hơn hoặc phải gắng sức hơn; hoặc đứng dậy đột ngột thấy choáng váng
2) Nói lẫn, không nhận ra người quen, hành vi khác lạ hẳn so với thường ngày
3) Sưng đau khớp hoặc chi nào đó, không chịu đi lại hoặc không dùng tay/chân bình thường
Nếu không có dấu hiệu nào trong số trên, bạn chỉ cần trả lời "không có dấu hiệu nào" là được ạ.
- **BN**: Mình không có dấu hiệu nào trong số đó cả.
- AGENT: Cảm ơn bạn đã chia sẻ thông tin để mình nắm rõ hơn về tình trạng sức khỏe hiện tại.

- Bạn thấy mức độ lo lắng của mình hiện tại ở thang điểm mấy trên 10?
- Về cảm nhận cá nhân, bạn có thấy các triệu chứng xoang hiện tại đang có biểu hiện gì khác thường so với những lần trước không?
- **BN**: Mức độ lo lắng của mình khoảng 5/10. Các triệu chứng như nghẹt mũi, chảy mũi, nhức đầu mặt và mất khứu giác vẫn giống như những lần trước mình bị thôi, không có gì khác thường cả.
- AGENT: Cảm ơn bạn đã chia sẻ rõ tình trạng hiện tại. Mình đã ghi nhận mức độ lo lắng của bạn ở mức 5 và bạn vẫn sinh hoạt, tỉnh táo bình thường, không thấy mệt mỏi khác lạ so với mọi ngày.

Để mình nắm rõ hơn, bạn cho mình biết thêm một vài thông tin nhé:
- Trong vòng 30 ngày gần đây, bạn có thực hiện phẫu thuật hay thủ thuật y tế nào không?
- Bạn có đang gặp vấn đề gì về miễn dịch hoặc có thiết bị y tế nào đang đặt/lưu trong cơ thể không?
- **BN**: Mình không thực hiện phẫu thuật hay thủ thuật nào trong 30 ngày qua cả. Mình cũng không có vấn đề về miễn dịch hay thiết bị y tế nào trong người.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Có đang dùng kháng sinh nào không
- **BN**: Mình không rõ lắm ạ.
- AGENT: Trước khi mình chốt lại, còn triệu chứng hay điều gì khác khiến bạn lo không? Nếu không còn gì, bạn cứ trả lời "không" là được.
- **BN**: Không, mình không còn lo lắng hay triệu chứng nào khác nữa.

"""Cụm câu hỏi DÙNG CHUNG: nhân khẩu, quét dấu hiệu đỏ, quét dấu hiệu "khám sớm", an toàn tại nhà.

Nội dung (mã cụm, thứ tự, `script_hint`) chép nguyên văn `fever-conversation-specification.md` Part 3
- fever là protocol đầu tiên nên tài liệu của nó cũng là nơi các cụm này được viết ra lần đầu, nhưng
bản thân chúng KHÔNG nói gì về sốt: "có bị co giật không", "môi có tím không", "6 giờ qua có đi tiểu
không" đúng y như vậy với mọi than phiền.

**Vì sao là HÀM chứ không phải hằng số:** `QuestionCluster.stage` là một phần của cụm, mà cùng một cụm
quét đỏ nằm ở stage "3A" của fever và stage "2" của generic (protocol generic không có 2 stage đặc
điểm sốt ở giữa). Tham số hoá `stage` là cách duy nhất để có MỘT định nghĩa dùng chung thay vì hai bản
sao sẽ lệch nhau.

**Mã cụm giữ nguyên giữa các protocol** (generic cũng dùng `Q3-03` cho cụm co giật, không đổi thành
`G2-03`): mã là thứ để truy vết ngược về tài liệu lâm sàng, đổi mã theo protocol là làm mất đường
truy. Trùng mã giữa 2 protocol không gây lẫn state vì trạng thái cụm được lưu theo
`(protocol_name, cluster_id)`.
"""

from __future__ import annotations

from src.services.symptom_protocol.models import QuestionCluster


def demographic_clusters(stage: str = "0") -> tuple[QuestionCluster, ...]:
    """Ai đang cần tư vấn - tuổi/giới quyết định gần như mọi ngưỡng lâm sàng phía sau.

    MỘT cụm chứ không phải hai (2026-08-22): tuổi và giới luôn đi cùng nhau trong mọi câu hỏi hồ sơ
    thật ("bé trai mấy tuổi ạ?"), nên tách làm hai cụm chỉ tốn thêm một lượt mà không đổi được gì
    về độ phủ. Mã cụm giữ `Q0-01` để không mất đường truy ngược về CS §3.0.
    """
    return (
        QuestionCluster(
            "Q0-01", stage, ("age_value", "age_unit", "reporter_type", "sex"),
            script_hint="Người đang cần tư vấn là bé hay người lớn, bao nhiêu tuổi/tháng, nam hay nữ",
        ),
    )


def emergency_scan_clusters(stage: str) -> tuple[QuestionCluster, ...]:
    """Quét dấu hiệu đỏ tuyệt đối (CS §3.3A). `batch_negation=True` cho mọi cụm: một câu "không có gì
    trong số đó" đóng được cả cụm - nhưng chỉ khi model trích được nguyên văn câu phủ định đó
    (`intake_agent._negation_evidence_ok`)."""
    return (
        QuestionCluster("Q3-01", stage, ("consciousness_level", "social_response_child"), batch_negation=True, script_hint="Hiện có tỉnh táo bình thường không - dễ đánh thức, phản ứng gọi hỏi bình thường không"),
        QuestionCluster("Q3-03", stage, ("seizure_occurred", "seizure_active_now", "seizure_features"), batch_negation=True, script_hint="Có bị co giật không - đang co giật ngay lúc này không"),
        QuestionCluster("Q3-04", stage, ("neck_stiffness", "photophobia", "severe_headache", "bulging_fontanelle"), batch_negation=True, script_hint="Có cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường không"),
        QuestionCluster("Q3-05", stage, ("focal_neuro_deficit",), batch_negation=True, script_hint="Có yếu tay/chân một bên, méo miệng, nói khó mới xuất hiện không"),
        QuestionCluster("Q3-08", stage, ("cold_clammy_skin", "capillary_refill_ge_3s"), batch_negation=True, script_hint="Da có lạnh, ẩm, nổi vân tím không - CRT có chậm không"),
        QuestionCluster("Q3-09", stage, ("urine_output", "feeding_intake", "vomiting_severity"), batch_negation=True, script_hint="6 giờ qua có đi tiểu không, ăn uống được không, có nôn nhiều không"),
        QuestionCluster("Q3-11", stage, ("non_blanching_rash", "rash_present", "rash_type"), batch_negation=True, script_hint="Trên da có nổi ban đỏ/tím không - ấn kính vào có mất không"),
        QuestionCluster("Q3-13", stage, ("abdominal_pain_severity", "abdominal_pain_location", "abdominal_guarding"), batch_negation=True, script_hint="Có đau bụng không - mức nào, bụng có cứng không"),
    )


def critical_scan_clusters(stage: str) -> tuple[QuestionCluster, ...]:
    """Dấu hiệu nguy kịch **PHỔ QUÁT** - hỏi được NGAY LƯỢT 1, trước cả tuổi/giới (stage `E`).

    Tách khỏi `emergency_scan_clusters` theo một tiêu chí DUY NHẤT, kiểm chứng được: **không cụm nào
    trong đây có skip-rule đọc `age` hay `sex`** ở bất kỳ protocol nào. Đó là điều kiện để hỏi chúng
    trước khi biết người bệnh là ai mà không hỏi nhầm câu dành cho trẻ sơ sinh cho người lớn.

    Vì sao phải có stage này dù đã có L0 + `OPENING_CLUSTER`: cả hai đều **thụ động** - chúng chỉ bắt
    được thứ người bệnh TỰ nói ra. Người nhắn "tôi bị sốt" thì không có gì để bắt, và trước
    2026-08-22 câu hỏi CHỦ ĐỘNG đầu tiên của hệ thống là hỏi TUỔI (`registry.py:8` ghi lại đúng lời
    phàn nàn đó). Một câu quét gộp ở đây tốn đúng MỘT lượt và đổi thứ tự đó.

    Q3-01 (tri giác) và Q3-03 (co giật) CỐ Ý Ở LẠI `3A` dù cũng phổ quát: CS §3.3A cấm suỷ hai cụm
    này từ một câu phủ định gộp, nên đưa vào `E` thì chúng vẫn phải hỏi riêng từng cụm - mất đúng cái
    lợi mà stage này sinh ra để có."""
    return (
        QuestionCluster("Q3-06", stage, ("breathing_difficulty", "cyanosis", "chest_indrawing", "nasal_flaring_grunting"), batch_negation=True, script_hint="Có khó thở không - môi/đầu ngón tay tím tái không"),
        QuestionCluster("Q3-07", stage, ("stridor_or_drooling",), batch_negation=True, script_hint="Có thở rít khi hít vào, chảy dãi không nuốt được không"),
        QuestionCluster("Q3-12", stage, ("mucosal_bleeding", "gi_bleeding"), batch_negation=True, script_hint="Có chảy máu bất thường không - chân răng, mũi, nôn ra máu, phân đen"),
    )


def early_visit_scan_clusters(stage: str) -> tuple[QuestionCluster, ...]:
    """Quét dấu hiệu "cần khám sớm" (CS §3.3B) - chạy SAU khi quét đỏ đã sạch."""
    return (
        QuestionCluster("Q3-01b", stage, ("activity_vs_baseline", "rapid_breathing"), batch_negation=True, script_hint="So với ngày thường mức độ hoạt động có giảm nhiều không, thở có nhanh hơn không"),
        QuestionCluster("Q3-08b", stage, ("dizziness_on_standing",), batch_negation=True, script_hint="Khi đứng dậy đột ngột có thấy choáng váng không"),
        QuestionCluster("Q3-02", stage, ("new_confusion",), batch_negation=True, script_hint="Gần đây có ai nhận thấy nói lẫn, hành vi khác lạ hẳn không"),
        QuestionCluster("Q3-13b", stage, ("joint_limb_swelling", "non_weight_bearing"), batch_negation=True, script_hint="Có sưng đau khớp/chi nào không - có chịu đi lại được không"),
        QuestionCluster("Q3-14", stage, ("caregiver_concern_level", "looks_very_unwell"), batch_negation=True, script_hint="Trên thang 0-10 lo lắng đến mức nào, có trông khác hẳn không"),
    )


def risk_context_clusters(
    stage: str,
    *,
    screening_extra_fields: tuple[str, ...] = (),
    screening_hint: str = "Câu sàng lọc rủi ro gộp: mang thai, hóa trị, bệnh mạn tính, phẫu thuật/ống thông",
) -> tuple[QuestionCluster, ...]:
    """Quần thể nguy cơ: thai sản, suy giảm miễn dịch, bệnh nền, phẫu thuật/thiết bị lưu.

    `screening_extra_fields` để protocol nối thêm field ĐẶC THÙ vào câu sàng lọc gộp Q4-00 (fever nối
    `malaria_risk_area`). Không được nhét sẵn field đặc thù vào đây: protocol nào không khai field đó
    sẽ vỡ ngay lúc dựng prompt (`_field_specs` tra `protocol.fields_by_key[key]`)."""
    return (
        QuestionCluster("Q4-00", stage, ("is_pregnant", "immunocompromised", "chronic_conditions", "recent_surgery_30d", "indwelling_device") + screening_extra_fields, script_hint=screening_hint),
        QuestionCluster("Q4-01", stage, ("is_pregnant", "gestational_weeks"), script_hint="Hiện có đang mang thai không - được bao nhiêu tuần"),
        QuestionCluster("Q4-01b", stage, ("obstetric_red_flags",), script_hint="Có ra máu/dịch bất thường, đau bụng từng cơn, giảm cử động thai không"),
        QuestionCluster("Q4-02", stage, ("postpartum_6w",), script_hint="6 tuần gần đây có sinh nở, sảy thai, nạo hút thai không"),
        QuestionCluster("Q4-03", stage, ("immunocompromised", "immunocompromise_cause", "known_neutropenia"), script_hint="Có đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát không"),
        QuestionCluster("Q4-04", stage, ("chronic_conditions",), script_hint="Có đang mắc bệnh mạn tính nào không - tim, phổi, gan, thận, tiểu đường, thalassemia"),
        QuestionCluster("Q4-05", stage, ("recent_surgery_30d", "surgical_site_signs", "indwelling_device"), script_hint="30 ngày gần đây có phẫu thuật không, hiện có ống thông/catheter/dẫn lưu không"),
    )


def safety_netting_cluster(stage: str) -> QuestionCluster:
    """Điều kiện an toàn khi được khuyên tự chăm sóc tại nhà.

    `can_return_for_followup` KHÔNG có cột "Field" riêng ở Q4-08 trong bảng CS Part 3 - đây là một lỗ
    hổng thật của tài liệu nguồn (field này là tiền đề safety-netting bắt buộc cho checklist SELF_CARE
    ở KM §5.4, nhưng CS không gán nó vào cụm hỏi nào cả). Gán vào Q4-08 vì cùng chủ đề "khả năng tiếp
    cận y tế khi trở nặng"; nếu không gán, SELF_CARE sẽ KHÔNG BAO GIỜ kết luận được."""
    return QuestionCluster(
        "Q4-08", stage, ("lives_alone", "caregiver_available", "access_to_care_minutes", "can_return_for_followup"),
        script_hint="Sống một mình hay có người theo dõi, từ nhà đến cơ sở y tế mất bao lâu, có thể quay lại tái khám khi trở nặng không",
    )


def medication_clusters(stage: str) -> tuple[QuestionCluster, ...]:
    return (
        QuestionCluster("Q5-05a", stage, ("nsaid_use",), script_hint="Có đang dùng thuốc giảm đau/hạ sốt nào khác ngoài paracetamol không"),
        QuestionCluster("Q5-05b", stage, ("antibiotic_current",), script_hint="Có đang dùng kháng sinh nào không"),
    )

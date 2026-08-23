"""Nhóm sàng lọc DÙNG CHUNG cho các cụm quét đỏ / quét "khám sớm" (`clusters.py`).

Cùng lý do tồn tại như `clusters.py`: các cụm này không nói gì về SỐT ("có bị co giật không", "môi có
tím không") nên cách GỘP chúng thành nhóm cơ quan cũng vậy. Để định nghĩa nhóm trong
`fever_protocol.py` là lặp lại đúng lỗi phân tầng mà lần tách `common_safety` vừa sửa: protocol thứ
hai sẽ phải import từ fever (sai chiều) hoặc chép lại (hai bản sao sẽ lệch).

**Vì sao là HÀM theo `stage`:** giống `emergency_scan_clusters`, cùng bộ cụm ấy nằm ở stage "3A" của
fever và stage "2" của generic, mà `ScreeningGroup.stage` là một phần của nhóm.

**Hai cụm cố ý ĐỨNG NGOÀI mọi nhóm** - Q3-01 (tri giác) và Q3-03 (co giật). CS §3.3A cấm suy diễn hai
cụm này từ một câu phủ định gộp: chúng là hai dấu hiệu tiên lượng mạnh nhất của toàn thang triage, và
người nhà thường không tự nhận ra "lơ mơ" hay "cơn giật ngắn" nếu không được hỏi thẳng. Vì chúng đứng
đầu thứ tự tài liệu, `next_cluster` trả chúng ra trước và `screening.next_probe` tự loại lượt sàng lọc
ở đó - không cần luật đặc biệt nào.

`probe_hint` được đọc NGUYÊN VĂN cho người bệnh (`screening.probe_question` ghép tĩnh, không qua LLM)
nên viết như lời nói, không phải như tên field.
"""

from __future__ import annotations

from src.services.symptom_protocol.models import ScreeningGroup


def critical_scan_groups(stage: str) -> tuple[ScreeningGroup, ...]:
    """MỘT nhóm cho `clusters.critical_scan_clusters(stage)` - câu quét cấp cứu ở LƯỢT 1 (stage `E`).

    Một nhóm chứ không phải ba: cả stage `E` phải đóng được bằng MỘT chữ "không", nếu không thì
    nó chỉ dời ba lượt từ `3A` lên đầu chứ không rút ngắn được gì.

    `probe_hint` được đọc NGUYÊN VĂN cho người bệnh (`screening.probe_question` ghép TĨNH, không qua
    LLM) - và đây là danh sách dấu hiệu nguy kịch, lược mất một ý là mất một cơ hội phát hiện."""
    return (
        ScreeningGroup(
            id="GE-CRIT",
            stage=stage,
            cluster_ids=("Q3-06", "Q3-07", "Q3-12"),
            probe_hint=(
                "Khó thở nặng hoặc tím tái; thở rít/chảy dãi khó nuốt; "
                "hoặc chảy máu không cầm, nôn ra máu hay đi ngoài phân đen"
            ),
            negative_values={"breathing_difficulty": "none"},
        ),
    )


def emergency_scan_groups(stage: str) -> tuple[ScreeningGroup, ...]:
    """Nhóm cho `clusters.emergency_scan_clusters(stage)` - trừ Q3-01/Q3-03 (xem docstring module)."""
    return (
        ScreeningGroup(
            id="G3A-NEURO",
            stage=stage,
            cluster_ids=("Q3-04", "Q3-05"),
            probe_hint=(
                "Cứng gáy, sợ ánh sáng, đau đầu dữ dội khác thường, thóp phồng (với trẻ nhỏ); "
                "hoặc mới yếu tay/chân một bên, méo miệng, nói khó"
            ),
        ),
        ScreeningGroup(
            id="G3A-CIRC",
            stage=stage,
            cluster_ids=("Q3-08", "Q3-09"),
            probe_hint=(
                "Da lạnh, ẩm, nổi vân tím, ấn đầu ngón tay hồng trở lại chậm; "
                "hoặc 6 giờ qua không đi tiểu, không ăn uống được, nôn nhiều không giữ được nước"
            ),
            negative_values={
                "urine_output": "normal",
                "feeding_intake": "normal",
                "vomiting_severity": "none",
            },
        ),
        ScreeningGroup(
            id="G3A-BLEED",
            stage=stage,
            cluster_ids=("Q3-11",),
            probe_hint="Nổi ban đỏ hoặc tím trên da, ấn kính vào không mất",
        ),
        ScreeningGroup(
            id="G3A-ABDO",
            stage=stage,
            cluster_ids=("Q3-13",),
            probe_hint="Đau bụng nhiều đến mức không cử động được, hoặc bụng cứng khi ấn vào",
            negative_values={"abdominal_pain_severity": "none"},
        ),
    )


def risk_context_groups(stage: str) -> tuple[ScreeningGroup, ...]:
    """Nhóm cho `clusters.risk_context_clusters(stage)` - quần thể nguy cơ (Stage 4 của fever).

    Vì sao stage này CẦN nhóm dù đã có cụm gộp `Q4-00`: `Q4-00` chỉ là một cụm thường, nên câu "không
    có gì cả" chỉ đóng đúng `Q4-00`. `Q4-03`/`Q4-05` vẫn bị hỏi tiếp vì các field CON của chúng
    (`immunocompromise_cause`, `known_neutropenia`, `surgical_site_signs`) còn `unknown` - đo được là
    nút thắt thật của ca lành tính (~7-8 lượt cho một stage mà mọi câu trả lời đều là "không").
    `field_dependencies` vá được phần field con; nhóm sàng lọc ở đây vá phần còn lại và cho phép đóng
    cả stage bằng MỘT câu.

    `Q4-00` cố ý KHÔNG nằm trong nhóm nào: nó chính là câu hỏi gộp của stage này, đưa vào nhóm nghĩa
    là câu sàng lọc đọc lại nguyên văn nội dung của chính nó. `Q4-06`/`Q4-07` (dịch tễ) và `Q4-08`
    (điều kiện an toàn khi tự chăm sóc tại nhà) cũng đứng ngoài - chúng hỏi bối cảnh, không hỏi dấu
    hiệu để phủ định, và `Q4-08` là tiền đề bắt buộc của checklist SELF_CARE nên phải hỏi thẳng.
    """
    return (
        ScreeningGroup(
            id="G4-OBST",
            stage=stage,
            cluster_ids=("Q4-01", "Q4-01b", "Q4-02"),
            probe_hint=(
                "Đang mang thai, hoặc 6 tuần gần đây có sinh nở/sảy thai/nạo hút thai"
            ),
        ),
        ScreeningGroup(
            id="G4-IMMUNO",
            stage=stage,
            cluster_ids=("Q4-03", "Q4-04"),
            probe_hint=(
                "Đang hóa trị, ghép tạng, dùng thuốc ức chế miễn dịch, HIV không kiểm soát; "
                "hoặc có bệnh mạn tính đang điều trị (tim, phổi, gan, thận, tiểu đường, thalassemia)"
            ),
            negative_values={"chronic_conditions": "none"},
        ),
        ScreeningGroup(
            id="G4-SURG",
            stage=stage,
            cluster_ids=("Q4-05",),
            probe_hint="30 ngày gần đây có phẫu thuật, hoặc hiện có ống thông/catheter/dẫn lưu",
            negative_values={"indwelling_device": "none"},
        ),
    )


def early_visit_scan_groups(stage: str) -> tuple[ScreeningGroup, ...]:
    """Nhóm cho `clusters.early_visit_scan_clusters(stage)`.

    Q3-14 đứng ngoài: nó hỏi mức lo lắng trên thang 0-10 và cảm nhận "trông khác hẳn" - không phủ định
    gộp được một CON SỐ, và theo CS §3.3B đây là câu "gut-check" cuối cùng, phải hỏi thẳng."""
    return (
        ScreeningGroup(
            id="G3B-FUNC",
            stage=stage,
            cluster_ids=("Q3-01b", "Q3-08b"),
            probe_hint=(
                "So với ngày thường thì chơi/hoạt động giảm hẳn, thở nhanh hơn hoặc phải gắng sức hơn; "
                "hoặc đứng dậy đột ngột thấy choáng váng"
            ),
            negative_values={"activity_vs_baseline": "normal"},
        ),
        ScreeningGroup(
            id="G3B-COG",
            stage=stage,
            cluster_ids=("Q3-02",),
            probe_hint="Nói lẫn, không nhận ra người quen, hành vi khác lạ hẳn so với thường ngày",
        ),
        ScreeningGroup(
            id="G3B-MSK",
            stage=stage,
            cluster_ids=("Q3-13b",),
            probe_hint="Sưng đau khớp hoặc chi nào đó, không chịu đi lại hoặc không dùng tay/chân bình thường",
        ),
    )

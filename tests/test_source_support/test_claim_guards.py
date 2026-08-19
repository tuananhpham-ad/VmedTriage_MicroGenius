"""Guard 0 - lớp duy nhất kiểm *claim ↔ quyết định gốc*. Không tốn một lời gọi API nào.

Đặc tả gốc để việc bắt lỗi này cho MỘT BÀI TEST TAY ("ca dị ứng da", mục Cách kiểm chứng #6), trong
khi chính nó đặt chuẩn "kiểm bằng code, không bằng prompt" cho bốn guard còn lại. File này biến bài
test tay đó thành assert chạy tự động.

Ca dùng làm mốc là ca khó nhất của thiết kế post-hoc: lập luận gốc dựa trên việc VẮNG MẶT dấu hiệu
("không khó thở, mặt không sưng"). Nếu bước tách claim lật nó thành mệnh đề đảo ("khó thở là dấu hiệu
cảnh báo phản vệ") thì mọi lớp guard phía sau đều xanh - đoạn trích NHS thật sự khẳng định mệnh đề
đảo đó - và output trích NHS chống lưng cho một lập luận NHS không hề nói.

`test_polarity_guard_catches_flipped_claim` là bài quan trọng nhất trong cả gói. Nó trượt nghĩa là
tầng trích nguồn đã mất lớp bảo vệ duy nhất chống lại lỗi im lặng đó.
"""

from __future__ import annotations

import pytest

from src.source_support.claims import ClaimGuardError, guard_grounded_in, guard_polarity
from src.source_support.schemas import Claim

# --- Ca dị ứng da: nhãn kham_som, lập luận dựa trên dấu hiệu VẮNG MẶT ---------------------------

ALLERGY_DECISION = {
    "decision_summary": (
        "Bệnh nhân nổi mẩn đỏ ngứa khắp người sau khi uống kháng sinh 2 ngày. "
        "Không thấy khó thở, mặt không sưng, nên chưa có dấu hiệu phản vệ cần cấp cứu ngay; "
        "tuy nhiên cần khám sớm để đánh giá dị ứng thuốc."
    ),
    "uncertainty_summary": "Chưa rõ loại kháng sinh đã dùng.",
    "evidence": [
        {"concept": "skin_redness", "status": "present", "source_span": "nổi mẩn đỏ khắp người"},
        {"concept": "itching", "status": "present", "source_span": "ngứa"},
        {"concept": "dyspnea", "status": "absent", "source_span": "Không thấy khó thở"},
        {"concept": "swelling", "status": "absent", "source_span": "mặt không sưng"},
    ],
}

_ABSENCE_REASONING = "Không thấy khó thở, mặt không sưng, nên chưa có dấu hiệu phản vệ cần cấp cứu ngay"


def _claim(claim_en: str, kind: str, grounded_in: str) -> Claim:
    return Claim(claim_en=claim_en, claim_vi="(bản tiếng Việt)", claim_kind=kind, grounded_in=grounded_in)


# --- Guard 0b: cực của mệnh đề -----------------------------------------------------------------


def test_polarity_guard_accepts_honest_rule_out() -> None:
    """Nhánh ĐÚNG: claim giữ nguyên chiều suy luận thật, khai `rule_out` -> đi lọt."""
    claims = [
        _claim(
            "Absence of difficulty breathing and facial swelling rules out anaphylaxis in a patient "
            "with a drug-induced rash.",
            "rule_out",
            _ABSENCE_REASONING,
        )
    ]
    guard_polarity(claims, ALLERGY_DECISION["evidence"])


def test_polarity_guard_catches_flipped_claim() -> None:
    """Nhánh TRÔI: cùng lập luận, claim bị lật thành mệnh đề đảo và khai `red_flag`.

    Đây chính là ca mà cả 5 guard của đặc tả gốc đều xanh. Guard 0b chặn được vì nó không đọc nội
    dung claim - nó đối chiếu `grounded_in` với `status` của evidence, thứ model không sửa được."""
    claims = [
        _claim(
            "Difficulty breathing and facial swelling are warning signs of anaphylaxis.",
            "red_flag",
            _ABSENCE_REASONING,
        )
    ]
    with pytest.raises(ClaimGuardError, match="Guard 0b"):
        guard_polarity(claims, ALLERGY_DECISION["evidence"])


@pytest.mark.parametrize("kind", ["red_flag", "temporal", "risk_modifier", "management"])
def test_polarity_guard_rejects_every_non_rule_out_kind(kind: str) -> None:
    """Lập luận chỉ dựa trên dấu hiệu vắng mặt thì MỌI nhãn khác `rule_out` đều bị chặn - cổng không
    chỉ chặn riêng `red_flag`."""
    with pytest.raises(ClaimGuardError, match="Guard 0b"):
        guard_polarity([_claim("X is a warning sign.", kind, _ABSENCE_REASONING)], ALLERGY_DECISION["evidence"])


def test_polarity_guard_allows_mixed_reasoning() -> None:
    """Lập luận nhắc CẢ dấu hiệu có lẫn dấu hiệu không -> không chặn.

    Độ hẹp này là cố ý: "sốt cao kèm co giật, không có ban xuất huyết, cần đánh giá cấp cứu" có mệnh
    đề chính đáng là `red_flag` về sốt và co giật. Bắt nó thành `rule_out` là chặn nhầm, và một guard
    hay chặn nhầm sẽ bị tắt đi. Trường hợp lẫn lộn để Guard 0c ở bước chấm verdict xử lý."""
    decision_evidence = [
        {"concept": "fever", "status": "present", "source_span": "sốt cao"},
        {"concept": "seizure", "status": "present", "source_span": "co giật"},
        {"concept": "petechiae", "status": "absent", "source_span": "không có ban xuất huyết"},
    ]
    reasoning = "sốt cao kèm co giật, không có ban xuất huyết, cần đánh giá cấp cứu"
    guard_polarity([_claim("Fever with seizure needs emergency assessment.", "red_flag", reasoning)], decision_evidence)


def test_polarity_guard_ignores_uncertain_status() -> None:
    """`uncertain` không tính vào phía nào: chưa rõ thì không suy ra được chiều mệnh đề."""
    evidence = [{"concept": "dyspnea", "status": "uncertain", "source_span": "chưa rõ có khó thở không"}]
    guard_polarity([_claim("Dyspnea is a warning sign.", "red_flag", "chưa rõ có khó thở không")], evidence)


# --- Guard 0a: grounded_in phải neo vào lập luận gốc -------------------------------------------


def test_grounded_in_guard_accepts_verbatim_quote() -> None:
    claims = [_claim("...", "rule_out", _ABSENCE_REASONING)]
    guard_grounded_in(claims, ALLERGY_DECISION)


def test_grounded_in_guard_is_whitespace_and_case_insensitive() -> None:
    """Chuẩn hoá bằng `normalise_span` - cùng hàm `llm_decision.py` dùng chặn evidence bịa. Khoảng
    trắng thừa và hoa/thường không được phép làm trượt một trích dẫn đúng."""
    noisy = "  không thấy KHÓ THỞ,   mặt không sưng, nên chưa có dấu hiệu phản vệ cần cấp cứu ngay  "
    guard_grounded_in([_claim("...", "rule_out", noisy)], ALLERGY_DECISION)


def test_grounded_in_guard_catches_invented_reasoning() -> None:
    """Claim bịa ra một lý lẽ quyết định chưa từng đưa -> raise, không phải cảnh báo."""
    invented = "Bệnh nhân có tiền sử sốc phản vệ nên cần theo dõi sát"
    with pytest.raises(ClaimGuardError, match="Guard 0a"):
        guard_grounded_in([_claim("...", "red_flag", invented)], ALLERGY_DECISION)


def test_grounded_in_guard_catches_paraphrase() -> None:
    """Diễn đạt lại cũng bị chặn: cổng đòi trích NGUYÊN VĂN, vì chỉ nguyên văn mới kiểm được bằng code."""
    paraphrase = "Vì không có dấu hiệu hô hấp nào nên chưa cần cấp cứu"
    with pytest.raises(ClaimGuardError, match="Guard 0a"):
        guard_grounded_in([_claim("...", "rule_out", paraphrase)], ALLERGY_DECISION)


def test_grounded_in_guard_accepts_uncertainty_summary() -> None:
    """`uncertainty_summary` cũng là lập luận hợp lệ để neo vào, không chỉ `decision_summary`."""
    guard_grounded_in([_claim("...", "temporal", "Chưa rõ loại kháng sinh đã dùng")], ALLERGY_DECISION)


def test_grounded_in_guard_rejects_empty() -> None:
    with pytest.raises(ClaimGuardError):
        guard_grounded_in([_claim("...", "red_flag", "   ")], ALLERGY_DECISION)

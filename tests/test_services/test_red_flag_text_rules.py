from src.models.schemas import StructuredSymptomData
from src.services.engines.red_flag import RedFlagSafetyLayer
from src.services.engines.red_flag_text_rules import TEXT_RED_FLAG_RULES, detect_text_red_flags

EXPECTED_RULE_COUNT = 103
"""Số rule hiện hành. Bản đầu có 100; `altered_mental_status`, `paracetamol_overdose_pattern` và
`acute_liver_failure_pattern` được thêm ở c969df0 (2026-08-22) mà không cập nhật con số này, nên test
đỏ từ đó tới 2026-08-27.

CỐ Ý VẪN LÀ MỘT CON SỐ CỨNG phải sửa tay. Bộ cụm này là tầng an toàn tất định và mỗi dòng cần được
duyệt lâm sàng - thêm hay bớt một rule PHẢI là hành động có ý thức, không được lẫn vào một commit
khác. Đổi số ở đây mà không kèm lý do trong commit message là đang bỏ qua chính cơ chế đó."""


def test_text_rule_catalog_size_and_codes_are_stable() -> None:
    assert len(TEXT_RED_FLAG_RULES) == EXPECTED_RULE_COUNT
    assert len({rule.code for rule in TEXT_RED_FLAG_RULES}) == EXPECTED_RULE_COUNT


def test_every_rule_carries_at_least_one_phrase() -> None:
    """Rule không có cụm nào thì không bao giờ khớp - nó im lặng biến mất khỏi tầng an toàn."""
    assert [rule.code for rule in TEXT_RED_FLAG_RULES if not rule.phrases] == []


def test_no_phrase_is_shared_between_two_rules() -> None:
    """Một cụm thuộc hai rule làm cả hai cùng bắn, và người đọc log không lần ra được cái nào mới là
    lý do ca bị đẩy lên."""
    seen: dict[str, str] = {}
    for rule in TEXT_RED_FLAG_RULES:
        for phrase in rule.phrases:
            assert phrase not in seen, f"cụm {phrase!r} có ở cả {seen[phrase]!r} và {rule.code!r}"
            seen[phrase] = rule.code


def test_text_rules_match_vietnamese_without_diacritics() -> None:
    findings = detect_text_red_flags("nguoi benh kho tho nang, moi tim tai")
    assert {rule.code for rule, _phrase in findings} >= {"severe_breathing", "cyanosis"}


def test_text_rules_do_not_match_a_non_emergency_statement() -> None:
    assert detect_text_red_flags("Tôi cảm nhẹ, vẫn ăn uống và sinh hoạt bình thường.") == []


def test_main_safety_layer_uses_free_text_rules_before_questionnaire_mapping() -> None:
    findings = RedFlagSafetyLayer().detect(StructuredSymptomData(), "Tôi bị sưng lưỡi và khó thở.")
    assert {finding.code for finding in findings} >= {"tongue_swelling"}

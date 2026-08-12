from src.models.schemas import StructuredSymptomData
from src.services.engines.red_flag import RedFlagSafetyLayer
from src.services.engines.red_flag_text_rules import TEXT_RED_FLAG_RULES, detect_text_red_flags


def test_text_rule_catalog_has_one_hundred_rules() -> None:
    assert len(TEXT_RED_FLAG_RULES) == 100
    assert len({rule.code for rule in TEXT_RED_FLAG_RULES}) == 100


def test_text_rules_match_vietnamese_without_diacritics() -> None:
    findings = detect_text_red_flags("nguoi benh kho tho nang, moi tim tai")
    assert {rule.code for rule, _phrase in findings} >= {"severe_breathing", "cyanosis"}


def test_text_rules_do_not_match_a_non_emergency_statement() -> None:
    assert detect_text_red_flags("Tôi cảm nhẹ, vẫn ăn uống và sinh hoạt bình thường.") == []


def test_main_safety_layer_uses_free_text_rules_before_questionnaire_mapping() -> None:
    findings = RedFlagSafetyLayer().detect(StructuredSymptomData(), "Tôi bị sưng lưỡi và khó thở.")
    assert {finding.code for finding in findings} >= {"tongue_swelling"}

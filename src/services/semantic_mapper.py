from __future__ import annotations

import re

from src.config import get_settings
from src.models.schemas import StructuredSymptomData


class RuleBackedSemanticMapper:
    """Local mapper fallback until the Gemma adapter is wired to production runtime."""

    async def map_message(self, message: str) -> StructuredSymptomData:
        normalized = message.casefold()
        fields: dict[str, object] = {}
        symptom_group = get_settings().default_symptom_group
        confidence = 0.50

        if _contains_any(normalized, ("đau ngực", "dau nguc", "chest pain", "tức ngực")):
            symptom_group = "chest_pain"
            fields["chest_pain"] = True
            confidence += 0.20

        if _contains_any(normalized, ("khó thở", "kho tho", "hụt hơi", "hut hoi", "shortness")):
            fields["shortness_of_breath"] = True
            if symptom_group == "general":
                symptom_group = "breathing"
            confidence += 0.15

        if _contains_any(normalized, ("từ sáng", "tu sang", "this morning")):
            fields["onset"] = "this_morning"
        elif _contains_any(normalized, ("hôm qua", "hom qua", "yesterday")):
            fields["onset"] = "yesterday"
        elif _contains_any(normalized, ("đột ngột", "dot ngot", "sudden")):
            fields["onset"] = "sudden"

        severity = _extract_numeric_severity(normalized)
        if severity is not None:
            fields["pain_severity"] = severity

        if _contains_any(normalized, ("lan tay", "tay trái", "tay trai", "hàm", "ham", "lưng", "lung")):
            fields["pain_radiation"] = True

        if _contains_any(normalized, ("méo miệng", "meo mieng", "lệch mặt", "lech mat")):
            symptom_group = "neurologic"
            fields["face_droop"] = True

        if _contains_any(normalized, ("yếu tay", "yeu tay", "yếu chân", "yeu chan", "liệt", "liet")):
            symptom_group = "neurologic"
            fields["arm_weakness"] = True

        if _contains_any(normalized, ("nói khó", "noi kho", "nói ngọng", "noi ngong", "lú lẫn", "lu lan")):
            symptom_group = "neurologic"
            fields["speech_difficulty"] = True

        if _contains_any(normalized, ("chảy máu", "chay mau", "bleeding")):
            symptom_group = "bleeding"
            fields["bleeding"] = True
            if _contains_any(normalized, ("nhiều", "nhieu", "heavy", "không cầm", "khong cam")):
                fields["bleeding_severity"] = "heavy"

        if _contains_any(normalized, ("co giật", "co giat", "seizure")):
            fields["seizure"] = True

        if _contains_any(normalized, ("ngất", "ngat", "mất ý thức", "mat y thuc", "unconscious")):
            fields["loss_of_consciousness"] = True

        if fields.get("shortness_of_breath") and _contains_any(normalized, ("nặng", "nang", "severe")):
            fields["breathing_severity"] = "severe"

        if _contains_any(normalized, ("đau bụng", "dau bung", "abdominal pain", "đau dạ dày", "dau da day")):
            if symptom_group == "general":
                symptom_group = "abdominal"
            if severity is not None:
                fields["abdominal_pain_severity"] = severity

        if _contains_any(
            normalized,
            ("nôn ra máu", "non ra mau", "đi ngoài phân đen", "di ngoai phan den", "phân đen", "phan den"),
        ):
            if symptom_group == "general":
                symptom_group = "abdominal"
            fields["vomiting_blood"] = True

        if _contains_any(normalized, ("bụng cứng", "bung cung", "gồng cứng", "gong cung", "rigid abdomen")):
            if symptom_group == "general":
                symptom_group = "abdominal"
            fields["rigid_abdomen"] = True

        if _contains_any(normalized, ("sốt", "sot", "fever")):
            if symptom_group == "general":
                symptom_group = "fever"
            if _contains_any(normalized, ("sốt cao", "sot cao", "high fever", "39", "40")):
                fields["fever_severity"] = "high"
            elif _contains_any(normalized, ("sốt nhẹ", "sot nhe", "mild fever")):
                fields["fever_severity"] = "mild"
            elif _contains_any(normalized, ("sốt vừa", "sot vua", "moderate fever")):
                fields["fever_severity"] = "moderate"

        if _contains_any(
            normalized,
            ("cứng cổ", "cung co", "neck stiffness", "đau đầu dữ dội", "dau dau du doi"),
        ):
            fields["neck_stiffness"] = True

        return StructuredSymptomData(
            symptom_group=symptom_group,
            fields=fields,
            confidence=min(confidence, 0.95),
            source="rule_backed_semantic_mapper",
        )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _extract_numeric_severity(value: str) -> int | None:
    match = re.search(r"\b(10|[1-9])\s*/\s*10\b", value)
    if match:
        return int(match.group(1))

    match = re.search(r"\b(10|[1-9])\s*(điểm|diem)\b", value)
    if match:
        return int(match.group(1))

    return None

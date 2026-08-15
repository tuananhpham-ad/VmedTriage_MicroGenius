"""Đính chính lời khai: xoá dây chuyền khi người bệnh rút lại một thông tin, và phát hiện mâu thuẫn
giữa thông tin mới với thông tin cũ. Cơ chế DÙNG CHUNG, không biết field của bệnh nào.

VÌ SAO CẦN: `_merge_answers` cho ghi đè theo từng key nhưng KHÔNG có khái niệm phụ thuộc. Lỗi thật
trong transcript `logs/fever/a421eb5f-...`: người dùng nói "à tôi nhầm, tôi không bị sốt" -
`fever_reported` đổi thành "false" nhưng `temp_c=39`, `fever_onset_at`, `fever_duration_days` vẫn nằm
nguyên trong hồ sơ và vẫn được gửi cho điều dưỡng.

HAI CHIỀU NGƯỢC NHAU, đừng lẫn:

1. `apply_retraction` - giá trị mới PHỦ ĐỊNH giá trị cũ ⇒ xoá các field phụ thuộc về "unknown".
   ("không sốt" ⇒ bỏ nhiệt độ, ngày khởi phát, thuốc hạ sốt...)

2. `find_contradictions` - giá trị mới MÂU THUẪN với giá trị cũ ⇒ KHÔNG xoá gì cả, chỉ mở lại cụm
   gốc để hỏi cho rõ. (đang ghi "không sốt" mà giờ khai "39.2 độ" - không biết cái nào đúng, nên
   phải hỏi, không được tự chọn.)

Chiều 2 là thứ vá được nửa sau của bug C2 (`_guidance/need_to_check_agent.md`): người dùng nói rõ
"39.2 độ, đo ở nách" ba lượt liền mà hệ thống vẫn giữ `fever_status=none`. `apply_retraction` một
mình KHÔNG bắt được ca đó vì nó chỉ so "dương -> âm", còn C2 là "unknown -> âm" ngay từ lượt đầu.
"""

from __future__ import annotations

from src.services.symptom_protocol.protocol import SymptomProtocol
from src.services.symptom_protocol.stage_machine import is_filled

TriState = str

_RETRACTED = "unknown"

# Giá trị được coi là "phủ định field cha". Cố ý HẸP: chỉ giá trị xác định, không có "unknown" -
# người dùng im lặng không phải là rút lại lời khai (cùng nguyên tắc với `_merge_answers`).
_NEGATIVE_VALUES: frozenset[str] = frozenset({"false", "none"})


def _clusters_containing(protocol: SymptomProtocol, keys: frozenset[str]) -> tuple[str, ...]:
    return tuple(cluster.id for cluster in protocol.clusters if keys.intersection(cluster.fields))


def retracted_dependents(
    protocol: SymptomProtocol, before: dict[str, TriState], after: dict[str, TriState],
) -> frozenset[str]:
    """Field nào phải bị xoá vì field cha vừa bị phủ định ở lượt này.

    Chỉ tính field cha ĐỔI GIÁ TRỊ trong lượt này (`before != after`). Nếu tính cả field vốn đã âm
    tính từ trước thì mọi lượt sau đó đều xoá lại đúng nhóm field đó, làm người dùng không bao giờ
    khai bổ sung được."""
    doomed: set[str] = set()
    for parent, dependents in protocol.field_dependencies.items():
        old_value, new_value = before.get(parent), after.get(parent)
        if old_value == new_value:
            continue
        if new_value not in _NEGATIVE_VALUES:
            continue
        doomed.update(key for key in dependents if is_filled(after.get(key)))
    return frozenset(doomed)


def apply_retraction(
    protocol: SymptomProtocol, before: dict[str, TriState], after: dict[str, TriState],
) -> tuple[dict[str, TriState], frozenset[str]]:
    """Xoá field phụ thuộc về "unknown", tính lại field dẫn xuất, trả về `(answers, cụm cần mở lại)`.

    Cụm cần mở lại = cụm có chứa field vừa bị xoá. Caller bỏ chúng khỏi tập "đã hoàn tất" để chúng
    ĐƯỢC PHÉP hỏi lại - còn có thực sự hỏi hay không thì `skip_rule` quyết định (không sốt thì cụm
    đặc điểm sốt vẫn bị skip, nên không hỏi lại vô ích)."""
    doomed = retracted_dependents(protocol, before, after)
    if not doomed:
        return after, frozenset()

    cleaned = {key: (_RETRACTED if key in doomed else value) for key, value in after.items()}
    if protocol.derive_fields is not None:
        # Bắt buộc tính lại: `fever_duration_days` dẫn xuất từ `fever_onset_at` vừa bị xoá, để
        # nguyên thì hồ sơ còn "sốt 2 ngày" trong khi đã ghi nhận là không sốt.
        derived = protocol.derive_fields(cleaned)
        for key, value in (derived or {}).items():
            if key not in doomed or is_filled(value):
                cleaned[key] = value
    return cleaned, frozenset(_clusters_containing(protocol, doomed))


def find_contradictions(
    protocol: SymptomProtocol, answers: dict[str, TriState],
) -> tuple[frozenset[str], tuple[str, ...]]:
    """Mâu thuẫn nội tại trong hồ sơ hiện tại, trả `(field liên quan, cụm cần hỏi lại)`.

    KHÔNG tự sửa giá trị nào: khi hai lời khai chọi nhau, hệ thống không có căn cứ để chọn bên nào -
    việc duy nhất đúng là hỏi lại người bệnh."""
    involved: set[str] = set()
    for detect in protocol.contradiction_rules:
        involved.update(detect(answers) or ())
    if not involved:
        return frozenset(), ()
    return frozenset(involved), _clusters_containing(protocol, frozenset(involved))

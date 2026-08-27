"""Cách câu sàng lọc HIỆN RA trước mặt người bệnh - và ràng buộc an toàn của việc đổi cách đó.

`probe_question` ghép tĩnh, không qua LLM, vì cả cơ chế phủ định gộp dựa trên tiền đề "nhóm chỉ được
đóng khi người bệnh đã THỰC SỰ nhìn thấy danh sách dấu hiệu của nó". Việc tách một `probe_hint` dài
thành nhiều dòng là sửa cách trình bày, nhưng nó chạm đúng vào chuỗi mang tiền đề đó - nên bài test
đắt nhất ở đây không phải bài kiểm định dạng, mà là `test_probe_lines_never_lose_a_signal`: mất một
dấu hiệu ở đây là mất một cơ hội phát hiện ca cấp cứu, và nó sẽ không lộ ra ở bất kỳ chỗ nào khác vì
mọi thứ phía sau vẫn "chạy được" như thường.
"""

from __future__ import annotations

import re

import pytest

from src.services.symptom_protocol import screening
from src.services.symptom_protocol.common_safety.screening_groups import (
    critical_scan_groups,
    emergency_scan_groups,
)
from src.services.symptom_protocol.models import ScreeningGroup

ALL_GROUPS = critical_scan_groups("E") + emergency_scan_groups("3A")


_MARKER = re.compile(r"^(?:\d+\)|-)\s*")
"""Dấu đầu dòng do `probe_lines` gắn thêm. Phải gỡ trước khi so từ - KHÔNG được bỏ chữ số một cách
chung chung, vì có dấu hiệu thật mang số ("6 giờ qua không đi tiểu")."""


def _body(line: str) -> str:
    return _MARKER.sub("", line)


def _words(text: str) -> list[str]:
    """Từ có nghĩa, bỏ dấu câu và các liên từ nối vế mà việc tách dòng cố ý bỏ đi."""
    dropped = {"hoặc", "hay"}
    return [word for word in re.findall(r"\w+", text.casefold()) if word not in dropped]


@pytest.mark.parametrize("group", ALL_GROUPS, ids=[group.id for group in ALL_GROUPS])
def test_probe_lines_never_lose_a_signal(group: ScreeningGroup) -> None:
    """BÀI QUAN TRỌNG NHẤT CỦA MODULE NÀY.

    Mọi từ trong `probe_hint` gốc phải còn nguyên sau khi tách dòng. Kiểm theo TỪ chứ không theo cả
    chuỗi, vì phép tách cố ý bỏ dấu chấm phẩy và liên từ đứng đầu vế - hai thứ không mang dấu hiệu
    lâm sàng nào. Bất cứ thứ gì khác biến mất đều là một dấu hiệu bị nuốt."""
    rendered = " ".join(_body(line) for line in screening.probe_lines((group,)))

    assert _words(rendered) == _words(group.probe_hint)


@pytest.mark.parametrize("group", ALL_GROUPS, ids=[group.id for group in ALL_GROUPS])
def test_every_semicolon_clause_becomes_its_own_line(group: ScreeningGroup) -> None:
    """Đúng ý của việc sửa: không "bê nguyên cả câu" nữa. Mỗi vế ngăn bằng chấm phẩy là một dòng."""
    expected = len([part for part in group.probe_hint.split(";") if part.strip()])

    assert len(screening.probe_lines((group,))) == expected


def test_the_single_group_scan_is_no_longer_a_one_item_numbered_list() -> None:
    """Stage quét cấp cứu cố ý chỉ có MỘT nhóm (`CRITICAL_STAGE_MIN_GROUPS`), nên trước đây nó hiện
    ra thành đúng một dòng "1)" - một danh sách đánh số một mục, tức là một câu bị gắn thừa số thứ tự.
    Ba dấu hiệu của nhóm giờ là ba mục thật."""
    lines = screening.probe_lines(critical_scan_groups("E"))

    assert len(lines) == 3
    assert [line[:2] for line in lines] == ["1)", "2)", "3)"]


def test_a_lone_signal_uses_a_bullet_instead_of_a_number() -> None:
    """Đánh số CÓ ĐIỀU KIỆN. Một mục thì gạch đầu dòng - đánh số một mục là đúng lỗi vừa sửa, chỉ
    dời từ cấp nhóm xuống cấp dấu hiệu."""
    lone = ScreeningGroup(
        id="G-TEST", stage="E", cluster_ids=("Q3-06",), probe_hint="Khó thở nặng hoặc tím tái",
    )

    assert screening.probe_lines((lone,)) == ("- Khó thở nặng hoặc tím tái",)


def test_a_clause_never_starts_with_a_dangling_conjunction() -> None:
    """Vế thứ hai trở đi trong `probe_hint` mở đầu bằng "hoặc" để nối với vế trước. Tách thành dòng
    riêng mà giữ nguyên liên từ thì mỗi dòng đọc lên như một câu cụt."""
    for line in screening.probe_lines(ALL_GROUPS):
        assert not _body(line).casefold().startswith(("hoặc ", "hay ")), line


def test_the_question_still_carries_the_intro_and_the_outro() -> None:
    """Câu chốt "không có dấu hiệu nào" là thứ người bệnh cần để đóng cả nhóm bằng một câu - mất nó
    thì cơ chế phủ định gộp không còn đường vào."""
    question = screening.probe_question(critical_scan_groups("E"))

    assert question.startswith(screening.PROBE_INTRO)
    assert question.endswith(screening.PROBE_OUTRO)

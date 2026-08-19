"""Nhánh red-flag thứ ba (model) và bước đối chiếu (§4.1 + §7.3 mục 1-4).

Bốn ràng buộc của §4.1 viết thành test. Ràng buộc 2 và 4 là hai bài quan trọng nhất - chúng canh
đúng hai đường mà một "cải tiến" về sau có thể lặng lẽ phá:

- nhánh model được phép TRỪ một phát hiện của rule (ràng buộc 2);
- `red_flag_agreement` được đọc để đổi mức ưu tiên (ràng buộc 4).
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import red_flag_branches as branches

RULE_CODE = "RF-07"
MODEL_CODE = "RF-08"


def _finding(code: str) -> branches.ModelFinding:
    return branches.ModelFinding(code=code, evidence="môi tím tái")


# --- §7.3 mục 1-2: hợp nhất bằng OR, model chỉ được THÊM -----------------------------------------


def test_a_flag_only_the_model_caught_still_escalates_and_lands_in_model_only():
    codes, agreement = branches.merge_findings(
        (), (_finding(MODEL_CODE),), model_status=branches.BRANCH_OK,
    )

    assert MODEL_CODE in codes, "hợp nhất bằng OR - một nhánh dương tính là đủ"
    assert agreement.model_only == [MODEL_CODE]


def test_the_model_can_never_turn_off_a_flag_the_rules_raised():
    """§7.3 mục 2 - kể cả khi model khẳng định ngược lại. Đây là hệ quả trực tiếp của bất biến §1
    mục 3, và `merge_findings` cố ý KHÔNG có tham số nào cho phép trừ."""
    codes, agreement = branches.merge_findings(
        (RULE_CODE,), (_finding(MODEL_CODE),), model_status=branches.BRANCH_OK,
    )

    assert RULE_CODE in codes
    assert agreement.rule_only == [RULE_CODE]


def test_deterministic_codes_always_come_first():
    """Phiếu đọc từ trên xuống nên phần có bằng chứng vững nhất phải đứng đầu."""
    codes, _ = branches.merge_findings(
        (RULE_CODE,), (_finding(MODEL_CODE),), model_status=branches.BRANCH_OK,
    )

    assert codes[0] == RULE_CODE


def test_a_flag_both_branches_caught_is_not_double_counted():
    codes, agreement = branches.merge_findings(
        (RULE_CODE,), (_finding(RULE_CODE),), model_status=branches.BRANCH_OK,
    )

    assert codes == (RULE_CODE,)
    assert agreement.both == [RULE_CODE]
    assert agreement.agreement_rate == 1.0


def test_a_clean_case_counts_as_agreement_not_as_disagreement():
    """Không phát hiện nào ở cả hai bên = đồng thuận rằng không có gì. Trả 0.0 ở đây sẽ dìm chỉ số
    xuống mức vô nghĩa, vì ca lành tính là đa số."""
    _, agreement = branches.merge_findings((), (), model_status=branches.BRANCH_OK)

    assert agreement.agreement_rate == 1.0


# --- §7.3 mục 3: lỗi model không được làm mất nhánh nào -------------------------------------------


@pytest.fixture
def broken_llm(monkeypatch):
    monkeypatch.setattr(
        provider_router, "complete", Mock(side_effect=TimeoutError("provider chết")),
    )


def test_a_dead_model_branch_never_raises_and_is_recorded_as_failed(broken_llm):
    findings, status = branches.detect_with_model(FEVER_PROTOCOL, "bé tím tái")

    assert findings == ()
    assert status == branches.BRANCH_FAILED


def test_a_dead_model_branch_leaves_the_two_deterministic_branches_intact(broken_llm):
    findings, status = branches.detect_with_model(FEVER_PROTOCOL, "bé tím tái")
    codes, agreement = branches.merge_findings((RULE_CODE,), findings, model_status=status)

    assert codes == (RULE_CODE,)
    assert agreement.model_branch_status == branches.BRANCH_FAILED


def test_broken_json_is_treated_as_a_failed_branch_not_as_no_findings(monkeypatch):
    """Phân biệt "model nói không có gì" với "model hỏng" là điều kiện để `agreement_rate` đọc được:
    gộp hai ca đó lại thì một provider chết cả ngày sẽ trông như một ngày không ca nào có red flag."""
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text="{ khong phai json", provider="fake", model="fake")),
    )

    _, status = branches.detect_with_model(FEVER_PROTOCOL, "bé tím tái")

    assert status == branches.BRANCH_FAILED


def test_a_code_the_model_invented_is_dropped(monkeypatch):
    """Mã bịa lọt vào `model_only` sẽ trông y hệt một phát hiện thật - mà `model_only` chính là danh
    sách người ta sẽ dựa vào để mở rộng rule. Loại bằng CODE, không bằng lời dặn trong prompt."""
    payload = {"red_flags": [{"code": "RF-KHONG-CO-THAT", "evidence": "x"}, {"code": MODEL_CODE, "evidence": "y"}]}
    monkeypatch.setattr(
        provider_router, "complete",
        Mock(return_value=provider_router.CompletionResult(text=json.dumps(payload), provider="fake", model="fake")),
    )

    findings, status = branches.detect_with_model(FEVER_PROTOCOL, "bé tím tái")

    assert status == branches.BRANCH_OK
    assert [item.code for item in findings] == [MODEL_CODE]


# --- §7.3 mục 4: đối chiếu là DỮ LIỆU, không phải quyết định --------------------------------------


def test_the_agreement_object_has_no_path_into_the_priority_decision():
    """Đổi nội dung `red_flag_agreement` và khẳng định mức ưu tiên không đổi.

    Kiểm bằng KIẾN TRÚC: `rule_engine` là nguồn thật duy nhất của `triage_level`, và nó không được
    biết `red_flag_branches` tồn tại. Một dòng import ở đó là đủ để mở đường."""
    import ast
    import inspect

    from src.services.symptom_protocol import rule_engine

    tree = ast.parse(inspect.getsource(rule_engine))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any("red_flag_branches" in name for name in imported)


def test_the_agreement_survives_a_round_trip_through_the_log():
    original = branches.RedFlagAgreement(
        rule_only=[RULE_CODE], model_only=[MODEL_CODE], both=[], model_branch_status=branches.BRANCH_OK,
    )

    restored = branches.parse_json_agreement(original.as_dict())

    assert restored.as_dict() == original.as_dict()

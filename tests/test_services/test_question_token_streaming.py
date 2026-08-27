"""Câu hỏi gửi người bệnh chảy ra TỪNG CHỮ, mà không phát ra chữ nào chưa qua guard.

Bản trước gom trọn câu rồi phát một cục, vì §6.5 đòi `output_guard` chạy trước khi người bệnh đọc
được chữ nào. Ràng buộc đó KHÔNG bị nới ở đây - nó chỉ được giữ bằng cách khác: mọi vi phạm nguy hiểm
của guard đều ĐƠN ĐIỆU (dựa trên "có chứa", nên tập con chuỗi chỉ nở ra), vì thế `check_prefix` phán
được ngay trên câu đang viết dở, và chữ chỉ rời khỏi agent sau khi tiền tố chứa nó đã sạch.

BÀI ĐẮT NHẤT LÀ `test_a_disease_name_split_across_chunks_never_reaches_the_screen`. Nó ép đúng kịch
bản mà một bản streaming ngây thơ sẽ lọt: cụm cấm bị provider cắt đôi giữa hai mẩu. Không giữ lại
đuôi thì nửa đầu của cụm đã nằm trên màn hình trước khi có đủ chữ để nhận ra nó - guard vẫn "chạy",
vẫn chặn, chỉ là chặn sau khi người bệnh đã đọc.
"""

from __future__ import annotations

import pytest

from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router
from src.services.symptom_protocol import dialogue, intake_agent, output_guard

CLUSTER = next(cluster for cluster in FEVER_PROTOCOL.clusters if cluster.fields)


@pytest.fixture
def plan():
    return dialogue.ResponsePlan(
        act=dialogue.DialogueAct.ANSWER,
        cluster_id=CLUSTER.id,
        missing_fields=tuple(CLUSTER.fields),
        max_questions=2,
    )


def _stream_of(text: str, *, chunk: int):
    """Provider giả phát `text` theo mẩu `chunk` ký tự."""

    def _fake(messages, **kwargs):
        for at in range(0, len(text), chunk):
            yield text[at:at + chunk]

    return _fake


def _run(monkeypatch, text: str, *, chunk: int, plan) -> tuple[str, list[str]]:
    monkeypatch.setattr(provider_router, "complete_stream", _stream_of(text, chunk=chunk))
    seen: list[str] = []
    question, _ = intake_agent._generate_question(
        FEVER_PROTOCOL, CLUSTER, answers={}, plan=plan, credential=None, on_token=seen.append,
    )
    return question, seen


@pytest.mark.parametrize("chunk", [1, 2, 5, 40])
def test_the_question_arrives_in_more_than_one_piece(monkeypatch, plan, chunk) -> None:
    """Điều được yêu cầu: chữ hiện dần chứ không đợi decode xong.

    Câu phải ĐỦ DÀI hơn phần đuôi giữ lại thì mới có gì để phát sớm - một câu ngắn hơn
    `PREFIX_SAFE_TAIL` vẫn ra một cục, và đó là hành vi đúng chứ không phải thiếu sót."""
    text = (
        "Bạn cho mình hỏi thêm là cơn khó chịu này bắt đầu từ khi nào, "
        "và từ lúc đó tới giờ nó có nặng thêm lên không ạ?"
    )
    question, seen = _run(monkeypatch, text, chunk=chunk, plan=plan)

    assert question == text
    assert "".join(seen) == text, "ghép các mẩu phải ra đúng câu cuối cùng, không thiếu không lặp"
    assert len(seen) > 1, "vẫn đang gom trọn rồi mới phát một cục"


def test_nothing_is_emitted_before_the_guard_has_seen_it(monkeypatch, plan) -> None:
    """Ràng buộc §6.5 vẫn nguyên: mẩu phát ra luôn nằm trong phần tiền tố đã được kiểm."""
    text = "Bạn thấy trong người khó chịu thế nào, và bắt đầu từ khi nào ạ?"
    _, seen = _run(monkeypatch, text, chunk=3, plan=plan)

    shown = ""
    for piece in seen:
        shown += piece
        # Mọi thứ đã hiện ra màn hình, tại mọi thời điểm, đều phải sạch theo guard tiền tố.
        assert output_guard.check_prefix(
            shown, plan=plan, protocol=FEVER_PROTOCOL, cluster=CLUSTER, answers={}
        ), shown


def test_a_disease_name_split_across_chunks_never_reaches_the_screen(monkeypatch, plan) -> None:
    """BÀI QUAN TRỌNG NHẤT.

    Provider cắt "sốt xuất huyết" làm đôi. Một bản streaming không giữ đuôi sẽ phát "…sốt xuất" ra
    màn hình rồi mới nhận ra ở mẩu sau - lúc đó đã muộn."""
    banned = next(name for name in output_guard.DISEASE_NAMES if len(name) > 6)
    text = f"Mình nghĩ khả năng cao là bạn đang bị {banned}, bạn thấy sao ạ?"

    question, seen = _run(monkeypatch, text, chunk=2, plan=plan)

    shown = "".join(seen)
    assert banned not in shown.casefold()
    # Cả tiền tố của cụm cấm cũng không được lọt: "sốt xuất" đã đủ để người bệnh tự điền nốt.
    assert banned[:7].casefold() not in shown.casefold(), shown
    assert banned.casefold() not in question.casefold(), "câu trả về vẫn dính tên bệnh"


def test_a_blocked_question_falls_back_to_the_static_script(monkeypatch, plan) -> None:
    """Guard chặn thì vẫn phải có câu để hỏi - im lặng là kiểu hỏng tệ nhất."""
    banned = next(iter(output_guard.DISEASE_NAMES))
    question, seen = _run(monkeypatch, f"Bạn bị {banned} phải không ạ?", chunk=4, plan=plan)

    assert question == CLUSTER.script_hint
    assert "".join(seen).endswith(CLUSTER.script_hint)


def test_a_broken_stream_still_produces_a_question(monkeypatch, plan) -> None:
    """Provider rớt giữa chừng không được làm lượt của người bệnh treo."""

    def _angry(messages, **kwargs):
        yield "Bạn cho mình hỏi"
        raise RuntimeError("provider rớt")

    monkeypatch.setattr(provider_router, "complete_stream", _angry)
    seen: list[str] = []
    question, ok = intake_agent._generate_question(
        FEVER_PROTOCOL, CLUSTER, answers={}, plan=plan, credential=None, on_token=seen.append,
    )

    assert question == CLUSTER.script_hint
    assert ok is False


def test_the_non_streaming_path_is_untouched(monkeypatch, plan) -> None:
    """`on_token=None` là đường mọi test cũ và mọi caller không stream đang đi."""
    text = "Bạn thấy khó chịu từ khi nào ạ?"
    monkeypatch.setattr(
        provider_router, "complete",
        lambda messages, **kwargs: provider_router.CompletionResult(
            text=text, provider="fake", model="fake",
        ),
    )
    question, ok = intake_agent._generate_question(
        FEVER_PROTOCOL, CLUSTER, answers={}, plan=plan, credential=None, on_token=None,
    )

    assert question == text
    assert ok is True

"""Hai kênh báo ra ngoài của part 3: tiến trình từng bước, và bản nháp chạy chữ ở bước 7.

ĐIỀU ĐÁNG KIỂM Ở ĐÂY KHÔNG PHẢI "CÓ SỰ KIỆN KHÔNG". Streaming là thứ dễ viết cho có: gắn một callback,
thấy chữ chạy trên màn hình, rồi tin là xong. Ba thứ hỏng được mà mắt thường không thấy:

1. **Bản nháp trượt Guard 5 nhưng vẫn nằm lại trên màn hình.** Bước 7 chỉ kiểm được URL/marker/quote
   khi đã có TRỌN đoạn văn, nên chữ đã stream luôn là chữ chưa kiểm. Hợp đồng bù lại là sự kiện
   `explanation_replaced`. Không có nó thì cả cơ chế stream ở đây là một lỗ hổng an toàn, không phải
   một tính năng - `test_guard_rejection_tells_the_caller_to_drop_the_draft` giữ đúng chỗ đó.

2. **Mẩu stream cắt giữa một escape.** Provider cắt chuỗi ở vị trí tuỳ ý, kể cả giữa `\\uXXXX`. Bộ
   bóc trường phải chịu được, và cách duy nhất để biết là nạp vào từng ký tự một.

3. **Bước 6 báo tiến trình từ ba luồng con.** Số thứ tự cài răng lược hay callback chạy chồng nhau
   chỉ lộ ra khi có nhiều claim - `test_parallel_grading_numbers_every_claim_exactly_once` ép đúng
   tình huống đó.
"""

from __future__ import annotations

import json

import pytest

from src.source_support import llm as llm_module
from src.source_support import pipeline as pipeline_module
from src.source_support.explain import CONTRADICTION_WARNING
from src.source_support.progress import ProgressEvent, ProgressReporter

# Dùng lại NGUYÊN bộ giả lập của bài e2e thay vì dựng bản sao: hai bộ giả lập cho cùng một pipeline
# sẽ trôi ra xa nhau, và lúc đó bài test nào đang nói về hệ thống thật thì không ai biết. Hai fixture
# `seeded_index`/`fake_llm` đến qua `conftest.py`, không import ở đây.
from tests.test_source_support._fixtures import CLAIM_JSON, DECISION, _replies

# --- bộ bóc trường đang stream -------------------------------------------------------------------


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 17])
@pytest.mark.parametrize("ensure_ascii", [True, False])
def test_decoder_rebuilds_the_field_from_chunks_cut_anywhere(chunk_size, ensure_ascii) -> None:
    """Cắt ở MỌI kích thước, kể cả 1 ký tự - đó là chỗ escape bị xẻ đôi."""
    body = 'Tình trạng hiện tại của cháu bé 14 tháng tuổi: CẤP CỨU\n\nBáo cáo mô tả "đang sốt cao" [1]'
    raw = json.dumps({"explanation_vi": body, "used_markers": ["[1]"]}, ensure_ascii=ensure_ascii)

    decoder = llm_module.StreamedFieldDecoder("explanation_vi")
    pieces = [decoder.feed(raw[at:at + chunk_size]) for at in range(0, len(raw), chunk_size)]

    assert "".join(pieces) == body


def test_decoder_stays_silent_until_the_field_appears() -> None:
    """Mấy mẩu đầu chưa có trường - đó là trạng thái bình thường, không phải lỗi, và tuyệt đối không
    được phát ra mẩu rác nào (một dấu ngoặc lạc vào màn hình điều dưỡng vẫn là một lỗi hiển thị)."""
    decoder = llm_module.StreamedFieldDecoder("explanation_vi")
    assert decoder.feed('{"used_mark') == ""
    assert decoder.feed('ers": ["[1]"], "explanation_') == ""
    assert decoder.feed('vi": "Xin') == "Xin"


def test_decoder_ignores_a_fenced_code_block() -> None:
    """Model bọc JSON trong ```json là chuyện thường xuyên và `parse_json_object` đã chịu được ở lượt
    cuối - đường stream cũng phải chịu được, nếu không thì hiệu ứng chữ chạy chỉ hoạt động với đúng
    những provider không bọc fence."""
    decoder = llm_module.StreamedFieldDecoder("explanation_vi")
    raw = '```json\n{"explanation_vi": "Xin chào", "used_markers": []}\n```'
    assert "".join(decoder.feed(char) for char in raw) == "Xin chào"


# --- reporter ------------------------------------------------------------------------------------


def test_a_broken_sink_never_breaks_the_run() -> None:
    """Người dùng đóng tab giữa chừng thì sink ném lỗi. Đó KHÔNG phải lý do để bỏ phần trích nguồn
    của ca đó - và sink hỏng phải bị tắt hẳn, không phải bị gọi lại ở mọi mốc sau."""
    calls = []

    def _angry(event: ProgressEvent) -> None:
        calls.append(event)
        raise BrokenPipeError("tab đã đóng")

    reporter = ProgressReporter(_angry)
    reporter.emit("start", "một")
    reporter.emit("done", "hai")

    assert len(calls) == 1
    assert reporter.enabled is False


def test_elapsed_never_goes_backwards() -> None:
    seen: list[ProgressEvent] = []
    reporter = ProgressReporter(seen.append)
    reporter.emit("a", "một")
    reporter.emit("b", "hai")
    assert seen[1].elapsed_ms >= seen[0].elapsed_ms >= 0


# --- luồng đủ bảy bước, có cả hai kênh -----------------------------------------------------------


def test_progress_covers_the_silent_steps_not_just_the_last_one(seeded_index, fake_llm) -> None:
    """Lý do cả cơ chế này tồn tại: mốc tiến trình phải phủ các bước KHÔNG có chữ để phát ra.

    Chỉ khẳng định phần đầu và phần cuối của chuỗi mốc là đủ - siết từng mốc một sẽ biến bài test
    thành bản sao của code, và mỗi lần thêm một dòng tiến trình lại phải sửa test."""
    _, replies = fake_llm
    replies.update(_replies())
    seen: list[ProgressEvent] = []

    pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index, on_progress=seen.append,
    )

    phases = [event.phase for event in seen]
    assert phases[0] == "start"
    assert phases[-1] == "done"
    # Bước 1 và bước 6 trả JSON, bước 7 mới có chữ. Mất mốc của hai bước đầu là quay lại đúng chỗ
    # cũ: người dùng nhìn màn hình đứng im suốt đoạn dài nhất.
    for required in ("claims_start", "claims_done", "verdict_start", "verdict_done", "explain_start"):
        assert required in phases, f"thiếu mốc {required}: {phases}"
    assert all(event.text for event in seen), "mọi sự kiện phải mang sẵn câu tiếng Việt đọc được"


def test_parallel_grading_numbers_every_claim_exactly_once(seeded_index, fake_llm, monkeypatch) -> None:
    """Bước 6 chấm song song. Ba luồng cùng đếm bằng `+=` sẽ in trùng số thứ tự."""
    _, replies = fake_llm
    three_claims = {"claims": [dict(CLAIM_JSON["claims"][0]) for _ in range(3)]}
    for position, claim in enumerate(three_claims["claims"]):
        claim["claim_en"] = f"{claim['claim_en']} (variant {position})"
    replies.update(_replies())
    replies["claim_splitter"] = three_claims

    seen: list[ProgressEvent] = []
    pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index, on_progress=seen.append,
    )

    numbers = sorted(
        event.detail["index"] for event in seen if event.phase in {"verdict_done", "verdict_failed"}
    )
    assert numbers == [1, 2, 3]


def test_explanation_streams_before_the_final_text_is_known(seeded_index, fake_llm, monkeypatch) -> None:
    """Bước 7 phát chữ dần, và cái phát ra phải ghép lại đúng bằng đoạn văn cuối cùng."""
    _, replies = fake_llm
    replies.update(_replies())
    payload = replies["source_explain"]

    def _fake_stream(messages, *, temperature=None, role=None, on_provider=None, **kwargs):
        if on_provider is not None:
            on_provider("fake", "fake-model")
        raw = json.dumps(payload, ensure_ascii=False)
        for at in range(0, len(raw), 5):
            yield raw[at:at + 5]

    monkeypatch.setattr(llm_module.provider_router, "complete_stream", _fake_stream)

    drafted: list[str] = []
    support = pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index, on_token=drafted.append,
    )

    assert "".join(drafted) == payload["explanation_vi"]
    assert support.explanation_vi.startswith(payload["explanation_vi"][:40])
    # Lượt stream vẫn phải vào sổ chi phí, và vào ĐÚNG TÊN provider đã viết nó - đó là toàn bộ lý do
    # `complete_stream` có tham số `on_provider`.
    assert support.cost.provider_calls["fake"] == 3, "bước 1 + bước 6 + bước 7(stream), không thiếu cái nào"


def test_guard_rejection_tells_the_caller_to_drop_the_draft(seeded_index, fake_llm, monkeypatch) -> None:
    """BÀI QUAN TRỌNG NHẤT CỦA MODULE NÀY.

    Model viết một URL trần vào đoạn văn -> Guard 5a chặn -> đoạn thật bị thay bằng bản dựng bằng
    code. Chữ đã chảy qua màn hình lúc đó là chữ SAI, và thứ duy nhất cứu được là sự kiện
    `explanation_replaced`. Mất nó thì người đọc giữ lại một đoạn văn trượt guard mà không hề biết."""
    _, replies = fake_llm
    replies.update(_replies())
    bad = {
        "explanation_vi": "Tình trạng hiện tại của cháu bé 14 tháng tuổi: CẤP CỨU\n\n"
                          "Xem thêm tại https://example.com/khong-nam-trong-tap-da-verify",
        "used_markers": [],
    }

    def _fake_stream(messages, *, temperature=None, role=None, on_provider=None, **kwargs):
        if on_provider is not None:
            on_provider("fake", "fake-model")
        yield json.dumps(bad, ensure_ascii=False)

    monkeypatch.setattr(llm_module.provider_router, "complete_stream", _fake_stream)

    drafted: list[str] = []
    seen: list[ProgressEvent] = []
    support = pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index,
        on_progress=seen.append, on_token=drafted.append,
    )

    assert "example.com" in "".join(drafted), "bản nháp đúng là đã chảy ra ngoài"
    assert "example.com" not in support.explanation_vi, "Guard 5a phải chặn được URL trần"
    assert "explanation_replaced" in [event.phase for event in seen], (
        "bản nháp bị vứt mà không báo ra: người gọi sẽ giữ lại một đoạn văn trượt guard"
    )


def test_an_injected_warning_also_voids_the_draft(seeded_index, fake_llm, monkeypatch) -> None:
    """Guard 5B, chứ không phải 5a - và đây là ca dễ bỏ sót nhất của cả cơ chế stream.

    Có claim `contradicts` thì câu cảnh báo do CODE chèn vào sau khi model viết xong, nên nó KHÔNG
    bao giờ nằm trong dòng chữ vừa chảy qua màn hình. Guard 5a không chặn ca này (đoạn văn hợp lệ),
    nên không có `ExplanationGuardError` nào để bắt: nếu bước 7 chỉ báo `explanation_replaced` ở
    nhánh except thì bản nháp thiếu cảnh báo sẽ nằm lại trên màn hình, im lặng, ở đúng ca nguy hiểm
    nhất mà tầng này tồn tại để báo động."""
    _, replies = fake_llm
    replies.update(_replies(verdict="contradicts"))
    payload = replies["source_explain"]

    def _fake_stream(messages, *, temperature=None, role=None, on_provider=None, **kwargs):
        if on_provider is not None:
            on_provider("fake", "fake-model")
        yield json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(llm_module.provider_router, "complete_stream", _fake_stream)

    drafted: list[str] = []
    seen: list[ProgressEvent] = []
    support = pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index,
        on_progress=seen.append, on_token=drafted.append,
    )

    assert CONTRADICTION_WARNING in support.explanation_vi
    assert CONTRADICTION_WARNING not in "".join(drafted), "bản nháp đúng là thiếu câu cảnh báo"
    assert "explanation_replaced" in [event.phase for event in seen], (
        "bản nháp thiếu cảnh báo mà không báo ra: người đọc giữ lại bản không có cảnh báo"
    )


def test_a_broken_stream_falls_back_to_one_shot(seeded_index, fake_llm, monkeypatch) -> None:
    """Stream hỏng chỉ được làm mất hiệu ứng chữ chạy, không được làm mất phần trích nguồn."""
    _, replies = fake_llm
    replies.update(_replies())

    def _angry_stream(messages, **kwargs):
        raise RuntimeError("provider rớt giữa chừng")
        yield  # pragma: no cover - giữ hàm là generator

    monkeypatch.setattr(llm_module.provider_router, "complete_stream", _angry_stream)
    # Đường lui của `call_json_streaming` gọi `call_json` của CHÍNH module `llm`, không phải cái đã bị
    # `fake_llm` vá trên `explain`. Không vá chỗ này thì bài test đi thẳng ra provider thật.
    monkeypatch.setattr(
        llm_module, "call_json",
        lambda *, system_prompt, user_prompt, schema, role, meter=None, temperature=0.0: (
            schema.model_validate(replies[role])
        ),
    )

    support = pipeline_module.run(
        DECISION, triage_label="cap_cuu", index=seeded_index, on_token=lambda piece: None,
    )

    assert support.explanation_vi
    assert support.explanation_citations, "vẫn phải trích được nguồn qua đường gọi một cục"

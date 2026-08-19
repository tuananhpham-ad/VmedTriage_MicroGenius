"""Bảy bước chạy liền một mạch, với LLM GIẢ và embedding GIẢ. Không một lời gọi API nào.

VÌ SAO GIẢ LẬP MODEL Ở ĐÂY. Thứ cần khẳng định là hệ THỐNG NỐI ĐÚNG: nhãn không rò xuống bước chấm,
Guard 0c loại được claim lệch, cờ người xem bật đúng lúc, và sổ chi phí đếm đúng. Không thứ nào trong
đó phụ thuộc vào model thật giỏi tới đâu, mà chạy model thật sẽ khiến bài test vừa chậm vừa nhấp nháy
vừa tốn quota - ba lý do để nó bị tắt đi, và một bài test bị tắt không bảo vệ được gì.

Chất lượng phán đoán của model là việc của cổng lọc provider (bài kiểm chứng #9), không phải việc của
bộ test này.

BÀI QUAN TRỌNG NHẤT: `test_grader_never_sees_the_triage_label`. Tính blind của bước 6 là thứ làm
`contradicts` có nghĩa. Nếu một lần refactor vô tình đẩy cả cục quyết định xuống bộ chấm thì mọi
verdict vẫn "chạy được", vẫn xanh, chỉ là không còn đáng tin - đúng loại hỏng không có triệu chứng.
"""

from __future__ import annotations

import json

import pytest

from src.source_support import claims as claims_module
from src.source_support import explain as explain_module
from src.source_support import pipeline as pipeline_module
from src.source_support import verdict as verdict_module
from src.source_support.explain import CONTRADICTION_WARNING
from src.source_support.index import Chunk, SourceIndex

QUOTE = "Call 999 if the seizure lasts longer than 5 minutes, or your child does not regain consciousness afterwards."
URL = "https://www.nhs.uk/conditions/febrile-seizures/"

DECISION = {
    "triage_label": "cap_cuu",
    "decision_summary": (
        "Báo cáo mô tả cháu đang sốt cao thì lên cơn co giật, người cứng lại, mắt trợn ngược khoảng "
        "hai phút; sau cơn lịm đi và gọi không phản ứng. Co giật khi đang sốt ở trẻ nhỏ kèm không "
        "đáp ứng kéo dài sau cơn cần được đánh giá cấp cứu."
    ),
    "uncertainty_summary": "Chưa rõ tiền sử co giật trước đây.",
    "requires_human_review": False,
    "risk_modifiers": [{"factor": "extreme_age", "source_span": "cháu bé 14 tháng tuổi"}],
    "evidence": [
        {"concept": "fever", "status": "present", "source_span": "đang sốt cao"},
        {"concept": "seizure", "status": "present", "source_span": "lên cơn co giật"},
        {"concept": "lethargy", "status": "present", "source_span": "lịm đi"},
    ],
}

CLAIM_JSON = {
    "claims": [
        {
            "claim_en": "A febrile seizure in a child under 5 followed by prolonged unresponsiveness "
                        "requires emergency assessment.",
            "claim_vi": "Co giật do sốt ở trẻ nhỏ kèm không đáp ứng kéo dài sau cơn cần được đánh giá cấp cứu.",
            "claim_kind": "red_flag",
            "grounded_in": "Co giật khi đang sốt ở trẻ nhỏ kèm không đáp ứng kéo dài sau cơn cần được "
                           "đánh giá cấp cứu",
        }
    ]
}


@pytest.fixture
def seeded_index(tmp_path) -> SourceIndex:
    index = SourceIndex(directory=tmp_path)
    index.chunks.append(
        Chunk(chunk_id="nhs-1", document_id="doc-nhs", url=URL, title="Febrile seizures",
              publisher="nhs.uk", text=QUOTE, retrieved_at="2026-08-14T09:12:03Z")
    )
    import numpy as np

    index.vectors = np.asarray([[1.0, 0.0]], dtype="float32")
    return index


@pytest.fixture
def fake_llm(monkeypatch):
    """Thay `call_json` bằng bộ trả lời cố định theo `role`, và GHI LẠI prompt để soi được rò rỉ."""
    seen: list[dict[str, str]] = []
    replies: dict[str, dict] = {}

    def _fake(*, system_prompt, user_prompt, schema, role, meter=None, temperature=0.0):
        seen.append({"role": role, "user_prompt": user_prompt})
        if meter is not None:
            meter.record_call("fake", system_prompt + user_prompt, "{}")
        return schema.model_validate(replies[role])

    for module in (claims_module, verdict_module, explain_module):
        monkeypatch.setattr(module, "call_json", _fake)
    # Vá trên `pipeline_module`, KHÔNG trên `retrieval_module`: pipeline dùng `from ... import retrieve`
    # nên nó giữ một tham chiếu riêng, vá module gốc không đổi được cái tham chiếu đó.
    monkeypatch.setattr(pipeline_module, "retrieve", _stub_retrieve)
    return seen, replies


def _stub_retrieve(claim, index, *, meter=None, threshold=None, index_only=None):
    """Bước 2 thật cần embedding cục bộ (torch). Ở đây chỉ cần nó trả về đúng ứng viên có sẵn."""
    from src.source_support.index import SearchHit
    from src.source_support.retrieval import ClaimEvidence
    from src.source_support.schemas import Retrieval

    return ClaimEvidence(
        claim=claim,
        candidates=[SearchHit(chunk=index.chunks[0], score=0.61)] if index.chunks else [],
        retrieval=Retrieval(from_index=True, searched_web=False, best_score=0.61),
    )


def _replies(verdict: str = "supports", *, matches: bool = True) -> dict[str, dict]:
    return {
        "claim_splitter": CLAIM_JSON,
        "source_verdict": {
            "verdict": verdict,
            "verdict_reason": "Đoạn trích nêu đúng tình trạng không tỉnh lại sau cơn.",
            "claim_matches_reasoning": matches,
            "best_chunk_id": "nhs-1",
        },
        "source_explain": {
            "explanation_vi": "Tình trạng hiện tại của cháu bé 14 tháng tuổi: CẤP CỨU\n\n"
                              "Báo cáo mô tả cháu \"đang sốt cao\", \"lên cơn co giật\".\n\n"
                              "Vì sao ở mức này:\n- Co giật do sốt kèm không tỉnh lại sau cơn [1]",
            "used_markers": ["[1]"],
        },
    }


# --- luồng đủ bảy bước --------------------------------------------------------------------------


def test_full_run_produces_a_cited_explanation(seeded_index, fake_llm) -> None:
    seen, replies = fake_llm
    replies.update(_replies())

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.summary.claims_examined == 1
    assert support.summary.claims_with_support == 1
    assert support.summary.verified_citations == 1
    assert support.summary.requires_human_review is False
    assert support.explanation_citations[0].url == URL
    assert support.explanation_citations[0].quote == QUOTE
    assert "[1]" in support.explanation_vi
    # Ba bước dùng model, đúng ba lời gọi - không có lượt thừa nào.
    assert [item["role"] for item in seen] == ["claim_splitter", "source_verdict", "source_explain"]
    assert support.cost.llm_calls == 3
    assert support.method.can_change_label is False


def test_grader_never_sees_the_triage_label(seeded_index, fake_llm) -> None:
    """Tính blind của bước 6 - lời hứa làm `contradicts` có nghĩa.

    Kiểm trên chính prompt đã gửi: nhãn không được xuất hiện ở bước tách claim lẫn bước chấm, dù dưới
    dạng khoá máy (`cap_cuu`) hay dạng hiển thị (`CẤP CỨU`)."""
    seen, replies = fake_llm
    replies.update(_replies())
    pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    for step in seen:
        if step["role"] in {"claim_splitter", "source_verdict"}:
            assert "cap_cuu" not in step["user_prompt"]
            assert "CẤP CỨU" not in step["user_prompt"]

    explain_prompt = next(s for s in seen if s["role"] == "source_explain")["user_prompt"]
    assert "CẤP CỨU" in explain_prompt, "bước diễn giải PHẢI có nhãn cho câu mở đầu"


def test_verdict_step_sees_no_other_claim(seeded_index, fake_llm) -> None:
    """Bộ chấm chỉ thấy MỘT mệnh đề. Thấy các mệnh đề khác là mời nó chấm cho nhất quán với nhau."""
    seen, replies = fake_llm
    replies.update(_replies())
    pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    payload = json.loads(next(s for s in seen if s["role"] == "source_verdict")["user_prompt"])
    assert set(payload) == {"menh_de", "lap_luan_goc", "cac_doan_trich"}
    assert isinstance(payload["menh_de"], str)


# --- Guard 0c -----------------------------------------------------------------------------------


def test_guard_0c_drops_a_drifted_claim(seeded_index, fake_llm) -> None:
    """`claim_matches_reasoning=false` -> claim bị BỎ HẲN, không hạ verdict.

    Một claim không phản ánh đúng lập luận thì kết quả đối chiếu của nó - dù `supports` hay
    `unsupported` - đều đang nói về một mệnh đề khác với mệnh đề hệ thống thật sự dựa vào."""
    _, replies = fake_llm
    replies.update(_replies(matches=False))

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.claims == []
    assert support.explanation_citations == []
    assert "Không tìm được tài liệu tham khảo" in support.explanation_vi
    assert support.summary.claims_examined == 1
    assert support.summary.claims_with_support == 0


# --- contradicts --------------------------------------------------------------------------------


def test_contradiction_raises_the_review_flag_and_says_so(seeded_index, fake_llm) -> None:
    """Đường DUY NHẤT part 3 tác động tới ca, và nó phải hiện ra trên màn hình chứ không chỉ trong cờ."""
    _, replies = fake_llm
    replies.update(_replies(verdict="contradicts"))

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.summary.requires_human_review is True
    assert support.summary.contradicted_claims
    assert CONTRADICTION_WARNING in support.explanation_vi
    # `contradicts` KHÔNG được cấp marker, nên đoạn văn không mang trích dẫn nào.
    assert support.explanation_citations == []
    assert pipeline_module.merge_human_review(False, support) is True


def test_unsupported_claim_gets_no_citation(seeded_index, fake_llm) -> None:
    _, replies = fake_llm
    replies.update(_replies(verdict="unsupported"))

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.summary.claims_with_support == 0
    assert support.explanation_citations == []
    assert support.summary.requires_human_review is False


# --- Guard 0 vẫn chặn trong luồng đầy đủ --------------------------------------------------------


def test_guard_0a_blocks_the_whole_run(seeded_index, fake_llm) -> None:
    """Guard chặn thì `run()` NÉM RA - nuốt lỗi là việc của tầng service, không phải của tầng này."""
    from src.source_support.claims import ClaimGuardError

    _, replies = fake_llm
    replies.update(_replies())
    replies["claim_splitter"] = {
        "claims": [{
            "claim_en": "x", "claim_vi": "x", "claim_kind": "red_flag",
            "grounded_in": "Bệnh nhân có tiền sử co giật do sốt nhiều lần",  # không có trong lập luận
        }]
    }
    with pytest.raises(ClaimGuardError, match="Guard 0a"):
        pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)


def test_no_claims_returns_the_honest_note(seeded_index, fake_llm) -> None:
    _, replies = fake_llm
    replies.update(_replies())
    replies["claim_splitter"] = {"claims": []}

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)
    assert "không có nghĩa đánh giá sai" in support.explanation_vi
    assert support.explanation_citations == []


# --- mô tả bệnh nhân lấy từ trích dẫn, không tự sinh --------------------------------------------


def test_patient_label_comes_from_a_verbatim_span() -> None:
    assert pipeline_module._patient_label(DECISION) == "cháu bé 14 tháng tuổi"
    assert pipeline_module._patient_label({}) == pipeline_module.DEFAULT_PATIENT_LABEL


def test_patient_spans_exclude_absent_findings() -> None:
    """Nhắc "không khó thở" trong phần mô tả triệu chứng đọc như một lời trấn an - đúng kiểu suy luận
    thiếu căn cứ mà cả tầng này đang tìm cách chặn."""
    decision = {"evidence": [
        {"status": "present", "source_span": "sốt cao"},
        {"status": "absent", "source_span": "không khó thở"},
    ]}
    assert pipeline_module._patient_spans(decision) == ["sốt cao"]


# --- đường lui tất định khi Guard 5 chặn --------------------------------------------------------


def test_contradiction_flag_survives_a_rejected_explanation(seeded_index, fake_llm) -> None:
    """Bài an toàn: model gõ thừa một marker KHÔNG được phép làm mất tín hiệu `contradicts`.

    Trước khi có đường lui tất định, Guard 5 chặn -> `run()` ném ra -> `service` nuốt thành `None` ->
    `merge_human_review` không thấy cờ nào để bật. Tức một lỗi ĐỊNH DẠNG của model vứt luôn thứ nguy
    hiểm nhất mà tầng này có nhiệm vụ báo ra. Đoạn văn được phép xấu; cái cờ thì không được mất."""
    _, replies = fake_llm
    replies.update(_replies(verdict="contradicts"))
    # `contradicts` không được cấp marker nào, nhưng model vẫn viết "[1]" -> Guard 5a chặn.

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.summary.requires_human_review is True
    assert CONTRADICTION_WARNING in support.explanation_vi
    assert support.explanation_citations == []
    assert "[1]" not in support.explanation_vi, "bản dự phòng chỉ dùng marker đã được cấp"
    assert pipeline_module.merge_human_review(False, support) is True


def test_fallback_explanation_is_built_without_a_model(seeded_index, fake_llm) -> None:
    """Bản dự phòng phải tự nó qua được Guard 5 - nó do code dựng nên điều đó đúng theo cấu trúc."""
    _, replies = fake_llm
    replies.update(_replies(verdict="unsupported"))

    support = pipeline_module.run(DECISION, triage_label="cap_cuu", index=seeded_index)

    assert support.explanation_vi.startswith("Tình trạng hiện tại của cháu bé 14 tháng tuổi: CẤP CỨU")
    assert "Không tìm được tài liệu tham khảo cho các lập luận sau:" in support.explanation_vi
    assert "http" not in support.explanation_vi, "bản dự phòng không bao giờ viết URL trần"


# --- mô tả bệnh nhân và trích dẫn triệu chứng ---------------------------------------------------


def test_patient_label_falls_back_to_age_in_the_summary() -> None:
    """Đo trên luồng thật (2026-08-19): part 2 KHÔNG phải lúc nào cũng sinh `risk_modifiers`, kể cả
    với bệnh nhi 14 tháng. Khi đó câu mở đầu tụt xuống "Tình trạng hiện tại của người bệnh" và mất
    hẳn thông tin tuổi - thứ quan trọng nhất để điều dưỡng định hướng."""
    assert pipeline_module._patient_label(
        {"decision_summary": "Bệnh nhân 14 tháng tuổi có triệu chứng sốt cao và co giật."}
    ) == "Bệnh nhân 14 tháng tuổi"


def test_patient_label_prefers_risk_modifier_over_regex() -> None:
    decision = {
        "risk_modifiers": [{"source_span": "cháu bé 14 tháng tuổi"}],
        "decision_summary": "Bệnh nhân 32 tuổi ...",
    }
    assert pipeline_module._patient_label(decision) == "cháu bé 14 tháng tuổi"


def test_patient_label_never_invents_a_description() -> None:
    """Không có tuổi ở đâu thì dùng cách gọi trung tính. Tự sinh mô tả bệnh nhân là bịa dữ kiện lâm
    sàng - ranh giới không được vượt."""
    assert pipeline_module._patient_label(
        {"decision_summary": "Bệnh nhân nổi mẩn đỏ sau khi uống kháng sinh."}
    ) == pipeline_module.DEFAULT_PATIENT_LABEL


def test_patient_spans_drop_the_form_field_prefix() -> None:
    """Phiếu tóm tắt dựng dạng "- <nhãn>: <giá trị>" nên `source_span` mang theo cả tiền tố, và đoạn
    diễn giải đọc ra "Người bệnh có biểu hiện *Sốt: đang sốt cao*" - như đọc biểu mẫu."""
    decision = {"evidence": [{"status": "present", "source_span": "Sốt: đang sốt cao từ chiều qua"}]}
    assert pipeline_module._patient_spans(decision) == ["đang sốt cao từ chiều qua"]


def test_clean_span_leaves_normal_prose_alone() -> None:
    long_sentence = "Bệnh nhân mô tả rất nhiều triệu chứng khác nhau và kéo dài liên tục: đau đầu"
    assert pipeline_module._clean_span("lên cơn co giật, người cứng lại") == "lên cơn co giật, người cứng lại"
    assert pipeline_module._clean_span(long_sentence) == long_sentence

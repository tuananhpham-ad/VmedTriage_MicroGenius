"""Đồ dùng chung của bộ test part 3: một ca mẫu, một index đã gieo sẵn, và bộ LLM giả.

TÁCH RA THÀNH MODULE RIÊNG vì đã có hai bộ test cần đúng những thứ này (`test_pipeline_end_to_end`
kiểm các bất biến của bảy bước, `test_progress_and_streaming` kiểm hai kênh báo ra ngoài). Dựng bản
sao thứ hai của cùng một bộ giả lập là cách hai bài test dần nói về hai hệ thống khác nhau mà vẫn
cùng xanh.

`conftest.py` bên cạnh chỉ làm đúng một việc: đưa hai fixture ở đây vào tầm nhìn của pytest, để test
module không phải import fixture (import fixture rồi nhận nó qua tham số là chỗ ruff báo F811, và
báo đúng - cái tên bị định nghĩa hai lần thật)."""

from __future__ import annotations

import pytest

from src.source_support import claims as claims_module
from src.source_support import explain as explain_module
from src.source_support import pipeline as pipeline_module
from src.source_support import verdict as verdict_module
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


def _stub_retrieve(claim, index, *, meter=None, threshold=None, index_only=None, **kwargs):
    """Bước 2 thật cần embedding cục bộ (torch). Ở đây chỉ cần nó trả về đúng ứng viên có sẵn.

    `**kwargs` nuốt các tham số báo tiến trình (`on_progress`, `claim_index`, `claim_total`): chúng
    không đổi kết quả bước 2, và liệt kê từng cái ở đây thì mỗi lần thêm một mốc tiến trình mới lại
    phải sửa stub - một ràng buộc không mua được gì cho bài test này."""
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

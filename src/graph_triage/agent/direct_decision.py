"""Direct production triage classifier used as the independent C6 branch.

This prompt is intentionally separate from benchmark prompts.  Benchmark prompts are frozen so
their historical scores remain reproducible; changing this production prompt requires a new
production-facing evaluation before enabling the safety gate.
"""

from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.config import get_settings
from src.graph_triage.graph_schema import normalise_span
from src.graph_triage.labels import TRIAGE_LABELS, normalize_label

_SYSTEM_PROMPT = """Bạn là bộ phân loại hỗ trợ phân luồng y tế nghiên cứu cho điều dưỡng.
Chỉ đọc thông tin người bệnh được cung cấp. Không chẩn đoán, không kê đơn, không bịa thông tin.

Chọn đúng một nhãn:
- cap_cuu: có dấu hiệu cần chuyển cấp cứu ngay.
- kham_som: cần được nhân viên y tế đánh giá sớm.
- theo_doi_tai_nha: chưa thấy dấu hiệu cần khám sớm từ thông tin hiện có.

Nếu thông tin thiếu hoặc không chắc chắn, chọn nhãn thận trọng hơn trong hai nhãn phù hợp.

Ngoài nhãn, viết `decision_summary` bằng tiếng Việt, ngắn gọn và CHỈ nêu các dữ kiện có trong phiếu.
Với mỗi dữ kiện lâm sàng dùng trong summary, đưa một evidence gồm `concept`, `status` và `source_span`.
`source_span` phải là một đoạn chép NGUYÊN VĂN từ phiếu, không diễn đạt lại. Không có dữ kiện phù hợp
thì trả `evidence` rỗng. Trả JSON đúng schema."""


class DirectEvidence(BaseModel):
    # OpenAI strict structured output requires every object in the JSON Schema to explicitly
    # forbid additional keys. Pydantic emits that constraint from extra="forbid".
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(min_length=1, max_length=120)
    status: Literal["present", "absent", "uncertain"]
    source_span: str = Field(min_length=1, max_length=500)


class DirectDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    triage_label: str
    decision_summary: str = Field(min_length=1, max_length=600)
    # Strict JSON Schema also requires every declared property to be required. The model can
    # still return an empty list when no evidence is available.
    evidence: list[DirectEvidence] = Field(max_length=3)

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "direct_triage_decision",
        "strict": True,
        "schema": DirectDecision.model_json_schema(),
    },
}


def decide_direct(patient_text: str, model: str) -> dict:
    """Return a grounded direct C6 decision for the subsequent Part 3 source pipeline.

    Errors are deliberately propagated to the service, which records the branch as unavailable
    and keeps the rule-engine priority.  Every evidence span is checked against the input summary
    before it can be passed to source support.
    """
    text = patient_text.strip()
    if not text:
        raise ValueError("patient_text must not be empty")
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Set OPENAI_API_KEY before running the direct safety classifier.")
    response = OpenAI(api_key=settings.openai_api_key).chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format=_RESPONSE_FORMAT,
        temperature=0,
        max_tokens=400,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Direct safety classifier returned an empty response.")
    decision = DirectDecision.model_validate(json.loads(content))
    normalized = normalize_label(str(decision.triage_label))
    if normalized not in TRIAGE_LABELS:
        raise ValueError(f"Direct safety classifier returned an unsupported label: {decision.triage_label!r}")
    for item in decision.evidence:
        if normalise_span(item.source_span) not in normalise_span(text):
            raise ValueError(f"Direct safety classifier returned evidence outside the summary: {item.source_span!r}")
    return {
        "triage_label": normalized,
        "decision_summary": decision.decision_summary,
        "evidence": [item.model_dump(mode="json") for item in decision.evidence],
    }


def classify_direct(patient_text: str, model: str) -> str:
    """Compatibility helper for callers that only need C6's label."""
    return decide_direct(patient_text, model)["triage_label"]

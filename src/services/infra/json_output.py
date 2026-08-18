"""Bóc JSON object khỏi output LLM. Hạ tầng thuần, không biết field/bệnh nào.

VÌ SAO TÁCH RA (§9 P5 mục 2). Hàm này ra đời trong `src/services/agents/intake_agent.py` - agent
intake CŨ, không còn nằm trên luồng UI. Luồng chuẩn (`symptom_protocol/intake_agent.py`) vẫn phải
`from src.services.agents.intake_agent import _parse_json_object`, nên xoá agent cũ là app không
import nổi. Đó là một phụ thuộc ngược: module đang sống phụ thuộc vào module chờ khai tử.

Dời ra `infra/` để việc dọn dẹp legacy sau này chỉ còn là xoá file, không phải gỡ một sợi dây."""

from __future__ import annotations

import json
import re

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(raw: str) -> dict:
    """Bóc JSON object khỏi output LLM (chịu được ```json fence và chữ thừa xung quanh).

    Ném `json.JSONDecodeError` khi không có gì bóc được - caller quyết định lỗi parse nghĩa là gì,
    vì "không trích được field nào" và "model chết" cần hai cách xử lý khác nhau. Trả `{}` khi JSON
    hợp lệ nhưng không phải object (model trả list/số): đó là output sai hợp đồng chứ không phải lỗi
    cú pháp, và caller không có gì để đọc từ nó."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(cleaned)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    return parsed if isinstance(parsed, dict) else {}

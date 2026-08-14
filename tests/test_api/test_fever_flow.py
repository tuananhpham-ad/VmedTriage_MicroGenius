"""Checkpoint 6(a) (_guidance/fever-detect-agent-task.md Bước 6) — end-to-end qua API thật, LLM mock.

LLM thật không dùng ở đây (CI không key, không xác định) - `provider_router.complete` được thay bằng
một "LLM có kịch bản": đọc field nào đang được hỏi từ chính system prompt thật mà `fever_intake_agent`
sinh ra (không cheat bằng cách biết trước thứ tự cụm), rồi trả đúng giá trị field đó từ dữ liệu case
gốc (`tests/fixtures/fever/part8_cases.json`). Đây vẫn là kiểm tra thật của toàn bộ pipeline API +
session + state machine + rule engine - chỉ có "trí tuệ ngôn ngữ" của LLM là được thay bằng tra bảng.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src import paths
from src.main import app
from src.services.engines.fever_protocol import FEVER_PROTOCOL
from src.services.infra import provider_router

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "fever" / "part8_cases.json"
PART8_CASES = {case["case_id"]: case for case in json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))}

_FIELD_KEY_RE = re.compile(r"^- (\w+) \(", re.MULTILINE)


class _ScriptedProvider:
    """LLM giả lập tra bảng theo field key thấy trong prompt thật - không hard-code thứ tự cụm.

    Field tri-state KHÔNG có trong `known` được trả `"false"`, không phải bỏ trống. Đây là mô hình
    đúng của ca gốc Part 8: bản ghi case chỉ liệt kê những gì CÓ, nên với ca lành tính (H1/V1) mọi
    red flag không được liệt kê nghĩa là người bệnh đã trả lời "không có" - đúng những gì một người
    bệnh thật đáp lại câu hỏi sàng lọc. Bản cũ để trống hết, tức mô phỏng một người KHÔNG BAO GIỜ phủ
    định điều gì: cụm nào cũng "chưa thu được gì" nên bị hỏi lại tới hạn mức, ca lành tính không bao
    giờ kết thúc nổi (và H1 cũng không thể đạt SELF_CARE, vì checklist tự chăm sóc đòi red flag phải
    ÂM TÍNH chứ không phải chưa biết).

    Field enum/số không có trong `known` vẫn để trống - không bịa được giá trị cụ thể thay người bệnh.
    """

    def __init__(self, known: dict[str, object]) -> None:
        self.known = known
        self.call_count = 0

    def __call__(self, messages, *, credential=None, temperature=None, max_attempts=3):
        self.call_count += 1
        system = messages[0]["content"]
        field_keys = _FIELD_KEY_RE.findall(system)

        if "Hãy diễn đạt lại Ý CẦN HỎI" in system:
            text = "Dạ mình xin phép hỏi thêm ạ?"
        elif field_keys:
            extracted = {key: self._value_for(key) for key in field_keys if self._value_for(key) is not None}
            if "BƯỚC 2 - HỎI TIẾP" in system:
                text = json.dumps({"extracted": extracted, "next_question": "Dạ mình hỏi tiếp nhé?"})
            else:
                text = json.dumps(extracted)
        else:
            text = "{}"

        return provider_router.CompletionResult(text=text, provider="scripted", model="scripted")

    def _value_for(self, key: str) -> object:
        value = self.known.get(key)
        if value is None:
            spec = FEVER_PROTOCOL.fields_by_key.get(key)
            return "false" if spec is not None and spec.tri_state else None
        if isinstance(value, bool):
            return "true" if value else "false"
        return value


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _drive_conversation(client: AsyncClient, case_id: str, *, max_turns: int = 60) -> dict:
    known_fields = PART8_CASES[case_id]["fields"]
    scripted = _ScriptedProvider(known_fields)
    import src.services.infra.provider_router as provider_router_module

    original_complete = provider_router_module.complete
    provider_router_module.complete = scripted
    try:
        response = await client.post("/api/v1/fever/sessions", json=None)
        assert response.status_code == 201, response.text
        body = response.json()
        session_id = body["session_id"]

        turns = 0
        while body["state"] == "collecting" and turns < max_turns:
            response = await client.post(
                f"/api/v1/fever/sessions/{session_id}/messages", json={"message": "vâng ạ"}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            turns += 1
            # Phiên còn chạy thì PHẢI có câu hỏi. Lỗi thật đo được khi chạy LLM thật: cụm cuối của
            # stage vừa được trả lời -> `run_turn` trả câu hỏi rỗng, session âm thầm nhảy sang cụm
            # đầu stage sau. Người bệnh nhận tin nhắn trống nhưng lượt kế tiếp vẫn bị trích theo
            # schema của cụm chưa từng được hỏi (5/40 lượt của ca lành tính rơi vào đúng cảnh này).
            if body["state"] == "collecting":
                assert body["next_question"], f"{case_id}: lượt {turns} trả câu hỏi RỖNG - {body}"

        assert turns < max_turns, f"{case_id}: hội thoại không kết thúc sau {max_turns} lượt - {body}"
        body["_turns"] = turns
        return body
    finally:
        provider_router_module.complete = original_complete


# --- 3 ca đại diện 3 mức triage ------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2_seizure_case_reaches_emergency(client):
    body = await _drive_conversation(client, "E2")
    assert body["state"] == "emergency"
    assert body["triage_level"] == "EMERGENCY"
    assert "R-E-02" in body["triggered_rules"]
    # §6.5 mô tả 3-6 câu là khoảng ĐIỂN HÌNH cho EMERGENCY chốt sớm ở Stage 3A - phát hiện nhanh hơn
    # (kể cả ngay lượt đầu, nếu người dùng tự mô tả red-flag từ tin nhắn đầu tiên như ca E2 gốc) an
    # toàn hơn, không phải vi phạm; chỉ trần TRÊN (không vượt quá 6) mới là ràng buộc thật sự.
    assert body["_turns"] <= 6, body


@pytest.mark.asyncio
async def test_v1_infant_temp_case_reaches_early_visit(client):
    body = await _drive_conversation(client, "V1")
    assert body["state"] == "awaiting_confirmation"
    assert body["triage_level"] == "EARLY_VISIT"


@pytest.mark.asyncio
async def test_h1_toddler_case_reaches_self_care(client):
    body = await _drive_conversation(client, "H1")
    assert body["state"] == "awaiting_confirmation"
    assert body["triage_level"] == "SELF_CARE"


# --- contract & log --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_contract_matches_fever_session_response_model(client):
    from src.models.fever_api import FeverSessionResponse

    body = await _drive_conversation(client, "E2")
    body.pop("_turns")
    FeverSessionResponse.model_validate(body)  # raise nếu thiếu/lệch kiểu field


@pytest.mark.asyncio
async def test_session_log_directory_has_expected_stage_files(client, tmp_path):
    from src.services.infra import fever_stage_log

    body = await _drive_conversation(client, "E2")
    session_id = body["session_id"]

    directory = fever_stage_log.session_dir(session_id)
    assert directory.exists()
    assert (directory / "session.json").exists()
    stage_files = list(directory.glob("stage-*.jsonl"))
    assert stage_files

    snapshot = fever_stage_log.read_session(session_id)
    assert snapshot["triage_level"] == "EMERGENCY"


@pytest.mark.asyncio
async def test_empty_message_returns_400(client):
    response = await client.post("/api/v1/fever/sessions", json=None)
    session_id = response.json()["session_id"]
    response = await client.post(f"/api/v1/fever/sessions/{session_id}/messages", json={"message": "   "})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_unknown_session_returns_404(client):
    response = await client.get("/api/v1/fever/sessions/does-not-exist")
    assert response.status_code == 404

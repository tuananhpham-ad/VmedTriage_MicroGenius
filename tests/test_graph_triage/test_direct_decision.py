from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.config import get_settings
from src.graph_triage.agent import direct_decision


def _response(label: str, *, evidence: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "triage_label": label,
            "decision_summary": "Đau ngực dữ dội cần được đánh giá ngay.",
            "evidence": evidence or [],
        })))]
    )


def test_direct_classifier_validates_structured_label(monkeypatch):
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _response("cap_cuu")

    monkeypatch.setattr(
        direct_decision,
        "OpenAI",
        lambda api_key: SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
    )
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-key")

    assert direct_decision.classify_direct("Đau ngực dữ dội.", "gpt-4o-mini") == "cap_cuu"
    assert captured["temperature"] == 0
    assert captured["response_format"]["type"] == "json_schema"


def test_direct_decision_keeps_only_evidence_from_the_summary(monkeypatch):
    class _Completions:
        def create(self, **kwargs):
            return _response("cap_cuu", evidence=[
                {"concept": "đau ngực", "status": "present", "source_span": "Đau ngực dữ dội"},
            ])

    monkeypatch.setattr(
        direct_decision,
        "OpenAI",
        lambda api_key: SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
    )
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-key")

    result = direct_decision.decide_direct("Đau ngực dữ dội.", "gpt-4o-mini")

    assert result["triage_label"] == "cap_cuu"
    assert result["evidence"][0]["source_span"] == "Đau ngực dữ dội"


def test_direct_classifier_rejects_unknown_label(monkeypatch):
    class _Completions:
        def create(self, **kwargs):
            return _response("khong_hop_le")

    monkeypatch.setattr(
        direct_decision,
        "OpenAI",
        lambda api_key: SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
    )
    monkeypatch.setattr(get_settings(), "openai_api_key", "test-key")

    with pytest.raises(ValueError, match="unsupported label"):
        direct_decision.classify_direct("Đau ngực dữ dội.", "gpt-4o-mini")

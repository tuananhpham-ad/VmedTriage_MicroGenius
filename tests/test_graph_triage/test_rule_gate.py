from __future__ import annotations

from types import SimpleNamespace

from src.graph_triage.agent import rule_gate


def test_rule_gate_evaluates_only_evidence_grounded_extracted_facts(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        rule_gate.intake_agent,
        "extract_turn",
        lambda *args, **kwargs: SimpleNamespace(
            llm_ok=True,
            all_fields={"fever_reported": "true", "new_confusion": "true", "temp_c": 39.5},
        ),
    )
    monkeypatch.setattr(rule_gate.registry, "select_protocol", lambda answers: "general")

    def evaluate(protocol, answers):
        captured["protocol"] = protocol
        captured["answers"] = answers
        return SimpleNamespace(
            triage_level="EMERGENCY",
            reason_codes=("RF-05",),
            triggered_rules=("R-E-04",),
        )

    monkeypatch.setattr(rule_gate.rule_engine, "evaluate", evaluate)

    result = rule_gate.extract_and_evaluate("Người bệnh lú lẫn và sốt cao.", credential=object())

    assert result == {
        "available": True,
        "protocol": rule_gate.GENERIC_PROTOCOL.name,
        "triage_level": "EMERGENCY",
        "emergency": True,
        "reason_codes": ["RF-05"],
        "triggered_rules": ["R-E-04"],
        "answers": {"fever_reported": "true", "new_confusion": "true", "temp_c": 39.5},
    }
    assert captured["protocol"] is rule_gate.GENERIC_PROTOCOL
    assert captured["answers"]["new_confusion"] == "true"


def test_rule_gate_returns_unavailable_when_fact_extraction_fails(monkeypatch):
    monkeypatch.setattr(
        rule_gate.intake_agent,
        "extract_turn",
        lambda *args, **kwargs: SimpleNamespace(llm_ok=False, all_fields={}),
    )

    assert rule_gate.extract_and_evaluate("Không đủ dữ liệu.", credential=object()) == {
        "available": False,
        "error": "fact extraction failed",
    }

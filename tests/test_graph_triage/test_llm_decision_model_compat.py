from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.graph_triage.agent.llm_decision import ToolCallingDecisionAgent


class _FakeEnsemble:
    def decide(self, patient_text: str) -> dict:
        assert patient_text == "patient report"
        return {
            "models": {
                name: {
                    "predicted_label": "cap_cuu",
                    "probabilities": {
                        "theo_doi_tai_nha": 0.1,
                        "kham_som": 0.2,
                        "cap_cuu": 0.7,
                    },
                }
                for name in ("logreg", "bert", "fusion")
            },
            "model_disagreement": False,
            "evidence_graph": {"patient": {}, "evidence": []},
            "decision_policy": {"name": "test"},
        }


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["tool_choice"] == "required":
            tool_calls = [
                SimpleNamespace(
                    id=f"call-{index}",
                    function=SimpleNamespace(name=name, arguments="{}"),
                )
                for index, name in enumerate(
                    (
                        "get_patient_report",
                        "get_model_predictions",
                        "get_evidence_graph",
                        "get_decision_constraints",
                    ),
                    start=1,
                )
            ]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=tool_calls))]
            )

        decision = {
            "triage_label": "cap_cuu",
            "decision_summary": "summary",
            "model_agreement_summary": "agreement",
            "uncertainty_summary": "uncertainty",
            "requires_human_review": False,
            "model_assessments": [
                {"model": name, "predicted_label": "cap_cuu", "role_in_decision": "test"}
                for name in ("logreg", "bert", "fusion")
            ],
            "risk_modifiers": [],
            "evidence": [],
            "disclaimer": "not medical advice",
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(decision), tool_calls=[]))]
        )


def _agent(model: str, completions: _FakeCompletions) -> ToolCallingDecisionAgent:
    agent = object.__new__(ToolCallingDecisionAgent)
    agent.ensemble = _FakeEnsemble()
    agent.model = model
    agent.max_tokens = 1100
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return agent


@pytest.mark.parametrize(
    ("model", "expected_temperature"),
    (("gpt-5.6-luna", None), ("gpt-4o-mini", 0)),
)
def test_chat_completion_temperature_is_model_compatible(model: str, expected_temperature: int | None):
    completions = _FakeCompletions()

    result = _agent(model, completions).decide("patient report")

    assert result["llm_decision"]["triage_label"] == "cap_cuu"
    assert len(completions.calls) == 2, "one tool round followed by one structured final response"
    for request in completions.calls:
        if expected_temperature is None:
            assert "temperature" not in request
        else:
            assert request["temperature"] == expected_temperature

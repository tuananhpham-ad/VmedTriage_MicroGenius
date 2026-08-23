from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "run_graph_triage_infer.py"
SPEC = importlib.util.spec_from_file_location("run_graph_triage_infer", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _result(label: str) -> dict:
    return {
        "model_analysis": {
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
            }
        },
        "llm_decision": {"triage_label": label},
    }


def test_select_case_returns_requested_id():
    case = type("Case", (), {"case_id": "semigran_37"})()

    assert runner.select_case([case], "semigran_37") is case


def test_select_case_rejects_missing_id():
    case = type("Case", (), {"case_id": "semigran_37"})()

    with pytest.raises(ValueError, match="id='semigran_99'"):
        runner.select_case([case], "semigran_99")


def test_parse_args_accepts_model_ablation_flags():
    args = runner.parse_args(["--id", "semigran_37", "--skip-bert", "--skip-fusion"])

    assert args.skip_bert is True
    assert args.skip_fusion is True


def test_build_payload_contains_case_metadata_and_prediction():
    case = type(
        "Case",
        (),
        {
            "case_id": "semigran_37",
            "patient_text": "Trẻ bị ong đốt.",
            "expected_label_vi": "Tự theo dõi",
        },
    )()

    payload = runner.build_payload(case, _result("theo_doi_tai_nha"))

    assert payload["id"] == "semigran_37"
    assert payload["predicted_urgency_level_vi"] == "Tự theo dõi"
    assert payload["is_correct"] is True
    assert len(payload["model_probability_summary"]) == 3

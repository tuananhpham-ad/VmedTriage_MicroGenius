from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "eval" / "scripts" / "run_graph_triage_eval.py"
SPEC = importlib.util.spec_from_file_location("run_graph_triage_eval", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _write_cases(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def _result(label: str, models: set[str] | None = None) -> dict:
    model_names = models or {"logreg", "bert", "fusion"}
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
                for name in model_names
            }
        },
        "llm_decision": {"triage_label": label},
    }


def test_load_cases_reads_vietnamese_text_and_label(tmp_path):
    path = tmp_path / "cases.jsonl"
    _write_cases(
        path,
        [
            {"id": "case-1", "case_description_vi": "Đau ngực dữ dội", "urgency_level_vi": "Cấp cứu"},
            {"id": "case-2", "case_description_vi": "Ho nhẹ", "urgency_level_vi": "Tự theo dõi"},
        ],
    )

    cases = runner.load_cases(path, limit=1)

    assert cases == [runner.SemigranCase("case-1", "Đau ngực dữ dội", "Cấp cứu")]


def test_load_cases_rejects_unknown_urgency_label(tmp_path):
    path = tmp_path / "cases.jsonl"
    _write_cases(
        path,
        [{"id": "case-1", "case_description_vi": "Đau ngực", "urgency_level_vi": "Không rõ"}],
    )

    with pytest.raises(ValueError, match="unsupported urgency_level_vi"):
        runner.load_cases(path)


def test_final_label_requires_all_three_models():
    with pytest.raises(ValueError, match="Expected predictions"):
        runner.final_label_vi(_result("cap_cuu", {"logreg", "bert"}))


def test_run_cases_prints_accuracy_and_counts_failures_as_incorrect():
    cases = [
        runner.SemigranCase("correct", "report 1", "Cấp cứu"),
        runner.SemigranCase("wrong", "report 2", "Khám sớm"),
        runner.SemigranCase("failure", "report 3", "Tự theo dõi"),
    ]

    class FakeAgent:
        def decide(self, patient_text: str) -> dict:
            if patient_text == "report 1":
                return _result("cap_cuu")
            if patient_text == "report 2":
                return _result("theo_doi_tai_nha")
            raise RuntimeError("fake API failure")

    output = io.StringIO()
    concise_output = io.StringIO()
    probability_output = io.StringIO()
    summary = runner.run_cases(
        cases,
        FakeAgent(),
        output,
        concise_stream=concise_output,
        probability_stream=probability_output,
    )

    assert summary == runner.EvalSummary(total=3, correct=1, failures=1)
    assert summary.accuracy_percent == pytest.approx(100 / 3)
    rendered = output.getvalue()
    assert "correct: thật=Cấp cứu | đoán=Cấp cứu | ĐÚNG" in rendered
    assert "wrong: thật=Khám sớm | đoán=Tự theo dõi | SAI" in rendered
    assert "failure: LỖI (RuntimeError: fake API failure)" in rendered
    assert "Đúng: 1/3" in rendered
    assert "Accuracy: 33.33%" in rendered
    assert "Lỗi inference: 1" in rendered
    assert concise_output.getvalue() == rendered
    probability_rendered = probability_output.getvalue()
    assert "LogReg: Tự theo dõi=10.00% | Khám sớm=20.00% | Cấp cứu=70.00% | chọn=Cấp cứu" in probability_rendered
    assert "PhoBERT: Tự theo dõi=10.00% | Khám sớm=20.00% | Cấp cứu=70.00% | chọn=Cấp cứu" in probability_rendered
    assert "Fusion (PhoBERT+HGT): Tự theo dõi=10.00% | Khám sớm=20.00% | Cấp cứu=70.00% | chọn=Cấp cứu" in probability_rendered
    assert "Accuracy: 33.33%" in probability_rendered

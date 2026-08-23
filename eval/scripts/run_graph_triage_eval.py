"""Run end-to-end graph-triage inference on the Vietnamese Semigran cases."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import get_settings  # noqa: E402

EXPECTED_VI_TO_INTERNAL = {
    "Tự theo dõi": "theo_doi_tai_nha",
    "Khám sớm": "kham_som",
    "Cấp cứu": "cap_cuu",
}
INTERNAL_TO_EXPECTED_VI = {value: key for key, value in EXPECTED_VI_TO_INTERNAL.items()}
REQUIRED_MODELS = ("logreg", "bert", "fusion")
ALL_KNOWN_MODELS = frozenset(REQUIRED_MODELS)  # tập đầy đủ để validate tên model
MODEL_DISPLAY_NAMES = {
    "logreg": "LogReg",
    "bert": "PhoBERT",
    "fusion": "Fusion (PhoBERT+HGT)",
}


@dataclass(frozen=True)
class SemigranCase:
    case_id: str
    patient_text: str
    expected_label_vi: str


@dataclass(frozen=True)
class EvalSummary:
    total: int
    correct: int
    failures: int

    @property
    def accuracy_percent(self) -> float:
        return 100.0 * self.correct / self.total if self.total else 0.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run case_description_vi through DeepSeek graph extraction, three local models, "
            "and GPT-4o-mini; compare the final label with urgency_level_vi."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("data/semigran_vignettes_vi.jsonl"),
        help="Vietnamese Semigran JSONL input.",
    )
    parser.add_argument("--limit", type=int, help="Run only the first N cases for a low-cost smoke test.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--model",
        default=get_settings().openai_model_name,
        help="OpenAI decision model; defaults to OPENAI_MODEL_NAME from .env.",
    )
    parser.add_argument("--max-length", type=int, default=256, help="Maximum PhoBERT input length.")
    parser.add_argument("--max-tokens", type=int, default=1100, help="Maximum tokens for each GPT response.")
    parser.add_argument(
        "--skip-bert", action="store_true",
        help="Exclude PhoBERT from the ensemble.",
    )
    parser.add_argument(
        "--skip-fusion", action="store_true",
        help="Exclude PhoBERT+HGT fusion from the ensemble.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval_result.txt"),
        help="Concise UTF-8 result file.",
    )
    parser.add_argument(
        "--probability-output",
        type=Path,
        default=Path("eval_result_probabilities.txt"),
        help="UTF-8 result file containing probabilities from all three local models.",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=Path("eval/results/graph_triage_records.jsonl"),
        help="Bản ghi ĐẦY ĐỦ từng ca (kèm requires_human_review, risk_modifiers, evidence). "
             "Mở chế độ APPEND và dùng để resume: ca đã 'ok' sẽ không gọi API lại.",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive.")
    if args.max_length < 1 or args.max_tokens < 1:
        parser.error("--max-length and --max-tokens must be positive.")
    return args


def load_cases(path: Path, limit: int | None = None) -> list[SemigranCase]:
    if not path.is_file():
        raise FileNotFoundError(f"Semigran cases file not found: {path}")

    cases: list[SemigranCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on line {line_number} of {path}: {error}") from error

        case_id = str(record.get("id") or "").strip()
        patient_text = str(record.get("case_description_vi") or "").strip()
        expected_label_vi = str(record.get("urgency_level_vi") or "").strip()
        if not case_id:
            raise ValueError(f"Missing id on line {line_number} of {path}.")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case id {case_id!r} in {path}.")
        if not patient_text:
            raise ValueError(f"Case {case_id!r} has an empty case_description_vi.")
        if expected_label_vi not in EXPECTED_VI_TO_INTERNAL:
            raise ValueError(
                f"Case {case_id!r} has unsupported urgency_level_vi={expected_label_vi!r}; "
                f"expected one of {sorted(EXPECTED_VI_TO_INTERNAL)}."
            )

        seen_ids.add(case_id)
        cases.append(SemigranCase(case_id, patient_text, expected_label_vi))

    if not cases:
        raise ValueError(f"No usable Semigran cases found in {path}.")
    return cases[:limit] if limit is not None else cases


def build_agent(args: argparse.Namespace) -> Any:
    """Load the selected local models once and enable live DeepSeek graph extraction."""
    import torch

    from src.graph_triage.agent.decision import (
        BertPredictor,
        DecisionAgent,
        FusionPredictor,
        GraphResolver,
        LogRegPredictor,
    )
    from src.graph_triage.agent.llm_decision import ToolCallingDecisionAgent

    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    device = torch.device(device_name)

    ensemble = DecisionAgent(
        logreg=LogRegPredictor(Path("runs/logreg_full/model.joblib")),
        bert=None if args.skip_bert else BertPredictor(Path("runs/bert_full/model"), device, args.max_length),
        graph_resolver=GraphResolver(None, allow_live_extraction=True),
        fusion=None if args.skip_fusion else FusionPredictor(Path("runs/fusion_full"), device),
    )
    return ToolCallingDecisionAgent(ensemble, model=args.model, max_tokens=args.max_tokens)


def final_label_vi(result: dict[str, Any]) -> str:
    _required_model_results(result)
    decision = result.get("llm_decision")
    if not isinstance(decision, dict):
        raise ValueError("Inference result is missing llm_decision.")
    internal_label = decision.get("triage_label")
    try:
        return INTERNAL_TO_EXPECTED_VI[internal_label]
    except KeyError as error:
        raise ValueError(f"GPT returned unsupported triage_label={internal_label!r}.") from error


def _required_model_results(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    analysis = result.get("model_analysis")
    if not isinstance(analysis, dict) or not isinstance(analysis.get("models"), dict):
        raise ValueError("Inference result is missing model_analysis.models.")
    models = analysis["models"]
    model_names = set(models)
    if not model_names or not model_names.issubset(ALL_KNOWN_MODELS):
        raise ValueError(f"Unexpected model names in result: {sorted(model_names)}; known={sorted(ALL_KNOWN_MODELS)}.")
    return models


def model_probability_lines(result: dict[str, Any]) -> list[str]:
    models = _required_model_results(result)
    lines = []
    for model_name in (name for name in REQUIRED_MODELS if name in models):
        model_result = models[model_name]
        probabilities = model_result.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != set(INTERNAL_TO_EXPECTED_VI):
            raise ValueError(f"Model {model_name!r} returned an invalid probability layout.")
        predicted_label = model_result.get("predicted_label")
        if predicted_label not in INTERNAL_TO_EXPECTED_VI:
            raise ValueError(f"Model {model_name!r} returned unsupported predicted_label={predicted_label!r}.")

        probability_text = " | ".join(
            f"{INTERNAL_TO_EXPECTED_VI[label]}={float(probabilities[label]) * 100:.2f}%"
            for label in INTERNAL_TO_EXPECTED_VI
        )
        lines.append(
            f"  {MODEL_DISPLAY_NAMES[model_name]}: {probability_text} | "
            f"chọn={INTERNAL_TO_EXPECTED_VI[predicted_label]}"
        )
    return lines


def load_completed(path: Path | None) -> dict[str, dict[str, Any]]:
    """Đọc JSONL đã có để bỏ qua ca đã chạy. Bản ghi CUỐI thắng (ca thử lại ghi thêm dòng mới).

    Không có lớp này thì mỗi lần ngắt giữa chừng là mất toàn bộ tiền đã tiêu: một lượt đầy đủ tốn
    ~45 lời gọi DeepSeek cộng ~180 lời gọi gpt-4o-mini.
    """
    if path is None or not path.is_file():
        return {}
    done: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            done[record["case_id"]] = record
    return done


def structured_record(case: SemigranCase, result: dict[str, Any], predicted_vi: str) -> dict[str, Any]:
    """Bản ghi ĐẦY ĐỦ cho một ca. Bản text chỉ giữ nhãn, nên mọi phân tích sau đó phải regex ngược
    và những trường quan trọng nhất - `requires_human_review`, `risk_modifiers`, `evidence` - thì
    mất hẳn. Đây là chỗ giữ chúng lại."""
    decision = result.get("llm_decision") or {}
    analysis = result.get("model_analysis") or {}
    return {
        "case_id": case.case_id,
        "status": "ok",
        "expected_vi": case.expected_label_vi,
        "predicted_vi": predicted_vi,
        "correct": predicted_vi == case.expected_label_vi,
        "triage_label": decision.get("triage_label"),
        "requires_human_review": decision.get("requires_human_review"),
        "risk_modifiers": decision.get("risk_modifiers", []),
        "evidence": decision.get("evidence", []),
        "decision_summary": decision.get("decision_summary"),
        "model_agreement_summary": decision.get("model_agreement_summary"),
        "uncertainty_summary": decision.get("uncertainty_summary"),
        "model_assessments": decision.get("model_assessments", []),
        "model_disagreement": analysis.get("model_disagreement"),
        "models": {
            name: {"predicted_label": item.get("predicted_label"), "probabilities": item.get("probabilities")}
            for name, item in (analysis.get("models") or {}).items()
        },
        "tool_audit": result.get("tool_audit"),
    }


def _print_to_streams(line: str, *streams: TextIO | None) -> None:
    seen: set[int] = set()
    for target in streams:
        if target is None or id(target) in seen:
            continue
        seen.add(id(target))
        print(line, file=target, flush=True)


def run_cases(
    cases: list[SemigranCase],
    agent: Any,
    stream: TextIO = sys.stdout,
    concise_stream: TextIO | None = None,
    probability_stream: TextIO | None = None,
    jsonl_sink: TextIO | None = None,
    completed: dict[str, dict[str, Any]] | None = None,
) -> EvalSummary:
    correct = 0
    failures = 0
    total = len(cases)
    completed = completed or {}

    for index, case in enumerate(cases, start=1):
        prior = completed.get(case.case_id)
        if prior is not None and prior.get("status") == "ok":
            # Ca đã chạy xong ở lượt trước: in lại từ bản ghi, KHÔNG gọi API lần nữa.
            correct += int(prior["correct"])
            _print_to_streams(
                f"[{index:02d}/{total:02d}] {case.case_id}: thật={prior['expected_vi']} | "
                f"đoán={prior['predicted_vi']} | {'ĐÚNG' if prior['correct'] else 'SAI'}  (đã có)",
                stream, concise_stream, probability_stream,
            )
            continue
        try:
            result = agent.decide(case.patient_text)
            predicted_label_vi = final_label_vi(result)
            probability_lines = model_probability_lines(result)
            matched = predicted_label_vi == case.expected_label_vi
            correct += int(matched)
            if jsonl_sink is not None:
                jsonl_sink.write(json.dumps(structured_record(case, result, predicted_label_vi),
                                            ensure_ascii=False) + "\n")
                jsonl_sink.flush()
            verdict = "ĐÚNG" if matched else "SAI"
            concise_line = (
                f"[{index:02d}/{total:02d}] {case.case_id}: "
                f"thật={case.expected_label_vi} | đoán={predicted_label_vi} | {verdict}"
            )
            _print_to_streams(concise_line, stream, concise_stream, probability_stream)
            for line in probability_lines:
                _print_to_streams(line, probability_stream)
        except Exception as error:
            failures += 1
            if jsonl_sink is not None:
                jsonl_sink.write(json.dumps({
                    "case_id": case.case_id, "status": "failed",
                    "expected_vi": case.expected_label_vi,
                    "error": f"{type(error).__name__}: {error}",
                }, ensure_ascii=False) + "\n")
                jsonl_sink.flush()
            error_line = (
                f"[{index:02d}/{total:02d}] {case.case_id}: LỖI "
                f"({type(error).__name__}: {error})"
            )
            _print_to_streams(error_line, stream, concise_stream, probability_stream)

    summary = EvalSummary(total=total, correct=correct, failures=failures)
    scored = total - failures
    for line in (
        "",
        f"Đúng: {summary.correct}/{summary.total}",
        f"Accuracy: {summary.accuracy_percent:.2f}%",
        # Hai mẫu số, cố ý: ca LỖI không có nhãn nên gộp nó vào "sai" là trộn hai loại thất bại
        # khác hẳn nhau. Bản cũ chỉ in dòng trên, và 16/45=35,6% đã bị đọc nhầm thành 16/40=40%.
        f"Accuracy (chỉ ca chấm được): {100.0 * summary.correct / scored if scored else 0.0:.2f}% "
        f"({summary.correct}/{scored})",
        f"Lỗi inference: {summary.failures}",
    ):
        _print_to_streams(line, stream, concise_stream, probability_stream)
    return summary


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    if args.output.resolve() == args.probability_output.resolve():
        raise ValueError("--output and --probability-output must be different files.")
    cases = load_cases(args.cases, args.limit)
    completed = load_completed(args.jsonl_output)
    if completed:
        print(f"Tìm thấy {len(completed)} ca đã chạy trong {args.jsonl_output}; sẽ bỏ qua chúng.")
    agent = build_agent(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.probability_output.parent.mkdir(parents=True, exist_ok=True)
    # Dòng đầu ghi RUN ID + model: hai file output cũ không mang dấu vết nào của lượt sinh ra chúng,
    # nên khi chúng mâu thuẫn nhau thì không ai biết là của hai lượt khác nhau.
    skipped = [name for name, enabled in (("bert", args.skip_bert), ("fusion", args.skip_fusion)) if enabled]
    header = (f"# run={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} model={args.model} "
              f"cases={len(cases)} max_length={args.max_length}"
              + (f" skip={','.join(skipped)}" if skipped else ""))
    with (
        args.output.open("w", encoding="utf-8", newline="\n") as concise_stream,
        args.probability_output.open("w", encoding="utf-8", newline="\n") as probability_stream,
    ):
        _print_to_streams(header, sys.stdout, concise_stream, probability_stream)
        if args.jsonl_output is not None:
            args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
            with args.jsonl_output.open("a", encoding="utf-8", newline="\n") as jsonl_sink:
                run_cases(cases, agent, concise_stream=concise_stream,
                          probability_stream=probability_stream, jsonl_sink=jsonl_sink,
                          completed=completed)
        else:
            run_cases(cases, agent, concise_stream=concise_stream,
                      probability_stream=probability_stream, completed=completed)
    print(f"Đã ghi kết quả gọn: {args.output}")
    print(f"Đã ghi kết quả xác suất: {args.probability_output}")
    if args.jsonl_output is not None:
        print(f"Đã ghi bản ghi đầy đủ: {args.jsonl_output}")


if __name__ == "__main__":
    main()

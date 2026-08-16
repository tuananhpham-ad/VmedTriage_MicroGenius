"""Model loading, probability ensemble, and evidence-grounded explanations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import torch
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from src.graph_triage.graph_schema import ClinicalGraph, validate_provenance
from src.graph_triage.labels import TRIAGE_LABELS

# `patient_graph` và `train_fusion` chỉ cần cho FusionPredictor, và `train_fusion` kéo theo cả
# scikit-learn/pandas qua `common.py`. Import chúng trong `FusionPredictor.__init__` để đường
# inference logreg + bert (Phần A, chưa có fusion) không phụ thuộc stack huấn luyện.

TRIAGE_DISPLAY = {
    "theo_doi_tai_nha": "Theo dõi tại nhà",
    "kham_som": "Khám sớm",
    "cap_cuu": "Cấp cứu",
}
MODEL_CARDS = {
    "logreg": {
        "architecture": "Character word-boundary TF-IDF + class-balanced Logistic Regression",
        "strengths": ["robust to Vietnamese spelling variation and short lexical cues", "fast, deterministic probability baseline"],
        "limitations": ["does not model long-range context", "does not use clinical entities, negation relations, or provenance graph"],
    },
    "bert": {
        "architecture": "PhoBERT sequence classifier over patient text",
        "strengths": ["uses contextual Vietnamese text representation", "can combine clues appearing across the input sequence"],
        "limitations": ["does not expose an explicit clinical evidence graph", "input is truncated to configured maximum length"],
    },
    "fusion": {
        "architecture": "PhoBERT document embedding + HGT Patient Graph embedding through a learned gate",
        "strengths": ["uses both text context and typed evidence/relation structure", "graph evidence is provenance-auditable"],
        "limitations": ["depends on graph extraction and concept normalization quality", "a graph-cache miss needs explicit live extraction before it can run"],
    },
}


def _softmax(logits: torch.Tensor) -> np.ndarray:
    return torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()


def _model_probabilities(values: np.ndarray) -> dict[str, float]:
    return {label: float(values[index]) for index, label in enumerate(TRIAGE_LABELS)}


def _load_metrics(path: Path) -> dict:
    if not path.is_file():
        return {"available": False, "warning": f"metrics.json was not found at {path}"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    evaluation = payload.get("evaluation") or payload.get("train")
    return {"available": True, "evaluation_scope": payload.get("setup", {}).get("evaluation", "unknown"), "metrics": evaluation.get("metrics") if evaluation else None}


class LogRegPredictor:
    def __init__(self, model_path: Path):
        if not model_path.is_file():
            raise FileNotFoundError(f"Logistic Regression model not found: {model_path}")
        self.model = joblib.load(model_path)
        self.metrics = _load_metrics(model_path.parent / "metrics.json")
        if not hasattr(self.model, "predict_proba"):
            raise TypeError("The supplied Logistic Regression artifact has no predict_proba method.")

    def predict(self, text: str) -> np.ndarray:
        probabilities = np.asarray(self.model.predict_proba([text])[0], dtype=float)
        if probabilities.shape != (len(TRIAGE_LABELS),):
            raise ValueError("Logistic Regression class layout does not match the triage labels.")
        return probabilities


class BertPredictor:
    def __init__(self, model_dir: Path, device: torch.device, max_length: int):
        if not model_dir.is_dir():
            raise FileNotFoundError(f"PhoBERT model directory not found: {model_dir}")
        self.device, self.max_length = device, max_length
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device).eval()
        self.metrics = _load_metrics(model_dir.parent / "metrics.json")
        if self.model.config.num_labels != len(TRIAGE_LABELS):
            raise ValueError("PhoBERT artifact does not have three triage labels.")

    def predict(self, text: str) -> np.ndarray:
        encoded = self.tokenizer(text, truncation=True, max_length=self.max_length, return_tensors="pt")
        with torch.inference_mode():
            return _softmax(self.model(**{name: value.to(self.device) for name, value in encoded.items()}).logits)


class GraphResolver:
    """Resolve a graph from the v1 cache; live extraction is explicitly opt-in."""

    def __init__(self, graph_cache: Path | None, allow_live_extraction: bool):
        self.allow_live_extraction = allow_live_extraction
        self.graph_by_text_hash: dict[str, ClinicalGraph] = {}
        if graph_cache is not None:
            if not graph_cache.is_file():
                raise FileNotFoundError(f"Patient Graph cache not found: {graph_cache}")
            for line in graph_cache.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                graph = ClinicalGraph.model_validate(record["graph"])
                self.graph_by_text_hash[record["text_sha256"]] = graph

    def resolve(self, text: str) -> ClinicalGraph:
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        graph = self.graph_by_text_hash.get(fingerprint)
        if graph is not None:
            validate_provenance(graph, text)
            return graph
        if not self.allow_live_extraction:
            raise ValueError("No exact patient-text match in the graph cache. Use a golden.csv patient text or pass --allow-live-extraction (this calls DeepSeek API).")
        from src.graph_triage.deepseek_extractor import DeepSeekExtractor
        return DeepSeekExtractor().extract(text)


class FusionPredictor:
    def __init__(self, model_dir: Path, device: torch.device):
        from src.graph_triage.patient_graph import PatientGraphBuilder
        from src.graph_triage.train_fusion import GatedFusionClassifier

        checkpoint_path, encoder_dir = model_dir / "model.pt", model_dir / "text_encoder"
        if not checkpoint_path.is_file() or not encoder_dir.is_dir():
            raise FileNotFoundError(f"Fusion artifact requires {checkpoint_path} and {encoder_dir}")
        checkpoint = torch.load(checkpoint_path, map_location=device)
        required = {"text_channels", "hidden_channels", "fusion_channels", "heads", "layers", "dropout", "max_length", "model_state_dict"}
        if missing := required.difference(checkpoint):
            raise ValueError(f"Fusion artifact is missing {sorted(missing)}. Retrain it with the current train_fusion.py.")
        self.device, self.max_length = device, int(checkpoint["max_length"])
        self.tokenizer = AutoTokenizer.from_pretrained(encoder_dir)
        encoder = AutoModel.from_pretrained(encoder_dir)
        self.model = GatedFusionClassifier(
            encoder, checkpoint["text_channels"], checkpoint["hidden_channels"], checkpoint["fusion_channels"],
            checkpoint["heads"], checkpoint["layers"], checkpoint["dropout"],
        ).to(device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.graph_builder = PatientGraphBuilder()
        self.metrics = _load_metrics(model_dir / "metrics.json")

    def predict(self, text: str, graph: ClinicalGraph) -> tuple[np.ndarray, float]:
        try:
            from torch_geometric.data import Batch
        except ImportError as error:
            raise RuntimeError("Fusion inference requires torch-geometric. Run: pip install -r requirements.txt") from error
        encoded = self.tokenizer(text, truncation=True, max_length=self.max_length, return_tensors="pt")
        batch = Batch.from_data_list([self.graph_builder.build(graph)]).to(self.device)
        with torch.inference_mode():
            logits, gate = self.model({name: value.to(self.device) for name, value in encoded.items()}, batch)
        return _softmax(logits), float(gate.mean().cpu())


def _observation_summary(node, observation) -> dict:
    fields = {}
    for name in ("onset_type", "onset_text", "duration_value", "duration_unit", "progression", "frequency", "pattern", "time_pattern", "functional_impacts", "subjective_severity"):
        value = getattr(observation, name)
        if value not in (None, [], ""):
            fields[name] = value
    if details := observation.details.model_dump(exclude_none=True):
        fields["details"] = details
    return {
        "concept": node.concept,
        "canonical_name": node.canonical_name,
        "type": node.type,
        "experiencer": node.experiencer,
        "surface_form": observation.surface_form,
        "status": observation.status,
        "certainty": observation.certainty,
        "attributes": fields,
        "source_span": observation.provenance.source_span,
    }


def evidence_summary(graph: ClinicalGraph, limit: int = 16) -> list[dict]:
    evidence = []
    for node in graph.nodes:
        if node.experiencer != "target_patient":
            continue
        evidence.extend(_observation_summary(node, observation) for observation in node.observations)
    return evidence[:limit]


def relation_summary(graph: ClinicalGraph, limit: int = 16) -> list[dict]:
    """Structural relations named by concept.

    This is what the graph holds that the raw text does not hand over directly: what triggered a symptom, what
    relieved it, where it sits. ``has_*`` edges are skipped because they only restate the evidence list.
    """
    concept_by_id = {node.id: node.concept for node in graph.nodes}
    target_patient = {node.id for node in graph.nodes if node.experiencer == "target_patient"}
    relations = []
    for edge in graph.edges:
        if edge.relation.startswith("has_") or edge.source not in target_patient or edge.target not in target_patient:
            continue
        relations.append({
            "source": concept_by_id[edge.source],
            "relation": edge.relation,
            "target": concept_by_id[edge.target],
            "source_span": edge.provenance.source_span,
        })
    return relations[:limit]


@dataclass
class DecisionAgent:
    logreg: LogRegPredictor
    bert: BertPredictor
    graph_resolver: GraphResolver
    fusion: FusionPredictor | None = None
    """Optional cho tới khi ``runs/fusion_full`` được train (Phần B của kế hoạch port).

    Khi chưa có, ``decide()`` bỏ hẳn khoá ``fusion`` và ``fusion_mean_text_gate`` khỏi payload thay vì
    điền 0.0 - LLM quyết định đọc payload này như sự thật, một số giả sẽ thành "model fusion tự tin
    mức 0" chứ không phải "không có model fusion".
    """

    def decide(self, patient_text: str) -> dict:
        text = patient_text.strip()
        if not text:
            raise ValueError("patient_text must not be empty.")
        graph = self.graph_resolver.resolve(text)
        predictors = {"logreg": self.logreg, "bert": self.bert}
        probabilities = {name: predictor.predict(text) for name, predictor in predictors.items()}
        mean_text_gate = None
        if self.fusion is not None:
            predictors["fusion"] = self.fusion
            probabilities["fusion"], mean_text_gate = self.fusion.predict(text, graph)
        votes = {name: TRIAGE_LABELS[int(values.argmax())] for name, values in probabilities.items()}
        payload = {
            "research_only": True,
            "decision_policy": "LLM tool-grounded decision; no automatic probability ensemble and no clinically validated safety override",
            "model_disagreement": len(set(votes.values())) != 1,
            "models": {
                name: {
                    "predicted_label": votes[name],
                    "probabilities": _model_probabilities(probabilities[name]),
                    "model_card": MODEL_CARDS[name],
                    "run_metrics": predictor.metrics,
                }
                for name, predictor in predictors.items()
            },
            "evidence_graph": {"schema_version": graph.schema_version, "patient": graph.patient.model_dump(mode="json", exclude_none=True), "evidence": evidence_summary(graph), "relations": relation_summary(graph)},
            "explanation": "Đây là gói evidence cho LLM quyết định: từng model được giữ riêng cùng model card và metric. Evidence bên dưới chỉ trích từ Patient Graph và source span gốc; không phải diễn giải hay chẩn đoán y khoa.",
        }
        if mean_text_gate is not None:
            payload["fusion_mean_text_gate"] = mean_text_gate
        return payload

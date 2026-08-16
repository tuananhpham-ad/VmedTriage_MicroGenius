"""Convert detailed validated Patient Graph JSON into PyG HeteroData case graphs."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Iterator
from typing import Any

import torch

from src.graph_triage.graph_schema import NODE_TYPES, ClinicalGraph, Observation, edge_triples

BASE_EDGES = edge_triples()
EDGE_TYPES = BASE_EDGES + tuple((target, f"rev_{relation}", source) for source, relation, target in BASE_EDGES)

FEATURE_DIMENSION, CONCEPT_BUCKETS = 128, 64
STATUS_INDEX = {"present": 64, "absent": 65, "uncertain": 66}
CERTAINTY_INDEX = {"certain": 67, "probable": 68, "possible": 69, "uncertain": 70}
ONSET_INDEX = {"sudden": 71, "gradual": 72, "unknown": 73}
PROGRESSION_INDEX = {"worsening": 74, "stable": 75, "improving": 76, "fluctuating": 77, "unknown": 78}
DURATION_UNIT_INDEX = {"minutes": 79, "hours": 80, "days": 81, "weeks": 82, "months": 83, "years": 84}
ATTRIBUTE_BUCKET_START, ATTRIBUTE_BUCKETS = 88, 35
PATIENT_SOURCE_INDEX = {"patient": 123, "family_member": 124, "unknown": 125}


def _hash_bucket(value: str, buckets: int) -> int:
    return int.from_bytes(hashlib.blake2s(value.encode("utf-8"), digest_size=4).digest(), "little") % buckets


def _attribute_tokens(value: Any, prefix: str = "") -> Iterator[str]:
    """Feature every explicit non-provenance detail without leaking raw patient text."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"provenance", "source_span", "surface_form"} or nested is None:
                continue
            yield from _attribute_tokens(nested, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for item in value:
            yield f"{prefix}={item}"
    elif isinstance(value, bool):
        yield f"{prefix}={str(value).lower()}"
    elif isinstance(value, str):
        yield f"{prefix}={value.casefold()}"
    elif isinstance(value, (int, float)):
        yield f"{prefix}=stated"


def _feature(concept: str, observations: list[Observation] | None = None, patient=None) -> torch.Tensor:
    vector = torch.zeros(FEATURE_DIMENSION, dtype=torch.float32)
    vector[_hash_bucket(concept, CONCEPT_BUCKETS)] = 1.0
    if patient is not None:
        vector[PATIENT_SOURCE_INDEX[patient.report_source]] = 1.0
        if patient.age is not None:
            vector[126] = patient.age / 130
        vector[127] = 1.0
        return vector
    if not observations:
        return vector
    for observation in observations:
        vector[STATUS_INDEX[observation.status]] = 1.0
        vector[CERTAINTY_INDEX[observation.certainty]] = 1.0
        if observation.onset_type:
            vector[ONSET_INDEX[observation.onset_type]] = 1.0
        if observation.progression:
            vector[PROGRESSION_INDEX[observation.progression]] = 1.0
        if observation.duration_unit:
            vector[DURATION_UNIT_INDEX[observation.duration_unit]] = 1.0
        for token in _attribute_tokens(observation.model_dump(exclude_none=True)):
            vector[ATTRIBUTE_BUCKET_START + _hash_bucket(token, ATTRIBUTE_BUCKETS)] = 1.0
    current = max(enumerate(observations), key=lambda item: (item[1].provenance.source_turn, item[0]))[1]
    if current.subjective_severity is not None:
        vector[85] = current.subjective_severity / 10
    if current.onset_hours_ago is not None:
        vector[86] = min(math.log1p(current.onset_hours_ago) / math.log1p(24 * 365), 1.0)
    if current.duration_value is not None:
        vector[87] = min(math.log1p(current.duration_value) / math.log1p(365), 1.0)
    return vector


class PatientGraphBuilder:
    node_types = NODE_TYPES
    edge_types = EDGE_TYPES

    def __init__(self) -> None:
        self.edges_outside_encoder: Counter[tuple[str, str, str]] = Counter()

    def build(self, graph: ClinicalGraph, label: int | None = None):
        try:
            from torch_geometric.data import HeteroData
        except ImportError as error:
            raise RuntimeError("HGT requires torch-geometric. Install requirements first.") from error
        data = HeteroData()
        grouped = {node_type: [] for node_type in NODE_TYPES if node_type != "patient"}
        for node in graph.nodes:
            grouped[node.type].append(node)
        index = {"patient": ("patient", 0)}
        data["patient"].x = _feature("patient", patient=graph.patient).unsqueeze(0)
        for node_type, nodes in grouped.items():
            data[node_type].x = torch.stack([_feature(node.concept, node.observations) for node in nodes]) if nodes else torch.zeros((0, FEATURE_DIMENSION))
            index.update({node.id: (node_type, position) for position, node in enumerate(nodes)})
        edge_lists = {edge_type: [] for edge_type in EDGE_TYPES}
        for edge in graph.edges:
            source_type, source_index = index[edge.source]
            target_type, target_index = index[edge.target]
            edge_type = (source_type, edge.relation, target_type)
            if edge_type not in edge_lists:
                # The JSON contract allows relations the trained encoders have no slot for; keep them auditable
                # in the graph and count them here rather than dropping them without trace.
                self.edges_outside_encoder[edge_type] += 1
                continue
            edge_lists[edge_type].append((source_index, target_index))
            edge_lists[(target_type, f"rev_{edge.relation}", source_type)].append((target_index, source_index))
        for edge_type, pairs in edge_lists.items():
            data[edge_type].edge_index = torch.tensor(pairs, dtype=torch.long).t().contiguous() if pairs else torch.empty((2, 0), dtype=torch.long)
        if label is not None:
            data.y = torch.tensor([label], dtype=torch.long)
        data.validate(raise_on_error=True)
        return data

    def audit(self, graphs: list[ClinicalGraph]) -> dict:
        node_counts: Counter[str] = Counter()
        edge_counts: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()
        experiencer_counts: Counter[str] = Counter()
        concepts_by_type: dict[str, set[str]] = {node_type: set() for node_type in NODE_TYPES if node_type != "patient"}
        observations = temporal = extension = functional = 0
        for graph in graphs:
            for node in graph.nodes:
                node_counts[node.type] += 1
                experiencer_counts[node.experiencer] += 1
                concepts_by_type[node.type].add(node.concept)
                for observation in node.observations:
                    observations += 1
                    status_counts[observation.status] += 1
                    temporal += int(any((observation.onset_type, observation.onset_text, observation.onset_hours_ago, observation.duration_value, observation.progression, observation.frequency, observation.pattern, observation.time_pattern)))
                    extension += int(bool(observation.details.model_dump(exclude_none=True)))
                    functional += int(bool(observation.functional_impacts))
            edge_counts.update(edge.relation for edge in graph.edges)
        cases = len(graphs)
        return {
            "cases": cases,
            "cases_with_nodes": sum(bool(graph.nodes) for graph in graphs),
            "mean_nodes_per_case": sum(len(graph.nodes) for graph in graphs) / cases if cases else 0,
            "mean_edges_per_case": sum(len(graph.edges) for graph in graphs) / cases if cases else 0,
            "mean_observations_per_case": observations / cases if cases else 0,
            "nodes_by_type": dict(node_counts), "edges_by_relation": dict(edge_counts),
            "observations_by_status": dict(status_counts), "nodes_by_experiencer": dict(experiencer_counts),
            "unique_concepts_by_type": {node_type: len(concepts) for node_type, concepts in concepts_by_type.items()},
            "temporal_observations": temporal, "extension_observations": extension,
            "functional_impact_observations": functional,
            "edges_outside_encoder": {" ".join(edge_type): count for edge_type, count in self.edges_outside_encoder.items()},
        }

"""Auditable, event-centric Patient Graph contract derived from graph.md."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NodeType = Literal["symptom", "finding", "body_location", "condition", "risk_factor", "context"]
Status = Literal["present", "absent", "uncertain"]
Relation = Literal[
    "has_symptom", "has_finding", "has_condition", "has_risk_factor", "has_context",
    "located_at", "radiates_to", "triggered_by", "worsened_by", "relieved_by", "associated_with",
]
Experiencer = Literal["target_patient", "reporter", "other"]

NODE_TYPES = ("patient", "symptom", "finding", "body_location", "condition", "risk_factor", "context")
PATIENT_RELATION_FOR_TYPE = {
    "symptom": "has_symptom", "finding": "has_finding", "condition": "has_condition",
    "risk_factor": "has_risk_factor", "context": "has_context",
}
PATIENT_RELATION_RANGE = {relation: node_type for node_type, relation in PATIENT_RELATION_FOR_TYPE.items()}
# A finding or an established condition can carry a body location, a trigger and a co-occurrence just as a symptom can.
# A trigger is not always a context either: a febrile seizure is a symptom triggered by another symptom.
STRUCTURAL_RELATION_TYPES = {
    "located_at": (("symptom", "finding", "condition"), ("body_location",)),
    "radiates_to": (("symptom", "finding", "condition"), ("body_location",)),
    "triggered_by": (("symptom", "finding"), ("context", "symptom", "finding")),
    "worsened_by": (("symptom", "finding"), ("context", "symptom", "finding")),
    "relieved_by": (("symptom", "finding"), ("context", "symptom", "finding")),
    "associated_with": (("symptom", "finding"), ("symptom", "finding")),
}

# The subset the released HGT/fusion checkpoints were trained on. The JSON contract above is deliberately wider:
# widening it again stays backward compatible, while changing this table invalidates every trained encoder.
ENCODER_RELATION_TYPES = {
    "located_at": (("symptom", "finding", "condition"), ("body_location",)),
    "radiates_to": (("symptom", "finding", "condition"), ("body_location",)),
    "triggered_by": (("symptom", "finding"), ("context",)),
    "worsened_by": (("symptom", "finding"), ("context",)),
    "relieved_by": (("symptom", "finding"), ("context",)),
    "associated_with": (("symptom", "finding"), ("symptom", "finding")),
}


def edge_triples(relation_types: dict | None = None) -> tuple[tuple[str, str, str], ...]:
    """Every (source, relation, target) a relation table allows, as PyG edge types."""
    table = ENCODER_RELATION_TYPES if relation_types is None else relation_types
    patient_edges = tuple(("patient", relation, node_type) for relation, node_type in PATIENT_RELATION_RANGE.items())
    structural_edges = tuple(
        (source, relation, target)
        for relation, (sources, targets) in table.items()
        for source in sources
        for target in targets
    )
    return patient_edges + structural_edges


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_span: str = Field(min_length=1)
    source_turn: int = Field(default=1, ge=1)
    source_role: Literal["patient", "family_member", "unknown"] = "patient"


class PatientContext(BaseModel):
    """Only attributes explicitly stated about the triage target."""
    model_config = ConfigDict(extra="forbid")
    age: int | None = Field(default=None, ge=0, le=130)
    report_source: Literal["patient", "family_member", "unknown"] = "patient"
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def age_requires_provenance(self) -> PatientContext:
        if self.age is not None and self.provenance is None:
            raise ValueError("A stated patient age requires provenance.")
        return self


class ClinicalDetails(BaseModel):
    """Optional symptom-family extensions. Omitted means unknown, never absent."""
    model_config = ConfigDict(extra="forbid")
    character: str | None = None
    movement_related: bool | None = None
    exertional: bool | None = None
    pleuritic: bool | None = None
    positional: bool | None = None
    at_rest: bool | None = None
    speech_limitation: bool | None = None
    work_of_breathing: str | None = None
    oral_intake: str | None = None
    vomiting_frequency: str | None = None
    blood_present: bool | None = None
    stool_change: str | None = None
    ongoing: bool | None = None
    estimated_amount: str | None = None
    clots: bool | None = None
    associated_syncope: bool | None = None
    focal_deficit: bool | None = None
    speech_change: bool | None = None
    consciousness_change: bool | None = None
    seizure_activity: bool | None = None


class Observation(BaseModel):
    """One evidence-bearing mention; multiple observations preserve contradiction/timeline."""
    model_config = ConfigDict(extra="forbid")
    surface_form: str = Field(min_length=1)
    status: Status
    certainty: Literal["certain", "probable", "possible", "uncertain"] = "certain"
    onset_type: Literal["sudden", "gradual", "unknown"] | None = None
    onset_text: str | None = None
    onset_hours_ago: float | None = Field(default=None, ge=0)
    duration_value: float | None = Field(default=None, ge=0)
    duration_unit: Literal["minutes", "hours", "days", "weeks", "months", "years"] | None = None
    duration_precision: Literal["exact", "approximate"] | None = None
    progression: Literal["worsening", "stable", "improving", "fluctuating", "unknown"] | None = None
    frequency: str | None = None
    pattern: str | None = None
    time_pattern: str | None = None
    functional_impacts: list[Literal["walking_limitation", "speech_limitation", "sleep_disruption", "unable_to_eat", "unable_to_drink", "unable_to_perform_daily_activity"]] = Field(default_factory=list)
    subjective_severity: float | None = Field(default=None, ge=0, le=10)
    details: ClinicalDetails = Field(default_factory=ClinicalDetails)
    provenance: Provenance

    @field_validator("subjective_severity", mode="before")
    @classmethod
    def parse_severity_scale(cls, value: object) -> object:
        """Chấp nhận thang điểm dạng chuỗi: "7/10", "7 trên 10", "7".

        Người bệnh nói "đau 7 trên 10" thì model trích ra "7/10" chứ hiếm khi ra số trần, và
        `float("7/10")` thì hỏng - trước khi có hàm này, MỌI ca có điểm đau đều trượt validate rồi
        thất bại sau cả 3 lần retry. Chỉ nhận mẫu <số>/<mẫu số>: đây là quy đổi ĐỌC HIỂU, không phải
        đoán mò, nên bất kỳ dạng nào khác vẫn để pydantic báo lỗi như cũ.
        """
        if not isinstance(value, str):
            return value
        text = value.strip().replace(",", ".")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:/|trên|tren|out of|of)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if match:
            numerator, denominator = float(match.group(1)), float(match.group(2))
            # Chỉ quy đổi khi mẫu số là 10; thang khác (vd "3/5") đổi sang thang 10 là bịa mức độ.
            return numerator if denominator == 10 else value
        return text

    @model_validator(mode="after")
    def surface_form_is_in_evidence(self) -> Observation:
        if normalise_span(self.surface_form) not in normalise_span(self.provenance.source_span):
            raise ValueError(
                f"surface_form {self.surface_form!r} is not a contiguous substring of its source_span "
                f"{self.provenance.source_span!r}. Shorten surface_form to one unbroken fragment of that span."
            )
        if (self.duration_value is None) != (self.duration_unit is None):
            raise ValueError("duration_value and duration_unit must be supplied together.")
        return self


class ClinicalNode(BaseModel):
    """A case-specific event/instance, not a global medical-ontology node."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: NodeType
    concept: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    canonical_name: str = Field(min_length=1)
    experiencer: Experiencer = "target_patient"
    observations: list[Observation] = Field(min_length=1)

    def current_observation(self) -> Observation:
        """Latest evidence is used as a feature; full history remains in the JSON graph."""
        return max(enumerate(self.observations), key=lambda item: (item[1].provenance.source_turn, item[0]))[1]


class ClinicalEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    relation: Relation
    target: str
    provenance: Provenance


class ClinicalGraph(BaseModel):
    """Evidence-only graph. Triage labels and inferred diagnoses are not representable."""
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["patient_graph_v1"] = "patient_graph_v1"
    patient: PatientContext = Field(default_factory=PatientContext)
    nodes: list[ClinicalNode]
    edges: list[ClinicalEdge]

    @model_validator(mode="after")
    def validate_graph(self) -> ClinicalGraph:
        node_by_id = {node.id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("Node IDs must be unique.")
        patient_links: set[tuple[str, str]] = set()
        structural_targets: set[str] = set()
        for edge in self.edges:
            if edge.source == edge.target:
                raise ValueError("Self-edges are not permitted.")
            if expected_type := PATIENT_RELATION_RANGE.get(edge.relation):
                if edge.source != "patient":
                    raise ValueError(f'{edge.relation} requires source "patient" exactly, not {edge.source!r}.')
                if edge.target not in node_by_id:
                    raise ValueError(f"{edge.relation} points at {edge.target!r}, which is not a declared node id.")
                if node_by_id[edge.target].type != expected_type:
                    raise ValueError(
                        f"{edge.relation} points at {edge.target}, which has type {node_by_id[edge.target].type}. "
                        f"Use {PATIENT_RELATION_FOR_TYPE[node_by_id[edge.target].type]} for that node type instead."
                    )
                if node_by_id[edge.target].experiencer != "target_patient":
                    raise ValueError(
                        f"Node {edge.target} has experiencer={node_by_id[edge.target].experiencer}, so it cannot carry the "
                        f"{edge.relation} edge from patient. Either set experiencer to target_patient when the fact is about the "
                        "triage target, or remove the patient edge and keep the node unattached."
                    )
                patient_links.add((edge.relation, edge.target))
                continue
            if edge.source not in node_by_id or edge.target not in node_by_id:
                raise ValueError("Every non-patient edge endpoint must reference a node.")
            source_type, target_type = node_by_id[edge.source].type, node_by_id[edge.target].type
            sources, targets = STRUCTURAL_RELATION_TYPES[edge.relation]
            if source_type not in sources or target_type not in targets:
                raise ValueError(
                    f"Edge {edge.source} -{edge.relation}-> {edge.target} connects {source_type}->{target_type}, but "
                    f"{edge.relation} allows only {'|'.join(sources)}->{'|'.join(targets)}."
                )
            structural_targets.add(edge.target)
        for node in self.nodes:
            patient_relation = PATIENT_RELATION_FOR_TYPE.get(node.type)
            if node.experiencer == "target_patient" and patient_relation and (patient_relation, node.id) not in patient_links:
                raise ValueError(
                    f"Target-patient {node.type} {node.id} requires an edge "
                    f'{{"source":"patient","relation":"{patient_relation}","target":"{node.id}"}} with its own provenance.'
                )
            if node.type == "body_location" and node.id not in structural_targets:
                raise ValueError(
                    f"body_location {node.id} is unreachable: add a located_at or radiates_to edge from the symptom node "
                    f"felt there, or delete {node.id}. A body_location never carries a patient edge of its own."
                )
        return self


def normalise_span(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def validate_provenance(graph: ClinicalGraph, patient_text: str) -> None:
    source = normalise_span(patient_text)
    provenances = ([graph.patient.provenance] if graph.patient.provenance else [])
    provenances.extend(observation.provenance for node in graph.nodes for observation in node.observations)
    provenances.extend(edge.provenance for edge in graph.edges)
    for provenance in provenances:
        if normalise_span(provenance.source_span) not in source:
            raise ValueError(
                f"source_span {provenance.source_span!r} is not a contiguous verbatim substring of the patient report. "
                "Copy one uninterrupted stretch of the report character for character, with its original diacritics and "
                "spelling, instead of paraphrasing, translating, correcting or joining separate fragments."
            )

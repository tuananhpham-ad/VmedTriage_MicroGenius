"""Typed records used by the five-group triage dataset builder."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["self_monitor", "consult_gp", "urgent_handoff", "ask_followup"]
TriageLabel = Literal["self_monitor", "consult_gp", "urgent"]


class Evidence(BaseModel):
    source_id: str
    source_url: str
    excerpt: str


class RedFlag(BaseModel):
    id: str
    symptom_group: str
    trigger_summary: str
    screening_question: str
    action: Literal["urgent_handoff"] = "urgent_handoff"
    evidence: Evidence


class ActionScenario(BaseModel):
    follow_up_candidates: list[str] = Field(min_length=1)
    patient_symptoms: list[str] = Field(default_factory=list)
    final_reply: str | None = None


class SymptomGroup(BaseModel):
    id: str
    condition_name: str
    condition_slug: str
    source_id: str
    user_templates: list[str] = Field(min_length=1)
    durations: list[str] = Field(min_length=1)
    base_symptoms: list[str] = Field(min_length=1)
    red_flag_ids: list[str] = Field(default_factory=list)
    pregnancy_question: str
    scenarios: dict[Action, ActionScenario]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ConversationRecord(BaseModel):
    conversation_id: str
    symptom_group: str
    action: Action
    triage_label: TriageLabel | None
    requires_followup: bool
    messages: list[ChatMessage]
    expected_red_flags: list[str]
    pregnancy_status: Literal["yes", "no", "unknown"]
    red_flag_catalog_version: str
    evidence: list[Evidence]
    label_origin: str = "red_flag_rule_candidate"
    artifact_status: str = "demo_only"
    csv_row_index: int | None = None


class CsvRow(BaseModel):
    condition_name: str
    condition_slug: str
    symptom_names: str
    symptom_slugs: str
    symptom_probabilities: str
    text: str
    num_symptoms: int
    max_symptom_probability: int
    mean_symptom_probability: float
    urgent_score: int
    gp_score: int
    self_score: int
    label: TriageLabel
    override_applied: bool = False
    text_len_words: int
    label_numeric: int

from __future__ import annotations

from src.agents.state import AgentState
from src.services.triage_pipeline import triage_pipeline


async def run_triage_pipeline_node(state: AgentState) -> dict:
    message = state.get("query", "")
    case_id = state.get("case_id")

    if not message:
        return {"error": "Patient message is required."}

    triage_case = await triage_pipeline.handle_patient_message(message, case_id)
    return {
        "case_id": triage_case.case_id,
        "triage_case": triage_case,
        "analysis": _build_analysis(triage_case),
    }


async def patient_safe_response_node(state: AgentState) -> dict:
    triage_case = state.get("triage_case")
    error = state.get("error")

    if error:
        return {"response": f"Lỗi: {error}"}

    if not triage_case:
        return {"error": "Triage case was not produced."}

    return {"response": triage_case.patient_visible_response or ""}


def _build_analysis(triage_case) -> str:
    proposal = triage_case.triage_proposal
    validation = triage_case.validation
    red_flags = triage_case.red_flags

    parts = [
        f"case_id={triage_case.case_id}",
        f"status={triage_case.status}",
    ]
    if proposal:
        parts.append(f"proposal={proposal.priority}")
    if validation:
        parts.append(f"missing_fields={validation.missing_fields}")
    if red_flags:
        parts.append("red_flags=" + ",".join(finding.code for finding in red_flags))

    return "; ".join(parts)

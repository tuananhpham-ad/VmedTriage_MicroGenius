from __future__ import annotations

import importlib

import pytest

from src.services.case_store import InMemoryCaseStore
from src.services.triage_pipeline import TriagePipeline
from src.tool.catalog.framework import ToolExecutionContext
from src.tool.catalog.orchestrator import tool_orchestrator
from src.tool.catalog.registry import catalog_tool_registry


def test_catalog_discovers_all_82_tools_in_stable_id_order() -> None:
    tools = catalog_tool_registry.list_tools()

    assert len(tools) == 82
    assert [tool.id for tool in tools] == list(range(1, 83))
    assert len({tool.name for tool in tools}) == 82


@pytest.mark.asyncio
async def test_every_tool_has_an_executable_entry_point_and_valid_output_contract() -> None:
    context = ToolExecutionContext(approved=True)

    for definition in catalog_tool_registry.list_tools():
        module = importlib.import_module(definition.local_module)
        result = await module.execute({}, context)

        assert result.ok, f"tool {definition.id} failed: {result.error}"
        assert set(definition.output).issubset(result.data)
        assert result.tool_id == definition.id
        assert result.tool_name == definition.name


@pytest.mark.asyncio
async def test_side_effect_tool_requires_explicit_human_approval() -> None:
    blocked = await catalog_tool_registry.call(
        "sms_notification_tool",
        {"recipient": "+84123456789", "message": "Approved message", "case_id": "case-1"},
    )
    approved = await catalog_tool_registry.call(
        "sms_notification_tool",
        {"recipient": "+84123456789", "message": "Approved message", "case_id": "case-1"},
        context=ToolExecutionContext(approved=True, actor_role="nurse"),
    )

    assert not blocked.ok
    assert blocked.metadata.requires_human_review
    assert approved.ok
    assert approved.data["sent"] is False


@pytest.mark.asyncio
async def test_patient_query_orchestrator_runs_safety_and_semantic_tools() -> None:
    run = await tool_orchestrator.run_patient_query(
        "Tôi đau ngực và khó thở từ sáng",
        case_id="case-orchestration",
    )

    assert run.ok
    assert len(run.results) == 6
    assert run.data_for("symptom_extraction_tool")["structured_symptoms"]["symptom_group"] == "chest_pain"
    assert "risk_detected" in run.data_for("self_harm_risk_detector")


@pytest.mark.asyncio
async def test_pipeline_escalates_high_self_harm_language_to_human_review() -> None:
    pipeline = TriagePipeline(store=InMemoryCaseStore())

    triage_case = await pipeline.handle_patient_message("Tôi muốn tự tử")

    assert any(item.code == "high_self_harm_risk" for item in triage_case.red_flags)
    assert triage_case.triage_proposal is not None
    assert triage_case.triage_proposal.priority.value == "Emergency"

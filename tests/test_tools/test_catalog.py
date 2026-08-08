from __future__ import annotations

import asyncio
import importlib
from threading import RLock

import pytest

from src.services.stores.case_store import InMemoryCaseStore
from src.services.triage_pipeline import TriagePipeline
from src.tool.catalog.framework import ToolExecutionContext
from src.tool.catalog.orchestrator import tool_orchestrator
from src.tool.catalog.registry import catalog_tool_registry
from src.tool.catalog.state import CatalogStateStore


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("đau", "vi"),
        ("dau nguc kho tho", "vi"),
        ("chest pain", "en"),
        ("Tôi have chest pain", "mixed"),
        ("aspirin", "unknown"),
    ],
)
async def test_language_detector_handles_short_unaccented_and_mixed_text(
    text: str,
    expected: str,
) -> None:
    result = await catalog_tool_registry.call("language_detector", {"text": text})

    assert result.ok
    assert result.data["language"] == expected
    assert 0.0 <= result.data["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_clinical_calculator_rejects_unsafe_or_incomplete_inputs() -> None:
    tiny_height = await catalog_tool_registry.call(
        "clinical_calculator_tool",
        {"calculator_name": "bmi", "values": {"height_m": 1e-310, "weight_kg": 70}},
    )
    missing_qsofa = await catalog_tool_registry.call(
        "clinical_calculator_tool",
        {"calculator_name": "qsofa", "values": {"respiratory_rate": 24}},
    )
    valid_qsofa = await catalog_tool_registry.call(
        "clinical_calculator_tool",
        {
            "calculator_name": "qsofa",
            "values": {
                "respiratory_rate": 24,
                "systolic_bp": 95,
                "altered_mentation": False,
            },
        },
    )

    assert tiny_height.data == {"score": None, "interpretation": "invalid_input"}
    assert missing_qsofa.data == {"score": None, "interpretation": "insufficient_input"}
    assert valid_qsofa.data == {"score": 2, "interpretation": "high_risk"}


class CountingLock:
    def __init__(self) -> None:
        self._lock = RLock()
        self.entries = 0

    def __enter__(self):
        self._lock.acquire()
        self.entries += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._lock.release()


@pytest.mark.asyncio
async def test_stateful_tools_lock_mutations_and_preserve_concurrent_writes() -> None:
    state = CatalogStateStore()
    counting_lock = CountingLock()
    state.lock = counting_lock
    context = ToolExecutionContext(case_id="concurrent-case", approved=True, state=state)

    results = await asyncio.gather(
        *(
            catalog_tool_registry.call(
                "conversation_memory_write",
                {"case_id": "concurrent-case", "role": "patient", "content": f"message-{index}"},
                context=context,
            )
            for index in range(100)
        )
    )

    assert all(result.ok for result in results)
    assert len(state.conversations["concurrent-case"]) == 100
    assert len({item["message_id"] for item in state.conversations["concurrent-case"]}) == 100
    assert counting_lock.entries >= 200  # One handler transaction and one audit append per call.

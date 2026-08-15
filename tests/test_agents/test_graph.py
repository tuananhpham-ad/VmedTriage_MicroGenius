import pytest

from src.agents.graph import agent


@pytest.mark.asyncio
async def test_agent_basic_flow():
    result = await agent.ainvoke({"query": "Tôi đau ngực từ sáng"})
    assert "response" in result


@pytest.mark.asyncio
async def test_agent_state_structure():
    result = await agent.ainvoke({"query": "Tôi đau ngực từ sáng"})
    assert isinstance(result, dict)
    assert "query" in result
    assert "triage_case" in result


@pytest.mark.asyncio
async def test_agent_red_flag_branch():
    result = await agent.ainvoke({"query": "Tôi đau ngực và khó thở nặng từ sáng"})
    triage_case = result["triage_case"]

    assert triage_case.triage_proposal.priority == "Emergency"
    assert triage_case.red_flags

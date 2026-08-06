from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import AgentState
from src.services.llm import get_llm

ANALYZE_SYSTEM_PROMPT = (
    "Bạn là một trợ lý phân tích. Tóm tắt ý định và các điểm chính "
    "trong câu hỏi của người dùng bằng 1-2 câu ngắn gọn."
)

RESPOND_SYSTEM_PROMPT = (
    "Bạn là một trợ lý hữu ích. Dựa vào phân tích được cung cấp, hãy trả lời "
    "câu hỏi gốc của người dùng một cách rõ ràng, chính xác và hữu ích."
)


async def analyze_node(state: AgentState) -> dict:
    """Phân tích query từ user bằng LLM."""
    query = state.get("query", "")

    try:
        llm = get_llm()
        result = await llm.ainvoke(
            [SystemMessage(content=ANALYZE_SYSTEM_PROMPT), HumanMessage(content=query)]
        )
        return {"analysis": result.content}
    except Exception as exc:
        return {"error": str(exc)}


async def respond_node(state: AgentState) -> dict:
    """Tạo response từ analysis bằng LLM."""
    query = state.get("query", "")
    analysis = state.get("analysis", "")
    error = state.get("error")

    if error:
        return {"response": f"Lỗi: {error}"}

    try:
        llm = get_llm()
        result = await llm.ainvoke(
            [
                SystemMessage(content=RESPOND_SYSTEM_PROMPT),
                HumanMessage(content=f"Câu hỏi: {query}\nPhân tích: {analysis}"),
            ]
        )
        return {"response": result.content}
    except Exception as exc:
        return {"response": f"Lỗi: {exc}"}

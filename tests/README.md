# Thu muc `tests`

Thu muc nay chua test suite dung `pytest` va `pytest-asyncio`. Test chu yeu dam bao API chay, LangGraph tao case dung, va 82 local catalog tools duoc discover/chay dung contract.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package test. |
| `conftest.py` | Fixture dung chung: `client` tao `httpx.AsyncClient` chay truc tiep FastAPI app, `mock_llm` tao mock LLM. |
| `test_api/` | Test endpoint HTTP. |
| `test_agents/` | Test LangGraph agent. |
| `test_tools/` | Test local catalog tools va policy. |

Chay test bang:

```bash
pytest tests/ -v
```


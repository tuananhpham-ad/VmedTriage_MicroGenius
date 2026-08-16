# Thu muc `src`

Day la phan code chinh cua ung dung VMedTriage. Khi chay server bang `uvicorn src.main:app`, Python se vao `main.py`, mount UI tinh, gan router API, sau do cac request triage se di qua agent, services va tool catalog.

Nen doc theo thu tu:

1. `main.py`
2. `api/routes.py` (endpoint `POST /chat` la loi vao cua luong benh nhan)
3. `services/symptom_protocol/` (agent trieu chung: stage machine, rule engine, intake agent)
4. `services/sessions/symptom_case_bridge.py` (phien agent -> `TriageCase` cho hang doi dieu duong)
5. `models/schemas.py`
6. `tool/catalog/README.md`

## File va folder

| Duong dan | Vai tro |
|---|---|
| `__init__.py` | Danh dau `src` la Python package de import duoc bang `src...`. |
| `main.py` | Entry point FastAPI: cau hinh logging, CORS, route `/health`, router `/api/v1`, va UI tinh tai `/`. |
| `config.py` | Tap trung cau hinh `.env`, rule bat buoc, cau hoi follow-up, red flag rules, triage protocol rules, va config MCP/Weaviate/LLM. |
| `api/` | Dinh nghia REST API cho chat, queue dieu duong, review case va tool calls. |
| `models/` | Pydantic schema va interface dung chung giua API, service, agent, tool. |
| `services/` | Business logic y te: mapping trieu chung, validation, red flag, triage priority, summary, queue, HITL. |
| `pipeline/` | Pipeline Weaviate Cloud/RAG: upload document/case, search, rerank, tao cau tra loi bang LLM. |
| `tool/` | Lop tool: descriptor MCP, registry, local catalog 82 tool va adapter goi MCP ben ngoai. |
| `ui/` | Demo web UI tinh HTML/CSS/JavaScript duoc FastAPI phuc vu truc tiep. |


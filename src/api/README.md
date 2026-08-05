# Thu muc `src/api`

Thu muc nay mo cac endpoint HTTP cho frontend va test goi vao. Logic nghiep vu khong nam o day; route chi nhan request, goi agent/service/tool registry, roi tra response Pydantic.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.api`. |
| `routes.py` | Dinh nghia router `/api/v1`: chat, status, list/call tools, nurse queue, lay case, va gui review cua dieu duong. |

## Cac endpoint chinh

| Endpoint | Muc dich |
|---|---|
| `POST /api/v1/chat` | Nhan tin nhan benh nhan, goi LangGraph agent, tra ve case, summary, proposal, trace va response an toan. |
| `GET /api/v1/status` | Kiem tra agent san sang. |
| `GET /api/v1/tools` | Liet ke tool descriptor dang expose qua API. |
| `POST /api/v1/tools/{tool_name}/call` | Goi MCP tool neu co server config, hoac local catalog tool neu tool thuoc catalog. |
| `GET /api/v1/nurse/queue` | Lay danh sach case dang nam trong queue cho dieu duong. |
| `GET /api/v1/cases/{case_id}` | Lay chi tiet mot case. |
| `POST /api/v1/cases/{case_id}/review` | Dieu duong approve, edit, reject, escalate hoac hoi them thong tin. |

`_build_pipeline_trace()` tao trace tung buoc de UI tab `Trace` hien thi duoc input, mapping, validation, triage va response.


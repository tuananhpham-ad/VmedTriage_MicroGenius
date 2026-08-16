# Thu muc `src/api`

Thu muc nay mo cac endpoint HTTP cho frontend va test goi vao. Logic nghiep vu khong nam o day; route chi nhan request, goi agent/service/tool registry, roi tra response Pydantic.

Nguon su that cho contract API la `docs/API_DOCUMENTATION.md` + `docs/openapi.yaml`.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.api`. |
| `routes.py` | Router chinh `/api/v1`: auth/tai khoan, `POST /chat` (luong benh nhan khai trieu chung), status, list/call tools, nurse queue, lay case, review cua dieu duong. |
| `routers/queue.py` | Feature 2 - hang doi + hanh dong duyet roi (`/queue`, `/approve`, `/override`, `/escalate`, `/reject`, `/ask_more`). |
| `routers/result.py` | Feature 4 - `/disclaimer` va `/cases/{id}/result` cho benh nhan sau khi duyet. |
| `routers/fever_intake.py` | Loi vao chuyen biet cho protocol sot (`/fever/*`). Chi `/confirm` duoc frontend goi that; 3 endpoint con lai la demo/test. |

## Cac endpoint chinh

| Endpoint | Muc dich |
|---|---|
| `POST /api/v1/chat` | **Luong chinh.** Nhan tin nhan benh nhan, chay agent trieu chung (`src/services/symptom_protocol/`), ghi case qua `symptom_case_bridge` vao `case_store`. `case_id` = `session_id` cua phien agent. |
| `POST /api/v1/fever/sessions/{case_id}/confirm` | Benh nhan xac nhan phieu tom tat truoc khi ban giao dieu duong. |
| `GET /api/v1/status` | Kiem tra agent san sang. |
| `GET /api/v1/tools` | Liet ke tool descriptor dang expose qua API. |
| `POST /api/v1/tools/{tool_name}/call` | Goi MCP tool neu co server config, hoac local catalog tool neu tool thuoc catalog. |
| `GET /api/v1/nurse/queue` | Lay danh sach case dang nam trong queue cho dieu duong. |
| `GET /api/v1/cases/{case_id}` | Lay chi tiet mot case (redact bot field noi bo neu role la patient). |
| `POST /api/v1/cases/{case_id}/review` | Dieu duong approve, edit, reject, escalate hoac hoi them thong tin. |

## Da xoa (2026-08-16)

`routers/cases.py` (`POST /cases`, `POST /cases/{id}/responses`) va `routers/intake.py` (`/intake/*`):
khong co caller nao - `cases.py` chay pipeline rule-based cu (`case_flow` -> `triage_pipeline`) song
song voi agent that, `intake.py` la router demo khong auth va khong day case sang dieu duong.
Chi tiet: `docs/API_DOCUMENTATION.md` muc 4.5.

`_build_pipeline_trace()` trong `routes.py` tao trace tung buoc cho UI tab `Trace` (input, mapping,
validation, triage, response).

# VMedTriage

AI Agent hỗ trợ điều dưỡng phân loại mức độ ưu tiên ban đầu cho bệnh nhân tư vấn online: thu thập triệu chứng theo checklist chuẩn, phát hiện red-flag, và đề xuất mức ưu tiên (Cấp cứu / Khám sớm / Tự theo dõi) — **cần điều dưỡng xác nhận (HITL) trước khi gửi cho bệnh nhân**, trừ escalate red-flag tức thời.

> Team MicroGenius 
## Yêu cầu

- Python 3.11+
- (tuỳ chọn) PostgreSQL nếu không dùng SQLite dev; Weaviate Cloud nếu bật lưu trữ case vector

## Setup

```bash
# Virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1   # Windows

# Cài dependencies
pip install -r requirements.txt
# Tuỳ chọn: bật src/graph_triage/ (second opinion, cần torch ~2.5GB)
# pip install -r requirements-graph.txt

# Cấu hình môi trường
cp .env.example .env
# Điền các key bên dưới, KHÔNG commit .env
```

## Chạy server

```bash
make run
# hoặc: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Test / lint

```bash
make test        # pytest tests/ -v
make coverage     # báo cáo coverage (ngưỡng tối thiểu 70%, xem pyproject.toml)
make lint         # ruff check
make format       # ruff format
make eval         # python eval/scripts/run_eval.py
```

## Biến môi trường chính

`.env.example`; `src/config.py` là nguồn cho default values.

| Biến | Mô tả | Bắt buộc |
|---|---|:---:|
| `DATABASE_URL` | Connection string (mặc định SQLite dev) | — |
| `JWT_SECRET_KEY` | Secret ký JWT, ≥32 ký tự; production từ chối khởi động nếu để giá trị mặc định |  (prod) |
| `NURSE_REGISTRATION_CODE` | Mã mời riêng để đăng ký tài khoản `nurse`; production từ chối khởi động nếu để trống | (prod) |
| `LLM_PROVIDER` | `auto` \| `openai` \| `deepseek` \| `gemini` \| `anthropic` \| `openrouter` | — |
| `LLM_PROVIDER_ORDER` | Thứ tự fallback khi `LLM_PROVIDER=auto` | — |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | API key cho provider tương ứng (chỉ cần key của provider đang dùng) | tuỳ provider |
| `WEAVIATE_URL` / `WEAVIATE_API_KEY` | Lưu trữ case dạng vector (best-effort, pipeline vẫn chạy nếu để trống) | — |
| `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` | Gửi email xác thực / reset mật khẩu; để trống `SMTP_HOST` khi dev sẽ ghi nội dung email ra log server | — |
| `ENABLE_GRAPH_TRIAGE_AGENT` | Bật module `src/graph_triage/` (second opinion, không bao giờ ghi đè `TriageProposal.priority`) — mặc định `false` | — |
| `CORS_ORIGINS` | Danh sách origin FE, phân tách bằng dấu phẩy | — |
| `BRAINTRUST_API_KEY` | Key cho tracing/eval qua Braintrust (`eval/`) — dùng để log span trace của Track 1 (`TriagePipeline`) và Track 2 (`graph_triage`/`source_support`). Hoàn toàn tuỳ chọn: để trống thì tracing tự tắt thành no-op, app/script KHÔNG crash | — |
| `BRAINTRUST_PROJECT` | Tên project Braintrust để log trace (mặc định `vmedtriage-eval`) | — |

## API & luồng chính

Luồng production thật là `/api/v1/chat` (xem `src/api/routes.py` + `src/services/symptom_protocol/`). Chi tiết:

- **Auth & phân quyền:** [docs/AUTH.md](docs/AUTH.md) — flow đăng ký/đăng nhập 2 role (`patient`/`nurse`), curl mẫu cho PowerShell/bash.
- **API reference đầy đủ:** [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md), [docs/openapi.yaml](docs/openapi.yaml).
- **Kiến trúc:** [ARCHITECTURE.md](ARCHITECTURE.md), [docs/architecture_diagram.md](docs/architecture_diagram.md).

### Sample query — chat triage

```bash
# 1. Đăng ký + đăng nhập bệnh nhân (xem docs/AUTH.md để có bản đầy đủ + role nurse)
curl -X POST http://localhost:8000/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email":"patient@example.com","password":"StrongPass123!","full_name":"Demo Patient","role":"patient"}'

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email":"patient@example.com","password":"StrongPass123!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Gửi tin nhắn triệu chứng tự do (không cần ghim protocol trước)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Tôi bị đau ngực và khó thở khi leo cầu thang"}'

# 3. (role nurse) Xem hàng đợi và duyệt ca
curl http://localhost:8000/api/v1/nurse/queue -H "Authorization: Bearer $NURSE_TOKEN"
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/review \
  -H "Authorization: Bearer $NURSE_TOKEN" -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'
```

## Cấu trúc dự án

```
src/
├── api/               # FastAPI routes (chat, cases, auth, nurse queue, MCP tools)
├── config.py           # Pydantic Settings + hằng số protocol/red-flag
├── middleware/          # Role-based auth middleware
├── models/              # Pydantic schemas
├── services/
│   ├── symptom_protocol/  # Agent hội thoại chính (luồng /chat)
│   ├── engines/           # ProtocolTriageEngine, RedFlagSafetyLayer, semantic_mapper
│   ├── sessions/           # session store, HITL review, case bridge
│   ├── stores/             # case_store
│   └── infra/              # mailer, v.v.
├── graph_triage/        # Module "second opinion" tuỳ chọn (mặc định tắt, xem CLAUDE.md #6)
└── main.py               # App entry point
tests/                   # pytest suite
eval/                    # Evaluation scripts + evidence
docs/                    # PRD, ADR, API docs, planning, guideline lâm sàng
```

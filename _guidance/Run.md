# Run - VMedTriage

File này hướng dẫn các cách chạy VMedTriage trong môi trường local, Docker và demo public.

## 1. Yêu cầu môi trường

- Python 3.11
- PowerShell trên Windows, hoặc bash trên Linux/macOS
- Docker Desktop nếu muốn chạy bằng Docker
- File `.env` ở root repository nếu cần cấu hình biến môi trường

Tạo `.env` từ file mẫu:

```powershell
Copy-Item .env.example .env
```

Trên Linux/macOS:

```bash
cp .env.example .env
```

MVP hiện có deterministic fallback nên có thể chạy demo cơ bản mà không cần secret thật. Không commit `.env` lên GitHub.

## 2. Cài đặt local

Tạo virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Cài dependencies:

```powershell
pip install -r requirements.txt
```

Nếu PowerShell chặn activate script, chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Trên Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Chạy demo UI local

Chạy FastAPI server:

```powershell
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Hoặc dùng Makefile nếu môi trường có `make`:

```bash
make run
```

Mở các URL sau:

```text
Demo UI:     http://localhost:8000/
Swagger UI:  http://localhost:8000/docs
Health:      http://localhost:8000/health
API status:  http://localhost:8000/api/v1/status
```

Demo flow đề xuất:

1. Mở `http://localhost:8000/`.
2. Nhập triệu chứng mẫu:

```text
Tôi đau ngực từ sáng, đi vài bước là hụt hơi.
```

3. Xem panel bệnh nhân, case details và nurse review.
4. Ở nurse review, thử các hành động `Approve`, `Escalate`, hoặc `Ask more`.

## 4. Chạy API bằng curl hoặc PowerShell

Kiểm tra health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Kiểm tra status:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/status
```

Gửi một tin nhắn triage:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"message":"Tôi đau ngực từ sáng, đi vài bước là hụt hơi."}'
```

Trên Linux/macOS:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Tôi đau ngực từ sáng, đi vài bước là hụt hơi."}'
```

Các endpoint chính:

```text
GET  /health
GET  /api/v1/status
POST /api/v1/chat
GET  /api/v1/nurse/queue
GET  /api/v1/cases/{case_id}
POST /api/v1/cases/{case_id}/review
GET  /api/v1/tools
POST /api/v1/tools/{tool_name}/call
```

## 5. Chạy bằng Docker

Build image:

```powershell
docker build -t vmedtriage .
```

Run container:

```powershell
docker run --env-file .env -p 8000:8000 vmedtriage
```

Mở:

```text
http://localhost:8000/
```

## 6. Chạy bằng Docker Compose

Docker Compose dùng `docker-compose.yml`, map port `8000:8000`, đọc `.env` và mount thư mục `./data`.

```powershell
docker compose up --build
```

Chạy nền:

```powershell
docker compose up --build -d
```

Xem log:

```powershell
docker compose logs -f backend
```

Dừng service:

```powershell
docker compose down
```

## 7. Chạy test, lint, format

Chạy test:

```powershell
pytest tests/ -v
```

Hoặc:

```bash
make test
```

Chạy lint:

```powershell
ruff check src/ tests/
```

Format code:

```powershell
ruff format src/ tests/
```

Chạy toàn bộ check nếu có `make`:

```bash
make check
```

Lưu ý: `make check` hiện chạy `lint`, `format`, rồi `test`. Vì `format` có thể sửa file, hãy kiểm tra `git status` sau khi chạy.

## 8. Chạy production-like local

Lệnh gần giống production, không bật reload:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Nếu muốn mô phỏng biến môi trường production, sửa `.env`:

```text
APP_ENV=production
```

Rồi chạy lại server.

## 9. Deploy Render

Repo có sẵn `render.yaml` cho Render Blueprint:

```text
buildCommand: pip install -r requirements.txt
startCommand: uvicorn src.main:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
```

Các bước chính:

1. Push code lên GitHub.
2. Vào Render Dashboard.
3. Chọn `New > Blueprint`.
4. Kết nối repository `P-141`.
5. Render đọc `render.yaml` và tạo service `vmedtriage`.
6. Kiểm tra public URL sau deploy.

Tài liệu chi tiết nằm ở:

```text
_guidance/deploy_render.md
```

## 10. Kiểm tra nhanh sau khi chạy

Server chạy đúng nếu các URL sau trả kết quả:

```text
http://localhost:8000/health
http://localhost:8000/api/v1/status
http://localhost:8000/
```

Kết quả `/health` kỳ vọng:

```json
{
  "status": "ok",
  "env": "development"
}
```

Kết quả `/api/v1/status` kỳ vọng:

```json
{
  "status": "ready",
  "agent": "VMedTriage Controlled Pipeline v1.0"
}
```

## 11. Lỗi thường gặp

### Port 8000 đã bị chiếm

Đổi sang port khác:

```powershell
uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
```

Mở:

```text
http://localhost:8001/
```

### Không import được package trong `src`

Đảm bảo đang chạy lệnh từ root repository:

```text
D:\Folder F\phamtuananh@23020010\UET.iSEML\2026.VinAI.Project\P-141
```

Sau đó chạy lại:

```powershell
uvicorn src.main:app --reload --port 8000
```

### Thiếu dependency

Cài lại dependencies trong virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Docker không đọc được `.env`

Kiểm tra file `.env` tồn tại ở root repository:

```powershell
Get-ChildItem .env
```

Nếu chưa có:

```powershell
Copy-Item .env.example .env
```

### Render deploy bị lỗi port

Không hard-code port production. Render cần dùng `$PORT`:

```text
uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

## 12. Chay Weaviate pipelines

Chay ingest pipeline:

```powershell
python -m src.pipeline.ingesting_pipeline
```

Chay querying pipeline:

```powershell
python -m src.pipeline.querying_pipeline
```

Can co `WEAVIATE_URL` va `WEAVIATE_API_KEY` trong `.env` truoc khi chay.

Kiem tra registry discover du 82 tool:

```powershell
python -c "from src.tool.catalog.registry import catalog_tool_registry as r; print(len(r.list_tools()))"
```

Ví dụ gọi tool read-only trong Python async:

```python
from src.tool.catalog.registry import catalog_tool_registry

result = await catalog_tool_registry.call(
    "snomed_concept_lookup",
    {"term": "đau ngực", "language": "vi"},
)
print(result.model_dump())
```

Tool side-effect bị chặn nếu chưa có phê duyệt. Khi gọi từ luồng nurse/HITL, truyền execution context:

```python
from src.tool.catalog.framework import ToolExecutionContext

context = ToolExecutionContext(
    case_id="case-123",
    actor_id="nurse-01",
    actor_role="nurse",
    approved=True,
)
result = await catalog_tool_registry.call(
    "fhir_task_create",
    {
        "patient_id": "patient-01",
        "task_payload": {"status": "requested"},
    },
    context=context,
)
```

Lưu ý phân biệt hai registry:

- `src.tool.catalog.registry`: 82 local-first tool dùng bởi orchestrator và pipeline.
- `src.tool.registry`: các MCP endpoint ngoài; tool đã có external descriptor vẫn trả lỗi cấu hình nếu URL
  MCP tương ứng chưa được khai báo.

FHIR/notification local adapter chỉ ghi state hoặc outbox. Hãy kiểm tra `sent`, `delivered` và `source`
trong output; không coi một message queued là đã được provider gửi thành công.

## 13. Ghi chú an toàn demo

- Không nhập PHI/PII thật vào demo public.
- Demo hiện dùng in-memory case store, dữ liệu có thể mất khi restart.
- AI chỉ tạo triage proposal, không thay thế bác sĩ hoặc điều dưỡng.
- Patient-facing response cuối cùng cần đi qua Human-in-the-Loop approval.

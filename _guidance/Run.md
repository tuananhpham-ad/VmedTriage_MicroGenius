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
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
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

## 3b. Demo hỏi đáp thu thập triệu chứng (Intake)

Đây là demo tách riêng cho phần **hỏi-đáp + checklist + phiếu tóm tắt + xác nhận của người bệnh**.
Phần duyệt của điều dưỡng và phần graph/GNN KHÔNG nằm trong demo này.

Sau khi server chạy (mục 3), mở:

```text
http://localhost:8000/intake.html
```

Luồng demo:

1. Agent chào và hỏi thông tin ban đầu.
2. Bạn trả lời tự nhiên, ví dụ:

```text
Bố tôi tên Trần Văn Hùng, 68 tuổi, sáng nay đột nhiên bị méo miệng và nói ngọng
```

3. Panel bên phải hiển thị % checklist đã thu thập và trường nào còn thiếu.
4. Agent tự sinh câu hỏi tiếp theo (bằng LLM) cho các trường còn trống.
5. Khi đạt **>= 85% trường bắt buộc** (6/7), hệ thống hiện **phiếu tóm tắt** và hỏi bạn xác nhận.
6. Bấm `✓ Đúng rồi` để chốt, hoặc `✎ Chưa đúng, cần sửa` rồi nhập nội dung đính chính.

Kiểm tra hệ thống đang chạy bằng LLM thật hay fallback:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/intake/health
```

Kết quả kỳ vọng khi đã cấu hình LLM:

```json
{ "llm_available": true }
```

Nếu `llm_available: false`, demo vẫn chạy được nhưng câu hỏi dùng mẫu cố định thay vì sinh tự nhiên
(cấu hình `GEMINI_API_KEY`, `OPENAI_API_KEY` hoặc `DEEPSEEK_API_KEY` trong `.env` để bật LLM).

Các endpoint của demo intake:

```text
GET  /api/v1/intake/health
POST /api/v1/intake/sessions
GET  /api/v1/intake/sessions/{session_id}
POST /api/v1/intake/sessions/{session_id}/messages   body: {"message": "..."}
POST /api/v1/intake/sessions/{session_id}/confirm    body: {"is_correct": true}
                                                      hoặc {"is_correct": false, "correction": "..."}
```

Lưu ý phạm vi demo:

- Router intake **không yêu cầu auth** (để chạy demo nhanh) — phải bổ sung trước khi dùng thật.
- Red-flag được quét bằng rule thuần **mỗi lượt**, không đợi checklist đủ, và không phụ thuộc LLM.
- Session lưu in-memory, mất khi restart process.

## 3c. Chạy Agent hỏi-đáp theo checklist TỪNG BỆNH (CLI, dùng LLM thật)

Đây là phần mới theo mục 10 của `_guidance/vmedtriage_solution_design_review.md`: agent hỏi-đáp dẫn
dắt người dùng điền checklist của **một bệnh cụ thể**, đủ ngưỡng thì sinh **phiếu tóm tắt tình trạng
bệnh** và xin người dùng xác nhận.

Khác demo intake ở mục 3b (bộ trường chung hardcode, chạy qua web UI), phần này:

- Checklist **nạp từ JSON** trong `src/domain/_<disease_id>.json` → thêm bệnh mới = thêm file JSON,
  không sửa code.
- Chạy bằng **CLI**, chưa có REST endpoint và chưa nối vào nurse queue.

### Cấu hình LLM trước khi chạy

`.env` cần có ít nhất một API key hợp lệ. Biến `LLM_PROVIDER` chỉ nhận đúng các giá trị sau
(xem `src/config.py`):

```text
auto | openai | deepseek | gemini | anthropic | openrouter
```

Đặt `LLM_PROVIDER=auto` để hệ thống tự chọn provider đầu tiên còn API key theo thứ tự trong
`LLM_PROVIDER_ORDER`, hoặc đặt tên một provider cụ thể để ép dùng đúng provider đó.

> ⚠️ Đặt nhầm **tên model** vào `LLM_PROVIDER` (ví dụ `LLM_PROVIDER="deepseek-chat"`) sẽ làm
> `get_settings()` raise `ValidationError` và **cả app không khởi động được**, không riêng gì phần này.
> Tên model đặt ở biến riêng: `DEEPSEEK_MODEL_NAME`, `GEMINI_MODEL_NAME`, ...

Kiểm tra nhanh provider nào đang khả dụng:

```powershell
python -c "from src.services import provider_router; print(provider_router.available_providers())"
```

Kết quả kỳ vọng khi đã cấu hình đúng, ví dụ:

```text
['deepseek']
```

Danh sách rỗng `[]` nghĩa là chưa có API key nào dùng được — CLI vẫn chạy nhưng rơi về fallback
deterministic (gán nguyên tin nhắn vào trường thiếu đầu tiên), và màn hình sẽ báo rõ chế độ đang chạy.

### Chạy CLI

Chạy từ root repository:

```powershell
# Kịch bản mẫu, không cần gõ tay - dùng để kiểm tra nhanh
python -m scripts.run_disease_qa --demo

# Hội thoại tương tác, tự gõ câu trả lời
python -m scripts.run_disease_qa

# Chỉ định bệnh khác (đọc src/domain/_<disease_id>.json)
python -m scripts.run_disease_qa disease_x
```

Trong chế độ tương tác, gõ `q` để thoát.

### Luồng CLI

1. Agent chào và hỏi trường đầu tiên trong checklist.
2. Bạn trả lời tự nhiên; LLM trích xuất thông tin vào đúng trường checklist.
3. Sau mỗi lượt, CLI in `[checklist N% - x/y trường bắt buộc]` và các trường còn thiếu.
4. Chưa đủ → LLM sinh câu hỏi tiếp theo tự nhiên (tối đa 2 trường/lượt) để dẫn dắt.
5. Đạt **>= 85%** trường bắt buộc → in **phiếu tóm tắt tình trạng bệnh** và hỏi xác nhận.
6. Chọn `d` (đúng) để chốt phiên, hoặc `s` (sửa) rồi nhập nội dung đính chính.

Kết quả mẫu khi chạy `--demo` với DeepSeek thật:

```text
Chế độ  : LLM thật (provider: deepseek)

[AGENT] Chào bạn, mình cần thu thập một vài thông tin về "Disease X (mock test)"...
[BẠN  ] Chào bạn, tôi thấy trong người không ổn
  [checklist 33% - 1/3 trường bắt buộc] còn thiếu: Tên, Thời gian phát bệnh
[AGENT] Dạ, để tiện theo dõi, mình xin phép hỏi thêm: tên của bạn là gì và bạn bắt đầu
        thấy người không ổn từ khi nào ạ?
...
====================================================================
Tóm tắt tình trạng bệnh - Disease X (mock test):
- Tên: Trần Minh Khoa
- Tình trạng bệnh: thấy trong người không ổn
- Thời gian phát bệnh: sáng hôm qua
====================================================================
```

### Log từng bước để tra cứu

Mỗi phiên tự ghi một file `logs/<session_id>.json`, ví dụ:

```text
logs/11566e1f-fb8d-440e-ad73-4bcb714778da.json
```

CLI in đường dẫn log ngay khi bắt đầu và khi kết thúc phiên.

Cấu trúc file:

```json
{
  "session_id": "...",
  "disease_id": "disease_x",
  "completion_threshold": 0.85,
  "final_state": "confirmed",
  "answers": { "name": "...", "condition": "...", "onset": "..." },
  "events":    [ ... trace tuần tự mọi bước ... ],
  "summaries": [ ... mọi phiên bản phiếu tóm tắt ... ]
}
```

**`events`** — trace tuần tự, mỗi bước có `seq` + `at` (UTC):

| `type` | Nội dung |
|---|---|
| `agent_question` | Câu hỏi system hỏi, `llm_used`, `targets` (trường đang nhắm), `source` |
| `user_message` | Nguyên văn câu trả lời của user, `turn` |
| `extraction` | LLM trích được gì, snapshot `answers` + `progress` sau lượt đó |
| `correction` | Như trên, kèm `overwritten` = giá trị CŨ bị ghi đè (tra được sửa từ gì sang gì) |
| `summary_generated` / `summary_revised` / `summary_confirmed` | Mốc sinh / sửa / chốt phiếu |
| `summary_rejected` | User bấm "chưa đúng", kèm nội dung đính chính |

**`summaries`** — lưu **tất cả** phiên bản phiếu, không chỉ bản cuối:

- `generated` — bản sinh lần đầu khi đủ ngưỡng
- `revised` — bản sau mỗi lần user đính chính
- `confirmed` — đúng bản user đã bấm xác nhận để gửi đi

Mỗi bản gồm `text` (phiếu dạng chữ), `rows` (dạng field-value) và `answers` tại thời điểm đó.

Ví dụ trace thật của một phiên có đính chính tên:

```text
 1. agent_question   Q: Chào bạn, mình cần thu thập một vài thông tin về "Disease X"...
 2. user_message     A: Tôi tên Trần Minh Khoa
 3. extraction       extracted={'name': 'Trần Minh Khoa'}
 4. agent_question   Q: Dạ thưa anh Khoa, anh có thể mô tả giúp em các triệu chứng...
 5. user_message     A: Tôi bị sốt cao 39 độ
 6. extraction       extracted={'condition': 'sốt cao 39 độ'}
 7. agent_question   Q: Dạ thưa anh Khoa, anh bắt đầu thấy sốt từ khi nào ạ?
 8. user_message     A: từ sáng hôm qua
 9. extraction       extracted={'onset': 'sáng hôm qua'}
10. summary_generated
11. summary_rejected correction=Tên tôi là Trần Minh Khôi chứ không phải Khoa
12. correction       extracted={'name': 'Trần Minh Khôi'} overwritten={'name': 'Trần Minh Khoa'}
13. summary_revised
14. summary_confirmed
```

Đọc nhanh một log bằng PowerShell:

```powershell
Get-Content logs\<session_id>.json -Encoding utf8 | ConvertFrom-Json | Select-Object -ExpandProperty events
```

Lưu ý:

- Ghi log **không bao giờ làm hỏng phiên**: mọi lỗi I/O đều được nuốt và chỉ ghi cảnh báo.
- File được **ghi đè toàn bộ** sau mỗi sự kiện nên luôn là JSON hợp lệ, kể cả khi process bị kill.
- ⚠️ **File log chứa nguyên văn hội thoại người bệnh (PHI).** `logs/` đã nằm trong `.gitignore`.
  Trước khi dùng thật cần bổ sung mã hoá at-rest, phân quyền đọc và chính sách xoá theo hạn lưu trữ.

### Thêm một bệnh mới

Tạo file `src/domain/_<disease_id>.json` theo đúng cấu trúc của `_disease_x.json`:

```json
{
  "disease_id": "disease_x",
  "disease_label": "Disease X (mock test)",
  "completion_threshold": 0.85,
  "fields": [
    { "key": "name",      "label": "Tên",                "required": true, "hint": "...", "value": null },
    { "key": "condition", "label": "Tình trạng bệnh",    "required": true, "hint": "...", "value": null },
    { "key": "onset",     "label": "Thời gian phát bệnh","required": true, "hint": "...", "value": null }
  ]
}
```

`hint` được đưa thẳng vào prompt để LLM biết trường đó cần trích xuất cái gì — viết `hint` càng rõ
thì trích xuất càng chính xác. `value: null` là giá trị khởi tạo, phiên chạy sẽ điền dần.

### Chạy test (không gọi LLM)

Test chỉ kiểm tra phần deterministic (nạp checklist, tính %, state machine, fallback):

```powershell
pytest tests/test_services/test_disease_session.py -v
```

### Giới hạn đã biết

- **Trường đã có giá trị sẽ KHÔNG bị ghi đè ở các lượt sau.** Nếu người dùng mô tả sơ sài trước
  ("thấy trong người không ổn") rồi mới nói chi tiết ("sốt 39 độ, đau họng, ho khan"), phần chi tiết
  **bị bỏ qua** và không vào phiếu tóm tắt. Policy này hợp lý với trường hành chính (tên, tuổi) nhưng
  sai với trường mô tả triệu chứng — cần bổ sung cơ chế cộng dồn cho các trường loại này.
- Chỉ có CLI, **chưa có REST endpoint** và chưa nối vào `TriagePipeline`/nurse queue.
- **Chưa có red-flag scan** trong luồng này (khác luồng intake ở mục 3b đã có). Không dùng để đánh
  giá mức độ khẩn cấp.
- Session lưu in-memory, mất khi kết thúc process.

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

Chay full pipeline voi sample upload + sample query:

```powershell
python -m src.pipeline.full_pipeline
```

Neu chua cau hinh Weaviate Cloud, chay dry-run de xem sample payload:

```powershell
python -m src.pipeline.full_pipeline --dry-run
```

Chay ingest pipeline:

```powershell
python -m src.pipeline.database_update_phase
```

Chay querying pipeline:

```powershell
python -m src.pipeline.user_answer_phase
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

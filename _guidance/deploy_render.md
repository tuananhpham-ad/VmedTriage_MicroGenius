# Deploy VMedTriage lên Render

VMedTriage deploy trên Render dưới dạng một Python Web Service. FastAPI phục vụ cả Demo UI tại `/` và API tại `/api/v1`.

## 1. Cấu hình Render

Khuyến nghị dùng Render Blueprint từ file `render.yaml` ở root repository.

| Mục | Giá trị |
|---|---|
| Service type | Web Service |
| Runtime | Python |
| Plan | Free cho demo public |
| Branch | `tuananhpham` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Public UI | `/` |
| API prefix | `/api/v1` |

Render tự cấp biến môi trường `$PORT`; không hard-code port production.

## 2. Deploy bằng GitHub + Blueprint

1. Push code lên GitHub repository:

```text
https://github.com/AI20K-Build-Phase-Cohort-3/P-141.git
```

2. Vào <https://dashboard.render.com/>.
3. Chọn **New > Blueprint**.
4. Kết nối GitHub và chọn repository `P-141`.
5. Render sẽ đọc `render.yaml` và tạo service `vmedtriage` từ branch `tuananhpham`.
6. Chọn **Apply** để Render build và deploy.

Sau khi deploy xong, URL public có dạng:

```text
https://vmedtriage.onrender.com
```

Kiểm tra:

```text
https://vmedtriage.onrender.com/health
https://vmedtriage.onrender.com/api/v1/status
```

## 3. Environment variables

MVP hiện chạy được không cần secret vì semantic mapper đang có deterministic fallback.

Khi bật các tích hợp thật, cấu hình trong Render Environment:

| Key | Khi nào dùng |
|---|---|
| `APP_ENV=production` | Deploy public |
| `MODEL_NAME=gemma-3-4b` | Khi nối adapter Gemma thật |
| `OPENAI_API_KEY` | Chỉ dùng nếu runtime LLM adapter cần OpenAI-compatible endpoint |
| `MCP_CLINICAL_GUIDELINE_SERVER_URL` | Khi bật MCP guideline search |
| `MCP_TERMINOLOGY_SERVER_URL` | Khi bật SNOMED/FHIR terminology MCP |
| `MCP_FHIR_SERVER_URL` | Khi bật EHR/FHIR context |
| `MCP_CDS_HOOKS_SERVER_URL` | Khi bật CDS Hooks bridge |
| `MCP_NOTIFICATION_SERVER_URL` | Khi bật nurse alert |
| `MCP_AUDIT_SERVER_URL` | Khi bật audit store |

Không commit `.env` hoặc secret vào GitHub.

## 4. Public demo flow

1. Mở `/`.
2. Nhập triệu chứng mẫu:

```text
Tôi đau ngực từ sáng, đi vài bước là hụt hơi.
```

3. UI hiển thị patient-safe response.
4. Panel case hiển thị structured mapping, red flags và triage proposal.
5. Panel điều dưỡng có thể `Approve`, `Escalate`, hoặc `Ask more`.

## 5. Lưu ý production

- Render Free có thể sleep khi không có traffic, request đầu tiên sẽ chậm.
- In-memory case store sẽ mất dữ liệu khi service restart/redeploy. Cần thay bằng database trước khi dùng thật.
- Demo public không được nhập PHI thật.
- AI không gửi hướng xử trí cuối cùng cho bệnh nhân nếu chưa có HITL approval.
- MCP/FHIR/CDS integrations cần auth, audit logging và phân quyền trước khi dùng trong môi trường y tế thật.

## 6. Tool catalog và external provider trên Render

Catalog 82 tool được load trực tiếp từ `src/tool/catalog/` khi process khởi động và không cần thêm build
step. Intake orchestrator dùng local adapter nên patient triage demo vẫn hoạt động khi chưa cấu hình MCP.

Hai loại runtime cần được phân biệt:

| Runtime | Mục đích | Persistence |
|---|---|---|
| Local catalog adapter | Demo, test và deterministic fallback | In-memory, mất khi restart/redeploy |
| External MCP/provider | Terminology, guideline, FHIR, CDS, notification, audit thật | Do server/provider ngoài quản lý |

Các tool FHIR write, SMS, email, push, paging và appointment local chỉ ghi vào state/outbox. Output
`sent=false` hoặc `delivered=false` không phải lỗi: nó xác nhận chưa có provider ngoài báo delivery thành
công. Không dùng local outbox làm notification backend production.

Khi bật external MCP trên Render:

1. Khai báo URL bằng Render Environment, không ghi secret trong repository.
2. Bảo đảm endpoint dùng HTTPS và có authentication phù hợp; URL hiện tại chỉ là cấu hình transport.
3. Cấu hình timeout, retry và idempotency tại MCP server/provider.
4. Gửi PHI tối thiểu cần thiết và chạy redaction/policy trước external call.
5. Lưu audit vào persistent append-only store thay vì in-memory list.
6. Kiểm thử trạng thái provider accepted/delivered/failed và fallback sang manual review.

Render Free không phù hợp cho webhook delivery, durable queue hoặc dữ liệu lâm sàng vì service có thể sleep
và filesystem/process state không bền vững. Trước production cần database, queue, secrets manager,
authentication/RBAC, encryption, backup, retention policy và clinical validation.

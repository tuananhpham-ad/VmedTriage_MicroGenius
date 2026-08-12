# Deploy VMedTriage lên Railway

VMedTriage deploy trên Railway dưới dạng một Web Service build từ `Dockerfile` có sẵn ở root
repository. FastAPI phục vụ cả Demo UI tại `/` và API tại `/api/v1`.

Railway build bằng Dockerfile là lựa chọn khuyến nghị cho project này (thay vì Nixpacks) vì
Dockerfile đã có multi-stage build, non-root user và healthcheck sẵn.

## 1. Chuẩn bị trước khi deploy

- Đảm bảo code đã push lên GitHub, branch cần deploy (ví dụ `tuananhpham` hoặc `main`).
- Không commit `.env` hoặc secret thật vào repo — dùng `.env.example` làm tham chiếu cho danh
  sách biến cần cấu hình trên Railway.
- Kiểm tra `Dockerfile` đang `EXPOSE 8000` và `CMD` chạy `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
  Railway sẽ tiêm biến `$PORT` runtime — cần sửa lệnh start để bind đúng cổng Railway cấp (xem mục 4).

## 2. Tạo project trên Railway

1. Vào <https://railway.app/> và đăng nhập bằng GitHub.
2. Chọn **New Project > Deploy from GitHub repo**.
3. Chọn repository chứa VMedTriage (ví dụ `AI20K-Build-Phase-Cohort-3/P-141`).
4. Railway tự phát hiện `Dockerfile` ở root và build bằng Docker thay vì Nixpacks.
5. Trong **Settings > Source**, chọn đúng branch cần deploy (mặc định Railway theo branch dùng khi
   tạo project; đổi trong **Settings > Source > Branch** nếu cần).

## 3. Cấu hình Service

Vào tab **Settings** của service vừa tạo:

| Mục | Giá trị |
|---|---|
| Builder | Dockerfile |
| Root Directory | `/` (root repo) |
| Healthcheck Path | `/health` |
| Healthcheck Timeout | 30s (mặc định là đủ) |
| Networking | Bật **Generate Domain** để có public URL dạng `*.up.railway.app` |

Railway tự cấp domain public khi bấm **Generate Domain** trong tab **Settings > Networking**,
không cần cấu hình thêm DNS trừ khi muốn gắn custom domain.

## 4. Sửa Dockerfile để bind đúng `$PORT` của Railway

Railway không đảm bảo cổng nội bộ luôn là 8000 — nó tiêm biến môi trường `PORT` và route traffic
tới cổng đó. `CMD` hiện tại hard-code `--port 8000`, cần sửa để đọc `$PORT`:

```dockerfile
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Thay dòng `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]` ở cuối
`Dockerfile` bằng dòng trên (dùng shell form để `$PORT` được expand). Giữ nguyên `EXPOSE 8000` —
chỉ có tính chất tài liệu, không ảnh hưởng routing của Railway.

## 5. Environment variables

Vào tab **Variables** của service, thêm các biến cần thiết (tham chiếu `.env.example`):

| Key | Ghi chú |
|---|---|
| `APP_ENV` | `production` |
| `APP_HOST` | `0.0.0.0` |
| `LLM_PROVIDER` | `deepseek` hoặc `auto` tuỳ cấu hình |
| `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` | Chỉ set provider thật sự dùng |
| `DEEPSEEK_MODEL_NAME`, `GEMINI_MODEL_NAME` | Theo model đang dùng |
| `DATABASE_URL` | Nếu dùng Postgres, trỏ tới connection string do Railway Postgres plugin cấp (xem mục 6) |
| `CORS_ORIGINS` | Domain frontend nếu tách riêng frontend/backend |
| `SMTP_*` | Chỉ cần khi bật gửi email thật; để trống thì reset link/verification code sẽ chỉ log ra server logs |

Railway hỗ trợ import hàng loạt bằng nút **Raw Editor** trong tab Variables — có thể dán nội dung
dạng `KEY=value` mỗi dòng.

**Không** set biến `PORT` thủ công — Railway tự inject giá trị này, override sẽ gây lỗi routing.

## 6. Database (tuỳ chọn)

Project dùng SQLAlchemy + `psycopg2-binary`, mặc định fallback SQLite (`sqlite:///./data/app.db`).
SQLite trên Railway **không bền vững** vì filesystem của container là ephemeral khi redeploy.

Nếu cần Postgres thật:

1. Trong project Railway, chọn **New > Database > Add PostgreSQL**.
2. Railway tự tạo biến `DATABASE_URL` nội bộ trong service Postgres.
3. Vào service backend, tab **Variables**, dùng **Add Variable Reference** để trỏ
   `DATABASE_URL` của backend sang biến `DATABASE_URL` của service Postgres
   (cú pháp `${{Postgres.DATABASE_URL}}`).
4. Chạy migration (nếu có Alembic) qua **Deploy hook** hoặc thủ công qua Railway CLI trước khi
   traffic thật vào service.

## 7. Deploy

Sau khi cấu hình xong Variables và sửa Dockerfile:

1. Commit và push thay đổi Dockerfile lên branch đang deploy.
2. Railway tự trigger build mới (auto-deploy on push bật mặc định, có thể tắt trong
   **Settings > Source**).
3. Theo dõi build log trong tab **Deployments**.
4. Sau khi deploy healthy, lấy public URL trong tab **Settings > Networking**, dạng:

```text
https://<service-name>-production.up.railway.app
```

Kiểm tra:

```text
https://<service-name>-production.up.railway.app/health
https://<service-name>-production.up.railway.app/api/v1/status
```

## 8. Public demo flow

1. Mở `/`.
2. Nhập triệu chứng mẫu:

```text
Tôi đau ngực từ sáng, đi vài bước là hụt hơi.
```

3. UI hiển thị patient-safe response.
4. Panel case hiển thị structured mapping, red flags và triage proposal.
5. Panel điều dưỡng có thể `Approve`, `Escalate`, hoặc `Ask more`.

## 9. Lưu ý production

- Railway free/hobby plan có giới hạn usage-based credit hàng tháng; theo dõi usage trong tab
  **Usage** để tránh service bị tạm dừng.
- In-memory case store sẽ mất dữ liệu khi service restart/redeploy — cần Postgres (mục 6) trước
  khi dùng thật.
- Demo public không được nhập PHI thật.
- AI không gửi hướng xử trí cuối cùng cho bệnh nhân nếu chưa có HITL approval.
- MCP/FHIR/CDS integrations cần auth, audit logging và phân quyền trước khi dùng trong môi trường
  y tế thật — xem chi tiết ở mục "Tool catalog và external provider" trong
  [deploy_render.md](deploy_render.md#6-tool-catalog-và-external-provider-trên-render), áp dụng
  tương tự trên Railway.
- Railway container filesystem là ephemeral — không lưu dữ liệu quan trọng (audit log, outbox) vào
  local disk/`data/` nếu chưa gắn Volume hoặc chuyển sang external store.

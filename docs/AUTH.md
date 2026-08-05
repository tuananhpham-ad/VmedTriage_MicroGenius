# Xác thực và phân quyền

API auth nằm dưới prefix hiện có `/api/v1`. Hệ thống có hai role:

| Role | Quyền chính |
|---|---|
| `patient` | Gửi chat triage, xem chi tiết ca |
| `nurse` | Xem hàng đợi, duyệt ca, gọi/list MCP tools, xem chi tiết ca |

`/health`, `/api/v1/status`, `/api/v1/register` và `/api/v1/login` là public. Các route được bảo vệ yêu cầu header `Authorization: Bearer <token>`.

## 1. Cấu hình

Sao chép `.env.example` thành `.env`, sau đó đặt tối thiểu:

```dotenv
DATABASE_URL=sqlite:///./data/app.db
JWT_SECRET_KEY=thay-bang-chuoi-ngau-nhien-dai-va-bi-mat
ACCESS_TOKEN_EXPIRE_MINUTES=60
NURSE_REGISTRATION_CODE=ma-moi-rieng-cho-dieu-duong
```

Không commit `JWT_SECRET_KEY` hoặc `NURSE_REGISTRATION_CODE`. Trong production, ứng dụng sẽ từ chối khởi động nếu còn JWT secret mặc định hoặc thiếu mã đăng ký điều dưỡng.

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

Bảng `users` được tạo khi ứng dụng khởi động. Với thay đổi schema ở production, nên bổ sung Alembic migration thay cho `create_all`.

## 2. Test bằng curl trên PowerShell

Đăng ký và đăng nhập bệnh nhân:

```powershell
'{"email":"patient@example.com","password":"StrongPass123!","full_name":"Demo Patient","role":"patient"}' | curl.exe -X POST http://localhost:8000/api/v1/register `
  -H "Content-Type: application/json" `
  --data-binary '@-'

$patientSession = '{"email":"patient@example.com","password":"StrongPass123!"}' | curl.exe -s -X POST http://localhost:8000/api/v1/login `
  -H "Content-Type: application/json" `
  --data-binary '@-' | ConvertFrom-Json
$patientToken = $patientSession.access_token
```

Đăng ký và đăng nhập điều dưỡng (thay mã cho khớp `.env`):

```powershell
'{"email":"nurse@example.com","password":"StrongPass123!","full_name":"Demo Nurse","role":"nurse","nurse_registration_code":"ma-moi-rieng-cho-dieu-duong"}' | curl.exe -X POST http://localhost:8000/api/v1/register `
  -H "Content-Type: application/json" `
  --data-binary '@-'

$nurseSession = '{"email":"nurse@example.com","password":"StrongPass123!"}' | curl.exe -s -X POST http://localhost:8000/api/v1/login `
  -H "Content-Type: application/json" `
  --data-binary '@-' | ConvertFrom-Json
$nurseToken = $nurseSession.access_token
```

Hai case bắt buộc của middleware:

```powershell
# Đúng role: nurse -> 200
curl.exe -i http://localhost:8000/api/v1/nurse/queue `
  -H "Authorization: Bearer $nurseToken"

# Sai role: patient -> 403
curl.exe -i http://localhost:8000/api/v1/nurse/queue `
  -H "Authorization: Bearer $patientToken"
```

Thiếu token sẽ trả `401`; token hợp lệ nhưng sai role trả `403`.

## 3. Test bằng Postman

1. Tạo request `POST {{baseUrl}}/api/v1/register`, chọn Body → raw → JSON và dùng payload như phần curl.
2. Tạo request `POST {{baseUrl}}/api/v1/login`; trong tab Tests lưu token bằng `pm.environment.set("token", pm.response.json().access_token)`.
3. Ở request được bảo vệ, chọn Authorization → Bearer Token → `{{token}}`.
4. Gọi queue bằng token điều dưỡng để nhận `200`, rồi đổi sang token bệnh nhân để xác nhận `403`.

Có thể chạy regression suite bằng:

```powershell
python -m pytest -q
./scripts/test_auth_curl.ps1
```

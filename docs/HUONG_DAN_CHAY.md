# Hướng dẫn chạy VMedTriage — từ máy cá nhân tới bản public

Tài liệu duy nhất cho việc chạy và deploy. Mỗi bước có lệnh copy-paste được và cách tự kiểm chứng.
Chi tiết API auth xem [AUTH.md](AUTH.md).

Hạ tầng của bản public:

| Thành phần | Dịch vụ | Chi phí |
|---|---|---|
| Web + UI + API | Azure Container Apps (2 vCPU / 4 GiB) | $0 — free grant + $100 credit sinh viên |
| Image registry | Azure Container Registry (Basic) | ~$5/tháng, trừ vào credit |
| Database | Neon Postgres | $0, free vĩnh viễn (0.5 GB) |
| Email xác thực | Gmail SMTP + App Password | $0, 500 email/ngày |

Chọn Azure vì đặt được **4 GiB RAM** — đủ để giữ `ENABLE_GRAPH_TRIAGE_AGENT=true` (PhoBERT
~500 MB + fusion ~500 MB + torch) — và **Azure for Students không cần thẻ tín dụng**, chỉ cần
email trường. Đã loại: Render free (512 MB, không đủ), Hugging Face Spaces free (2026 khoá cả
Docker lẫn CPU Basic sau PRO), Google Cloud Run (bắt buộc có thẻ).

> **Ba giới hạn của subscription Azure for Students** — đều phát hiện lúc deploy thật, không tài
> liệu nào cảnh báo trước. Đọc trước để khỏi mất thời gian như lần đầu:
>
> 1. **Chỉ deploy được vào 5 vùng**: `eastasia`, `koreacentral`, `japaneast`, `malaysiawest`,
>    `indiasouthcentral`. Singapore (`southeastasia`) bị chặn bằng lỗi `RequestDisallowedByAzure`.
>    Dùng **`eastasia`** (Hong Kong) — gần Việt Nam nhất.
> 2. **ACR Tasks bị khoá** (`TasksOperationsNotAllowed`) — không build image trên cloud được, phải
>    build tại máy rồi push.
> 3. **Cloud Build bằng Buildpack của `az containerapp up` hỏng** (`/lifecycle/analyzer:
>    Permission denied`), và nó cũng bỏ qua Dockerfile của dự án.

---

## Phần 0 — Dọn secret trước khi đụng tới bản public

`.env.example` đang được git theo dõi và chứa **key thật** (`LANGFUSE_SECRET_KEY` dòng 48,
`TAVILY_API_KEY` dòng 99). File đã commit từ trước nên dòng `.env.example` trong `.gitignore`
không còn tác dụng — nó đang nằm trên GitHub, ai clone cũng đọc được.

```bash
# 1. Vào dashboard Langfuse và Tavily REVOKE hai key đó
#    (bắt buộc — key đã nằm trong lịch sử git, xoá khỏi file không cứu được)
# 2. Thay giá trị trong .env.example bằng placeholder rỗng
# 3. Ngừng theo dõi file
git rm --cached .env.example
git commit -m "chore: stop tracking .env.example, revoke leaked keys"
```

Kiểm chứng: `git ls-files .env.example` không in ra gì.

---

## Phần 1 — Chạy local

### 1.1 Môi trường

```powershell
# PowerShell, trong thư mục P-141/
..\.venv\Scripts\Activate.ps1        # venv nằm ở thư mục CHA (2026.MAS.MedicineTriage\.venv)
pip install -r requirements.txt
pip install -r requirements-graph.txt   # chỉ khi muốn bật graph triage (~2.5 GB torch)
```

### 1.2 Cấu hình `.env`

Tối thiểu để đăng ký/đăng nhập chạy được:

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./data/app.db
JWT_SECRET_KEY=<chuỗi ngẫu nhiên >= 32 ký tự>
NURSE_REGISTRATION_CODE=<mã mời cho điều dưỡng>
OPENROUTER_API_KEY=<key LLM>
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # sinh JWT secret
```

Email ở local: **để trống `SMTP_HOST`** thì mã xác thực in thẳng ra log server thay vì gửi đi —
đỡ phải mở Gmail mỗi lần test. Muốn thử email thật thì điền đủ 6 biến `SMTP_*` (xem 2.2).

`DATABASE_URL` phải là SQLite khi chạy local.

### 1.3 Chạy

```bash
make run
# hoặc: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# nếu gặp "Fatal error in launcher": python -m uvicorn src.main:app --reload --port 8000
```

| Địa chỉ | Nội dung |
|---|---|
| http://localhost:8000/ | Giao diện web (patient + nurse) |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | `{"status":"ok","env":"development"}` |

Chạy bằng Docker, đúng image sẽ chạy trên Azure:

```bash
docker compose up --build     # mở http://localhost:8000
```

### 1.4 Tài khoản demo (bỏ qua xác thực email)

```bash
python -m scripts.seed_demo_users
```

Tạo `user0/user0` (patient) và `nurse0/nurse0` (nurse), cả hai `email_verified=True`. Đăng nhập
được bằng tên đăng nhập hoặc email.

### 1.5 Test luồng đăng ký thật ở local

```bash
BASE=http://localhost:8000

curl -X POST $BASE/api/v1/register -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123!","full_name":"Test","role":"patient"}'
# SMTP_HOST rỗng -> mã 6 số hiện trong log terminal đang chạy uvicorn

curl -X POST $BASE/api/v1/auth/email-verification/confirm -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","code":"<mã 6 số>"}'

curl -X POST $BASE/api/v1/login -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123!"}'
```

Chưa xác thực email mà đăng nhập → **403** kèm "Email chưa được xác thực". Đó là hành vi đúng.
Tài khoản nurse: thêm `"role":"nurse","nurse_registration_code":"<mã trong .env>"`.

---

## Phần 2 — Hạ tầng cho bản public

### 2.1 Database — Neon Postgres

1. https://neon.tech → sign up bằng GitHub → **Create project**, region **Singapore**.
2. Copy *Connection string*:
   `postgresql://<user>:<pass>@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   Giữ nguyên `?sslmode=require` — bỏ đi là Neon từ chối kết nối.
3. **Không cần bật Neon Auth.** Dự án có hệ auth riêng (argon2 + JWT + mã xác thực email); bật
   Neon Auth chỉ thêm một bảng `neon_auth.users_sync` nằm không.
4. Kiểm chứng từ máy:
   ```bash
   python -c "import io,sqlalchemy as sa; env=dict(l.strip().split('=',1) for l in io.open('deploy/azure/env',encoding='utf-8') if l.strip() and not l.startswith('#') and '=' in l); print(sa.create_engine(env['DATABASE_URL']).connect().execute(sa.text('select version()')).scalar())"
   ```

App tự `CREATE TABLE` lúc khởi động ([src/main.py](../src/main.py)), không cần migration.

### 2.2 Email thật — Gmail SMTP

Trang App passwords **không còn nằm trong mục 2-Step Verification** — vào thẳng
**https://myaccount.google.com/apppasswords**, gõ tên app (`vmedtriage`) → **Create** → chuỗi 16
ký tự (chỉ hiện một lần). Mật khẩu Gmail thường không dùng được cho SMTP từ 2022.

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=<gmail của bạn>
SMTP_PASSWORD=<app password 16 ký tự>
SMTP_FROM_EMAIL=<thường trùng SMTP_USERNAME>
```

Kiểm chứng credential mà không gửi email nào:

```bash
python -c "import io,smtplib; env=dict(l.strip().split('=',1) for l in io.open('.env',encoding='utf-8') if l.strip() and not l.startswith('#') and '=' in l); s=smtplib.SMTP(env['SMTP_HOST'],int(env['SMTP_PORT']),timeout=20); s.starttls(); s.login(env['SMTP_USERNAME'],env['SMTP_PASSWORD']); print('SMTP OK'); s.quit()"
```

Hạn mức free: 500 email/ngày.

---

## Phần 3 — Deploy public lên Azure Container Apps

### 3.1 Chuẩn bị một lần

**Tài khoản:** https://azure.microsoft.com/free/students → **Start free** → xác minh bằng email
trường (`@vnu.edu.vn`). Không cần thẻ. Nhận $100 credit trong 12 tháng.

**Công cụ trên máy:**

```powershell
winget install -e --id Microsoft.AzureCLI      # bấm Yes ở cửa sổ UAC
# đóng terminal, mở lại (PATH chỉ nạp lúc khởi động)
az login                                       # trình duyệt mở ra, chọn tài khoản trường
```

Docker Desktop phải **đang chạy** — build diễn ra tại máy (xem giới hạn số 2 ở đầu tài liệu).

**Budget alert** (khuyến nghị, cảnh báo email khi tiêu quá $5/tháng):

```bash
SUB=$(az account show --query id -o tsv)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/vmedtriage-budget?api-version=2023-05-01" \
  --body @deploy/azure/budget.json
```

### 3.2 Biến môi trường

```bash
cp deploy/azure/env.example deploy/azure/env
```

Điền giá trị thật vào `deploy/azure/env`. Thiếu 3 biến đầu thì app **từ chối khởi động** ở
`APP_ENV=production`:

| Biến | Lấy từ đâu |
|---|---|
| `DATABASE_URL` | Chuỗi Neon ở 2.1, giữ nguyên `?sslmode=require` |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `NURSE_REGISTRATION_CODE` | Tự đặt, là mã mời để đăng ký tài khoản nurse |
| `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` | Copy từ `.env` |
| `OPENROUTER_API_KEY` | Copy từ `.env`, hoặc key của provider bạn dùng |
| `PASSWORD_RESET_BASE_URL` / `CORS_ORIGINS` | URL của app — chưa biết ở lần deploy đầu, xem 3.4 |

File này đã nằm trong `.gitignore`, không bao giờ lên git.

### 3.3 Deploy

Chạy trong **Git Bash**, không phải PowerShell:

```bash
./scripts/deploy_azure.sh
```

Hoặc gọi từ PowerShell mà không đổi cửa sổ:

```powershell
& "C:\Program Files\Gitinash.exe" ./scripts/deploy_azure.sh
```

PowerShell không hiểu shebang nên gõ thẳng `./scripts/deploy_azure.sh` sẽ **im lặng không làm gì**;
còn `python ./scripts/deploy_azure.sh` thì báo `SyntaxError: invalid decimal literal`.

Script tự làm, tất cả đều idempotent nên chạy lại bao nhiêu lần cũng được:

1. Đăng ký resource provider `Microsoft.App`, `OperationalInsights`, `ContainerRegistry`
2. Tạo resource group + Container Apps environment ở **eastasia**
3. Tạo Container Registry (Basic) nếu chưa có
4. `docker build` tại máy → `docker push` lên registry
5. Tạo/cập nhật container app: image mới, biến môi trường từ `deploy/azure/env`, ingress public,
   2 vCPU / 4 GiB, min 0 / max 3 replica
6. In ra URL

Lần đầu **25–40 phút**: build ~20 phút (torch CPU + transformers + tải ~1 GB artifact graph
triage) và push ~2–3 GB lên registry. **Các lần sau chỉ vài phút** — Docker chỉ đẩy layer đã đổi,
mà layer artifact 1 GB thì không đổi.

Đổi mặc định nếu cần:

```bash
RESOURCE_GROUP=my-rg LOCATION=koreacentral APP_NAME=vmedtriage ./scripts/deploy_azure.sh
```

### 3.4 Điền URL rồi chạy lại

Lần deploy đầu in ra URL dạng
`https://vmedtriage.calmtree-cb126742.eastasia.azurecontainerapps.io`. Sửa
`PASSWORD_RESET_BASE_URL` và `CORS_ORIGINS` trong `deploy/azure/env` thành URL đó, chạy lại
`./scripts/deploy_azure.sh` (lần này nhanh, không build lại).

Bỏ qua bước này thì link đặt lại mật khẩu trong email gửi cho người dùng trỏ về
`http://localhost:8000` và bấm vào là hỏng.

### 3.5 Kiểm chứng bản public

```bash
BASE=https://vmedtriage.calmtree-cb126742.eastasia.azurecontainerapps.io

curl -s $BASE/health          # {"status":"ok","env":"production"}
curl -s $BASE/api/v1/status   # {"status":"ready",...}

# Đăng ký bằng Gmail thật -> mở hộp thư lấy mã 6 số
curl -s -X POST $BASE/api/v1/register -H "Content-Type: application/json" \
  -d '{"email":"ban@gmail.com","password":"StrongPass123!","full_name":"Ten That","role":"patient"}'

curl -s -X POST $BASE/api/v1/auth/email-verification/confirm -H "Content-Type: application/json" \
  -d '{"email":"ban@gmail.com","code":"123456"}'
```

Rồi mở `$BASE` trên trình duyệt, đăng ký/đăng nhập bằng giao diện.

Xem log:

```bash
az containerapp logs show --name vmedtriage --resource-group vmedtriage-rg --follow
```

---

## Lưu ý vận hành

- **Tắt máy cá nhân không ảnh hưởng bản public.** App chạy trên hạ tầng Azure, DB ở Neon, email do
  server Azure gửi. Máy bạn chỉ là chỗ build và đẩy image.
- **Artifact được nướng sẵn vào image lúc build** ([Dockerfile](../Dockerfile)) chứ không tải lúc
  khởi động — cold start không phải chờ tải ~1 GB.
- **Cold start**: `min-replicas 0` nghĩa là không có request thì replica bị thu hồi; request kế
  tiếp phải khởi động container và nạp model — chậm vài chục giây. Trước buổi demo nên gọi
  `/health` một lần cho nóng máy.
- **Dữ liệu người dùng nằm ở Neon**, không mất khi redeploy hay khi replica bị thu hồi.
- **Neon** tự suspend khi rảnh nhưng thức lại trong ~1 giây.
- Theo dõi credit ở **Azure Portal → Cost Management + Billing**.

---

## Xử lý sự cố

| Triệu chứng | Nguyên nhân |
|---|---|
| `make: *** No rule to make target 'run'` | Đang đứng ở thư mục cha — `cd P-141` trước |
| `Fatal error in launcher: Unable to create process using ...python.exe` | Venv tạo lúc thư mục còn tên khác; các `.exe` trong `Scripts/` nhúng cứng đường dẫn cũ. Dùng `python -m uvicorn ...`, hoặc xoá venv tạo lại |
| Gõ `./scripts/deploy_azure.sh` mà không có gì xảy ra | Đang ở PowerShell. Script là bash — chạy trong Git Bash, hoặc `& "C:\Program Files\Gitinash.exe" ./scripts/deploy_azure.sh` |
| `SyntaxError: invalid decimal literal` | Chạy script bash bằng `python`. Xem dòng trên |
| `az : The term 'az' is not recognized` | Terminal mở trước lúc cài Azure CLI. Mở terminal mới, hoặc `$env:PATH += ";C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin"` |
| `could not translate host name "dpg-..."` | `DATABASE_URL` là chuỗi **nội bộ** của Render, chỉ dùng được bên trong Render |
| `UnicodeDecodeError: 'charmap' codec` khi `pip install -r` | File requirements có chữ tiếng Việt có dấu; pip đọc bằng locale cp1252. Giữ requirements thuần ASCII, hoặc `$env:PYTHONUTF8=1` |
| `UnicodeEncodeError: '\u2713'` khi chạy `az` | Console cp1252 không in được ký tự ✓ của Azure CLI. Đặt `$env:PYTHONIOENCODING="utf-8"` |
| `RequestDisallowedByAzure` | Deploy vào vùng ngoài 5 vùng cho phép của Azure for Students. Dùng `eastasia` |
| `TasksOperationsNotAllowed` | Subscription sinh viên không được dùng ACR Tasks. Phải build tại máy — đúng cách script đang làm |
| `/lifecycle/analyzer: Permission denied` | Buildpack của `az containerapp up` hỏng. Đừng dùng `--source`, build bằng Dockerfile rồi push |
| Không nhận được email xác thực | Log có `Account email delivery failed` → sai app password; có `SMTP is not configured` → thiếu `SMTP_HOST` |
| Login trả 403 | Chưa xác thực email — gọi `/api/v1/auth/email-verification/resend` |
| Login trả 401 dù mật khẩu đúng | `seed_demo_users` chưa chạy được, hoặc đang trỏ nhầm database |
| App không khởi động ở production | Thiếu `JWT_SECRET_KEY` / `NURSE_REGISTRATION_CODE`, hoặc `DATABASE_URL` vẫn là SQLite |
| `no such column` / `SchemaDriftError` | DB cũ thiếu cột: xoá `data/app.db` (local) rồi chạy lại |
| Replica chết khi có request đầu (OOM) | Memory dưới 4 GiB — graph triage nạp PhoBERT + fusion là hết 2 GiB. Gói Consumption bắt buộc memory = cpu × 2 GiB, nên 2 vCPU đi với đúng 4 GiB |
| `docker build` báo không tìm thấy Dockerfile khi build trên cloud | `Dockerfile` bị liệt kê trong `.dockerignore` |
| Push image rất lâu | Bình thường ở lần đầu (~2–3 GB). Lần sau chỉ đẩy layer code |
| Cảnh báo `Direct use of automatic function calling (AFC)...` | Cảnh báo vô hại của SDK `google-genai`. Muốn tắt: `logging.getLogger("google_genai.models").setLevel(logging.ERROR)` |

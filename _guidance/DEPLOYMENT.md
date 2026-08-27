# Hướng dẫn deploy VMedTriage

Tài liệu này dành cho người **chưa từng deploy repo này**. Đọc hết mục 1–2 trước khi gõ lệnh đầu tiên.

Có hai đường deploy, chọn theo nhu cầu:

| | **Azure Container Apps** | **Render (free)** |
|---|---|---|
| Script / config | `scripts/deploy_azure.sh` | `render.yaml` (auto-deploy theo commit) |
| Graph triage (AI đề xuất ở màn hình điều dưỡng) | **Có** (`GRAPH_TRIAGE_MODE=c6`) | **Không** — 512 MB RAM không nạp nổi PhoBERT + fusion |
| Chi phí | Credit Azure for Students (~$0 nếu `min-replicas=0`) | $0 |
| Cần Docker ở máy | Có | Không |
| Lần deploy đầu | ~20–30 phút (build + push ~2–3 GB) | ~5 phút |

> **Chọn Azure** nếu cần demo đầy đủ luồng điều dưỡng. **Chọn Render** nếu chỉ cần bản public cho luồng chat + HITL cơ bản.

Cả hai đường đều **không** kèm database: dùng Neon Postgres (free vĩnh viễn). App từ chối khởi động khi `APP_ENV=production` mà `DATABASE_URL` vẫn là SQLite.

---

## 1. Xin bí mật trước khi bắt đầu

`deploy/azure/env` **nằm trong `.gitignore`** — clone repo về sẽ không có nó. Người deploy phải tự tạo từ `deploy/azure/env.example` và xin các giá trị sau từ team (Tuấn Anh / Dũng):

**Bắt buộc, không có thì app không chạy:**

| Biến | Lấy ở đâu |
|---|---|
| `DATABASE_URL` | Chuỗi kết nối Neon, giữ nguyên `?sslmode=require` |
| `JWT_SECRET_KEY` | Tự sinh chuỗi ngẫu nhiên ≥32 ký tự (`openssl rand -hex 32`) — **không** dùng lại của môi trường khác |
| `NURSE_REGISTRATION_CODE` | Tự đặt; đây là mã mời để đăng ký tài khoản điều dưỡng |
| Ít nhất một LLM key | `OPENROUTER_API_KEY` (khuyến nghị) hoặc `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` |

**Nên có, thiếu thì mất tính năng chứ không chết app:**

| Biến | Thiếu thì sao |
|---|---|
| `SMTP_*` | Không gửi được email xác thực / reset mật khẩu (dev: nội dung email ghi ra log) |
| `TAVILY_API_KEY` | `source_support` không trích được nguồn y văn |
| `WEAVIATE_URL` / `WEAVIATE_API_KEY` | Không lưu case dạng vector (best-effort, pipeline vẫn chạy) |

**Đừng tự bật:** `LONG_MEMORY_ENABLED` giữ `false` cho tới khi PM trả lời consent + retention bằng văn bản (xem `_guidance/features/F04_memory.md`). Đây là dữ liệu y tế sống lâu hơn phiên sinh ra nó — bật nó là một quyết định có người ký, không phải một mặc định lọt vào production kèm một lần deploy.

Bàn giao bí mật qua kênh riêng (1Password / tin nhắn trực tiếp), **không** qua PR, issue, hay channel chung.

---

## 2. Chạy thử tại máy trước (10 phút, tiết kiệm nhiều giờ)

Đừng deploy một bản chưa từng chạy. Build và chạy đúng image sẽ lên cloud:

```bash
cp deploy/azure/env.example deploy/azure/env   # rồi điền giá trị thật
docker build -t vmedtriage .
docker run --rm -p 8000:8080 -e PORT=8080 --env-file deploy/azure/env vmedtriage
```

Kiểm tra:

```bash
curl http://localhost:8000/health
python -m scripts.check_nurse_flow            # luồng thật: chat -> phiếu chốt -> hàng đợi điều dưỡng -> AI đề xuất
```

`check_nurse_flow` là bài kiểm quan trọng nhất — nó bắt được đúng thứ mà `/health` **không** bắt được: ca không nổi lên hàng đợi điều dưỡng, hoặc `graph_decision` trả `null`. Lưu ý bài này **tốn API thật**.

---

## 3. Deploy lên Azure Container Apps

### 3.1 Cài đặt một lần

```bash
winget install -e --id Microsoft.AzureCLI    # Windows
az login
```

Cộng thêm: **Docker Desktop đang chạy**, và chạy script bằng **Git Bash** (không phải PowerShell / CMD).

### 3.1b Cho đồng đội quyền deploy

**Không chia sẻ tài khoản `az` của chủ subscription.** Tài khoản đó là `@vnu.edu.vn` (tài khoản trường) và đang giữ vai trò **Owner cấp subscription** — đưa credential là đưa cả billing, credit, và quyền xoá mọi thứ, trong khi mọi thao tác vẫn ghi log dưới tên chủ tài khoản. Riêng repo này còn một rò rỉ cụ thể: `az containerapp show` in thẳng toàn bộ env vars ra màn hình, gồm `DATABASE_URL`, `JWT_SECRET_KEY` và mọi API key.

Cách đúng: đồng đội tự `az login` bằng tài khoản của họ, chủ subscription cấp quyền **có phạm vi**:

```bash
az role assignment create \
  --assignee <email-cua-ho> \
  --role Contributor \
  --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/vmedtriage-rg
```

Thu hồi bằng `az role assignment delete` với cùng tham số.

Hai lưu ý:

* Người được cấp phải **cùng tenant**. Đồng đội có email `@vnu.edu.vn` thì đã ở sẵn trong tenant. Người ngoài phải được mời làm guest — việc này do IT của trường cấu hình và có thể bị chặn.
* Contributor phạm vi resource group **không** đăng ký được resource provider (đó là thao tác cấp subscription). Script đã xử lý: nó bỏ qua provider nào đã `Registered`. Nếu gặp provider chưa đăng ký, script dừng và in ra lệnh để chủ subscription chạy giúp một lần.

### 3.1c Service principal (deploy không cần tài khoản cá nhân)

Dùng khi người deploy không có tài khoản trong tenant, hoặc khi muốn deploy tự động từ CI. Service principal là "tài khoản máy" — không gắn với người nào.

Chủ subscription tạo một lần:

```bash
az ad sp create-for-rbac --name vmedtriage-deploy \
  --role Contributor \
  --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/vmedtriage-rg \
  --years 1
```

Lệnh in ra `appId`, `password`, `tenant`. **`password` chỉ hiện đúng một lần** — không đọc lại được, mất thì phải reset. Bàn giao qua kênh riêng như mọi bí mật khác (mục 1).

Người deploy đăng nhập bằng bộ đó rồi chạy script như bình thường:

```bash
az login --service-principal -u <appId> -p <password> --tenant <tenant>
az account set --subscription <SUBSCRIPTION_ID>
./scripts/deploy_azure.sh
```

Đánh đổi cần biết trước khi chọn cách này:

* **Ai cầm secret cũng dùng được**, và audit log chỉ ghi tên service principal — không truy được người thật đứng sau. Cấp quyền cho từng tài khoản cá nhân (3.1b) vẫn là mặc định tốt hơn khi người đó có tài khoản trong tenant.
* **Secret hết hạn sau 1 năm.** Deploy đột nhiên báo lỗi xác thực sau một thời gian dài không đụng tới thì nghĩ tới đây đầu tiên.
* Không đăng ký được resource provider (cùng giới hạn như 3.1b).

Reset secret khi lộ, hoặc xoá hẳn khi hết dùng:

```bash
az ad sp credential reset --id <appId>        # cấp secret mới, secret cũ hết hiệu lực
az ad sp delete --id <appId>                  # xoá hẳn, kèm luôn role assignment
```

> **Vì sao build tại máy chứ không trên cloud:** subscription Azure for Students chặn cả hai đường build cloud — `az acr build` trả `TasksOperationsNotAllowed`, còn `az containerapp up --source .` dùng Buildpack (bỏ qua Dockerfile của dự án) và Buildpack đó chết. Đổi lại, layer artifact ~1 GB chỉ push **một lần**; các lần deploy sau chỉ đẩy vài MB code.

### 3.2 Ràng buộc vùng — đọc kỹ, đây là chỗ dễ hỏng nhất

Azure for Students chỉ cho deploy vào 5 vùng: `koreacentral`, `malaysiawest`, `eastasia`, `indiasouthcentral`, `japaneast`.

**Trong 5 vùng đó, KHÔNG được chọn `eastasia`.** Hong Kong nằm ngoài danh sách phục vụ của cả OpenAI lẫn Gemini (403 / 400 `FAILED_PRECONDITION`). Hệ quả không hiển nhiên: app **không** chết hẳn (DeepSeek vẫn sống), nó chỉ mất nhánh GPT-direct của C6 — và vì `service.py` trả `None` khi nhánh đó hỏng, **mọi ca không phải cấp cứu biến mất khỏi hàng đợi điều dưỡng**. Triệu chứng nhìn thấy: "điều dưỡng chỉ nhận được ca red-flag". Đã xảy ra thật trên revision 0000005 (2026-08-24).

Mặc định của script là `japaneast` — cứ để nguyên.

### 3.3 Chạy

```bash
./scripts/deploy_azure.sh
```

Script tự làm 6 bước: đọc env → tạo resource group + environment → tạo/dùng lại container registry → build image tại máy → push → tạo/cập nhật container app. Sau đó nó tự chạy hai bước kiểm tra và in URL ra.

Ghi đè mặc định bằng biến môi trường nếu cần: `RESOURCE_GROUP`, `LOCATION`, `ENVIRONMENT`, `APP_NAME`, `IMAGE_TAG`.

### 3.4 Vòng hai: cập nhật URL rồi chạy lại

Lần deploy đầu bạn chưa biết URL, nên `PASSWORD_RESET_BASE_URL` và `CORS_ORIGINS` trong env vẫn là giá trị mẫu. Sau khi script in URL ra:

1. Sửa hai biến đó trong `deploy/azure/env` thành URL thật.
2. Chạy lại `./scripts/deploy_azure.sh` — lần này nhanh vì Docker layer đã cache.

Bỏ qua bước này thì link đặt lại mật khẩu gửi cho người dùng trỏ về `localhost:8000`.

### 3.5 Nghiệm thu

```bash
python -m scripts.check_nurse_flow --base-url https://<url-vua-in-ra>
```

**Deploy chỉ được coi là xong khi bài này pass**, không phải khi `/health` trả 200. Lần gọi đầu phải chờ cold start (`min-replicas=0`), có thể mất vài phút.

---

## 4. Deploy lên Render (bản free)

1. Kết nối repo với Render, nó tự đọc `render.yaml` (branch `dev`, auto-deploy theo commit).
2. Vào dashboard điền các secret có `sync: false` — Render **không** đọc chúng từ file, phải nhập tay: `DATABASE_URL`, `JWT_SECRET_KEY`, `NURSE_REGISTRATION_CODE`, các `*_API_KEY`, `SMTP_*`, `WEAVIATE_*`, `TAVILY_API_KEY`.
3. Sửa `PASSWORD_RESET_BASE_URL` và `CORS_ORIGINS` trong `render.yaml` thành URL thật của service.

Giới hạn cần biết: 512 MB RAM, ngủ sau 15 phút không request, 750 giờ/tháng cho cả workspace. Không có disk gắn ngoài nên `data/source_index/` bị dựng lại mỗi lần deploy (vài chục giây) — dữ liệu người dùng nằm ở Neon nên không mất gì.

Bật graph triage trên Render cần đổi sang instance ≥2 GB và sửa `buildCommand` / `startCommand` (hướng dẫn nằm ngay trong comment của `render.yaml`).

---

## 5. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Điều dưỡng **chỉ** nhận được ca red-flag | App đang ở `eastasia`, hoặc `GRAPH_TRIAGE_MODE` không phải `c6` | Xem 3.2; đọc lại env trên server |
| Deploy "thành công" nhưng không có AI đề xuất | Git Bash (MSYS) dịch đường dẫn POSIX thành `C:/Program Files/Git/...` | Để trống `GRAPH_TRIAGE_ARTIFACT_ROOT` trong env — Dockerfile đã set sẵn. Script tự cảnh báo ở bước kiểm tra 1/2 |
| `InvalidResourceGroupLocation` | Resource group đã tồn tại ở vùng khác | Không sao — script tự dùng lại group cũ; vùng của group chỉ là nhãn metadata |
| `MaxNumberOfGlobalEnvironmentsInSubExceeded` | Azure for Students chỉ cho **một** Container App Environment trên cả subscription | `./scripts/azure_teardown_env.sh` (chạy không cờ để xem trước, `--yes` để xoá thật) |
| `ManagedEnvironmentHasBuilders` | Tàn dư builder của `az containerapp up` | Script teardown đã xử lý đúng thứ tự: app → builders → environment |
| Environment ở sai vùng | Environment **không đổi vùng được** sau khi tạo | Tạo environment + app mới: `ENVIRONMENT=vmedtriage-japaneast-env APP_NAME=vmedtriage-japaneast ./scripts/deploy_azure.sh` (giữ nguyên `RESOURCE_GROUP` để dùng lại registry, khỏi push lại vài GB) |
| App chết ngay khi khởi động | — | Xem log: `az containerapp logs show -n vmedtriage -g vmedtriage-rg --follow` |

---

## 6. Chi phí và dọn dẹp

`deploy/azure/budget.json` đặt ngân sách $5/tháng với cảnh báo ở 50% và 90%. Đổi `contactEmails` sang email của người deploy trước khi áp dụng.

`--min-replicas 0` nghĩa là không có request thì không tốn credit — đánh đổi là cold start vài phút cho lần gọi đầu.

Không xoá container registry khi đổi vùng: image đã push nằm trong đó, và app ở vùng mới kéo image từ registry vùng cũ hoàn toàn bình thường. Xoá registry = phải build + push lại vài GB.

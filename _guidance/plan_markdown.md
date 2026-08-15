# Kế hoạch triển khai — Demo hub + BYO API key + Console logging

> Trạng thái: **✅ ĐÃ IMPLEMENT XONG** (2026-08-08). Kế hoạch bên dưới giữ nguyên làm lịch sử thiết kế.
> Kết quả thực tế và các khác biệt so với kế hoạch ghi ở **mục 5** cuối file.
>
> Kiểm chứng: `pytest` **82 pass**, `ruff` pass, chạy thật với DeepSeek.

---

## 0. Bối cảnh — đã có gì trước kế hoạch này

Phần agent hỏi-đáp theo checklist từng bệnh **đã làm xong và test thật với DeepSeek**:

| File | Vai trò |
|---|---|
| `src/domain/_disease_x.json` | Checklist mock: `name`, `condition`, `onset` (`value: null`) |
| `src/services/disease_checklist.py` | Nạp checklist từ JSON, tính % hoàn thành |
| `src/services/disease_agent.py` | LLM trích xuất + sinh câu hỏi; summary là template deterministic |
| `src/services/disease_session.py` | State machine `collecting → awaiting_confirmation → confirmed` |
| `src/services/session_log.py` | Ghi `logs/<session_id>.json`: mọi hỏi/đáp + mọi bản summary |
| `scripts/run_disease_qa.py` | CLI: `python -m scripts.run_disease_qa --demo` |
| `tests/test_services/test_disease_session.py` | 73/73 test pass, không gọi LLM thật |

Đã sửa `.env`: `LLM_PROVIDER` phải là **tên provider** (`deepseek`), không phải tên model
(`deepseek-chat`) — đặt sai làm `get_settings()` raise `ValidationError` và cả app không khởi động được.

---

## 1. Yêu cầu cần làm

1. **Trang hub tại `/`** — liệt kê link tới các demo, thay vì vào thẳng một demo như hiện nay.
2. **Console logging đẹp** — in ra terminal từng bước hỏi-đáp để quan sát khi chạy server.
3. **BYO API key** — người test tự nhập API key + chọn model LLM của họ trên UI, kèm gợi ý các model
   hiện có. Không bắt họ dùng key trong `.env` của dự án.

---

## 2. ⚠️ Chặn đường: lỗi API key bị đè giữa các user

**Phải sửa TRƯỚC khi làm mục 1.3 (BYO key), nếu không sẽ rò key/billing giữa những người test.**

Hiện trạng:

- Mọi provider trong `src/providers/*` đọc key bằng `os.getenv(self.api_key_env)` **bên trong
  `complete()`** — xem `openai_provider.py:39`, `gemini_provider.py:97`, `anthropic_provider.py:60`.
- `provider_router._build_provider()` (`src/services/provider_router.py:96`) ghi key vào
  `os.environ[spec.env_var]` — đây là **biến toàn process**.

Hệ quả khi mỗi user nhập key riêng: user A set `DEEPSEEK_API_KEY=keyA`, user B set `keyB` xen giữa →
request của A có thể chạy bằng key của B. Tính tiền nhầm người, và là rò rỉ credential.

**Cách sửa đã chốt:** truyền `api_key` tường minh xuống provider, không đi qua `os.environ`.

```python
# src/providers/openai_provider.py (và gemini, anthropic tương tự)
def __init__(self, *, api_key_env=..., api_key: str | None = None, base_url=None, default_model=None):
    self.api_key = api_key          # None -> giữ nguyên hành vi cũ

def complete(...):
    api_key = self.api_key or os.getenv(self.api_key_env)   # backward compatible
```

Giữ `os.getenv` làm fallback để không phá luồng hiện tại (`.env` vẫn chạy như cũ).

---

## 3. Các bước triển khai (theo đúng thứ tự phụ thuộc)

### Bước 1 — Providers nhận `api_key` tường minh

- Sửa `openai_provider.py`, `gemini_provider.py`, `anthropic_provider.py`: thêm param `api_key`.
- `deepseek_provider.py`, `openrouter_provider.py` kế thừa `OpenAIProvider` → forward param xuống.
- `src/providers/__init__.py`: `make_provider(name, *, api_key=None, model=None)`.
- **Ràng buộc:** mặc định `api_key=None` phải giữ nguyên hành vi cũ (đọc `os.getenv`) → không phá test.

### Bước 2 — `provider_router` hỗ trợ credential theo phiên

- Thêm dataclass:

```python
@dataclass(frozen=True, slots=True)
class LLMCredential:
    provider: str
    api_key: str
    model: str | None = None
```

- `complete(messages, *, credential: LLMCredential | None = None, ...)`:
  - Có `credential` → dùng đúng provider đó với key đó, **không đụng `os.environ`**, không fallback
    sang provider khác (key của người ta, không tự ý chuyển provider).
  - Không có → giữ nguyên logic hiện tại (đọc `Settings`, fallback theo `llm_provider_order`).
- Thêm catalog model gợi ý cho UI:

```python
SUGGESTED_MODELS: dict[str, list[str]] = {
    "deepseek":   ["deepseek-chat", "deepseek-reasoner"],
    "openai":     ["gpt-4o-mini", "gpt-4o"],
    "gemini":     ["gemini-2.0-flash", "gemini-2.0-flash-lite"],
    "anthropic":  ["claude-haiku-4-5-20251001", ...],
    "openrouter": ["openai/gpt-4o-mini", ...],
}
```

  ⚠️ **Phải verify tên model trước khi ghi vào code** — `.env` hiện có
  `GEMINI_MODEL_NAME="gemini-3.5-flash-lite"` là tên **không tồn tại**. Đừng chép lại tên sai.

- Thêm endpoint `GET /api/v1/llm/providers` trả `SUGGESTED_MODELS` + provider nào server có sẵn key,
  để UI render dropdown.

### Bước 3 — Truyền credential xuống session

- `DiseaseQAAgent.__init__(checklist, credential=None)` → forward vào mọi `provider_router.complete`.
- `disease_session.start_session(disease_id, credential=None)` → lưu credential trong
  `DiseaseSession`.
- Tương tự cho `IntakeAgent`/`intake_session` (demo `/intake.html`).

**🔒 Ràng buộc bảo mật bắt buộc:**

- API key **chỉ giữ in-memory trong session**, không ghi ra `logs/<session_id>.json`,
  không log ra console, không trả lại trong API response.
- `session_log.py` hiện log nguyên `payload` — phải rà lại để chắc chắn credential không lọt vào.
- Response chỉ trả về dạng đã che: `sk-••••1f13` + tên provider/model đang dùng.
- Cân nhắc thêm test riêng: "credential không xuất hiện trong file log".

### Bước 4 — Console logging đẹp

- Module mới `src/services/console_log.py` (hoặc mở rộng `session_log`).
- In ra terminal mỗi bước, có màu ANSI + căn lề:

```text
┌─ session c9e83f17 · disease_x · deepseek/deepseek-chat
│  ① AGENT  Chào bạn, mình cần thu thập một vài thông tin...
│  ② USER   Tôi tên Trần Minh Khoa
│     ↳ extracted  name="Trần Minh Khoa"          [33% · 1/3]
│  ③ AGENT  Dạ thưa anh Khoa, anh có thể mô tả...
...
└─ ✓ confirmed · 3/3 trường · 4 lượt
```

- Bật/tắt qua env (vd `CONSOLE_TRACE=1`), mặc định bật ở `APP_ENV=development`.
- Dùng `logging` chuẩn, không `print()` rải rác.
- **Windows:** terminal cp1252 không in được tiếng Việt/box-drawing → cần
  `sys.stdout.reconfigure(encoding="utf-8")` như đã làm trong `scripts/run_disease_qa.py`,
  và có nhánh không-màu khi không phải TTY.
- **Không in API key, không in nguyên văn PHI ở mức INFO** (chỉ ở DEBUG).

### Bước 5 — Trang hub tại `/`

Hiện `src/ui/static_files.py` mount `StaticFiles(html=True)` tại `/` → `/` đang trả thẳng
`index.html` (chính là demo triage).

- Đổi tên `static/index.html` → `static/triage.html` (nhớ sửa link tới `app.js`, `styles.css`).
- Tạo `static/index.html` mới = trang hub, dạng danh sách card:

| Demo | Link | Ghi chú |
|---|---|---|
| Triage pipeline | `/triage.html` | Rule-based, không dùng LLM |
| Hỏi-đáp intake | `/intake.html` | Dùng LLM, có BYO key |
| Disease X QA | *(CLI)* | `python -m scripts.run_disease_qa --demo` — chưa có REST endpoint |
| API docs | `/docs` | Swagger |
| Health | `/health` | |

- Trang hub cần ghi rõ demo nào dùng LLM, demo nào rule-based — tránh hiểu nhầm như lần trước.

### Bước 6 — Panel nhập API key trên UI

- Thêm khối cấu hình ở đầu `intake.html` (và `triage.html` nếu sau này dùng LLM):
  - Dropdown **Provider** → filter dropdown **Model** theo `SUGGESTED_MODELS`, cho phép gõ tay model khác.
  - Input **API key** dạng `type="password"`, kèm nút hiện/ẩn.
  - Nút **Kiểm tra kết nối** → gọi thử 1 request ngắn, báo OK/lỗi.
  - Badge trạng thái: `đang dùng key của bạn` / `đang dùng key server` / `fallback deterministic`.
- Lưu key ở `sessionStorage` (mất khi đóng tab), **không dùng `localStorage`**.
- Ghi rõ trên UI: key gửi lên server chỉ để gọi LLM, không lưu xuống đĩa.

### Bước 7 — Test + verify

- Test mới: credential override không rò vào log; `api_key=None` giữ nguyên hành vi cũ.
- `pytest tests/ -q` (baseline hiện tại: **73 pass**).
- `ruff check` trên file mới.
  - Lưu ý: `src/services/triage_pipeline.py` **đã có sẵn 1 lỗi import-sort từ trước**, không phải do
    thay đổi này gây ra.
- Verify thật: mở `/`, bấm sang `/intake.html`, nhập key thật, chạy trọn 1 phiên, xem console trace.

### Bước 8 — Cập nhật tài liệu

- `_guidance/Run.md`: mục mới cho trang hub + BYO key + cách bật console trace.
- `_guidance/vmedtriage_solution_design_review.md`: ghi nhận việc providers nhận key tường minh.

---

## 4. Việc còn tồn từ đợt trước (chưa làm, đừng quên)

### 4.1. 🐛 Bug ghi đè trường — ✅ ĐÃ SỬA (xem mục 5)

Phát hiện khi test thật với DeepSeek:

```text
[USER] Tôi bị sốt cao 39 độ, đau họng và ho khan nhiều
   → condition vẫn là 'thấy trong người không ổn'   ← thông tin lâm sàng bị vứt
```

Nguyên nhân: `DiseaseQAAgent._collect(skip_existing=...)` bê nguyên policy "không ghi đè trường đã
có" từ `intake_agent`. Đúng với trường hành chính (tên, tuổi), **sai với trường mô tả triệu chứng** —
loại trường này người bệnh bồi đắp dần qua nhiều lượt.

Cách sửa đã định (chưa làm): thêm cờ `"accumulate": true` vào field spec trong JSON checklist; trong
`_collect`, field `accumulate` thì **cộng dồn** thay vì bỏ qua. Riêng luồng `extract_correction`
(người dùng chủ động sửa) vẫn phải **ghi đè**, không cộng dồn.

Đã ghi vào `_guidance/Run.md` mục "Giới hạn đã biết".

### 4.2. Các giới hạn khác của luồng disease QA

- Chỉ có CLI, **chưa có REST endpoint**, chưa nối `TriagePipeline`/nurse queue.
- **Chưa có red-flag scan** (khác luồng intake đã có) → không dùng để đánh giá mức khẩn cấp.
- Session in-memory, mất khi restart process.

### 4.3. Nợ kỹ thuật nền

- `src/services/llm.py` (LangChain) **không được gọi ở đâu cả** — trùng vai trò với
  `provider_router.py`. Nên xoá hoặc gộp, tránh người sau sửa nhầm file chết.
- `logs/` chứa nguyên văn hội thoại (PHI). Đã trong `.gitignore`, nhưng trước production cần mã hoá
  at-rest, phân quyền đọc, chính sách xoá theo hạn.
- Kế hoạch lớn hơn (SLM checklist theo bệnh → graph → GNN advisory → nurse feedback scoring) nằm ở
  **mục 10** của `_guidance/vmedtriage_solution_design_review.md`.

---

## 5. Kết quả thực tế (2026-08-08)

### 5.1. File đã thêm/sửa

| File | Thay đổi |
|---|---|
| `src/providers/*.py` | Nhận `api_key` tường minh; `api_key=None` giữ nguyên hành vi cũ |
| `src/providers/__init__.py` | `make_provider(name, *, api_key=None)` |
| `src/services/provider_router.py` | **Mới**: `LLMCredential` (có `masked()` + `__repr__` che key), `SUGGESTED_MODELS`, `complete(..., credential=)`, `_complete_with_credential` |
| `src/services/console_log.py` | **Mới** — trace terminal, ASCII fallback, tự bỏ màu, `set_enabled()` |
| `src/services/disease_checklist.py` | `ChecklistField.accumulate` |
| `src/services/disease_agent.py` | Nhận credential; `_merge_description()`; `_collect()` xử lý accumulate |
| `src/services/disease_session.py` | Credential theo phiên; agent **không cache** khi có credential; nối console trace |
| `src/services/intake_agent.py` / `intake_session.py` | Tương tự cho luồng intake |
| `src/api/routers/intake.py` | `GET /providers`, `POST /providers/test`, `POST /sessions` nhận credential |
| `src/models/intake_api.py` | `IntakeCredentialRequest`; response thêm `llm_source`/`llm_provider`/`llm_model`/`llm_key_masked` |
| `src/config.py` | `console_trace: auto\|on\|off` |
| `src/ui/static/index.html` | **Mới** — trang hub (demo triage cũ chuyển sang `triage.html`) |
| `src/ui/static/intake.html` / `intake.js` | Panel cấu hình LLM + nút kiểm tra kết nối |
| `src/domain/_disease_x.json` | `condition` có `"accumulate": true` |
| `scripts/run_disease_qa.py` | Cờ `--trace` (mặc định tắt để không in trùng) |
| `tests/.../test_disease_session.py` | +9 test: accumulate, credential không rò log, agent isolation |

### 5.2. Khác biệt so với kế hoạch

- **Endpoint không phải `/api/v1/llm/providers`** như kế hoạch, mà là
  `/api/v1/intake/providers` — gom vào router intake sẵn có thay vì tạo router mới cho 1 endpoint.
- **`SUGGESTED_MODELS` không chép tên model từ `.env`**: `.env` có
  `GEMINI_MODEL_NAME="gemini-3.5-flash-lite"` là tên **không tồn tại**. Đã dùng tên có thật
  (`gemini-2.0-flash`, …). `.env` vẫn nên sửa lại.
- **Phát sinh thêm `console_log.set_enabled()`** ngoài kế hoạch: chạy CLI mà bật trace thì in trùng
  hai bản cùng nội dung, nên cần công tắc theo tiến trình.
- **Trace vẫn in nguyên văn hội thoại ở mức mặc định** (kế hoạch ghi "chỉ ở DEBUG"). Lý do: mục đích
  của tính năng là quan sát hội thoại; giấu đi thì trace vô dụng. Bù lại: mặc định **tắt ở
  production** và có cảnh báo PHI rõ ràng trong docstring + `Run.md`.

### 5.3. Việc phát sinh đã xử lý trong đợt này (không có trong kế hoạch)

- **Không đăng nhập/đăng ký được** — hai lỗi chồng nhau:
  1. `data/app.db` giữ schema cũ (7 cột) trong khi model cần 18 cột; `create_all` dùng
     `CREATE TABLE IF NOT EXISTS` nên **không migrate** → `no such column: users.username` → HTTP 500.
     Đã sao lưu `data/app.db.bak-*`, drop bảng cũ, tạo lại. Thêm `_check_schema_drift()` trong
     `src/database.py` để lần sau báo lỗi rõ ngay lúc khởi động.
  2. `app.js` đọc body `Response` hai lần (`.json()` rồi `.text()`) → ném
     `body stream already read`, **che mất lỗi thật**. Đã sửa: đọc text một lần rồi `JSON.parse`.

### 5.4. Còn tồn sau đợt này

- Luồng disease QA vẫn **chỉ có CLI**, chưa có REST endpoint, chưa nối `TriagePipeline`/nurse queue,
  **chưa có red-flag scan**.
- `src/services/llm.py` vẫn là code chết (mục 4.3) — chưa xoá.
- `src/services/triage_pipeline.py` vẫn còn 1 lỗi ruff import-sort có sẵn từ trước.
- `.env`: `GEMINI_MODEL_NAME` sai tên; chứa Gmail app password dạng plaintext (đã gitignore).
- Bước xác thực email khi đăng ký cần SMTP thật; bỏ `SMTP_HOST` thì mã in ra console (chế độ dev).

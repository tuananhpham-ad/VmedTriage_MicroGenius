# F03 — Database: ba lỗ hổng thật

> **Ưu tiên `**`**. Chủ trì: Fullstack AI Engineer.

---

## 1. Trạng thái: DB **đã có và đang chạy thật**

Yêu cầu ghi "database cơ bản", nhưng cần nói rõ để không ai viết lại từ đầu: hệ thống **đã** có
SQLAlchemy + SQLite với dữ liệu thật.

```python
# src/database.py
class Base(DeclarativeBase): ...                       # :12-13
def configure_database(): create_engine(..., pool_pre_ping=True)   # :32-52
def create_tables(): Base.metadata.create_all(...)     # :113-119
def session_scope(): ...                               # :137-160  commit/rollback, mọi store dùng
```

`src/config.py:135` — `database_url: str = "sqlite:///./data/app.db"`.

**Bảy bảng, có dữ liệu thật:**

| Bảng | Model | Số dòng |
| --- | --- | --- |
| `users` | `models/user.py:23-55` | 8 |
| `password_reset_tokens` | `models/password_reset.py:9-18` | 0 |
| `email_verification_codes` | `models/password_reset.py:22-30` | 8 |
| `triage_cases` | `models/case_record.py:35-49` | **252** |
| `approval_records` | `case_record.py:52-63` | 4 |
| `audit_log` | `case_record.py:66-81` | 6 |
| `conversations` | `case_record.py:84-120` — PK `(conversation_id, user_id)` | **194** |

Ba store: `services/stores/case_store.py`, `approval_store.py`, `conversation_store.py`.

> ⚠️ Docstring của `src/services/stores/__init__.py` vẫn ghi "in-memory" — **đã lỗi thời**, sửa luôn.

---

## 2. Ba lỗ hổng

### 2.1. Không có migration tool — đổi schema là mất dữ liệu

```python
# src/database.py:93-110
def _apply_additive_sqlite_migrations():   # hardcode 4 cột nullable của `users`
    ...  raw ALTER TABLE users ADD COLUMN

# src/database.py:59-90
def _check_schema_drift():
    raise SchemaDriftError(...)   # :85-89 nói thẳng: "Dự án chưa dùng migration tool"
                                  # hướng dẫn xử lý là XOÁ data/app.db
```

Không có Alembic, không có thư mục `migrations/`. Cách này chạy được khi DB là đồ bỏ đi; nó **không**
chạy được khi có 252 ca thật, và càng không chạy được sau khi `F01`/`F02` đổi schema phiếu.

**Việc phải làm:** đưa Alembic vào, baseline từ schema hiện tại, bỏ `_apply_additive_sqlite_migrations`.
`_check_schema_drift` giữ lại nhưng đổi thông điệp thành "chạy `alembic upgrade head`".

### 2.2. `HandoffSummary` chôn trong blob JSON — không query được

```python
# src/services/stores/case_store.py:58
row.payload = triage_case.model_dump(mode="json")
```

Toàn bộ phiếu bàn giao — gồm `narrative` (`summary_text`), `red_flags`, `missing_information`,
`proposed_priority` — nằm trong **một cột JSON** của `triage_cases`. Các cột phẳng (`status`,
`priority`, `has_red_flag`) chỉ để lọc hàng đợi, và bị **ghi đè mỗi lượt** vì `symptom_case_bridge`
dựng lại case từ đầu sau mỗi tin nhắn.

Hệ quả cụ thể: mọi chỉ số ở `F01` §6 và `F06` §2 hiện **không truy vấn được bằng SQL** — phải đọc file
log. Đó là lý do §9.1 của tài liệu cũ phải chạy script trên thư mục `logs/` với 227 phiên trộn nhiều
phiên bản code.

**Việc phải làm:** rút các trường cần thống kê ra cột thật (`narrative_source`, `stop_reason`,
`is_complete`, `turn_count`, `protocol_name`). Giữ `payload` làm nguồn đầy đủ — đây là bổ sung cột,
không phải bỏ blob.

> **Ràng buộc:** ISBAR và `field_summary` là dữ liệu **dẫn xuất**, tính lại mỗi request
> (`routes.py:471-484`). **Không persist chúng** — persist một bản dẫn xuất là tạo ra một nguồn sự thật
> thứ hai có thể lệch với snapshot, đúng thứ mà `summary_render.py:4-6` tồn tại để tránh.

### 2.3. Deploy Render mất sạch dữ liệu mỗi lần deploy

`render.yaml` **không set `DATABASE_URL`**, nên production chạy SQLite mặc định `./data/app.db` trên
đĩa ephemeral của gói free. Mỗi lần deploy: mất toàn bộ user, ca, hội thoại.

**Việc phải làm:** hoặc gắn Render Persistent Disk, hoặc chuyển sang Postgres (`.env.example:18` đã có
sẵn dòng mẫu). Quyết định này chặn `F04` M3 — ký ức xuyên phiên vô nghĩa nếu DB mất mỗi lần deploy.

---

## 3. Thứ tự làm

Có phụ thuộc, không làm song song được:

```text
2.3 (đĩa bền)  ->  2.1 (Alembic)  ->  2.2 (rút cột)
```

2.3 trước vì hai cái sau vô nghĩa trên một DB bị xoá mỗi lần deploy. 2.1 trước 2.2 vì 2.2 **là** một
lần đổi schema, và đó đúng là thứ cần Alembic.

---

## 4. Test bắt buộc

1. `alembic upgrade head` trên một bản copy của `data/app.db` hiện có **giữ nguyên 252 ca + 194 hội thoại**.
2. `alembic downgrade` rồi `upgrade` lại cho ra schema y hệt.
3. Cột rút ra ở 2.2 khớp với giá trị trong `payload` cho mọi hàng — test property trên dữ liệu thật.
4. Restart process giữa phiên: phiên đang dở khôi phục được (đã có, không được làm hỏng —
   `conversation_store.py:151-207`).
5. Không có đường nào đọc được hồ sơ của `user_id` khác.

---

## 5. Tiêu chí chấp nhận

- Đổi một cột của `HandoffSummary` mà **không phải xoá `data/app.db`**.
- Trả lời được bằng **một câu SQL**: "tỉ lệ phiên rơi về narrative fallback tháng này là bao nhiêu"
  (chỉ số `F06` cần).
- Deploy lại Render mà user vẫn đăng nhập được bằng tài khoản cũ.

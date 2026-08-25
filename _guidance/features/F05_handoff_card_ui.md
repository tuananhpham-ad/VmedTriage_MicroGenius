# F05 — Phiếu thông tin: trường có thông tin lên đầu, trường thiếu gập lại

> Chủ trì: Fullstack AI Engineer. **Thuần frontend** — backend đã đúng.
> Tiêu thụ hợp đồng của `F02`.

---

## 1. Yêu cầu

> "Phiếu thông tin: thiếu cho vào 1 chỗ up-down, những trường có thông tin thì hiện lên đầu."

---

## 2. Vấn đề — và vì sao nó KHÔNG nằm ở backend

**Backend đã lọc trường rỗng đúng.** Kiểm chứng:

```python
# src/services/sessions/summary_render.py:202-209
def _present(rows):
    return {label: value for label, value in rows.items()
            if value is not None and value != "" and value != []}
```

Cố ý **không** dùng `if not value` — để `False` và `0` sống sót, vì `is_complete=False` là đúng thứ
điều dưỡng cần thấy. `to_isbar()` (`:199`) còn bỏ luôn cả khối nếu khối rỗng, và `as_text()` (`:59-60`)
bỏ khối rỗng tương tự.

**Vấn đề nằm hết ở `src/ui/new/`:**

| Vấn đề | Bằng chứng |
| --- | --- |
| Không có khối gập nào cho phiếu | **Không có `<details>` nào trong toàn bộ `src/ui/new/`.** `aria-expanded` chỉ dùng cho dropdown tài khoản, panel hướng dẫn đăng nhập, và các panel **hành động** của điều dưỡng (`nurse.js:276-310`, toggle ở `:334-344`) |
| Trường có và trường thiếu **xen kẽ** | `collectedFields()` (`nurse.js:431-449`) duyệt `summary_fields` theo thứ tự protocol, gắn tag `<span class="missing-tag">Thiếu thông tin</span>` **tại chỗ** (`:439`) |
| ISBAR không dồn trường rỗng xuống | `to_isbar()` bỏ trường rỗng **tại chỗ**, giữ nguyên thứ tự khai báo (`summary_render.py:163-198`) |
| Chỉ có scroll, không có gập | `styles.css:544-545` — `#intake-summary .record-body { max-height:58vh; overflow-y:auto }` |

Hai card trong màn hình ca: `#intake-summary` ("Phiếu tóm tắt", `nurse.js:229-240`) và
`#handoff-summary` ("Phiếu bàn giao (ISBAR)", `:242-245`, nạp sau bằng
`GET /api/v1/cases/{id}/summary` ở `:654-663`).

---

## 3. Thiết kế

### 3.1. Hai khối, không phải một danh sách

```text
┌─ Đã ghi nhận ────────────────────  (mở sẵn, lên đầu)
│  Triệu chứng chính   Đau bụng bên phải
│  Khởi phát           Sáng nay
│  ...
├─ Người bệnh phủ nhận ────────────  (mở sẵn — dữ kiện lâm sàng, KHÔNG gập)
│  Nôn, tiêu chảy
├─ Dấu hiệu an toàn chưa xác định ─  (mở sẵn — LUÔN hiện, xem §3.2)
│  Đau lan xuống tay, ngất
└─ ▸ Còn thiếu (12) ───────────────  (<details>, GẬP SẴN)
```

Trường thiếu **không phải xoá** — gom vào một `<details>` gập sẵn, kèm số đếm ở nhãn để điều dưỡng biết
còn bao nhiêu mà không phải mở ra.

### 3.2. Ranh giới không nới

> **Field an toàn `false` và `unknown` LUÔN được render, không bao giờ gập vào khối "còn thiếu".**

Lý do đã ghi ở `summary_render.py:18-21`: *"người bệnh phủ nhận đau lan xuống tay"* và *"chưa ai hỏi về
đau lan xuống tay"* là hai thứ điều dưỡng **bắt buộc** phải phân biệt được — và đó chính là chỗ họ nhìn
đầu tiên. Gập chúng lại là làm hỏng đúng mục đích của phiếu.

Vì thế khối thứ ba ở §3.1 là một khối **riêng, mở sẵn**, không phải một phần của `<details>`.

### 3.3. Bốn trạng thái, bốn nhãn (từ `F02`)

| Trạng thái | Nhãn UI | Khối |
| --- | --- | --- |
| `"true"` | giá trị thật | Đã ghi nhận (mở) |
| `"false"` | "Người bệnh phủ nhận" | Phủ nhận (mở) |
| `"unknown"` + field an toàn | "Đã hỏi, chưa xác định" | Dấu hiệu an toàn (mở) |
| `"unknown"` / `None` + field thường | "Chưa hỏi tới" | Còn thiếu (gập) |

---

## 4. Thay đổi cụ thể

| File | Sửa gì |
| --- | --- |
| `src/ui/new/features/nurse.js:431-449` | `collectedFields()` — chia nhóm trước khi render, thay vì duyệt tuyến tính |
| `src/ui/new/features/nurse.js:665-675` | `isbarMarkup()` — dồn trường rỗng của mỗi khối xuống cuối khối |
| `src/ui/new/features/nurse.js:689-701` | `narrativeMarkup()` — thêm khối `reported` (xem `F06` §2, cùng bug) |
| `src/ui/new/styles.css:544-548`, `:903-916` | Style cho `<details>`; bỏ `max-height` scroll nếu đã gập |

Backend: **không sửa gì cho F05**, trừ phần `never_asked` mà `F02` §4 đã yêu cầu.

---

## 5. Test bắt buộc

1. Field an toàn `false` **hiển thị**, không nằm trong `<details>` gập.
2. Field an toàn `unknown` **hiển thị**, không nằm trong `<details>` gập.
3. Số đếm trên nhãn "Còn thiếu (N)" khớp với `missing_information` của phiếu.
4. Phiếu không có trường thiếu nào thì **không render `<details>` rỗng**.
5. `is_complete = false` vẫn hiển thị (không bị `if not value` nuốt).
6. Responsive: ở mobile (`styles.css:888-890` đang flip `.value` sang `text-align:left`) khối gập vẫn
   bấm được và không tràn ngang.

---

## 6. Tiêu chí chấp nhận

- Mở một ca thật: **không phải cuộn** để thấy hết trường đã có thông tin.
- Trường thiếu vẫn đếm được và mở ra xem được, không bị xoá khỏi phiếu.
- Không dấu hiệu an toàn nào bị gập.

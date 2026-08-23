# F06 — Tóm tắt văn xuôi: giảm fallback, sửa bug thiếu khối, căn lề hai đầu

> Chủ trì: Agent Lead (mục 2.1) + Fullstack (mục 2.2, 2.3).

---

## 1. Yêu cầu, và một đính chính về chẩn đoán

> "Tóm tắt văn xuôi: đang hardcode, ngu quá, chỉ tóm tắt những trường có thông tin, hiển thị căn lề
> hai đầu."

**Đính chính: phần văn xuôi KHÔNG hardcode.** `src/services/sessions/narrative.py:54-119` gọi LLM thật:

```python
result = provider_router.complete(
    [{"role": "system", "content": _SYSTEM_PROMPT},
     {"role": "user",   "content": deterministic}],
    temperature=0.2, credential=credential, role=provider_router.ROLE_SYNTHESIS)
```

Thứ trông giống "hardcode ngu" là **bản fallback tất định** `FieldSummary.as_text()`
(`summary_render.py:50-61`) — một danh sách gạch đầu dòng, không phải văn xuôi:

```python
blocks = [("Triệu chứng ghi nhận:", self.reported),
          ("Người bệnh phủ nhận:",  self.denied),
          ("Chưa xác định được:",   self.unknown_safety)]
```

Nó bắn ra ở **ba** đường:

| Đường | Nơi | `source` trả về |
| --- | --- | --- |
| Provider lỗi/timeout | `narrative.py:98-101` | `"provider_unavailable"` |
| **Guard chặn** | `narrative.py:113-117` | mã vi phạm, ví dụ `VIOLATION_INVENTED_DENIAL` |
| Hồ sơ rỗng | `narrative.py:82-86` | `"empty_record"` (trả chuỗi rỗng) |

Nên việc phải làm là **đo rồi giảm tỉ lệ fallback**, không phải "viết lại phần hardcode".

**Còn "chỉ tóm tắt trường có thông tin" thì đã đạt** — cả ba tầng đều lọc: `_present()`
(`summary_render.py:202-209`), `as_text()` (`:59-60`), và `narrativeMarkup()` (`nurse.js:689-701`).

---

## 2. Ba việc

### 2.1. Đo `narrative_fallback_rate` — làm trước, vì không có số thì không biết đang sửa gì

Đường log **đã có sẵn**: `narrative.py:67-80` ghi một dòng `stage_log` với `narrative_source` mỗi lần
sinh văn xuôi. Chưa ai đọc ra số.

Cần biết tỉ lệ theo **từng** `source`, vì ba nguyên nhân cần ba cách sửa khác hẳn nhau:

- `provider_unavailable` cao thì là vấn đề hạ tầng/quota, không phải prompt.
- `VIOLATION_INVENTED_DENIAL` cao thì model đang biến `unknown` thành lời phủ nhận — sửa **prompt**,
  không sửa guard (§3).
- `VIOLATION_UNGROUNDED` cao thì model trả đoạn văn tổng quát không dính gì tới ca này.

Chỗ đọc: `eval/scripts/experience_report.py`. Cần `F03` §2.2 để truy vấn được bằng SQL thay vì quét
thư mục `logs/`.

### 2.2. Bug thật: phiếu không hiển thị "Triệu chứng ghi nhận"

```javascript
// src/ui/new/features/nurse.js:689-701
function narrativeMarkup(data) {
  const fields = data.field_summary || {};
  const narrative = data.narrative ? ... : "";
  // render `denied`, render `unknown_safety`
  return `${narrative}${denied}${unknown}`;   // <- KHÔNG BAO GIỜ render fields.reported
}
```

API **có** trả `field_summary.reported` (`routes.py:471-484`), backend **có** tính đúng
(`field_summary()`, `summary_render.py:64-76`). UI bỏ hẳn nhóm quan trọng nhất — đúng các triệu chứng
người bệnh **có**.

Cùng một hàm với `F05` §4 — sửa một lần.

### 2.3. Căn lề hai đầu

```css
/* src/ui/new/styles.css:548 */
.field-row > dd, .field-row > .value { ...; text-align:right; text-wrap:pretty; }
```

`.value` đang **căn phải** — hợp lý cho giá trị một dòng, sai cho một đoạn văn 3–5 câu.

Khối văn xuôi dùng `.field-row.is-block` (`styles.css:903-916`, `display:block`). Thêm
`text-align: justify` **cho riêng selector đó**, không đụng các `.value` một dòng. Nhớ giữ override
mobile (`:888-890`).

---

## 3. Ràng buộc không nới

> **`narrative_invents_denials` (`summary_render.py:98-131`) không được nới.**

Nó bắt lỗi im lặng nguy hiểm nhất, và **ca thật đã xảy ra 2026-08-19**: với ca "bé 2 tháng sốt 38",
model viết *"Người bệnh không ghi nhận các triệu chứng như mệt mỏi, khó chịu, co giật, cứng gáy, yếu
liệt..."* trong khi **toàn bộ** những field đó đang `unknown` — chưa ai hỏi tới. Phiếu đọc ra như thể
đã hỏi và người nhà nói không có.

`narrative_is_grounded` **không** bắt được ca này (model nhắc đúng field, chỉ sai **cực**) — đó là lý do
phải có kiểm tra thứ hai.

Guard chặt chính là **nguyên nhân** fallback cao. Nới nó để "đỡ fallback" là đổi một phiếu đọc-xấu lấy
một phiếu đọc-đẹp-và-sai. Hướng đúng là sửa `_SYSTEM_PROMPT` (`narrative.py:34-46` đã có 4 dòng nói về
nhóm "Chưa xác định được" — nếu vẫn vi phạm thì tăng ràng buộc ở đó, hoặc bỏ nhóm `unknown` khỏi input
của model và render nó tất định).

---

## 4. Thay đổi cụ thể

| File | Sửa gì |
| --- | --- |
| `eval/scripts/experience_report.py` | Thêm `narrative_fallback_rate`, tách theo `source` |
| `src/ui/new/features/nurse.js:689-701` | Render `fields.reported` |
| `src/ui/new/styles.css:903-916` | `text-align: justify` cho `.field-row.is-block .value` |
| `src/services/sessions/narrative.py:34-46` | Chỉ khi §2.1 cho thấy `INVENTED_DENIAL` là nguyên nhân chính |

---

## 5. Test bắt buộc

1. `field_summary.reported` không rỗng thì UI **phải** render khối "Triệu chứng ghi nhận".
2. Provider hỏng thì phiếu vẫn bàn giao được, `source = "provider_unavailable"`, không ném lỗi ra ngoài.
3. Văn xuôi nói người bệnh phủ nhận một field đang `unknown` thì **bị guard chặn** — ca test giữ
   nguyên, không được nới.
4. Hồ sơ rỗng thì trả chuỗi rỗng, **không** bịa ra một đoạn văn.
5. Văn xuôi và `summary_json` đọc **cùng một** snapshot — đổi snapshot thì cả hai đổi theo.

---

## 6. Tiêu chí chấp nhận

- Có **con số** `narrative_fallback_rate` tách theo `source`, kèm mẫu số.
- Phiếu hiển thị đủ ba nhóm: ghi nhận / phủ nhận / chưa xác định.
- Đoạn văn xuôi căn lề hai đầu; giá trị một dòng vẫn căn phải như cũ.
- `hallucinated negative rate` vẫn **0%** trên tập safety.

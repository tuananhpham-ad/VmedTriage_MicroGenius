# F02 — Hợp đồng trạng thái trường: Null / true / false / unknown

> **Ưu tiên `***`** (phần đỡ của F01). Chủ trì: Agent Lead.
> `F01` sinh dữ liệu theo hợp đồng này; `F05` và `F06` hiển thị nó.

---

## 1. Yêu cầu

> "Các trường thì bây giờ sẽ là Null, khi hỏi người dùng thì agent sẽ tự động fill vào các trường đấy
> (true, false, unknown)."

## 2. Trạng thái: **phần lớn đã chạy** — đây là tài liệu hoá, không phải xây mới

Kiểm chứng bằng code, không phải bằng tài liệu cũ:

| Trạng thái | Trong snapshot | Nghĩa lâm sàng |
| --- | --- | --- |
| **chưa hỏi** | field vắng mặt / `None` | Chưa ai hỏi tới. Đây chính là "Null" của yêu cầu |
| **có** | `"true"` | Người bệnh xác nhận |
| **không** | `"false"` | Người bệnh **phủ nhận** — dữ kiện lâm sàng có giá trị, không phải chỗ trống |
| **không rõ** | `"unknown"` | Đã hỏi, người bệnh không trả lời được |

Nguồn:

```python
# src/services/symptom_protocol/models.py:18,24   FieldSpec.tri_state + allowed_values
# src/services/symptom_protocol/stage_machine.py:36-39
def is_filled(value): return value is not None and value != "unknown" and value != ""
# stage_machine.py:45
NEGATED_PARENT_VALUES = frozenset({"false", "none"})   # "unknown KHÔNG phải phủ định"
```

### 2.1. Vì sao KHÔNG có giá trị thứ tư trong snapshot

```text
# src/services/symptom_protocol/reducer.py:25-28
SNAPSHOT VẪN ĐÚNG 3 GIÁ TRỊ. `unset` là OPERATION, không phải giá trị thứ tư: reducer quy nó về
"unknown" trong snapshot và ghi một AuditEvent để phân biệt "chưa bao giờ hỏi" với "đã khai rồi rút lại".
`rule_engine.evaluate` và `common_safety/predicates.py` đang giả định đúng ba giá trị - thêm giá trị
thứ tư là thay đổi lan ra toàn bộ tầng luật an toàn.
```

Ba operation (`reducer.py:44`): `set` / `unset` / `no_change`.
Bốn loại `AuditEvent` (`:113-116`): `set` / `unset` / `retract_dependent` / `retract_held`.

Nói cách khác: **"Null" và "unknown" phân biệt được, nhưng phân biệt bằng lịch sử audit chứ không bằng
giá trị.** Đây là quyết định đúng và không nên đảo — thêm giá trị thứ tư thì mọi luật an toàn đang so
sánh 3 giá trị đều phải viết lại, và mỗi chỗ quên là một lỗ.

### 2.2. Trạng thái thứ năm, ở tầng khác: "moot"

`field_is_settled` (`stage_machine.py:66-68`) = đã điền **hoặc** `field_not_applicable` (field cha đã
bị phủ định). Dùng để không hỏi lại con của một field cha đã "không". Đây là trạng thái **dẫn xuất**,
không lưu trong snapshot.

### 2.3. Ai được suy `false` khi người bệnh im lặng

Chỉ tier **O/H** (`batching.py:240-265`). M0/M1 im lặng thành `unknown` và được **hỏi lại đúng một lần**.

| Tier | Bỏ qua trong batch thì | Lý do |
| --- | --- | --- |
| M0/M1, field an toàn | `unknown` + hỏi lại một lần, ngắn gọn | Không được suy diễn ở chỗ đắt nhất |
| C (protocol-specific) | `unknown`, không hỏi lại | Ghi vào `missing_information` là đủ |
| O/H (tuỳ chọn) | `false` | Chi phí sai thấp, lợi ích tốc độ thật |

> **Đây là chỗ tài liệu cố ý làm khác yêu cầu, và lý do.** Yêu cầu ban đầu là "bỏ qua cái nào thì cho
> cái đấy là False luôn". Im lặng không phải phủ định: khi field là `loss_of_consciousness` thì suy
> `False` tạo ra một phiếu ghi *"người bệnh phủ nhận ngất"* trong khi **chưa ai hỏi họ về ngất**. Điều
> dưỡng đọc phiếu đó không có cách nào biết sự khác nhau.
>
> Cách rẻ hơn mọi suy diễn: **cho người bệnh phủ định gộp một câu**. `ScreeningGroup` đã làm sẵn — hỏi
> "còn 4 dấu hiệu sau, bạn có cái nào không?" và một chữ "không" đóng cả bốn field một cách **tường
> minh**, vì người bệnh đã nghe đọc đủ danh sách. Đó là cách hợp lệ để một lượt lấp nhiều field:
> *người bệnh phủ định, chứ không phải hệ thống suy ra.*

---

## 3. Lỗ hổng thật: bốn trạng thái chưa bao giờ hiện đủ ra UI

Backend giữ đủ; renderer mới là chỗ lọc (`summary_render.py:18-21`). Nhưng UI hiện chỉ phân biệt được
"có giá trị" và "thiếu":

- `nurse.js:431-449` `collectedFields()` — render trường có giá trị, hoặc tag `Thiếu thông tin`. Hai
  trạng thái, không phải bốn.
- `nurse.js:689-701` `narrativeMarkup()` — render `denied` và `unknown_safety`, nhưng **bỏ hẳn
  `reported`** (xem `F06` §2).

Hệ quả: điều dưỡng không phân biệt được **"người bệnh nói không"** với **"chưa ai hỏi"** ở phần lớn
trường — đúng thứ mà toàn bộ thiết kế 3 giá trị tồn tại để tránh.

---

## 4. Thay đổi cụ thể

| File | Sửa gì |
| --- | --- |
| `src/services/sessions/summary_render.py` | Bổ sung `never_asked` vào `FieldSummary` (field `None`, tách khỏi `unknown`) — dùng `AuditEvent` để phân biệt |
| `src/api/routes.py:452-486` | `GET /cases/{id}/summary` trả đủ 4 nhóm trong `field_summary` |
| `src/ui/new/features/nurse.js` | Hiển thị 4 nhãn phân biệt — xem `F05` |

**Ràng buộc:** thêm nhóm ở tầng **render**, không thêm giá trị thứ tư vào snapshot (§2.1).
Field an toàn `false` và `unknown` **luôn** được render, kể cả khi khối khác bị gập.

---

## 5. Test bắt buộc

1. Field chưa bao giờ hỏi và field đã hỏi-không-trả-lời-được cho ra **hai nhóm khác nhau** trong
   `field_summary`.
2. Snapshot vẫn đúng **3 giá trị** sau thay đổi — không có giá trị thứ tư nào lọt vào `answers`.
3. Người bệnh trả lời 3/6 ý trong một batch: field M0/M1 bị bỏ qua thành `unknown`, **không** `false`;
   chỉ tier O/H mới được suy `false`.
4. Field M0/M1 bị bỏ qua được hỏi lại **đúng một lần**, không lặp vòng.
5. Phủ định gộp: một chữ "không" chỉ đóng đúng các field trong danh sách vừa đọc lên.
6. `unset` (rút lời) cho ra `unknown` trong snapshot **và** một `AuditEvent` phân biệt được với
   "chưa hỏi".

---

## 6. Tiêu chí chấp nhận

- Điều dưỡng mở phiếu và phân biệt được **cả bốn** trạng thái mà không phải hỏi ai.
- `hallucinated negative rate` = **0%** trên tập safety — không có field `unknown` nào bị trình bày
  như lời phủ nhận của người bệnh, ở bất kỳ đâu (phiếu, văn xuôi, UI).
- Không test hiện có nào đỏ.

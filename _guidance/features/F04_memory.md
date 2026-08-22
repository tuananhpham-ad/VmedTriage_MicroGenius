# F04 — Memory: M2 nén context, M3 ký ức xuyên phiên

> **Ưu tiên `*`**. Chủ trì: Agent Lead. **Chặn bởi `F03` §2.3** (đĩa bền).

---

## 1. M1 — **đã xong**, đừng làm lại

| Yêu cầu | Trạng thái |
| --- | --- |
| Khoá composite `user_id + conversation_id` | ✅ PK `(conversation_id, user_id)` — `models/case_record.py:84-120` |
| Phiên sống qua restart | ✅ `SqliteConversationStore` — `services/stores/conversation_store.py:151-207` |
| Không dùng timestamp làm khoá | ✅ `created_at` là cột riêng |

Cách nối: `ProtocolSessionStore._sessions` vẫn là dict in-memory (`session.py:294`), nhưng `get()`
tra memory rồi tra `self._persist` (`session.py:312-331`) và `_remember()` ghi sau **mỗi lượt được
nhận** (`:333-337`). Wire ở `services/sessions/symptom_session.py:22`.

Hai thứ **cố ý không** persist, giữ nguyên:

- **Credential không bao giờ được lưu** — `dump_session()` bỏ qua (`conversation_store.py:51-95`),
  `case_record.py:100-102`, `provider_router.py:143`.
- **Object protocol không lưu** (là code, không phải state) — chỉ lưu tên, resolve lại qua `registry`
  (`conversation_store.py:243-250`). Riêng `current_cluster` **có** dump đầy đủ (`:216-228`) vì cụm
  tổng hợp `BATCH-`/`SCREEN-`/`CATCH-ALL` không nằm trong registry.

---

## 2. M2 — Short memory hybrid: chỉ thiếu bước nén

```text
Structured snapshot   [ĐÃ CÓ - reducer, là nguồn sự thật]
+ Tóm tắt lượt cũ      [CHƯA CÓ - cần khi context dài]
+ N lượt raw gần nhất  [ĐÃ CÓ - session.conversation]
```

**Bất biến:** summarizer nén **phần hội thoại**, không bao giờ ghi đè snapshot. Nếu tóm tắt và snapshot
bất đồng thì **snapshot thắng** — nó là thứ có bằng chứng `evidence_span`, bản tóm tắt thì không.

Việc: thêm bước nén khi context vượt ngưỡng. Ngưỡng đặt theo token, không theo số lượt.

---

## 3. M3 — Long memory: hỏi thăm 3 phiên gần nhất

Lưu `nurse_summary_json` thành cột; mở hội thoại mới thì lấy 3 `conversation_id` gần nhất của cùng
`user_id`, tóm tắt lại để agent hỏi thăm.

Trải nghiệm nó mở ra là thứ đáng làm — *"Lần trước bạn đau bụng, hiện đã đỡ hơn chưa?"* biến sản phẩm
từ một form hỏi bệnh thành một chỗ có người theo dõi. Ba điều kiện tối thiểu, vì đây là PHI:

1. **Bất biến số một — dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.**
   `previous fever = true` **không** được nạp thành `current fever = true`. Nó vào namespace riêng
   `history.*`, chỉ dùng để agent hỏi lại, và snapshot phiên mới bắt đầu từ `Null` như mọi phiên khác
   (bất biến 9, `INVARIANTS.md`).
2. **Truy cập theo đúng `user_id` đang đăng nhập** — không có đường nào đọc chéo hồ sơ người khác.
   Cần một test riêng cho việc này.
3. **Consent + retention** — bệnh nhân biết hệ thống nhớ gì và trong bao lâu. **Đây là câu hỏi cho PM,
   không phải cho kỹ thuật**, nhưng phải có câu trả lời **trước khi** M3 lên production.

---

## 4. Thứ tự — không được đảo

```text
F03 §2.3 (đĩa bền)  ->  M2 (nén)  ->  M3 (xuyên phiên)
```

M3 trước M1 là lỗi thiết kế kinh điển: bàn tới ký ức xuyên phiên trong khi phiên đang dở còn chưa sống
nổi qua một lần deploy. M1 đã xong; nhưng nếu `F03` §2.3 chưa xử lý thì trên Render nó vẫn mất — nên
`F03` vẫn chặn.

---

## 5. Test bắt buộc

1. Hai phiên mở cùng một giây thì `conversation_id` không đụng nhau.
2. Restart giữa phiên: phiên đang dở khôi phục được từ event log. *(đã có — không được làm hỏng)*
3. Nén context dài **không** ghi đè snapshot; bất đồng thì snapshot thắng.
4. **`previous fever = true` của phiên trước không nạp thành `current fever = true`.**
5. Không có đường nào đọc được hồ sơ của `user_id` khác.
6. Credential không xuất hiện trong bất kỳ bản dump nào.

---

## 6. Tiêu chí chấp nhận

- Phiên dài vượt ngưỡng context vẫn chạy đúng, không mất field đã thu.
- Mở hội thoại mới, agent hỏi thăm được phiên trước **mà snapshot mới vẫn rỗng hoàn toàn**.
- PM đã trả lời câu hỏi consent/retention bằng văn bản trước khi M3 lên production.

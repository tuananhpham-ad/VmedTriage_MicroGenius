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

## 2. M2 — Short memory hybrid: **đã xong**

```text
Structured snapshot   [ĐÃ CÓ - reducer, là nguồn sự thật]
+ Tóm tắt lượt cũ      [✅ `symptom_protocol/compaction.py`]
+ N lượt raw gần nhất  [ĐÃ CÓ - session.conversation]
```

**Bất biến:** summarizer nén **phần hội thoại**, không bao giờ ghi đè snapshot. Nếu tóm tắt và snapshot
bất đồng thì **snapshot thắng** — nó là thứ có bằng chứng `evidence_span`, bản tóm tắt thì không.
Bất biến này được thi hành bằng **hình dạng code**: `compaction` không import `reducer`, không nhận
`answers`, và không có hàm nào trả ra thứ ghi được vào snapshot.

| Yêu cầu | Trạng thái |
| --- | --- |
| Ngưỡng theo **token**, không theo số lượt | ✅ `Settings.context_compaction_token_budget` (2400) |
| Giữ nguyên văn N lượt gần nhất | ✅ `context_compaction_keep_turns` (6) — nén không ăn vào cửa sổ này |
| Tóm tắt sống qua restart | ✅ `conversation_summary` + `summarized_turns` vào `payload` |
| Model chết vẫn có bản tóm tắt | ✅ rơi về bản tất định (ghép nguyên văn lời người bệnh) |

Nén chạy ở `ProtocolSessionStore._remember` — cùng chỗ với persist, vì cả hai trả lời cùng một câu
hỏi "một lượt vừa được nhận thì phải làm gì". Cái được nén là **khung nhìn gửi cho model**
(`compaction.history_view`); `session.conversation` vẫn giữ đủ lượt thô vì đó là bản ghi bàn giao.

---

## 3. M3 — Long memory: **code đã xong, cờ đang TẮT**

Lưu `nurse_summary_json` thành cột; mở hội thoại mới thì lấy 3 `conversation_id` gần nhất của cùng
`user_id`, tóm tắt lại để agent hỏi thăm.

| Yêu cầu | Trạng thái |
| --- | --- |
| Cột `nurse_summary_json` | ✅ `ConversationRow` — ghi khi phiên đóng (`routes._remember_nurse_summary`) |
| Lấy 3 phiên gần nhất của cùng `user_id` | ✅ `conversation_store.recent_summaries_for_user` |
| Câu hỏi thăm | ✅ `sessions/history_recall.py` — **TĨNH, không qua LLM** |
| Công tắc | ⚠️ `LONG_MEMORY_ENABLED` mặc định `false` — xem điều kiện 3 |

Câu hỏi thăm không qua LLM vì nó chỉ được nói đúng một điều — lần trước người bệnh kể bị gì — và một
câu model viết lại có thể thêm chi tiết lâm sàng mà không phiên nào từng ghi nhận. Nó cũng **không**
nhắc lại `proposed_priority` (đề xuất đang chờ điều dưỡng duyệt, `CLAUDE.md` nguyên tắc 1) hay
`narrative` (đọc hồ sơ của người bệnh ra loa).

Trải nghiệm nó mở ra là thứ đáng làm — *"Lần trước bạn đau bụng, hiện đã đỡ hơn chưa?"* biến sản phẩm
từ một form hỏi bệnh thành một chỗ có người theo dõi. Ba điều kiện tối thiểu, vì đây là PHI:

1. **Bất biến số một — dữ kiện lịch sử không tự trở thành dữ kiện hiện tại.** ✅
   `previous fever = true` **không** được nạp thành `current fever = true`. Nó vào namespace riêng
   `history.*`, chỉ dùng để agent hỏi lại, và snapshot phiên mới bắt đầu từ `Null` như mọi phiên khác
   (bất biến 9, `INVARIANTS.md`). Thi hành bằng **kiểu dữ liệu**: thứ đi ra khỏi kho lịch sử là
   `PastConversation` (5 trường chữ, không có `answers`, không có `TriState`) — không có gì để nhét
   nhầm vào snapshot.
2. **Truy cập theo đúng `user_id` đang đăng nhập** ✅ — khoá composite `(conversation_id, user_id)`,
   và `user_id = 0` (khách) không có lịch sử. Test riêng:
   `test_no_path_reads_another_users_history`, `test_a_guest_session_has_no_history`.
3. **Consent + retention** — bệnh nhân biết hệ thống nhớ gì và trong bao lâu. **Đây là câu hỏi cho PM,
   không phải cho kỹ thuật**, nhưng phải có câu trả lời **trước khi** M3 lên production.
   ⚠️ **CHƯA CÓ CÂU TRẢ LỜI** ⇒ `LONG_MEMORY_ENABLED=false` ở mọi môi trường (`render.yaml`).
   `history_recall._RECALL_MAX_AGE_DAYS = 30` là trần tạm giữ chỗ cho chính sách đó.

---

## 4. Thứ tự — không được đảo

```text
F03 §2.3 (đĩa bền)  ->  M2 (nén)  ->  M3 (xuyên phiên)
```

M3 trước M1 là lỗi thiết kế kinh điển: bàn tới ký ức xuyên phiên trong khi phiên đang dở còn chưa sống
nổi qua một lần deploy.

Cả ba mắt xích đã thông: `F03` §2.3 xử lý xong bằng Neon Postgres (`render.yaml` khai `DATABASE_URL`
là secret, không dùng đĩa ephemeral của gói free), M1 xong, M2 xong, M3 xong phần code.

> ⚠️ `F03` §2.1 (Alembic) **vẫn chưa có**. Cột `nurse_summary_json` của M3 đi qua
> `database._apply_additive_migrations` — bản vá thêm cột nullable, chạy được trên cả SQLite lẫn
> Postgres và không bắt ai xoá DB. Đó là một bản vá, không phải một migration tool.

---

## 5. Test bắt buộc

| # | Bài | Ở đâu |
| --- | --- | --- |
| 1 | Hai phiên mở cùng một giây thì `conversation_id` không đụng nhau | ✅ `test_conversation_memory.py` |
| 2 | Restart giữa phiên: phiên đang dở khôi phục được | ✅ `test_conversation_memory.py` |
| 3 | Nén context dài **không** ghi đè snapshot; bất đồng thì snapshot thắng | ✅ `test_conversation_memory_m2_m3.py::test_the_snapshot_wins_when_the_summary_contradicts_it` |
| 4 | **`previous fever = true` không nạp thành `current fever = true`** | ✅ `..._m2_m3.py::test_previous_fever_does_not_become_current_fever` |
| 5 | Không có đường nào đọc được hồ sơ của `user_id` khác | ✅ cả hai file |
| 6 | Credential không xuất hiện trong bất kỳ bản dump nào | ✅ `test_conversation_memory.py` |

19 bài mới ở `tests/test_services/test_conversation_memory_m2_m3.py`; 9 bài M1 cũ giữ nguyên xanh.

---

## 6. Tiêu chí chấp nhận

- ✅ Phiên dài vượt ngưỡng context vẫn chạy đúng, không mất field đã thu.
- ✅ Mở hội thoại mới, agent hỏi thăm được phiên trước **mà snapshot mới vẫn rỗng hoàn toàn**.
- ⬜ **PM đã trả lời câu hỏi consent/retention bằng văn bản trước khi M3 lên production.**
  Đây là mục duy nhất còn mở, và nó không phải việc của kỹ thuật. Chừng nào chưa có câu trả lời,
  `LONG_MEMORY_ENABLED` giữ `false` — code chạy được không phải là lý do để bật nó.

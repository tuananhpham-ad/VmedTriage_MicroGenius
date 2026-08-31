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
| Đường ghi ĐƯỢC GỌI THẬT | ✅ từ 2026-08-25 — xem cảnh báo dưới bảng |
| Lấy 3 phiên gần nhất của cùng `user_id` | ✅ `conversation_store.recent_summaries_for_user` |
| Câu hỏi thăm | ✅ `sessions/history_recall.py` — nội dung TẤT ĐỊNH (xem §3.2) |
| Chắt lọc 3 phiếu thành 1 câu, **lưu sẵn** | ✅ bảng `followup_questions` — `stores/followup_store.py` |
| Model viết câu hỏi thăm, guard bằng code | ✅ `sessions/followup_writer.py` — `ROLE_FOLLOWUP_QUESTION` |
| Công tắc | ⚠️ `LONG_MEMORY_ENABLED` mặc định `false` — xem điều kiện 3 |

> ⚠️ **Đã từng hỏng câm trong production (sửa 2026-08-25).** `_remember_nurse_summary` tồn tại nhưng
> **không có chỗ nào gọi**, và nhánh đỏ `_escalate_from_text_signal` không gọi `_remember` — nên cột
> `nurse_summary_json` luôn `NULL` và `recent_summaries_for_user` (chỉ lấy hàng CÓ phiếu) luôn trả
> rỗng: bật cờ cũng không bao giờ có 3 phiếu để chắt lọc. Cả 42 bài test M2/M3 vẫn xanh vì chúng gọi
> thẳng `conversation_store.save_nurse_summary`, không đi qua route. Ba việc đã làm:
> (1) `_finish_chat_turn` + `force_complete_case` gọi `_remember_nurse_summary`;
> (2) `submit_message` trở thành vỏ mỏng gọi `_turn()` rồi `_remember()` đúng một lần — chốt sổ không
> còn rải trên 9 nhánh `return` để mỗi nhánh tự nhớ;
> (3) `save_nurse_summary` trả `True` ở lần ghi ĐẦU, và chỉ lần đó mới `refresh_for_user` — nếu không,
> mọi lượt sau khi phiên đóng đều xoá `asked_at` của câu đang chờ hỏi.
> Bài chặn: `tests/test_api/test_routes.py::test_a_closed_chat_turn_writes_the_nurse_summary_to_the_conversation_row`
> — đi qua route, không đi qua store.

### 3.1 Câu hỏi thăm được sinh TRƯỚC, không sinh lúc mở hội thoại

```text
Phiên N đóng   -> chắt lọc 3 phiếu gần nhất -> GHI `followup_questions`   (chỗ RẢNH)
Phiên N+1 mở   -> SELECT một hàng theo khoá  -> ghép vào câu mở           (chỗ ĐANG CHỜ)
```

Lượt mở là lượt duy nhất người bệnh phải chờ mà chưa nhận lại được gì, nên phần đắt (truy vấn 3 hàng
+ chắt lọc) chuyển sang đuôi lượt trước đó (`routes._remember_nurse_summary` -> `refresh_for_user`).

**Chắt lọc = 3 phiếu vào, MỘT nhãn ra.** Nhãn được chọn là than phiền LẶP LẠI nhiều nhất (hoà thì lấy
mới nhất), vì đó là thứ duy nhất mà ba phiếu biết còn một phiếu thì không - lấy phiếu mới nhất thì
không cần tới ba phiếu làm gì. Đọc cả ba nhãn cho người bệnh nghe là mở đầu bằng một bản tóm tắt hồ
sơ chứ không phải một câu hỏi thăm (`_MAX_MENTIONED = 1`).

**Hỏi đúng một lần cho mỗi câu được sinh** (`asked_at`): lặp lại nó ở mọi lần mở biến một câu quan tâm
thành một dòng chào tự động. Phiên mới đóng ⇒ câu mới ⇒ `asked_at` về `None`.

Bảng vẫn nằm dưới cùng công tắc `LONG_MEMORY_ENABLED` và cùng trần tuổi `_RECALL_MAX_AGE_DAYS`: cờ
tắt thì không chắt lọc và không ghi - "mới ghi sẵn thôi chứ chưa hỏi" vẫn là ghi một dẫn xuất của PHI.

### 3.2 Hai con LLM của tầng ký ức — cố ý KHÔNG dùng chung một vai trò

| | `ROLE_CONTEXT_SUMMARY` (M2) | `ROLE_FOLLOWUP_QUESTION` (M3) |
| --- | --- | --- |
| Ở đâu | `symptom_protocol/compaction.py` | `sessions/followup_writer.py` |
| Đầu vào | các lượt THÔ của phiên đang chạy | vài nhãn than phiền của các phiên đã đóng |
| Đầu ra đi tới | model đang hỏi tiếp ở cùng phiên | **thẳng tới người bệnh** |
| Sai thì mất gì | phần đầu bối cảnh của một phiên | một câu y khoa bịa, đọc như lời hệ thống |
| Fallback | tóm tắt tất định (ghép nguyên văn) | câu tĩnh `history_recall.greeting` |

Tách hai vai trò vì hai lý do, và lý do thứ hai mới là lý do bắt buộc: (1) gộp lại thì không bao giờ
đọc được số liệu latency/chi phí riêng của cái nào; (2) ghim một model rẻ cho phần nén là **vô tình
ghim luôn** cho câu đi thẳng tới người bệnh. Hai biến riêng: `ROLE_ORDER_CONTEXT_SUMMARY`,
`ROLE_ORDER_FOLLOWUP_QUESTION` (để trống = kế thừa thứ tự toàn cục).

**Phân vai giữa code và model: code chọn NÓI VỀ CÁI GÌ, model chọn NÓI THẾ NÀO.** Nhãn được nhắc tới
do `_ranked_complaints` chốt (tất định); model chỉ đổi cách nói, vì đọc đúng một khuôn câu tới lần
thứ ba thì nó thành tiếng ồn.

M3 bị siết ở **cả hai đầu**, cả hai bằng code chứ không bằng prompt:

1. **Đầu vào chỉ có nhãn** — model không nhìn thấy `narrative` (văn xuôi phiếu, đọc hồ sơ ra loa) hay
   `proposed_priority` (đề xuất đang chờ điều dưỡng duyệt, `CLAUDE.md` nguyên tắc 1). Không đưa vào
   thì không có gì để rò ra.
2. **Đầu ra bị `followup_writer._accept` kiểm** — đúng một câu hỏi, có đúng nhãn đã chắt lọc, không
   chữ số, không mức ưu tiên, không từ chẩn đoán/kê đơn/hướng xử trí. Trượt ⇒ dùng câu tĩnh, **không
   sửa** câu model viết: thứ còn lại sau khi cắt không phải câu model định nói.

Công tắc `FOLLOWUP_QUESTION_LLM_ENABLED` (mặc định bật) chỉ chọn *ai viết*; *có hỏi thăm hay không*
vẫn do `LONG_MEMORY_ENABLED` quyết định.

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
   📌 **Quyết định 2026-08-25 (Agent Lead): BẬT — `LONG_MEMORY_ENABLED=true` trong `deploy/azure/env`.**
   Trước đó cờ này `true` mà không có dòng nào giải thích; nay nó là một lựa chọn có người và có ngày.
   **Câu trả lời bằng văn bản của PM VẪN CÒN THIẾU** — bật trước, chờ văn bản sau, và đó là rủi ro
   được nhận lấy một cách có ý thức chứ không phải một sơ suất. Hai việc kéo theo, chưa làm:
   - PM chốt nội dung thông báo cho bệnh nhân (nhớ gì, trong bao lâu, tắt bằng cách nào);
   - `history_recall._RECALL_MAX_AGE_DAYS = 30` hiện là trần tạm giữ chỗ, phải khớp lại với thời hạn
     PM chốt.

   Mẫu `deploy/azure/env.example` vẫn để `false`: mặc định cho một môi trường mới phải là TẮT, vì
   người dựng môi trường đó chưa chắc đã đọc quyết định này.

---

## 4. Thứ tự — không được đảo

```text
F03 §2.3 (đĩa bền)  ->  M2 (nén)  ->  M3 (xuyên phiên)
```

M3 trước M1 là lỗi thiết kế kinh điển: bàn tới ký ức xuyên phiên trong khi phiên đang dở còn chưa sống
nổi qua một lần deploy.

Cả ba mắt xích đã thông: `F03` §2.3 xử lý xong bằng Neon Postgres (`DATABASE_URL` khai trong
`deploy/azure/env`, không dùng đĩa ephemeral của container), M1 xong, M2 xong, M3 xong phần code.

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
- ⬜ **PM trả lời câu hỏi consent/retention bằng văn bản.** Vẫn là mục duy nhất còn mở, và vẫn không
  phải việc của kỹ thuật. Khác với trước: M3 **đã được bật** ở production theo quyết định 2026-08-25
  (§3 điều kiện 3), nên đây không còn là điều kiện CHẶN mà là **món nợ đang chạy** — mỗi phiên bệnh
  nhân từ đây tích thêm dữ liệu dưới một chính sách chưa ai viết ra. Càng để lâu càng khó lùi.

# F07 — Streaming cảm nhận được + logging chi tiết tool/agent

> Chủ trì: Fullstack AI Engineer.
> Nguồn: dòng ghi chú cuối `what_to_do_next.md` — *"chưa có streaming, cần logging thêm chi tiết hơn
> khi dùng các tool, các agent nào"*.

---

## 1. Streaming

### 1.1. Trạng thái: đã nối đủ đầu-cuối, nhưng **không cảm nhận được** — và đó là cố ý

Hạ tầng có thật:

| Tầng | Nơi |
| --- | --- |
| Endpoint SSE | `src/api/routes.py:263-343` — `POST /api/v1/chat/stream` |
| Đẩy token từ threadpool về event loop | `routes.py:305-308` — `loop.call_soon_threadsafe` |
| Client đọc stream | `src/ui/new/api.js:32-53` |
| Fallback về `/chat` khi stream không dùng được | `src/ui/new/features/patient.js:541-562` |

Nhưng `on_token` chỉ bắn **một lần**, với trọn câu, sau khi gom hết:

```python
# src/services/symptom_protocol/intake_agent.py:1005-1014
pieces: list[str] = []
for piece in provider_router.complete_stream(...):
    pieces.append(piece)                      # GOM TRỌN, không phát ra ngoài
question = "".join(pieces).strip().strip('"')
if question and _passes_output_guard(question, protocol, cluster, plan, answers):
    if on_token is not None:
        on_token(question)                    # phát MỘT lần, cả câu
```

> **Không được "sửa" bằng cách phát sớm.** Comment tại `:1001-1004` nói đúng lý do: `output_guard` phải
> chạy **trước** khi người bệnh đọc được chữ nào. Phát từng token rồi mới kiểm thì lúc guard bắt được
> một tên bệnh, câu đó đã nằm trên màn hình — và "đính chính" một câu vừa hiện ra còn tệ hơn là chờ.
> Guard chạy sau khi người bệnh đã đọc thì không còn là guard (bất biến 1 và 4).

Cái giá đã đo: **p50 ~1.2s im lặng** trước chữ đầu tiên (`eval/baselines/2026-08-17-p0-summary.md`).

### 1.2. Cách đúng: lấp khoảng im lặng bằng trạng thái thật

Hiện chỉ phát **đúng một** `status` phase, ngay đầu lượt:

```python
# src/api/routes.py:327
yield _sse("status", {"phase": "reading", "text": "Đang đọc câu trả lời của bạn"})
```

Rồi im cho tới `done`. Bổ sung phase cho từng chặng thật của lượt — mỗi chặng phát khi nó **bắt đầu**:

| Phase | Ứng với | Chi phí thật |
| --- | --- | --- |
| `reading` | nhận tin nhắn *(đã có)* | — |
| `extracting` | `fact_extractor` | **p50 3.83s** — chặng dài nhất |
| `checking` | `reducer` + `rule_engine` | ~0, nhưng là chỗ đáng nói "đang đối chiếu dấu hiệu" |
| `writing` | `synthesis` | p50 1.23s |

UI đã có sẵn bong bóng pending với `role="status"` + `aria-live="polite"` và ba chấm
(`patient.js:502-504`) — chỉ cần đổi chữ theo phase thay vì giữ một câu cố định.

Đây là chỗ loading indicator có giá trị nhất, và cũng là mục ⛔ duy nhất còn lại của bảng UX §5.1.

---

## 2. Logging

### 2.1. Langfuse: có key, **không dùng ở đâu**

`.env.example:47-49` khai `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASE_URL`.
`grep -rn "langfuse" src/ --include=*.py` cho **0 kết quả**. Cũng vậy với `AI_LOG_SERVER` /
`AI_LOG_API_KEY` / `AI_LOG_DIR` (`:52-54`).

**Quyết định cần chốt:** nối Langfuse vào `provider_router` hay bỏ ba biến đó khỏi `.env.example`.
Không để nửa vời — một biến môi trường có key thật mà không ai đọc là thứ sẽ làm người sau tưởng đã có
tracing.

> ⚠️ Nếu nối: **Langfuse nhận nguyên văn hội thoại người bệnh (PHI)**. Phải trả lời trước: dữ liệu đi
> ra ngoài hạ tầng dự án có được phép không, giữ bao lâu, ai truy cập được (`CLAUDE.md` nguyên tắc 5).
> Đây là câu hỏi cho PM, không phải cho engineering.

### 2.2. Cái đã có: `stage_log`

`src/services/infra/fever_stage_log.py` ghi từng bước với `session_id`, `turn`, `stage`, `cluster_id`,
`event`, `input`, `output`, `llm_used`. `narrative.py:76-80` dùng đúng đường này.

Ba lỗ so với yêu cầu *"chi tiết hơn khi dùng các tool, các agent nào"*:

| Thiếu | Vì sao cần |
| --- | --- |
| **Vai trò model của mỗi lời gọi** | `provider_router` đã có `RoleProfile` (`ROLE_SYNTHESIS`, `ROLE_EXTRACTOR`, ...) nhưng vai trò không xuống tới log. Không biết lời gọi nào thuộc chặng nào thì không tách được latency §1.2 |
| **Tool nào được gọi** | `src/tool/catalog/` có 82 tool; không có dòng log nào nói tool nào chạy, tham số gì, kết quả ra sao |
| **Nhánh nào bị bỏ qua** | Controller quyết `invoke_extractor=False` (lượt greeting/off_topic) — không log thì `skippable_turn_ratio` không đo được |

> ⚠️ **`logs/` chứa nguyên văn hội thoại người bệnh (PHI).** Đã nằm trong `.gitignore`. Log thêm chi
> tiết thì lượng PHI tăng theo — mã hoá at-rest, phân quyền đọc và chính sách xoá theo hạn lưu trữ phải
> có **trước** khi dùng thật, không phải sau.

---

## 3. Thay đổi cụ thể

| File | Sửa gì |
| --- | --- |
| `src/api/routes.py:301-336` | Phát thêm phase `extracting` / `checking` / `writing` |
| `src/services/symptom_protocol/session.py:405-513` | Gọi callback phase tại đầu mỗi chặng |
| `src/ui/new/features/patient.js:547-562` | Đổi chữ bong bóng pending theo `phase` |
| `src/services/infra/fever_stage_log.py` | Thêm `role`, `tool_name`, `skipped_stage` vào bản ghi |
| `src/services/infra/provider_router.py` | Truyền `role` xuống log |
| `.env.example:47-54` | Nối Langfuse hoặc gỡ biến — theo quyết định §2.1 |

**Không đụng:** thứ tự `output_guard` chạy trước khi phát chữ (§1.1).

---

## 4. Test bắt buộc

1. Guard chặn câu trả lời thì **không token nào** đã kịp tới client trước đó.
2. Client không hỗ trợ SSE thì fallback `/chat` vẫn cho kết quả đúng (`patient.js:543-546`).
3. Người dùng đóng tab giữa chừng thì lượt bị huỷ, threadpool không giữ chỗ (`routes.py:334-336` — đã có).
4. Lỗi ghi log **không bao giờ** làm hỏng phiên — mọi lỗi I/O bị nuốt và chỉ ghi cảnh báo.
5. API key **không bao giờ** xuất hiện trong log, kể cả bản Langfuse.

---

## 5. Tiêu chí chấp nhận

- Người bệnh thấy trạng thái đổi ít nhất **2 lần** trong khoảng chờ, thay vì một câu đứng im 4s.
- Đọc log một phiên và trả lời được: lượt nào gọi model nào ở vai trò gì, tool nào chạy, lượt nào bị bỏ
  qua extractor.
- `skippable_turn_ratio` tính ra được số.
- Không còn biến môi trường nào có key thật mà không ai đọc.

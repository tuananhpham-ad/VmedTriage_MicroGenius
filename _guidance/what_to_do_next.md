# Việc cần làm — mục lục

> **Bản 2026-08-22.** File này đã được **tách thành spec theo từng feature** trong
> [`_guidance/features/`](features/). Đây chỉ còn là điểm vào.
>
> - Bản đầy đủ 1263 dòng trước khi tách: `_guidance/archive/what_to_do_next_2026-08-22_full.md`
> - Bản 2026-08-19: `_guidance/archive/what_to_do_next_2026-08-19_full.md`
>
> Lý do tách: file cũ trộn ba thứ khác loại — bất biến kiến trúc, backlog kỹ thuật, và yêu cầu sản phẩm
> — nên không đọc để duyệt được, cũng không giao việc được.

---

## Bắt đầu ở đâu

👉 **[`features/00_INDEX.md`](features/00_INDEX.md)** — mục lục đầy đủ, thứ tự đọc, phụ thuộc giữa các
feature, và "việc `***` tiếp theo là gì".

👉 **[`features/INVARIANTS.md`](features/INVARIANTS.md)** — đọc trước tiên, luôn luôn. 10 bất biến,
sơ đồ 6 tầng, bảng "đã chạy, đừng viết lại", 6 công tắc ngắt, baseline hiện tại.

---

## Bảng nhanh

| Ưu tiên | File | Nội dung |
| --- | --- | --- |
| `***` | [`F01_agent_qa_flow.md`](features/F01_agent_qa_flow.md) | Quy trình 5 bước, tự sinh câu hỏi, giảm số lượt |
| `***` | [`F02_field_state_model.md`](features/F02_field_state_model.md) | Hợp đồng `Null / true / false / unknown` |
| `**` | [`F03_database.md`](features/F03_database.md) | Migration, rút cột khỏi blob JSON, đĩa bền |
| `*` | [`F04_memory.md`](features/F04_memory.md) | M2 nén context, M3 ký ức xuyên phiên |
| — | [`F05_handoff_card_ui.md`](features/F05_handoff_card_ui.md) | Phiếu: trường có lên đầu, trường thiếu gập lại |
| — | [`F06_narrative_summary.md`](features/F06_narrative_summary.md) | Văn xuôi: giảm fallback, sửa bug, căn lề hai đầu |
| — | [`F07_streaming_and_logging.md`](features/F07_streaming_and_logging.md) | Streaming cảm nhận được, logging tool/agent |
| ⛔ | [`B01_backlog_clinical.md`](features/B01_backlog_clinical.md) | **Ngoài phạm vi** — chủ trì lâm sàng |
| ⛔ | [`B02_backlog_architecture.md`](features/B02_backlog_architecture.md) | **Ngoài phạm vi** — kiến trúc/eval |

---

## Ba câu hỏi cho planning

Cả ba là quyết định **phạm vi**, không phải kỹ thuật:

1. **PC chèn trước hay track P chạy trước** (`B01` §4) — quyết định cả sprint. Không chốt thì mặc định
   trôi theo hướng "track P trước", không phải vì ai chọn nó mà vì track P dễ bắt đầu hơn.
2. **Ai chủ trì PC** (`B01` §3) — giao nhầm cho track engineering thì ước lượng sai từ đầu.
3. **Consent + retention cho memory M3** (`F04` §3) — phải có câu trả lời trước khi M3 lên production.

Câu hỏi thứ tư, cho Fullstack: **nối Langfuse hay gỡ key khỏi `.env.example`** (`F07` §2.1). Hiện có
key thật mà không dòng code nào đọc.

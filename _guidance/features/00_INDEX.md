# Mục lục feature — VMedTriage

> Tách từ `_guidance/what_to_do_next.md` (1263 dòng) ngày **2026-08-22**.
> Bản đầy đủ trước khi tách: `_guidance/archive/what_to_do_next_2026-08-22_full.md`.
>
> Mỗi file dưới đây theo cùng một khung: **Vấn đề (kèm `file:line` đã kiểm chứng) → Yêu cầu → Thiết kế
> → Thay đổi cụ thể → Ràng buộc không được vi phạm → Test bắt buộc → Tiêu chí chấp nhận.**

---

## Đọc theo thứ tự này

**`INVARIANTS.md` trước tiên, luôn luôn.** 10 bất biến + sơ đồ 6 tầng + bảng "đã chạy, đừng viết lại".
Mọi file khác trỏ về đó thay vì chép lại.

| Ưu tiên | File | Nội dung | Chủ trì |
| --- | --- | --- | --- |
| `***` | [`F01_agent_qa_flow.md`](F01_agent_qa_flow.md) | Quy trình 5 bước, tự sinh câu hỏi, giảm số lượt | Agent Lead |
| `***` | [`F02_field_state_model.md`](F02_field_state_model.md) | Hợp đồng `Null / true / false / unknown` | Agent Lead |
| `**` | [`F03_database.md`](F03_database.md) | Migration, rút cột khỏi blob JSON, đĩa bền | Fullstack |
| `*` | [`F04_memory.md`](F04_memory.md) | M2 nén context, M3 ký ức xuyên phiên | Agent Lead |
| — | [`F05_handoff_card_ui.md`](F05_handoff_card_ui.md) | Phiếu: trường có lên đầu, trường thiếu gập lại | Fullstack |
| — | [`F06_narrative_summary.md`](F06_narrative_summary.md) | Văn xuôi: giảm fallback, sửa bug, căn lề hai đầu | Agent Lead + Fullstack |
| — | [`F07_streaming_and_logging.md`](F07_streaming_and_logging.md) | Streaming cảm nhận được, logging tool/agent | Fullstack |
| `**` | [`F08_c6_latency_cost.md`](F08_c6_latency_cost.md) | C6 chặn đường request, ba nhánh chạy tuần tự — đo trước, cắt sau | Agent Lead + Fullstack |
| `***` | [`F09_symptom_protocols.md`](F09_symptom_protocols.md) | 4 nhóm còn thiếu (ngực/bụng/hô hấp/đầu), pipeline 5 bước, router đa nhóm | Agent Lead + Data Lead |
| `***` | [`F10_intake_quality_fixes.md`](F10_intake_quality_fixes.md) | 4 lỗi khai thác sau khi lên 5 nhóm: chọn nhầm nhóm, hỏi lại thứ đã khai, quá nhiều câu, nhầm người khai | Agent Lead |
| ⛔ | [`B01_backlog_clinical.md`](B01_backlog_clinical.md) | **Ngoài phạm vi** — chủ trì lâm sàng | Data Lead |
| ⛔ | [`B02_backlog_architecture.md`](B02_backlog_architecture.md) | **Ngoài phạm vi** — kiến trúc/eval | Agent Lead |

---

## Việc `***` tiếp theo là gì

**`F10` §7 — chạy test cho Fix A + Fix B đã code nhưng CHƯA CHẠY TEST lần nào.**

- *Vì sao trước:* code đang nằm trong working tree ở trạng thái chưa xác nhận. Fix A đổi hành vi
  `registry.select_protocol`, rủi ro cao nhất ở `test_generic_protocol_and_switching.py` và
  `test_fever_flow.py`.
- *Lệnh và mốc đối chiếu:* `F10` §7 (9 test fail sẵn trên HEAD — đừng nhầm chúng là hồi quy mới).

Sau đó theo thứ tự `F10` §7: Fix D+E (tầng sinh câu hỏi) → Fix F (người khai) → Fix C (số lượt, lớn
nhất).

> `F01` §3.1 (stage `E`) **đã xong** — cả 5 protocol mới đều có `STAGE_ORDER` bắt đầu bằng `"E"` và
> `emergency_scan_stage` tường minh, đúng khuyến nghị "tách khái niệm ra khỏi vị trí". Phần còn lại
> của `F01` (§3.2 gộp lượt, §3.3 nới renderer) được `F10` Fix C và Fix D tiêu thụ.

---

## Phụ thuộc giữa các feature

```text
F03 §2.3 (đĩa bền) ──> F03 §2.1 (Alembic) ──> F03 §2.2 (rút cột) ──┬─> F04 (M2, M3)
                                                                    └─> F06 §2.1 (đo fallback)

F02 (hợp đồng 4 trạng thái) ──┬─> F05 (hiển thị 4 trạng thái)
                              └─> F06 §2.2 (khối `reported`)

B02 §5 (property test hoán vị) ──> F01 (gate cứng, không có thì không merge được)

B01 §3 (4 protocol) ──> lãi đầy đủ của F01  (F01 vẫn làm được trước, chỉ hẹp hơn)

F10 A,B (đã code) ──> F10 D,E ──> F10 F ──> F10 C (số lượt; đụng nội dung cụm, làm cuối)
B02 §5 (property test hoán vị) ──> F10 C  (gate duy nhất chặn 'rút ngắn bằng cách bỏ hỏi')
```

`F05` và `F06` §2.2 sửa **cùng một hàm** (`nurse.js:689-701`) — làm một lần.

---

## Ba đính chính so với yêu cầu gốc

Ghi ở đây vì chúng đổi nội dung công việc, và spec viết theo sự thật chứ không theo giả định:

1. **Tóm tắt văn xuôi KHÔNG hardcode.** `narrative.py:54-119` gọi LLM thật. Thứ trông như hardcode là
   bản **fallback tất định** khi provider lỗi hoặc guard chặn. Việc phải làm là *đo và giảm tỉ lệ
   fallback* (`F06` §2.1), không phải viết lại. → `F06`
2. **"Chỉ tóm tắt trường có thông tin" đã đạt ở backend** (`_present`, `as_text`). Phần còn thiếu nằm
   hoàn toàn ở UI. → `F05`
3. **`Null` vs `true/false/unknown` đã chạy.** Snapshot cố ý đúng 3 giá trị; "chưa hỏi" phân biệt với
   "đã rút lời" bằng `AuditEvent`, không bằng giá trị thứ tư. Việc còn lại là *hiển thị đủ 4 trạng
   thái*. → `F02`

Đính chính thứ tư, về `F07`: **streaming đã nối đủ đầu-cuối**, nhưng `on_token` bắn một lần sau khi gom
trọn — **cố ý**, vì `output_guard` phải chạy trước khi người bệnh đọc chữ nào. Cách đúng là thêm
trạng thái chờ, không phải phát sớm.

---

## Quy ước

- Ngôn ngữ: identifier/code tiếng Anh; nội dung hiển thị cho người dùng tiếng Việt.
- Branch: `<type>/<mô-tả-ngắn>-<ddmm>`. Commit: Conventional Commits, trỏ về mã `T-xxx` trong `Plan.xlsx`.
- Mọi thay đổi liên quan Agent/red-flag/priority phải chạy qua bộ test chuẩn trước khi merge; **không
  giảm số lượng hoặc độ phủ 5 nhóm triệu chứng**.
- **Mọi ngưỡng phần trăm phải đi kèm mẫu số. Không có mẫu số thì không phải gate.**

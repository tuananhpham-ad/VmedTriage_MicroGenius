# B01 — Backlog lâm sàng (NGOÀI phạm vi đợt này)

> **Không thuộc 6 việc ưu tiên hiện tại.** Ghi ở đây để không mất thông tin.
>
> ⚠️ **Ba trong bốn việc dưới đây KHÔNG phải việc engineering.** Giao nhầm cho track kỹ thuật thì ước
> lượng sai từ đầu, và sprint sẽ trông như đang chạy mà gate an toàn không nhích được.
>
> Chủ trì: **Data Lead + review lâm sàng**, không phải Agent Lead.

---

## 1. Bảng quy đổi mã red flag

**Loại: quyết định lâm sàng. Đang chặn một gate ở §8.**

Hệ thống dùng `RF-07` / `TEXT_SIGNAL_*`; golden case dùng `RF-TRAUMA-POISONING-001`. Hai hệ từ vựng
khác nhau nên **red-flag recall đo ra 0% dù hệ thống có phát hiện** — con số 0% ở baseline là lỗi đo,
không phải lỗi phát hiện.

Cho tới khi có bảng quy đổi, mọi chỉ số red-flag recall đều vô nghĩa.

---

## 2. Ký duyệt `SHORT_CIRCUIT_CODES`

**Loại: quyết định lâm sàng.** Hiện mới 32/100 mã được duyệt.

Hệ thống đang **an toàn nhưng kém nhạy** — liên quan trực tiếp tới `emergency recall 48.9%` (22/45).
Đây là con số quan trọng nhất đang có, và nó không cải thiện được bằng code.

---

## 3. Track PC — 4 protocol lâm sàng còn thiếu

**Hạng mục lớn nhất còn lại, và vẫn chưa có người chủ trì.**

4/5 nhóm MVP (Đau bụng, Đau ngực, Khó thở, Đau đầu) chưa tồn tại — tất cả đang rơi vào
`GENERIC_PROTOCOL` (`src/services/engines/generic_protocol.py`, 211 dòng).

### Quy mô thật

`fever_protocol.py` là **696 dòng** và **không phải bảng dữ liệu**: 7 stage, ~10 hàm skip-rule,
`determine_route`, `conservatism_tier`, `_is_dengue_context`, `budget_key`, `derive_duration`. Bốn
protocol nữa là **bốn lần chừng đó logic lâm sàng viết tay**.

**Đừng ước lượng PC như một task code** — phần lớn công là đọc tài liệu lâm sàng và quyết ngưỡng.

### Thừa hưởng, không viết lại

`common_safety/rules.py`, `clusters.py`, `fields.py`, `screening_groups.py`, `stage_machine`,
`screening`, `batching`, `retraction` — đã trung lập với nhóm triệu chứng.

### Phải viết riêng từng nhóm

Field + tier (M0/M1/C/O/H), cụm câu hỏi, `ScreeningGroup`, skip-rule, `determine_route`, ngưỡng budget,
luật triage riêng.

### Các bước

1. Chốt nguồn lâm sàng — `data/triage_*.csv` là **nguyên liệu thô**, không phải protocol.
2. Làm **một** nhóm trọn vẹn trước (đề xuất Khó thở hoặc Đau ngực vì tỉ trọng red flag cao), rút kinh
   nghiệm rồi mới làm ba nhóm còn lại song song.
3. Mỗi nhóm đủ test như fever.
4. Bổ sung golden case trước khi merge.

### Ràng buộc khi viết protocol mới

Giữ cho rule **không trôi ngược thành `if/else` theo bệnh**. Hệ thống hiện không có
`if fever: ... if chest_pain: ...`; nó có 5 guardrail:

| Guardrail | Hiện thực |
| --- | --- |
| Safety | `common_safety/` (L0 + rules), không tắt được (`flags.py:12-15`) |
| Critical information | tier M0/M1 + `mandatory_unasked` |
| Unsupported recommendation | `output_guard.check()` |
| Conversation stop | `should_stop` |
| Output validation | `EvidencePolicy` + `_evidence_in_message` |

Mỗi protocol mới là một cơ hội để `if` theo bệnh lẻn vào. Review PC phải bám đúng bảng trên.

### Ảnh hưởng tới F01

`GENERIC_PROTOCOL` có ít cụm hơn hẳn fever, nên không gian "hỏi theo mạch người bệnh" cũng hẹp hơn hẳn.
`F01` vẫn làm được và vẫn có giá trị trên generic + fever, nhưng lãi đầy đủ chỉ có sau PC.

Ngoài ra, cả hai con số bất thường ở §9.1 tài liệu cũ (`sessions_with_unasked_mandatory = 9`,
`repeat_question_rate = 0.32`) đều đến **duy nhất từ `GENERIC_PROTOCOL`** — đã điều tra xong, đã sửa,
nhưng nó cho thấy generic là nơi lỗi dữ liệu protocol dễ trốn nhất.

---

## 4. Câu hỏi cho planning

1. **PC chèn trước hay track P chạy trước** — quyết định cả sprint.
   - Demo V1 cần đủ 5 nhóm thì PC chèn trước.
   - Một nhóm chạy thật tốt thì track P trước, ghi rõ trong demo rằng 4 nhóm còn lại đi qua
     `GENERIC_PROTOCOL`.
   - **Không chốt thì mặc định trôi theo hướng thứ hai** — không phải vì ai chọn nó, mà vì track P dễ
     bắt đầu hơn.
2. **Ai chủ trì PC.**
3. **SLA lâm sàng** — `SLA_clinical` phải quyết trước bằng lý do y tế, rồi bố trí nhân sự để
   `p99_observed` chui xuống dưới nó. Chốt tạm 5 phút. Nếu `p99_observed > SLA_clinical` thì đó là
   **vấn đề nhân sự**, không phải vấn đề cấu hình — nới SLA cho vừa số đo là hợp thức hoá độ trễ.

# Baseline hội thoại đầy đủ — 2026-08-17 (§9 P4.3–P4.4)

Lần đầu tiên §12 có **số thật**. Trước bản này, mọi ngưỡng về trải nghiệm và độ phủ trong tài liệu kế
hoạch đều không có chỗ nào tính ra được — tức là không phải gate, chỉ là câu trong tài liệu.

| | |
| --- | --- |
| Công cụ | `eval/scripts/run_conversation_eval.py --limit 10 --stratify` |
| Model | `deepseek-chat` (cả agent lẫn bệnh nhân mô phỏng) |
| Mẫu | **10 ca**, lấy đều theo `expected_triage` (2 ca mỗi nhóm trong 5 nhóm) |
| Lỗi lời gọi model | **0/257** — đây là điều kiện để đọc được lần chạy này |
| Phiên chạm trần lượt | 0/10 |
| Lượt bệnh nhân phải dùng câu dự phòng | 0 |

> **Mẫu số là 10.** Mọi con số dưới đây phải đọc kèm điều đó. §12 nói rõ: "100% trên 20 ca không
> chứng minh được gì" — và 10 ca thì càng không. Đây là **mốc để so trước/sau**, không phải bằng
> chứng đạt gate.

## 1. Kết quả tổng hợp

```json
{
  "sessions": 10,
  "sessions_normal_close": 6,
  "sessions_red_flag": 4,
  "sessions_never_closed": 0,
  "mandatory_coverage_at_close": { "value": 0.0, "n": 6, "covered": 0 },
  "turns_median": 18.0,
  "turns_median_normal_close": 18.0,
  "user_led_ratio":       { "value": 0.1579, "n": 133 },
  "repeat_question_rate": { "value": 0.1278, "n": 133 },
  "deferral_depth":       { "value": 0.6696, "n": 9 },
  "catch_all_yield":      { "value": 0.125,  "n": 8, "yielded": 1 }
}
```

Độ trễ theo vai trò (§9 P1.4 — số liệu để trả lời điều kiện §7.2):

| Vai trò | Lời gọi | Lỗi | p50 | p95 |
| --- | --- | --- | --- | --- |
| `fact_extractor` | 150 | 0 | **2578 ms** | 5000 ms |
| `synthesis` | 107 | 0 | **2093 ms** | 3359 ms |

## 2. Ba phát hiện, xếp theo mức nghiêm trọng

### 2.1. Không một ca nào chạm tới `SELF_CARE` — và cả 6 ca lành tính đều dừng vì HẾT NGÂN SÁCH

| Nhóm nhãn golden | Kết quả hệ thống | Lý do dừng | Protocol |
| --- | --- | --- | --- |
| `emergency_now` (2 ca) | `EMERGENCY` | `RED_FLAG` | fever/general |
| 4 nhóm còn lại (6 ca) | **`EARLY_VISIT` — cả 6** | **`BUDGET_EXHAUSTED` — cả 6** | **`general` — cả 6** |

Đây là bằng chứng bằng số cho §10, thứ trước đây chỉ là lập luận: **cả 6 ca không-cấp-cứu đều rơi về
`GENERIC_PROTOCOL`**, và checklist tự chăm sóc của protocol đó không bao giờ đủ điều kiện để kết luận
`SELF_CARE`. Ca lành tính vì thế chạy hết ngân sách rồi bị đẩy lên `EARLY_VISIT`.

Đối chiếu: ca sốt lành tính H1 (`test_fever_flow.py`) đóng ở **21 lượt với `SELF_CARE`** — cùng cơ
chế, khác protocol. Chênh lệch nằm ở nội dung lâm sàng, không ở kiến trúc.

**Hệ quả cho roadmap:** không thêm router, ranking hay model nào chữa được việc này. Chỉ có track
`PC` (4 protocol còn thiếu) chữa được. §9.0 để ngỏ thứ tự cho PM chốt; số liệu này nghiêng hẳn về
`PC` chèn trước.

### 2.2. `mandatory_coverage_at_close = 0%` — nhưng gate của §12 đặt lên NHẦM chỉ số

6/6 phiên đóng bình thường đều thiếu field M0/M1. Nhìn qua thì đây là vi phạm nặng. Không phải:

- field còn thiếu là `diarrhea`, `chronic_conditions`, `immunocompromised`, `complaint_onset_at`…;
- **chúng đã được hỏi**, người bệnh mô phỏng trả lời "không rõ" hoặc né;
- §8.5 quy tắc 3 nói rõ đó là một **kết quả hợp lệ**, không phải nợ.

Hệ thống **cố ý không bảo đảm** chỉ số này — nó không ép được người bệnh biết điều họ không biết. Bất
biến thật sự được giữ là `mandatory_unasked` rỗng: *linh hoạt đổi được thứ tự hỏi, không được bỏ hỏi*
(§8.2 mục 1). §12 đã được sửa theo phát hiện này.

> ⚠️ **`mandatory_unasked` CHƯA CÓ SỐ THẬT.** Bản chạy này báo 6/6 phiên có field bỏ sót, đúng một
> field `indwelling_device`. Truy ra là **lỗi của chỉ số, không phải của hệ thống**: nó so MÃ CỤM,
> trong khi cụm tổng hợp mang mã tự sinh (`SCREEN-<stage>` không mã hoá cụm thành phần nào cả), nên
> mọi field chỉ được hỏi qua đường sàng lọc gộp đều bị báo bỏ sót giả. Đã sửa sang đếm theo FIELD và
> có test chặn (`test_a_synthesised_cluster_still_counts_its_fields_as_asked`), **nhưng chưa chạy lại
> được trên model thật** — xem §4.

### 2.3. `user_led_ratio = 15.8%` (n=133) — thấp, và §10 giải thích phần lớn

Chỉ ~1/6 câu hỏi thuộc cụm mà người bệnh vừa tự nhắc tới. Ba nguyên nhân, không loại trừ nhau:

1. `GENERIC_PROTOCOL` ít cụm hơn hẳn fever (210 dòng so với 696), nên không gian để "hỏi theo mạch
   người bệnh" hẹp hơn hẳn — lại là §10;
2. phần lớn lượt đi qua **sàng lọc gộp**, nơi câu hỏi là danh sách tĩnh chứ không phải một cụm được
   xếp hạng;
3. bản thân `relevance` chỉ ăn điểm khi người bệnh nhắc tới field của một cụm **còn dở**.

`deferral_depth = 0.67` cho thấy xếp hạng có thật sự hoãn cụm và ledger có thật sự đòi lại — cơ chế
§8.5 đang chạy, không phải code chết.

## 3. Chất lượng diễn đạt (đọc bằng mắt, không phải chỉ số)

Đọc `2026-08-17-conversation-transcripts-p4.md`. Điểm tốt: có công nhận thông tin vừa nhận, gạch đầu
dòng đúng chỗ, tiếng Việt tự nhiên, không câu nào nêu chẩn đoán.

**Một khuyết điểm mà không chỉ số nào bắt được:** khung câu lặp gần như mọi lượt — *"Em xin phép hỏi
thêm chút để rõ hơn tình trạng của chị nhé"*. `repeat_question_rate` (12.8%) đếm cụm bị hỏi lại, không
đếm **cách diễn đạt** bị dùng lại. Đây đúng là chỗ §12 nói không thay được bằng chỉ số tự động, và là
việc cho gate mềm có người chấm.

## 4. Việc chưa làm được, và vì sao

**Tài khoản DeepSeek hết số dư giữa chừng (HTTP 402).** Lần chạy thứ hai — bản duy nhất có chỉ số
`mandatory_unasked` đã sửa — hỏng vì đúng lý do đó: `fact_extractor` lỗi **216/279** lời gọi, 5/10
phiên chạm trần lượt. Bản hỏng đã bị loại bỏ, không đưa vào baseline.

Hai việc cần làm khi có quota trở lại, theo thứ tự:

1. **Chạy lại `--limit 10 --stratify`** để lấy `mandatory_unasked` thật. Đây là chỉ số duy nhất trong
   bản này chưa có số, và nó lại là chỉ số mang gate cứng.
2. Nâng mẫu lên 25–30 ca cho `user_led_ratio` và `repeat_question_rate` — 133 câu hỏi là đủ để thấy
   xu hướng, chưa đủ để làm ngưỡng.

Hai cải tiến công cụ đã làm sau sự cố này, để nó không lặp lại:

- tên file kết quả có **giờ-phút**, không chỉ ngày — lần chạy thứ hai đã ghi đè im lặng lên baseline
  tốt của lần thứ nhất và xoá mất nó;
- `health_warnings` in ra màn hình **và ghi vào file kết quả** khi tỉ lệ lỗi model > 5%, khi có phiên
  chạm trần lượt, hoặc khi bệnh nhân mô phỏng phải dùng câu dự phòng. Số liệu hỏng mà im lặng thì tệ
  hơn hẳn không có số liệu — nó vào baseline rồi thành mốc so sánh cho mọi thay đổi sau.

## 5. Một quan sát chưa kết luận

Khi `fact_extractor` lỗi liên tục (lần chạy hỏng), phiên **không escalate và cũng không bàn giao** —
nó tiếp tục hỏi cho tới khi harness cắt ở lượt 40. §7.3 quy định `fact_extractor` fallback qua nhiều
provider, nhưng không quy định chuyện gì xảy ra khi **mọi** provider chết. Chưa đủ dữ liệu để nói đây
là bug hay chỉ là hệ quả của trần lượt nhân tạo trong harness — cần một bài test có chủ đích với LLM
giả luôn lỗi. Ghi lại ở đây để không rơi mất.

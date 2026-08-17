# Evaluation

Thư mục này dùng để chạy evaluation cho VMedTriage sau mỗi version.

## Cấu trúc

```text
eval/
  README.md
  scripts/
    run_eval.py                  # chấm nhãn trên 2 lượt gốc của golden case
    run_conversation_eval.py     # chạy hội thoại ĐẦY ĐỦ tới khi phiên đóng
    simulated_patient.py
    record_baseline.py
  baselines/                     # số liệu mốc, có ngày trong tên file
  results/
    logging/
      <version>/
        metrics.json
        predictions.jsonl
        failures.jsonl
        report.md
```

Dataset mặc định hiện nằm ở:

```text
data/golden_cases_v1.jsonl
```

## Chạy evaluation local

Chạy trực tiếp pipeline Python, không cần bật server:

```powershell
python eval/scripts/run_eval.py
```

Nếu không truyền `--version`, runner tự tạo tên version theo thời gian local:

```text
YYYYMMDD_HHMMSS
```

Ví dụ:

```text
eval/results/logging/20260803_014512/
```

Giới hạn số case khi debug:

```powershell
python eval/scripts/run_eval.py --limit 10
```

Output được ghi vào:

```text
eval/results/logging/<version>/
```

## Chạy evaluation qua API

Bật server trước:

```powershell
uvicorn src.main:app --reload --port 8000
```

Sau đó chạy:

```powershell
python eval/scripts/run_eval.py --mode api --base-url http://localhost:8000
```

## Chạy bằng Makefile

```bash
make eval
```

Make target mặc định chạy:

```text
python eval/scripts/run_eval.py
```

## Chạy hội thoại đầy đủ (bệnh nhân mô phỏng)

`run_eval.py` phát đúng **2 lượt bệnh nhân** của mỗi golden case rồi chấm. Đủ để đo nhánh ĐỎ, nhưng
không bao giờ chạm tới lúc phiên đóng — nên mọi chỉ số về độ dài hội thoại, độ phủ khi đóng và trải
nghiệm (§12) không có dữ liệu. `run_conversation_eval.py` lấy chính golden case làm **hồ sơ** cho một
bệnh nhân mô phỏng rồi để nó trả lời tới cùng:

```powershell
python eval/scripts/run_conversation_eval.py --limit 10 --stratify
```

- `--stratify` lấy mẫu **đều theo `expected_triage`**. Gần như bắt buộc: `golden_cases_v1.jsonl` sắp
  xếp theo mức, 45 ca `emergency_now` nằm liền nhau ở đầu — lấy 10 ca đầu là chỉ đo nhánh đỏ.
- Chạy **in-process qua luồng chuẩn** (`symptom_protocol.session`), không phải `TriagePipeline`
  legacy mà `run_eval.py --mode direct` chạy. Không cần server, nhưng cũng không đo tầng HTTP/auth.
- Tốn API thật: mỗi ca ~15-20 lượt × 3 lời gọi (trích xuất + diễn đạt + bệnh nhân giả).

**Script này KHÔNG đo triage accuracy.** Nhãn golden case gắn với 2 lượt gốc; phần hội thoại sau là do
model bệnh nhân sinh ra trong khuôn khổ lời kể, nên một ca có thể diễn tiến hợp lý mà vẫn ra mức khác
nhãn. Mức triage in ra là để xem **phân bố** (có chạm được `EARLY_VISIT`/`SELF_CARE` không).

Bệnh nhân mô phỏng **không được biết nhãn** — nó chỉ nhận lời kể của chính người bệnh. Cho nó biết đáp
án thì nó sẽ lái hội thoại về phía đáp án, và bài đo hoá ra đo chính cái đáp án vừa đưa vào.

## Metrics chính

- `triage_accuracy`: tỷ lệ priority dự đoán khớp nhãn golden.
- `handoff_accuracy`: tỷ lệ chuyển Human-in-the-Loop đúng kỳ vọng.
- `red_flag_exact_match_accuracy`: tỷ lệ bộ mã red flag khớp hoàn toàn.
- `red_flag_macro_recall`: trung bình recall trên các case có expected red flag.
- `red_flag_macro_precision`: trung bình precision trên các case có actual red flag.
- `emergency_recall`: tỷ lệ case `Emergency` được phát hiện đúng.
- `latency_ms`: thời gian chạy trung bình, p95 và max.

## Mapping nhãn

Dataset dùng nhãn triage dạng workflow:

```text
emergency_now -> Emergency
same_day -> Urgent
soon_24_72h -> Routine
home_monitoring -> Self-care
insufficient_information_or_handoff -> Manual review
```

Runtime hiện dùng một số mã red flag nội bộ. Eval runner có alias để chấm với mã golden `RF-*` mà chưa cần đổi API public.

## Dùng threshold cho CI hoặc pre-release

Ví dụ fail nếu accuracy hoặc red-flag recall thấp hơn ngưỡng:

```powershell
python eval/scripts/run_eval.py `
  --fail-under-triage-accuracy 0.80 `
  --fail-under-red-flag-recall 0.80
```

Nếu cần gắn tên version thủ công, vẫn có thể truyền:

```powershell
python eval/scripts/run_eval.py --version v0.1.0
```

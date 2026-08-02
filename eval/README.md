# Evaluation

Thư mục này dùng để chạy evaluation cho VMedTriage sau mỗi version.

## Cấu trúc

```text
eval/
  README.md
  scripts/
    run_eval.py
  results/
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
eval/results/20260803_014512/
```

Giới hạn số case khi debug:

```powershell
python eval/scripts/run_eval.py --limit 10
```

Output được ghi vào:

```text
eval/results/<version>/
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

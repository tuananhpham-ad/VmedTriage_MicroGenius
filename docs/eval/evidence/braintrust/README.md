# Braintrust trace exports — retest v2 (2026-08-28)

Nguồn raw của Track B trong `docs/eval/eval-evidence-v1.0.md`. Export từ Braintrust Dataset/Experiment `retest-v2` (task = gọi `POST /api/v1/chat` thật + simulated patient chạy hết hội thoại; scorer `match` = so khớp `actual_priority` với `expected` 3 mức, exact match).

Lưu 3 file export gốc vào thư mục này:

| File | Số dòng | Case bao phủ |
|---|---|---|
| `retest-v2-1787853748.csv` | 10 | CN-* + AB-* (lần chạy 1) |
| `retest-v2-1787882862.csv` | 3 | CN-EMG-01/02, CN-EV-01 (chạy lại) |
| `retest-v2-1787883106.csv` | 16 | DD-*, KT-*, ST-* |

**Bao phủ:** 30/30 case protocol. 10 case adversarial.

**Cột dùng tới:** `output` (`actual_priority`, `status`, `turns`), `scores.match` (0/1 = FAIL/PASS), `metrics.duration` (giây, wall-clock cả hội thoại), `metadata.latency_ms`, `metadata.case_id`, `metadata.manual_run_note`.

**Lưu ý khi đọc latency:** `duration`/`latency_ms` là wall-clock end-to-end của **toàn bộ hội thoại mô phỏng** (gồm cả thời gian model bệnh nhân mô phỏng sinh câu trả lời + HTTP + xử lý hệ thống). `metrics.llm_calls = 0`, `llm_duration = null` → harness không đo tách được thời gian LLM nội bộ. Đây là **cận trên**.

Bảng tổng hợp phẳng: `docs/eval/evidence/dataset_v2.csv`.

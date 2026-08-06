# Thu muc `scripts`

Thu muc nay chua script ho tro dataset, demo query, evaluation data validation va AI usage logging hooks.

## File

| File | Lam gi |
|---|---|
| `_pyrun.cmd` | Wrapper Windows de chay Python script trong repo. |
| `_pyrun.sh` | Wrapper shell de chay Python script trong repo. |
| `demo_query.py` | Goi triage pipeline/agent tu command line voi mot message demo va in ket qua de doc. |
| `build_triage_v1_dataset.py` | Build dataset golden cases tu nguon raw/manifest, tao JSON/JSONL/report/readme cho triage data. |
| `audit_medical_dataset.py` | Audit dataset y te: hash, UTF-8 status, duplicate, source URL, thong ke CSV. |
| `gemini_turn_generator.py` | Goi Gemini de sinh follow-up turns cho case dataset, co validation va retry. |
| `validate_triage_data.py` | Validate dataset triage: red flags, flows, cases, manifest, quality report, review log. |
| `log_hook.py` | Hook tu dong ghi AI prompt/tool usage vao `.ai-log/session.jsonl`. |
| `log_antigravity.py` | Quet transcript Antigravity IDE va ghi prompt lien quan repo vao AI log. |
| `log_manual.py` | Ghi log thu cong cho ChatGPT/web tools khi khong co hook tu dong. |
| `submit_log.py` | Submit AI logs khi git push va archive/restore pending logs. |
| `setup_hooks.sh` | Cai git/AI logging hooks tren Linux/macOS/Git Bash. |
| `setup_hooks.ps1` | Cai git/AI logging hooks tren Windows PowerShell. |


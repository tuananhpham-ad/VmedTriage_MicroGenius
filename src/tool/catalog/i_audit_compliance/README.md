# Nhom I - Audit, compliance va governance

Nhom nay xu ly audit trail, redaction, policy guardrail, access control va consent logging. Day la nhom quan trong neu dua he thong gan moi truong production.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group I. |
| `tool_057_triage_audit_log_write.py` | `triage_audit_log_write` | Ghi audit event cho triage. |
| `tool_058_tool_call_audit_logger.py` | `tool_call_audit_logger` | Log tool call voi input/output/policy/latency/status. |
| `tool_059_phi_redactor.py` | `phi_redactor` | Redact PHI truoc khi gui ra ngoai hoac ghi log. |
| `tool_060_policy_guardrail_checker.py` | `policy_guardrail_checker` | Phat hien noi dung vi pham safety policy nhu chan doan/ke don/tri hoan cap cuu. |
| `tool_061_patient_visible_safety_filter.py` | `patient_visible_safety_filter` | Kiem tra response cho benh nhan ve advice nguy hiem, disclaimer, approval. |
| `tool_062_data_retention_policy_checker.py` | `data_retention_policy_checker` | Kiem tra du lieu co duoc luu va luu bao lau. |
| `tool_063_access_control_checker.py` | `access_control_checker` | Kiem tra actor co quyen truy cap resource/action hay khong. |
| `tool_064_consent_audit_logger.py` | `consent_audit_logger` | Log consent grant/refusal/revocation. |


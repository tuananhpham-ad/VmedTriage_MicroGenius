# Nhom A - Intake va conversation

Nhom nay xu ly dau vao ban dau cua benh nhan: chuan hoa tin nhan, nhan dien ngon ngu, doc/ghi hoi thoai, doc profile va kiem tra consent.

Moi file `tool_*.py` chua `TOOL_SPEC` va `execute()`. Logic xu ly that nam trong `src/tool/catalog/implementations.py`, ham `run_tool()`.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau day la package tool group A. |
| `tool_001_patient_message_normalizer.py` | `patient_message_normalizer` | Chuan hoa typo, tieng Viet khong dau, slang va whitespace trong tin nhan. |
| `tool_002_language_detector.py` | `language_detector` | Nhan dien text la tieng Viet, tieng Anh, mixed hay unknown. |
| `tool_003_medical_translation_tool.py` | `medical_translation_tool` | Dich text y te giua Viet/Anh va giu lai thuat ngu clinical quan trong. |
| `tool_004_conversation_memory_read.py` | `conversation_memory_read` | Doc lich su hoi thoai cua mot `case_id` tu local state. |
| `tool_005_conversation_memory_write.py` | `conversation_memory_write` | Ghi them mot message vao memory cua case; day la side-effect tool nen can approval khi goi qua registry policy. |
| `tool_006_patient_profile_read.py` | `patient_profile_read` | Doc thong tin ho so benh nhan gia lap: tuoi, gioi, thai ky, nguy co. |
| `tool_007_consent_checker.py` | `consent_checker` | Kiem tra consent cho viec luu/xu ly thong tin suc khoe. |


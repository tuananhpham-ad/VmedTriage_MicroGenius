# Nhom G - EHR va FHIR

Nhom nay doc/ghi du lieu lien quan EHR/FHIR. Cac tool ghi (`create`, `write`) la side-effect tool va bi registry chan neu khong co `approved=True`.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group G. |
| `tool_041_fhir_patient_context_read.py` | `fhir_patient_context_read` | Doc context gioi han cua benh nhan tu FHIR/local mock. |
| `tool_042_fhir_observation_read.py` | `fhir_observation_read` | Doc vital signs/lab observations gan day. |
| `tool_043_fhir_condition_read.py` | `fhir_condition_read` | Doc active/historical conditions. |
| `tool_044_fhir_medication_read.py` | `fhir_medication_read` | Doc medications hien tai. |
| `tool_045_fhir_allergy_read.py` | `fhir_allergy_read` | Doc allergy/intolerance records. |
| `tool_046_fhir_encounter_create.py` | `fhir_encounter_create` | Tao encounter triage trong EHR/FHIR sau approval. |
| `tool_047_fhir_task_create.py` | `fhir_task_create` | Tao FHIR Task cho nurse/clinician follow-up. |
| `tool_048_fhir_document_reference_write.py` | `fhir_document_reference_write` | Ghi handoff summary da duyet thanh FHIR DocumentReference. |


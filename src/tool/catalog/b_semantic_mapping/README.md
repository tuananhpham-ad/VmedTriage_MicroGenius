# Nhom B - Semantic mapping

Nhom nay bien van ban tu do thanh du lieu co cau truc va ma y khoa. Day la buoc giup pipeline hieu "benh nhan noi gi" theo dang field ro rang.

Moi file `tool_*.py` chua metadata va entry point. Logic local dung chung nam trong `src/tool/catalog/implementations.py`.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group B. |
| `tool_008_symptom_extraction_tool.py` | `symptom_extraction_tool` | Rut trich chief complaint, onset, severity, location, radiation va symptom lien quan. |
| `tool_009_snomed_concept_lookup.py` | `snomed_concept_lookup` | Map trieu chung sang concept SNOMED CT gia lap/local. |
| `tool_010_icd10_lookup.py` | `icd10_lookup` | Map trieu chung/condition sang ICD-10 cho reporting sau review. |
| `tool_011_loinc_lookup.py` | `loinc_lookup` | Map ten observation/lab sang LOINC. |
| `tool_012_rxnorm_lookup.py` | `rxnorm_lookup` | Chuan hoa ten thuoc sang concept RxNorm. |
| `tool_013_allergy_extraction_tool.py` | `allergy_extraction_tool` | Rut trich allergy va reaction tu text hoac EHR note. |
| `tool_014_medication_extraction_tool.py` | `medication_extraction_tool` | Rut trich thuoc dang dung, lieu va thoi diem dung. |
| `tool_015_risk_factor_extraction_tool.py` | `risk_factor_extraction_tool` | Rut trich risk factors nhu tuoi cao, thai ky, tim mach, tieu duong, suy giam mien dich. |


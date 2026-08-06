# Nhom E - Clinical knowledge va RAG

Nhom nay tim, tom tat va kiem tra tri thuc y khoa cho dieu duong/clinician. Trong MVP, nhieu ket qua la local/mock de test duoc ma khong can server ngoai.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group E. |
| `tool_029_clinical_guideline_search.py` | `clinical_guideline_search` | Tim guideline/protocol clinical da duyet. |
| `tool_030_local_protocol_retriever.py` | `local_protocol_retriever` | Lay protocol noi bo theo symptom group/site. |
| `tool_031_triage_pathway_search.py` | `triage_pathway_search` | Tim pathway triage cho chest pain, breathing, neurologic, bleeding... |
| `tool_032_drug_interaction_checker.py` | `drug_interaction_checker` | Kiem tra tuong tac thuoc. |
| `tool_033_contraindication_checker.py` | `contraindication_checker` | Kiem tra chong chi dinh dua tren allergy, pregnancy, condition, medication. |
| `tool_034_clinical_calculator_tool.py` | `clinical_calculator_tool` | Tinh score y khoa clinician-facing neu input du; test hien co kiem tra BMI/qSOFA. |
| `tool_035_medical_knowledge_summarizer.py` | `medical_knowledge_summarizer` | Tom tat guideline/protocol dai cho nurse review. |


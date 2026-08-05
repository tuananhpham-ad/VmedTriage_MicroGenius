# Thu muc `src/services`

Day la tang business logic cua VMedTriage. API va agent goi vao day de xu ly case; service khong nen phu thuoc vao UI.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.services`. |
| `triage_pipeline.py` | Orchestrator nghiep vu chinh: tao/load case, chay intake tools, map trieu chung, validate, detect red flags, de xuat priority, tao summary/queue item, luu case. |
| `semantic_mapper.py` | Mapper rule-based: nhan text tieng Viet/Anh va rut ra `StructuredSymptomData` cho cac nhom chest pain, breathing, neurologic, bleeding, general. |
| `checklist_validator.py` | Kiem tra field bat buoc theo symptom group, phat hien contradiction don gian, tao cau hoi follow-up. |
| `red_flag.py` | Ap dung `RED_FLAG_RULES` de tim dau hieu nguy hiem. |
| `triage_engine.py` | De xuat `Emergency`, `Urgent`, `Routine`, `Manual review` dua tren red flags, validation va protocol rules. |
| `summary_generator.py` | Tao `HandoffSummary` cho dieu duong tu structured data, validation, red flags va proposal. |
| `nurse_queue.py` | Tao `NurseQueueItem`, gan queue priority cao neu case Emergency. |
| `case_store.py` | In-memory store cho `TriageCase`; mat du lieu khi process restart. |
| `hitl_review.py` | Xu ly hanh dong human-in-the-loop: approve, edit, reject, escalate, ask_more. |
| `llm.py` | Chon LLM provider theo `.env`: OpenAI, DeepSeek hoac Gemini; tra ve LangChain chat model. |

## Luong can nam

`TriagePipeline.handle_patient_message()` la ham nen doc ky nhat. No gom gan nhu toan bo luong triage MVP va la noi cac service nho duoc ghep lai.


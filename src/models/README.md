# Thu muc `src/models`

Thu muc nay dinh nghia data contract dung chung. Neu muon hieu object nao di qua API, agent, service va UI, doc `schemas.py` truoc.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.models`. |
| `schemas.py` | Pydantic models/enums: role hoi thoai, trang thai case, action HITL, priority, structured symptom data, validation, red flag, proposal, summary, queue item, request/response API. |
| `protocols.py` | Khai bao `SemanticMapper` protocol de service co the nhan nhieu implementation mapper khac nhau. |

## Model quan trong

| Model | Dung de lam gi |
|---|---|
| `TriageCase` | Object trung tam cua mot case: conversation, structured data, validation, red flags, proposal, summary, queue item, status, response. |
| `ChatRequest` / `ChatResponse` | Input/output cua endpoint chat. |
| `NurseReviewRequest` / `NurseReviewResponse` | Input/output khi dieu duong review case. |
| `StructuredSymptomData` | Ket qua map tin nhan tu do sang du lieu co cau truc. |
| `TriageProposal` | De xuat muc uu tien triage, ly do, protocol id va confidence. |


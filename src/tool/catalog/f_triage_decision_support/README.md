# Nhom F - Triage decision support

Nhom nay bien du lieu da map va validate thanh de xuat triage, score queue va route cham soc. Day la clinical decision support nen mac dinh can human review.

| File | Tool | Lam gi |
|---|---|---|
| `__init__.py` | Package marker | Danh dau package tool group F. |
| `tool_036_protocol_triage_engine.py` | `protocol_triage_engine` | Match structured symptoms voi protocol rules de tao triage proposal. |
| `tool_037_cds_hooks_triage_advice.py` | `cds_hooks_triage_advice` | Lay CDS Hooks cards cho clinician-facing advice. |
| `tool_038_priority_score_calculator.py` | `priority_score_calculator` | Tinh diem uu tien queue tu red flags, risk factors, validation va wait time. |
| `tool_039_manual_review_decider.py` | `manual_review_decider` | Quyet dinh output co bat buoc human review hay khong. |
| `tool_040_care_navigation_router.py` | `care_navigation_router` | Route case toi ER, urgent review, routine appointment hoac hoi them thong tin. |


# Thu muc `tests/test_tools`

Nhom test nay kiem tra local tool catalog va policy execution.

| File | Lam gi |
|---|---|
| `__init__.py` | Danh dau package test tools. |
| `test_catalog.py` | Kiem tra discover du 82 tool theo id 1-82, moi tool co `execute()`, side-effect tool bi chan neu khong approval, orchestrator chay 6 intake tools, self-harm escalation, language detector, clinical calculator va lock khi ghi concurrent. |


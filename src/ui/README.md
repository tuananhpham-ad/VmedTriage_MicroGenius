# Thu muc `src/ui`

Thu muc nay chua frontend static theo feature. FastAPI mount thu muc `new/` tai route `/`, nen mo `http://localhost:8000/` se thay UI.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.ui`. |
| `static_files.py` | Ham `build_demo_static_app()` tra ve `StaticFiles(directory=new, html=True)` de `main.py` mount UI. |
| `new/` | HTML/CSS/JS cua giao dien dang chay, tach theo `features/auth.js`, `features/patient.js` va `features/nurse.js`. |


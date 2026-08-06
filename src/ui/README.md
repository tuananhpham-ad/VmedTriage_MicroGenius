# Thu muc `src/ui`

Thu muc nay chua demo frontend dang static files. FastAPI mount thu muc `static/` tai route `/`, nen mo `http://localhost:8000/` se thay UI.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.ui`. |
| `static_files.py` | Ham `build_demo_static_app()` tra ve `StaticFiles(directory=static, html=True)` de `main.py` mount UI. |
| `static/` | HTML/CSS/JS cua giao dien demo. |


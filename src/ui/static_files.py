from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles


def build_demo_static_app() -> StaticFiles:
    static_dir = Path(__file__).resolve().parent / "static"
    return StaticFiles(directory=static_dir, html=True)

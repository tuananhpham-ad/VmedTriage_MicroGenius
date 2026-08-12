from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles


def build_demo_static_app() -> StaticFiles:
    """Serve the feature-based VMedTriage frontend."""
    static_dir = Path(__file__).resolve().parent / "new"
    return StaticFiles(directory=static_dir, html=True)

from __future__ import annotations

from typing import Protocol

from src.models.schemas import StructuredSymptomData


class SemanticMapper(Protocol):
    async def map_message(self, message: str) -> StructuredSymptomData:
        """Convert patient free text into normalized symptom data."""

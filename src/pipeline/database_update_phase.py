from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.schemas import TriageCase
from src.pipeline.weaviate_cloud import WeaviateCloudRepository


@dataclass(slots=True)
class DatabaseUpdateResult:
    collection: str
    object_id: str | None
    stored: bool
    source: str = "weaviate_cloud"
    metadata: dict[str, Any] = field(default_factory=dict)


class DatabaseUpdatePhase:
    """Phase 1: update Weaviate Cloud when users upload documents or cases are created."""

    def __init__(self, repository: WeaviateCloudRepository | None = None) -> None:
        self.repository = repository or WeaviateCloudRepository()

    async def store_triage_case(self, triage_case: TriageCase) -> DatabaseUpdateResult:
        object_id = await asyncio.to_thread(self.repository.store_case, triage_case)
        return DatabaseUpdateResult(
            collection=self.repository.case_collection,
            object_id=object_id,
            stored=True,
            metadata={"case_id": triage_case.case_id},
        )

    async def store_triage_cases(self, triage_cases: Iterable[TriageCase]) -> list[DatabaseUpdateResult]:
        results: list[DatabaseUpdateResult] = []
        for triage_case in triage_cases:
            results.append(await self.store_triage_case(triage_case))
        return results

    async def update_from_uploaded_document(
        self,
        *,
        title: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        source: str = "uploaded_document",
        link: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DatabaseUpdateResult:
        object_id = await asyncio.to_thread(
            self.repository.store_document,
            title=title,
            content=content,
            topic=topic,
            tags=tags,
            source=source,
            link=link,
            metadata=metadata,
        )
        return DatabaseUpdateResult(
            collection=self.repository.knowledge_collection,
            object_id=object_id,
            stored=True,
            metadata={"title": title, "topic": topic or "", "link": link, "metadata": metadata or {}},
        )

    async def ensure_collections(self) -> None:
        await asyncio.to_thread(self.repository.ensure_collections)


async def _demo() -> None:
    phase = DatabaseUpdatePhase()
    try:
        await phase.ensure_collections()
        print("Weaviate collections are ready.")
    except RuntimeError as exc:
        print(str(exc))


if __name__ == "__main__":
    asyncio.run(_demo())

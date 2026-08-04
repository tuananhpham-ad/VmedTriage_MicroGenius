from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.models.schemas import TriageCase
from src.pipeline.repository import WeaviateCloudRepository


@dataclass(slots=True)
class IngestionResult:
    collection: str
    object_id: str | None
    stored: bool
    source: str = "weaviate_cloud"
    metadata: dict[str, Any] = field(default_factory=dict)


class IngestingPipeline:
    """Pipeline for pushing triage and knowledge data into Weaviate Cloud."""

    def __init__(self, repository: WeaviateCloudRepository | None = None) -> None:
        self.repository = repository or WeaviateCloudRepository()

    async def ingest_triage_case(self, triage_case: TriageCase) -> IngestionResult:
        object_id = await asyncio.to_thread(self.repository.store_case, triage_case)
        return IngestionResult(
            collection=self.repository.case_collection,
            object_id=object_id,
            stored=True,
            metadata={"case_id": triage_case.case_id},
        )

    async def ingest_triage_cases(self, triage_cases: Iterable[TriageCase]) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        for triage_case in triage_cases:
            results.append(await self.ingest_triage_case(triage_case))
        return results

    async def ingest_knowledge_document(
        self,
        *,
        title: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        source: str = "ingesting_pipeline",
    ) -> IngestionResult:
        object_id = await asyncio.to_thread(
            self.repository.store_document,
            title=title,
            content=content,
            topic=topic,
            tags=tags,
            source=source,
        )
        return IngestionResult(
            collection=self.repository.knowledge_collection,
            object_id=object_id,
            stored=True,
            metadata={"title": title, "topic": topic or ""},
        )

    async def ensure_collections(self) -> None:
        await asyncio.to_thread(self.repository.ensure_collections)


async def _demo() -> None:
    pipeline = IngestingPipeline()
    try:
        await pipeline.ensure_collections()
        print("Weaviate collections are ready.")
    except RuntimeError as exc:
        print(str(exc))


if __name__ == "__main__":
    asyncio.run(_demo())

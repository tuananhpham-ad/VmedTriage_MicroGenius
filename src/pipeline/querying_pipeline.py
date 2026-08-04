from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from src.pipeline.repository import WeaviateCloudRepository, WeaviateSearchHit

SearchMode = Literal["bm25", "semantic"]
QueryScope = Literal["cases", "knowledge"]
SearchHit = WeaviateSearchHit


@dataclass(slots=True)
class QueryResult:
    query: str
    collection: str
    mode: SearchMode
    hits: list[WeaviateSearchHit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryingPipeline:
    """Pipeline for querying case and knowledge data from Weaviate Cloud."""

    def __init__(self, repository: WeaviateCloudRepository | None = None) -> None:
        self.repository = repository or WeaviateCloudRepository()

    async def query(
        self,
        query: str,
        *,
        scope: QueryScope = "knowledge",
        limit: int | None = None,
        mode: SearchMode = "bm25",
    ) -> QueryResult:
        collection = (
            self.repository.case_collection if scope == "cases" else self.repository.knowledge_collection
        )
        hits = await asyncio.to_thread(
            self.repository.search,
            collection_name=collection,
            query=query,
            limit=limit,
            mode=mode,
        )
        return QueryResult(query=query, collection=collection, mode=mode, hits=hits)

    async def find_case(self, case_id: str) -> QueryResult:
        hits = await asyncio.to_thread(self.repository.find_case_by_id, case_id)
        return QueryResult(
            query=case_id,
            collection=self.repository.case_collection,
            mode="bm25",
            hits=hits,
            metadata={"case_id": case_id},
        )

    async def ensure_collections(self) -> None:
        await asyncio.to_thread(self.repository.ensure_collections)


async def _demo() -> None:
    pipeline = QueryingPipeline()
    try:
        result = await pipeline.query("đau ngực", scope="knowledge", limit=3)
        print(
            {
                "collection": result.collection,
                "mode": result.mode,
                "hits": [hit.properties for hit in result.hits],
            }
        )
    except RuntimeError as exc:
        print(str(exc))


if __name__ == "__main__":
    asyncio.run(_demo())

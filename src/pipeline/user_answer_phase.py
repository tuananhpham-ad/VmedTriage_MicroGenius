from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.weaviate_cloud import WeaviateCloudRepository, WeaviateSearchHit
from src.services.llm import get_llm

SearchMode = Literal["bm25", "semantic", "hybrid"]
QueryScope = Literal["cases", "knowledge"]
SearchHit = WeaviateSearchHit


@dataclass(slots=True)
class UserAnswerResult:
    query: str
    collection: str
    mode: SearchMode
    answer: str
    hits: list[WeaviateSearchHit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class UserAnswerPhase:
    """Phase 2: retrieve data from Weaviate Cloud, rerank it, and answer with an LLM."""

    def __init__(self, repository: WeaviateCloudRepository | None = None) -> None:
        self.repository = repository or WeaviateCloudRepository()

    async def answer_user(
        self,
        query: str,
        *,
        scope: QueryScope = "knowledge",
        limit: int | None = None,
        mode: SearchMode = "hybrid",
        alpha: float = 0.5,
        use_llm: bool = True,
    ) -> UserAnswerResult:
        collection = self.repository.case_collection if scope == "cases" else self.repository.knowledge_collection
        hits = await asyncio.to_thread(
            self.repository.search,
            collection_name=collection,
            query=query,
            limit=limit,
            mode=mode,
            alpha=alpha,
            rerank=True,
        )
        context = self._build_context(hits)
        prompt = self._build_prompt(query, context)
        answer = await asyncio.to_thread(self._generate_answer, prompt) if use_llm else self._build_answer(query, hits)

        return UserAnswerResult(
            query=query,
            collection=collection,
            mode=mode,
            answer=answer,
            hits=hits,
            metadata={
                "alpha": alpha,
                "embedding_model": "bkai-foundation-models/vietnamese-bi-encoder",
                "reranker_model": "AITeamVN/Vietnamese_Reranker",
                "context": context,
                "llm_prompt": prompt,
            },
        )

    async def find_case(self, case_id: str) -> UserAnswerResult:
        hits = await asyncio.to_thread(self.repository.find_case_by_id, case_id)
        return UserAnswerResult(
            query=case_id,
            collection=self.repository.case_collection,
            mode="bm25",
            answer=self._build_answer(case_id, hits),
            hits=hits,
            metadata={"case_id": case_id},
        )

    async def ensure_collections(self) -> None:
        await asyncio.to_thread(self.repository.ensure_collections)

    def _build_answer(self, query: str, hits: list[WeaviateSearchHit]) -> str:
        if not hits:
            return "Chua tim thay du lieu phu hop trong Weaviate Cloud."

        snippets = []
        for hit in hits[:3]:
            title = hit.properties.get("title") or hit.properties.get("case_id") or "Ket qua"
            content = hit.properties.get("content") or hit.properties.get("summary") or hit.properties.get("response") or ""
            snippets.append(f"- {title}: {str(content)[:300]}")

        return "Tim thay du lieu lien quan cho truy van: " + query + "\n" + "\n".join(snippets)

    def _build_context(self, hits: list[WeaviateSearchHit]) -> str:
        if not hits:
            return ""

        blocks = []
        for index, hit in enumerate(hits, start=1):
            props = hit.properties
            blocks.append(
                "\n".join(
                    [
                        f"[{index}] title: {props.get('title') or props.get('case_id') or 'unknown'}",
                        f"link: {props.get('link') or ''}",
                        f"metadata: {props.get('metadata') or props.get('tags') or ''}",
                        f"source: {props.get('source') or ''}",
                        f"context: {props.get('context') or props.get('content') or props.get('summary') or ''}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""Ban la tro ly truy van tri thuc y te.
Chi dung CONTEXT ben duoi de tra loi. Neu context khong du, noi ro la chua du du lieu.
Tra loi bang tieng Viet, ngan gon, co trich dan nguon theo dang [1], [2] khi phu hop.

QUERY:
{query}

CONTEXT:
{context}
"""

    def _generate_answer(self, prompt: str) -> str:
        llm = get_llm()
        response = llm.invoke(prompt)
        return str(getattr(response, "content", response))


async def _demo() -> None:
    phase = UserAnswerPhase()
    try:
        result = await phase.answer_user("dau nguc", scope="knowledge", limit=3)
        print(
            {
                "collection": result.collection,
                "mode": result.mode,
                "answer": result.answer,
                "hits": [hit.properties for hit in result.hits],
            }
        )
    except RuntimeError as exc:
        print(str(exc))


if __name__ == "__main__":
    asyncio.run(_demo())

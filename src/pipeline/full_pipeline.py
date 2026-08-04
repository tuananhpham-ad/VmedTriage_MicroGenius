from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.pipeline.database_update_phase import DatabaseUpdatePhase, DatabaseUpdateResult
from src.pipeline.sample_data import SAMPLE_QUERY, SAMPLE_UPLOADED_DOCUMENTS
from src.pipeline.user_answer_phase import UserAnswerPhase, UserAnswerResult
from src.pipeline.weaviate_cloud import WeaviateCloudRepository


@dataclass(slots=True)
class FullPipelineRunResult:
    database_updates: list[DatabaseUpdateResult] = field(default_factory=list)
    query_result: UserAnswerResult | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class FullPipeline:
    """Run all pipeline phases: upload/update database, then answer a user query."""

    def __init__(self, repository: WeaviateCloudRepository | None = None) -> None:
        self.repository = repository or WeaviateCloudRepository()
        self.database_update_phase = DatabaseUpdatePhase(self.repository)
        self.user_answer_phase = UserAnswerPhase(self.repository)

    async def run(
        self,
        *,
        documents: list[dict[str, Any]] | None = None,
        query: str = SAMPLE_QUERY,
        dry_run: bool = False,
    ) -> FullPipelineRunResult:
        documents = documents or SAMPLE_UPLOADED_DOCUMENTS

        if dry_run or not self.repository.configured:
            return FullPipelineRunResult(
                dry_run=True,
                metadata={
                    "reason": "Weaviate Cloud is not configured." if not self.repository.configured else "Dry run requested.",
                    "required_env": [
                        "WVC_URL",
                        "WVC_API_KEY",
                        "one of OPENAI_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY",
                    ],
                    "sample_documents": documents,
                    "sample_query": query,
                },
            )

        try:
            await self.database_update_phase.ensure_collections()
            updates = []
            for document in documents:
                updates.append(
                    await self.database_update_phase.update_from_uploaded_document(
                        title=str(document["title"]),
                        content=str(document["content"]),
                        topic=str(document.get("topic") or ""),
                        tags=list(document.get("tags") or []),
                        source=str(document.get("source") or "sample_upload"),
                        link=str(document.get("link") or ""),
                        metadata=dict(document.get("metadata") or {}),
                    )
                )

            query_result = await self.user_answer_phase.answer_user(
                query,
                scope="knowledge",
                limit=4,
                mode="hybrid",
                alpha=0.5,
                use_llm=True,
            )
        except Exception as exc:
            return FullPipelineRunResult(
                dry_run=True,
                metadata={
                    "reason": str(exc),
                    "required_env": [
                        "WEAVIATE_URL",
                        "WEAVIATE_API_KEY",
                        "one of OPENAI_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY",
                    ],
                    "sample_documents": documents,
                    "sample_query": query,
                },
            )

        return FullPipelineRunResult(
            database_updates=updates,
            query_result=query_result,
            metadata={
                "uploaded_documents": len(updates),
                "query": query,
                "knowledge_collection": self.repository.knowledge_collection,
            },
        )


async def run_full_pipeline(*, dry_run: bool = False, query: str = SAMPLE_QUERY) -> FullPipelineRunResult:
    return await FullPipeline().run(dry_run=dry_run, query=query)


def _sep(title: str) -> None:
    print("-" * 80)
    print(title)
    print("-" * 80)


def _print_result(result: FullPipelineRunResult) -> None:
    if result.dry_run:
        _sep("DRY RUN")
        print(result.metadata["reason"])
        print("Required env:", ", ".join(result.metadata["required_env"]))
        print()
        print("Sample documents that would be uploaded:")
        for index, document in enumerate(result.metadata["sample_documents"], start=1):
            print(f"{index}. {document['title']} [{document.get('topic', '')}]")
        print()
        print("Sample query:")
        print(result.metadata["sample_query"])
        return

    _sep("STAGE 1 - DATABASE UPDATE / UPLOAD")
    for update in result.database_updates:
        print(
            {
                "collection": update.collection,
                "object_id": update.object_id,
                "stored": update.stored,
                "metadata": update.metadata,
            }
        )

    _sep("STAGE 2 - HYBRID RETRIEVAL")
    if result.query_result is None:
        print("No query result.")
        return
    print("Query:", result.query_result.query)
    print("Collection:", result.query_result.collection)
    print("Mode:", result.query_result.mode)
    print("Alpha:", result.query_result.metadata.get("alpha"))
    print("Embedding:", result.query_result.metadata.get("embedding_model"))
    for index, hit in enumerate(result.query_result.hits, start=1):
        props = hit.properties
        print()
        print(f"Hit {index}")
        print("uuid:", hit.uuid)
        print("hybrid_score:", hit.score)
        print("title:", props.get("title") or props.get("case_id") or "")
        print("link:", props.get("link") or "")
        print("metadata:", props.get("metadata") or props.get("tags") or "")
        print("source:", props.get("source") or "")
        print("context:", str(props.get("context") or props.get("content") or "")[:1000])

    _sep("STAGE 3 - RERANK")
    print("Reranker:", result.query_result.metadata.get("reranker_model"))
    for index, hit in enumerate(result.query_result.hits, start=1):
        props = hit.properties
        print(
            {
                "rank": index,
                "rerank_score": hit.rerank_score,
                "hybrid_score": hit.score,
                "title": props.get("title") or props.get("case_id") or "",
                "link": props.get("link") or "",
            }
        )

    _sep("STAGE 4 - CONTEXT SENT TO LLM")
    print(result.query_result.metadata.get("context") or "")

    _sep("STAGE 5 - LLM PROMPT")
    print(result.query_result.metadata.get("llm_prompt") or "")

    _sep("STAGE 6 - RESPONSE")
    print(result.query_result.answer)


async def _main() -> None:
    _configure_console_output()
    parser = argparse.ArgumentParser(description="Run real Weaviate hybrid retrieval, rerank, and LLM answer pipeline.")
    parser.add_argument("--query", default=None, help="Query to run after sample documents are uploaded.")
    parser.add_argument("--dry-run", action="store_true", help="Show sample payloads without calling Weaviate Cloud.")
    args = parser.parse_args()

    query = _resolve_query(args.query, dry_run=args.dry_run)

    result = await run_full_pipeline(dry_run=args.dry_run, query=query)
    _print_result(result)


def _resolve_query(query: str | None, *, dry_run: bool = False) -> str:
    if query:
        return query
    if dry_run:
        return SAMPLE_QUERY
    try:
        return input("Nhap query: ").strip() or SAMPLE_QUERY
    except EOFError:
        return SAMPLE_QUERY


def _configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(_main())

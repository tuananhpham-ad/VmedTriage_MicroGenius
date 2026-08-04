from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import get_settings
from src.models.schemas import TriageCase

try:  # Optional at import time so the project still loads before dependency install.
    import weaviate
    from weaviate.classes.config import Configure, DataType, Property
    from weaviate.classes.init import Auth
    from weaviate.classes.query import Filter
except Exception:  # pragma: no cover - exercised only when dependency is missing.
    weaviate = None
    Configure = DataType = Property = Auth = Filter = None

try:  # Optional because tests and non-RAG app paths should not need local ML models.
    import numpy as np
    from sentence_transformers import CrossEncoder, SentenceTransformer
    from underthesea import word_tokenize
except Exception:  # pragma: no cover - exercised only when dependency is missing.
    np = SentenceTransformer = CrossEncoder = word_tokenize = None


EMBEDDING_MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
RERANKER_MODEL_NAME = "AITeamVN/Vietnamese_Reranker"

_embedding_model: Any | None = None
_reranker_model: Any | None = None


@dataclass(slots=True)
class WeaviateSearchHit:
    uuid: str | None
    collection: str
    properties: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    rerank_score: float | None = None


class WeaviateCloudRepository:
    """Weaviate Cloud adapter shared by the database-update and answer phases."""

    def __init__(
        self,
        cluster_url: str | None = None,
        api_key: str | None = None,
        case_collection: str | None = None,
        knowledge_collection: str | None = None,
    ) -> None:
        settings = get_settings()
        self.cluster_url = cluster_url or settings.weaviate_url
        self.api_key = api_key or settings.weaviate_api_key
        self.case_collection = case_collection or settings.weaviate_cases_collection
        self.knowledge_collection = knowledge_collection or settings.weaviate_knowledge_collection
        self.query_limit = settings.weaviate_query_limit

    @property
    def configured(self) -> bool:
        return bool(self.cluster_url and self.api_key)

    def connect(self):
        if weaviate is None:
            raise RuntimeError(
                "weaviate-client is not installed. Install requirements and set WEAVIATE_URL/WEAVIATE_API_KEY."
            )
        if not self.configured:
            raise RuntimeError("WEAVIATE_URL and WEAVIATE_API_KEY must be configured for Weaviate Cloud.")

        return weaviate.connect_to_weaviate_cloud(
            cluster_url=self.cluster_url,
            auth_credentials=Auth.api_key(self.api_key),
            skip_init_checks=True,
        )

    def ensure_collections(self) -> None:
        client = self.connect()
        try:
            self._ensure_collection(client, self.case_collection, self._case_properties())
            self._ensure_collection(client, self.knowledge_collection, self._knowledge_properties())
        finally:
            client.close()

    def store_case(self, triage_case: TriageCase) -> str:
        client = self.connect()
        try:
            self._ensure_collection(client, self.case_collection, self._case_properties())
            collection = client.collections.use(self.case_collection)
            return str(collection.data.insert(self._case_payload(triage_case)))
        finally:
            client.close()

    def store_document(
        self,
        *,
        title: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        source: str = "database_update_phase",
        link: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        client = self.connect()
        try:
            self._ensure_collection(client, self.knowledge_collection, self._knowledge_properties())
            collection = client.collections.use(self.knowledge_collection)
            document_id = _new_id("doc")
            object_ids = []
            chunks = _chunk_text(content)
            for index, chunk in enumerate(chunks, start=1):
                payload = {
                    "document_id": document_id,
                    "chunk_id": f"{document_id}-chunk-{index}",
                    "title": title,
                    "content": chunk,
                    "context": chunk,
                    "topic": topic or "",
                    "tags": _json_dumps(tags or []),
                    "metadata": _json_dumps(metadata or {}),
                    "link": link,
                    "source": source,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                object_ids.append(str(collection.data.insert(properties=payload, vector=_embed(chunk))))
            return object_ids[0]
        finally:
            client.close()

    def search(
        self,
        *,
        collection_name: str,
        query: str,
        limit: int | None = None,
        mode: str = "hybrid",
        alpha: float = 0.5,
        rerank: bool = True,
    ) -> list[WeaviateSearchHit]:
        client = self.connect()
        try:
            self._ensure_collection(
                client,
                collection_name,
                self._knowledge_properties() if collection_name == self.knowledge_collection else self._case_properties(),
            )
            collection = client.collections.use(collection_name)
            limit = limit or self.query_limit
            objects = self._search_collection(collection, query=query, limit=limit, mode=mode, alpha=alpha)
            hits = [
                WeaviateSearchHit(
                    uuid=str(item.uuid) if item.uuid else None,
                    collection=collection_name,
                    properties=dict(item.properties),
                    score=_metadata_score(item),
                )
                for item in objects
            ]
            return _rerank_hits(query, hits, limit) if rerank else hits[:limit]
        finally:
            client.close()

    def find_case_by_id(self, case_id: str) -> list[WeaviateSearchHit]:
        client = self.connect()
        try:
            self._ensure_collection(client, self.case_collection, self._case_properties())
            collection = client.collections.use(self.case_collection)
            response = collection.query.fetch_objects(
                filters=Filter.by_property("case_id").equal(case_id),
                limit=self.query_limit,
            )
            return [
                WeaviateSearchHit(
                    uuid=str(item.uuid) if item.uuid else None,
                    collection=self.case_collection,
                    properties=dict(item.properties),
                )
                for item in response.objects
            ]
        finally:
            client.close()

    def _search_collection(self, collection, *, query: str, limit: int, mode: str, alpha: float):
        query_segmented = _segment(query)
        if mode == "semantic":
            try:
                response = collection.query.near_vector(
                    near_vector=_embed(query_segmented),
                    limit=limit,
                    return_metadata=["distance", "score"],
                )
                return response.objects
            except Exception:
                pass
        if mode == "hybrid":
            response = collection.query.hybrid(
                query=query_segmented,
                vector=_embed(query_segmented),
                alpha=alpha,
                limit=limit * 2,
                return_metadata=["score"],
            )
            return _dedupe_objects(response.objects, limit)
        response = collection.query.bm25(query=query_segmented, limit=limit, return_metadata=["score"])
        return response.objects

    def _ensure_collection(self, client, name: str, properties: list[Property]) -> None:
        try:
            collection = client.collections.get(name)
            self._ensure_properties(collection, properties)
        except Exception:
            if name == self.knowledge_collection:
                client.collections.create(
                    name,
                    properties=properties,
                    vectorizer_config=Configure.Vectorizer.none(),
                )
            else:
                client.collections.create(name, properties=properties)

    def _ensure_properties(self, collection: Any, properties: list[Property]) -> None:
        try:
            existing = {prop.name for prop in collection.config.get().properties}
            for prop in properties:
                if prop.name not in existing:
                    collection.config.add_property(prop)
        except Exception:
            return

    def _case_properties(self) -> list[Property]:
        return [
            Property(name="case_id", data_type=DataType.TEXT),
            Property(name="patient_message", data_type=DataType.TEXT),
            Property(name="conversation", data_type=DataType.TEXT),
            Property(name="status", data_type=DataType.TEXT),
            Property(name="priority", data_type=DataType.TEXT),
            Property(name="response", data_type=DataType.TEXT),
            Property(name="summary", data_type=DataType.TEXT),
            Property(name="structured_data", data_type=DataType.TEXT),
            Property(name="validation", data_type=DataType.TEXT),
            Property(name="red_flags", data_type=DataType.TEXT),
            Property(name="triage_proposal", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="created_at", data_type=DataType.TEXT),
            Property(name="updated_at", data_type=DataType.TEXT),
        ]

    def _knowledge_properties(self) -> list[Property]:
        return [
            Property(name="document_id", data_type=DataType.TEXT),
            Property(name="chunk_id", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="context", data_type=DataType.TEXT),
            Property(name="topic", data_type=DataType.TEXT),
            Property(name="tags", data_type=DataType.TEXT),
            Property(name="metadata", data_type=DataType.TEXT),
            Property(name="link", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="created_at", data_type=DataType.TEXT),
            Property(name="updated_at", data_type=DataType.TEXT),
        ]

    def _case_payload(self, triage_case: TriageCase) -> dict[str, Any]:
        conversation = [message.model_dump() for message in triage_case.conversation]
        latest_message = conversation[-1]["content"] if conversation else ""
        proposal = triage_case.triage_proposal.model_dump() if triage_case.triage_proposal else {}
        summary = triage_case.summary.model_dump() if triage_case.summary else {}
        validation = triage_case.validation.model_dump() if triage_case.validation else {}
        structured = triage_case.structured_data.model_dump() if triage_case.structured_data else {}

        return {
            "case_id": triage_case.case_id,
            "patient_message": latest_message,
            "conversation": _json_dumps(conversation),
            "status": _enum_value(triage_case.status),
            "priority": _enum_value(triage_case.triage_proposal.priority) if triage_case.triage_proposal else "",
            "response": triage_case.patient_visible_response or "",
            "summary": _json_dumps(summary),
            "structured_data": _json_dumps(structured),
            "validation": _json_dumps(validation),
            "red_flags": _json_dumps([item.model_dump() for item in triage_case.red_flags]),
            "triage_proposal": _json_dumps(proposal),
            "source": "triage_pipeline",
            "created_at": _now(),
            "updated_at": _now(),
        }


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _json_dumps(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}-{uuid4()}"


def _segment(text: str) -> str:
    if word_tokenize is None:
        raise RuntimeError("underthesea is not installed. Install requirements before running retrieval.")
    return word_tokenize(text, format="text")


def _embedding() -> Any:
    global _embedding_model
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers is not installed. Install requirements before running retrieval.")
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def _embed(text: str) -> list[float]:
    return _embedding().encode(text).tolist()


def _reranker() -> Any:
    global _reranker_model
    if CrossEncoder is None:
        raise RuntimeError("sentence-transformers is not installed. Install requirements before running rerank.")
    if _reranker_model is None:
        _reranker_model = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker_model


def _rerank_hits(query: str, hits: list[WeaviateSearchHit], limit: int) -> list[WeaviateSearchHit]:
    if not hits:
        return []
    passages = [str(hit.properties.get("context") or hit.properties.get("content") or "") for hit in hits]
    scores = np.asarray(_reranker().predict([(query, passage) for passage in passages]))
    ranked_indices = np.argsort(scores)[::-1][:limit]
    ranked_hits = []
    for index in ranked_indices:
        hit = hits[int(index)]
        hit.rerank_score = float(scores[int(index)])
        ranked_hits.append(hit)
    return ranked_hits


def _metadata_score(item: Any) -> float | None:
    metadata = getattr(item, "metadata", None)
    if metadata is None:
        return None
    score = getattr(metadata, "score", None)
    if score is None:
        score = getattr(metadata, "distance", None)
    return float(score) if score is not None else None


def _dedupe_objects(objects: list[Any], limit: int) -> list[Any]:
    seen = set()
    results = []
    for item in objects:
        properties = dict(item.properties)
        text = str(properties.get("context") or properties.get("content") or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(item)
        if len(results) == limit:
            break
    return results


def _chunk_text(content: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [part.strip() for part in content.splitlines() if part.strip()]
    if not paragraphs:
        paragraphs = [content.strip()]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(paragraph[start : start + max_chars] for start in range(0, len(paragraph), max_chars))
            continue
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks or [content]

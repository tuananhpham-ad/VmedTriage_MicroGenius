from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.config import get_settings
from src.models.schemas import TriageCase

try:  # Optional at import time so the project still loads before dependency install.
    import weaviate
    from weaviate.classes.config import DataType, Property
    from weaviate.classes.init import Auth
    from weaviate.classes.query import Filter
except Exception:  # pragma: no cover - exercised only when dependency is missing.
    weaviate = None
    DataType = Property = Auth = Filter = None


@dataclass(slots=True)
class WeaviateSearchHit:
    uuid: str | None
    collection: str
    properties: dict[str, Any] = field(default_factory=dict)


class WeaviateCloudRepository:
    """Small Weaviate Cloud adapter for persistence and retrieval."""

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
        source: str = "ingesting_pipeline",
    ) -> str:
        client = self.connect()
        try:
            self._ensure_collection(client, self.knowledge_collection, self._knowledge_properties())
            collection = client.collections.use(self.knowledge_collection)
            payload = {
                "document_id": _new_id("doc"),
                "title": title,
                "content": content,
                "topic": topic or "",
                "tags": _json_dumps(tags or []),
                "source": source,
                "created_at": _now(),
                "updated_at": _now(),
            }
            return str(collection.data.insert(payload))
        finally:
            client.close()

    def search(
        self,
        *,
        collection_name: str,
        query: str,
        limit: int | None = None,
        mode: str = "bm25",
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
            objects = self._search_collection(collection, query=query, limit=limit, mode=mode)
            return [WeaviateSearchHit(uuid=str(item.uuid) if item.uuid else None, collection=collection_name, properties=dict(item.properties)) for item in objects]
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

    def _search_collection(self, collection, *, query: str, limit: int, mode: str):
        if mode == "semantic":
            try:
                response = collection.query.near_text(query=query, limit=limit)
                return response.objects
            except Exception:
                pass
        response = collection.query.bm25(query=query, limit=limit)
        return response.objects

    def _ensure_collection(self, client, name: str, properties: list[Property]) -> None:
        try:
            client.collections.get(name)
        except Exception:
            client.collections.create(name, properties=properties)

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
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="topic", data_type=DataType.TEXT),
            Property(name="tags", data_type=DataType.TEXT),
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

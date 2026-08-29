import pytest

from app.services.assistant_vector_memory_service import (
    AssistantVectorMemoryService,
)


def test_vector_memory_returns_most_similar_context_first():
    memory = AssistantVectorMemoryService(dimensions=128)
    memory.remember(
        "update product decision documentation",
        {"file": "project_brain/ROADMAP.md"},
    )
    memory.remember(
        "fix stock executor retry handling",
        {"file": "app/services/assistant_stock_executor_service.py"},
    )

    result = memory.search(
        "product decision documentation update",
        limit=1,
    )

    assert result["error"] is False
    assert result["count"] == 1
    assert result["results"][0]["payload"]["file"] == (
        "project_brain/ROADMAP.md"
    )
    assert result["results"][0]["similarity"] > 0


def test_vector_memory_supports_injected_embedding_service():
    class FakeEmbeddingService:
        vectors = {
            "sales report": [1.0, 0.0],
            "stock report": [0.0, 1.0],
            "sales analytics": [0.9, 0.1],
        }

        def embed(self, text):
            return self.vectors[text]

    memory = AssistantVectorMemoryService(
        embedding_service=FakeEmbeddingService(),
    )
    memory.remember("sales report", {"kind": "sales"})
    memory.remember("stock report", {"kind": "stock"})

    result = memory.search("sales analytics")

    assert result["results"][0]["payload"]["kind"] == "sales"
    assert result["results"][0]["similarity"] > (
        result["results"][1]["similarity"]
    )


def test_vector_memory_respects_limit_and_similarity_threshold():
    memory = AssistantVectorMemoryService(dimensions=128)
    memory.remember("documentation roadmap update", {"id": 1})
    memory.remember("documentation changelog update", {"id": 2})
    memory.remember("unrelated stock calculation", {"id": 3})

    result = memory.search(
        "documentation update",
        limit=2,
        min_similarity=0.1,
    )

    assert result["count"] == 2
    assert [item["payload"]["id"] for item in result["results"]] == [1, 2]
    assert all(item["similarity"] >= 0.1 for item in result["results"])


def test_vector_memory_does_not_expose_mutable_internal_payload():
    memory = AssistantVectorMemoryService()
    original_payload = {"files": ["ROADMAP.md"]}
    memory.remember("roadmap", original_payload)

    original_payload["files"].append("CHANGELOG.md")
    first = memory.search("roadmap")["results"][0]
    first["payload"]["files"].append("DECISIONS.md")
    second = memory.search("roadmap")["results"][0]

    assert second["payload"]["files"] == ["ROADMAP.md"]


def test_vector_memory_rejects_embedding_dimension_mismatch():
    class VariableEmbeddingService:
        def embed(self, text):
            if text == "first":
                return [1.0, 0.0]
            return [1.0, 0.0, 0.0]

    memory = AssistantVectorMemoryService(
        embedding_service=VariableEmbeddingService(),
    )
    memory.remember("first")

    with pytest.raises(ValueError, match="embedding dimensions must match"):
        memory.search("second")


def test_vector_memory_clear_removes_all_items():
    memory = AssistantVectorMemoryService()
    memory.remember("one")
    memory.remember("two")

    cleared = memory.clear()
    result = memory.search("one")

    assert cleared == {"error": False, "cleared": True}
    assert result == {"error": False, "results": [], "count": 0}

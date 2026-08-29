import hashlib
import math
import re
from copy import deepcopy


class AssistantVectorMemoryService:
    """Dependency-free vector memory for Development Autopilot context lookup.

    The default embedder is deterministic and local. A richer embedding provider can
    be injected later through the same ``embed(text)`` contract without changing
    the memory/search API.
    """

    def __init__(
        self,
        embedding_service=None,
        dimensions=64,
    ):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")

        self.embedding_service = embedding_service
        self.dimensions = dimensions
        self.items = []

    def remember(self, text, payload=None):
        normalized_text = self._normalize_text(text)
        vector = self._embed(normalized_text)

        item = {
            "text": normalized_text,
            "payload": deepcopy(payload or {}),
            "vector": vector,
        }

        self.items.append(item)

        return {
            "error": False,
            "memory": self._public_item(item),
            "count": len(self.items),
        }

    def search(
        self,
        query,
        limit=5,
        min_similarity=0.0,
    ):
        if limit <= 0:
            return {
                "error": False,
                "results": [],
                "count": 0,
            }

        query_text = self._normalize_text(query)
        query_vector = self._embed(query_text)
        scored = []

        for index, item in enumerate(self.items):
            similarity = self._cosine_similarity(
                query_vector,
                item["vector"],
            )

            if similarity < min_similarity:
                continue

            result = self._public_item(item)
            result["similarity"] = similarity
            result["_index"] = index
            scored.append(result)

        scored.sort(
            key=lambda item: (
                -item["similarity"],
                item["_index"],
            )
        )

        results = scored[:limit]

        for item in results:
            item.pop("_index", None)

        return {
            "error": False,
            "results": results,
            "count": len(results),
        }

    def clear(self):
        self.items = []

        return {
            "error": False,
            "cleared": True,
        }

    def _embed(self, text):
        if self.embedding_service is not None:
            vector = self.embedding_service.embed(text)
            return self._normalize_vector(vector)

        vector = [0.0] * self.dimensions

        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        return self._normalize_vector(vector)

    def _normalize_text(self, text):
        if text is None:
            return ""

        return str(text).strip()

    def _tokenize(self, text):
        return re.findall(
            r"[\w-]+",
            text.lower(),
            flags=re.UNICODE,
        )

    def _normalize_vector(self, vector):
        values = [float(value) for value in vector]
        magnitude = math.sqrt(
            sum(value * value for value in values)
        )

        if magnitude == 0:
            return values

        return [value / magnitude for value in values]

    def _cosine_similarity(self, left, right):
        if len(left) != len(right):
            raise ValueError("embedding dimensions must match")

        return sum(
            left_value * right_value
            for left_value, right_value in zip(left, right)
        )

    def _public_item(self, item):
        return {
            "text": item["text"],
            "payload": deepcopy(item["payload"]),
        }

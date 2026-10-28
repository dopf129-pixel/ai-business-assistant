"""Durable immutable snapshots of same-SKU unit-price comparisons."""

from copy import deepcopy
from hashlib import sha256
import json


class UnitPriceComparisonHistoryService:
    """Persist comparison rankings and label changes without recalculating history."""

    def __init__(self, *, repository, planning_service, observation_ranking_service):
        self.repository = repository
        self.planning_service = planning_service
        self.observation_ranking_service = observation_ranking_service

    def create_for_observation(self, observation_id, *, owner_id, store_id, now=None):
        ranked = self._rank(observation_id, owner_id, store_id, now)
        if ranked.get("error") is True:
            return ranked
        payload = self._snapshot_payload(ranked)
        if payload is None:
            return self._error("UNIT_PRICE_COMPARISON_SNAPSHOT_INVALID")
        key = self._idempotency_key("create", payload)
        saved = self.repository.create_unit_price_comparison(
            payload, idempotency_key=key, owner_id=owner_id, store_id=store_id,
        )
        if saved.get("error") is True:
            return saved
        return self.get(
            saved["comparison_id"], revision=saved["revision"],
            owner_id=owner_id, store_id=store_id,
        )

    def refresh(self, comparison_id, *, expected_revision, owner_id, store_id, now=None):
        current = self.repository.get_unit_price_comparison(
            comparison_id, revision=expected_revision,
            owner_id=owner_id, store_id=store_id,
        )
        if current.get("error") is True:
            return current
        observation_id = (current["payload"].get("source_references") or [{}])[0].get(
            "observation_id"
        )
        if not isinstance(observation_id, str):
            return self._error("PLANNING_COMPARISON_CORRUPT")
        ranked = self._rank(observation_id, owner_id, store_id, now)
        if ranked.get("error") is True:
            return ranked
        payload = self._snapshot_payload(ranked)
        if payload is None:
            return self._error("UNIT_PRICE_COMPARISON_SNAPSHOT_INVALID")
        if payload == current["payload"]:
            return {
                **current, "error": False, "refresh_status": "NO_NEW_EVIDENCE",
                "latest_revision": current["latest_revision"],
            }
        saved = self.repository.append_unit_price_comparison_revision(
            comparison_id, payload, expected_revision=expected_revision,
            idempotency_key=self._idempotency_key(
                f"refresh-{expected_revision}", payload,
            ),
            owner_id=owner_id, store_id=store_id,
        )
        if saved.get("error") is True:
            return saved
        result = self.get(
            comparison_id, revision=saved["revision"],
            owner_id=owner_id, store_id=store_id,
        )
        result["refresh_status"] = "NEW_EVIDENCE_SAVED"
        return result

    def get(self, comparison_id, *, revision=None, owner_id, store_id):
        stored = self.repository.get_unit_price_comparison(
            comparison_id, revision=revision, owner_id=owner_id, store_id=store_id,
        )
        if stored.get("error") is True:
            return stored
        stale = self._sources_stale(
            stored["payload"], owner_id=owner_id, store_id=store_id,
        )
        if stored["superseded"] and stale:
            label = "SUPERSEDED_AND_STALE"
        elif stored["superseded"]:
            label = "SUPERSEDED"
        elif stale:
            label = "STALE"
        else:
            label = "CURRENT"
        return {
            **stored, "freshness_status": label,
            "historical_ranking_unchanged": True,
            "source_reads": False,
        }

    def list(self, *, limit=10, offset=0, owner_id, store_id):
        result = self.repository.list_unit_price_comparisons(
            limit=limit, offset=offset, owner_id=owner_id, store_id=store_id,
        )
        if result.get("error") is True:
            return result
        items = []
        for item in result["items"]:
            opened = self.get(
                item["comparison_id"], revision=item["revision"],
                owner_id=owner_id, store_id=store_id,
            )
            if opened.get("error") is True:
                return opened
            items.append(opened)
        return {**result, "items": items, "source_reads": False}

    def export_json(self, comparison_id, *, revision=None, owner_id, store_id):
        """Export only a persisted snapshot; no collection or recalculation occurs."""
        opened = self.get(
            comparison_id, revision=revision, owner_id=owner_id, store_id=store_id,
        )
        if opened.get("error") is True:
            return opened
        payload = opened["payload"]
        export = {
            "schema_version": 1,
            "comparison_revision": opened["revision"],
            "latest_revision": opened["latest_revision"],
            "freshness_status": opened["freshness_status"],
            "identity": deepcopy(payload["identity"]),
            "ranking": deepcopy(payload["ranking"]),
            "source_versions": [{
                "observation_result_revision": item["result_revision"],
                "saved_plan_revision": item["source_document_revision"],
            } for item in payload["source_references"]],
        }
        try:
            encoded = json.dumps(
                export, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return self._error("UNIT_PRICE_COMPARISON_EXPORT_FAILED")
        return {"error": False, "content": encoded, "mime_type": "application/json",
                "source_reads": False}

    def _rank(self, observation_id, owner_id, store_id, now):
        return self.observation_ranking_service.rank_for_observation(
            observation_id, owner_id=owner_id, store_id=store_id, now=now,
        )

    @staticmethod
    def _snapshot_payload(ranked):
        identity = ranked.get("identity")
        ranking = ranked.get("ranking")
        references = ranked.get("source_references")
        if (ranked.get("error") is True or not isinstance(identity, dict)
                or not isinstance(ranking, dict) or not isinstance(references, list)):
            return None
        return {
            "schema_version": 1,
            "identity": deepcopy(identity),
            "ranking": deepcopy(ranking),
            "source_references": deepcopy(references),
            "known_source_references": deepcopy(ranked.get("known_source_references")),
        }

    def _sources_stale(self, payload, *, owner_id, store_id):
        for reference in payload.get("source_references", []):
            loaded = self.repository.get_unit_price_observation(
                reference["observation_id"], owner_id=owner_id, store_id=store_id,
            )
            if loaded.get("error") is True:
                return True
            observation = loaded.get("observation") or {}
            if (observation.get("store_id") != store_id
                    or observation.get("status") == "ARCHIVED"
                    or observation.get("result_revision") != reference["result_revision"]
                    or observation.get("source_plan") != {
                        "document_id": reference["source_document_id"],
                        "revision": reference["source_document_revision"],
                    }):
                return True
            plan = self.planning_service.repository.get_document(
                reference["source_document_id"], owner_id=owner_id, store_id=store_id,
            )
            if (not isinstance(plan, dict) or plan.get("error") is True
                    or (plan.get("document") or {}).get("revision")
                    != reference["source_document_revision"]):
                return True
        known = {
            item["observation_id"]: item["result_revision"]
            for item in payload.get("known_source_references", [])
        }
        identity = payload.get("identity") or {}
        offset = 0
        page_size = 10
        for _ in range(self.repository.MAX_UNIT_PRICE_OBSERVATIONS_PER_STORE // page_size):
            page = self.repository.list_unit_price_observations(
                include_archived=False, limit=page_size, offset=offset,
                owner_id=owner_id, store_id=store_id,
            )
            if not isinstance(page, dict) or page.get("error") is True:
                return True
            for observation in page.get("items", []):
                current_identity = observation.get("identity") or {}
                if not all(current_identity.get(key) == identity.get(key) for key in (
                    "product_id", "offer_id", "sku", "sale_schema",
                )):
                    continue
                observation_id = observation.get("observation_id")
                result_revision = observation.get("result_revision")
                if (type(result_revision) is int and result_revision > 0
                        and known.get(observation_id) != result_revision):
                    return True
            if page.get("has_more") is not True:
                break
            next_offset = page.get("next_offset")
            if type(next_offset) is not int or next_offset <= offset:
                return True
            offset = next_offset
        else:
            return True
        return False

    @staticmethod
    def _idempotency_key(operation, payload):
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return "upo-" + operation[:18] + "-" + sha256(encoded).hexdigest()[:48]

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "source_reads": False}

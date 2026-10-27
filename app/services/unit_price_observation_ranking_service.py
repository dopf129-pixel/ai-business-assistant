"""Read saved same-SKU observations and rank them without refreshing sources."""

from hashlib import sha256
import json

from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter


class UnitPriceObservationRankingService:
    """Build Q21-approved candidates from immutable, tenant-scoped records."""

    PAGE_SIZE = 10
    MAX_OBSERVATIONS_PER_STORE = 100

    def __init__(self, *, repository, planning_service, ranking_service):
        self.repository = repository
        self.planning_service = planning_service
        self.ranking_service = ranking_service

    def rank_for_observation(self, observation_id, *, owner_id, store_id, now=None):
        selected = self.repository.get_unit_price_observation(
            observation_id, owner_id=owner_id, store_id=store_id,
        )
        if not isinstance(selected, dict) or selected.get("error") is True:
            return self._error(selected.get("code") if isinstance(selected, dict) else None)
        selected_observation = selected.get("observation") or {}
        target_identity = selected_observation.get("identity")
        if (selected_observation.get("store_id") != store_id
                or selected_observation.get("observation_id") != observation_id
                or not isinstance(target_identity, dict)):
            return self._error("PLANNING_OBSERVATION_NOT_FOUND")

        listed = self._list_observations(owner_id, store_id)
        if listed.get("error") is True:
            return listed
        same_sku = [
            item for item in listed["items"]
            if item.get("store_id") == store_id
            and self._same_identity(item.get("identity"), target_identity)
            and type(item.get("result_revision")) is int
            and item["result_revision"] > 0
        ]
        evaluated = []
        for item in same_sku:
            loaded = self.repository.get_unit_price_observation(
                item.get("observation_id"), owner_id=owner_id, store_id=store_id,
            )
            if not isinstance(loaded, dict) or loaded.get("error") is True:
                return self._error(loaded.get("code") if isinstance(loaded, dict) else None)
            observation = loaded.get("observation") or {}
            result_record = loaded.get("result") or {}
            result = result_record.get("payload")
            if (observation.get("observation_id") != item.get("observation_id")
                    or observation.get("store_id") != store_id
                    or not self._same_identity(observation.get("identity"), target_identity)
                    or not isinstance(result, dict)):
                continue
            evaluated.append({
                "result": result,
                "result_revision": result_record.get("revision"),
                "created_at": result_record.get("created_at") or observation.get("updated_at") or "",
                "assumption_signature": self._assumption_signature(
                    observation, owner_id=owner_id, store_id=store_id,
                ),
            })

        # Repeated collections at one price are history, not price variants.
        newest_by_price = {}
        for candidate in evaluated:
            cents = candidate["result"].get("seller_price_cents")
            if type(cents) is not int or cents < 1:
                continue
            current = newest_by_price.get(cents)
            if current is None or self._saved_recency_key(candidate) > self._saved_recency_key(current):
                newest_by_price[cents] = candidate
        distinct = list(newest_by_price.values())
        distinct.sort(key=self._window_recency_key, reverse=True)
        max_candidates = self.ranking_service.quality_service.MAX_CANDIDATES
        omitted = max(0, len(distinct) - max_candidates)
        checked = distinct[:max_candidates]
        checked.sort(key=self._chronology_key)
        candidates = [{
            "index": index,
            "result_revision": item["result_revision"],
            "result": item["result"],
            "assumption_signature": item["assumption_signature"],
            "owner_id": owner_id, "store_id": store_id,
        } for index, item in enumerate(checked)]
        ranking = self.ranking_service.rank_observations(candidates, now=now)
        if not isinstance(ranking, dict) or ranking.get("error") is True:
            return self._error(ranking.get("code") if isinstance(ranking, dict) else None)
        ranking["omitted_candidate_count"] = omitted
        ranking["omitted_repeated_price_count"] = max(0, len(evaluated) - len(distinct))
        return {
            "error": False, "ranking": ranking,
            "identity": {"sku": target_identity.get("sku"), "sale_schema": target_identity.get("sale_schema")},
            "read_only": True, "executed": False,
        }

    def _list_observations(self, owner_id, store_id):
        items = []
        offset = 0
        page_count = self.MAX_OBSERVATIONS_PER_STORE // self.PAGE_SIZE
        for _ in range(page_count):
            page = self.repository.list_unit_price_observations(
                limit=self.PAGE_SIZE, offset=offset,
                owner_id=owner_id, store_id=store_id,
            )
            if not isinstance(page, dict) or page.get("error") is True:
                return self._error(page.get("code") if isinstance(page, dict) else None)
            page_items = page.get("items")
            if not isinstance(page_items, list):
                return self._error("PLANNING_OBSERVATION_LIST_INVALID")
            items.extend(page_items)
            if page.get("has_more") is not True:
                return {"error": False, "items": items}
            next_offset = page.get("next_offset")
            if type(next_offset) is not int or next_offset <= offset:
                return self._error("PLANNING_OBSERVATION_LIST_INVALID")
            offset = next_offset
        return self._error("UNIT_PRICE_RANKING_OBSERVATION_LIMIT_EXCEEDED")

    def _assumption_signature(self, observation, *, owner_id, store_id):
        source_plan = observation.get("source_plan") or {}
        document_id = source_plan.get("document_id")
        revision = source_plan.get("revision")
        if not isinstance(document_id, str) or type(revision) is not int or revision < 1:
            return None
        loaded = self.planning_service.get_document(document_id, revision=revision)
        if not isinstance(loaded, dict) or loaded.get("error") is True:
            return None
        document = loaded.get("document") or {}
        if (document.get("document_id") != document_id
                or document.get("revision") != revision
                or document.get("owner_id") != owner_id
                or document.get("store_id") != store_id):
            return None
        payload = document.get("payload") or {}
        items = payload.get("items")
        if not isinstance(items, list):
            return None
        matching = [
            item for item in items
            if isinstance(item, dict) and self._same_plan_identity(
                item.get("identity"), observation, store_id,
            )
        ]
        if len(matching) != 1:
            return None
        item = matching[0]
        inputs, _ = PlanningCrossDockingAdapter.restore_item(payload, item)
        sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
        if not isinstance(inputs, dict):
            return None
        snapshot = sources.get("tariff_resolution")
        profiles = snapshot.get("profiles") if isinstance(snapshot, dict) else None
        has_frozen_tariff = isinstance(profiles, list) and bool(profiles)
        assumption_inputs = {
            key: value for key, value in inputs.items()
            if key not in {"price", "advertising_rate"}
            and not (key == "commission_rate" and has_frozen_tariff)
        }
        material = {
            "version": 1,
            "inputs": assumption_inputs,
            "tariff_profiles": profiles if has_frozen_tariff else None,
            "commission_rate_without_range_profile": (
                None if has_frozen_tariff else inputs.get("commission_rate")
            ),
        }
        try:
            encoded = json.dumps(
                material, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return None
        return sha256(encoded).hexdigest()

    @staticmethod
    def _same_identity(left, right):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        return all(
            str(left.get(key) or "").strip() == str(right.get(key) or "").strip()
            for key in ("product_id", "offer_id", "sku", "sale_schema")
        )

    @classmethod
    def _same_plan_identity(cls, identity, observation, store_id):
        expected = observation.get("identity") if isinstance(observation, dict) else {}
        return (
            isinstance(identity, dict)
            and str(identity.get("store_id") or "") == str(store_id or "")
            and all(
                str(identity.get(key) or "").strip() == str(expected.get(key) or "").strip()
                for key in ("product_id", "offer_id", "sku")
            )
            and str(identity.get("scheme") or "").upper()
                == str(expected.get("sale_schema") or "").upper()
        )

    @staticmethod
    def _saved_recency_key(candidate):
        return str(candidate.get("created_at") or "")

    @staticmethod
    def _window_recency_key(candidate):
        result = candidate.get("result") or {}
        window = result.get("window") or {}
        return (
            str(window.get("to") or ""), str(window.get("from") or ""),
            str(candidate.get("created_at") or ""),
        )

    @staticmethod
    def _chronology_key(candidate):
        result = candidate.get("result") or {}
        window = result.get("window") or {}
        return (
            str(window.get("from") or ""), str(window.get("to") or ""),
            str(candidate.get("created_at") or ""),
        )

    @staticmethod
    def _error(code):
        return {
            "error": True, "code": str(code or "UNIT_PRICE_RANKING_UNAVAILABLE"),
            "read_only": True, "executed": False,
        }

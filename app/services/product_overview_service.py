"""Read-only product overview projections backed by scoped transient snapshots."""

import hashlib
import json
from collections import OrderedDict
from datetime import datetime, timezone
from math import isfinite
from secrets import token_hex
from threading import RLock
from time import monotonic

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class ProductOverviewService:
    SNAPSHOT_KIND = "product_overview"
    MAX_SELECTION = 20
    DEFAULT_PAGE_SIZE = 5
    MAX_PAGE_SIZE = 20
    MAX_VIEW_TOKENS = 64
    MAX_PRICE_PLAN_ITEMS = 10
    MAX_PRICE_PLAN_SCOPES = 64
    VIEW_TOKEN_TTL_SECONDS = 600

    _METRIC_UNITS = {
        "sales_velocity": "units_per_day",
        "sales_trend": "trend",
        "current_stock": "units",
        "days_of_stock": "days",
        "stock_priority": "priority",
        "decision_profit_per_unit": "RUB_per_unit",
        "decision_margin_percent": "percent",
    }
    FILTERS = {
        "all_selected",
        "existing_priority",
        "negative_unit_profit",
        "low_margin_decision",
        "stock_without_sales",
        "incomplete_or_stale",
    }
    SORT_FIELDS = {
        "priority",
        "sales_velocity",
        "current_stock",
        "days_of_stock",
        "decision_profit_per_unit",
        "decision_margin_percent",
    }
    PRIORITY_ORDER = {
        "CRITICAL": 0,
        "HIGH": 1,
        "NORMAL": 2,
        "LOW": 3,
        "NONE": 4,
    }
    _SOURCE_FIELDS = {
        "sales": (
            "sales_observed_at",
            "sales_source_recorded_at",
            "sales_period_from",
            "sales_period_to",
        ),
        "stock": (
            "stock_observed_at",
            "stock_source_recorded_at",
        ),
        "unit_economics": (
            "unit_economics_observed_at",
            "unit_economics_source_recorded_at",
        ),
    }
    _ROW_STATUSES = {
        "READY",
        "INCOMPLETE",
        "SOURCE_UNAVAILABLE",
        "NOT_FOUND",
        "IDENTITY_AMBIGUOUS",
        "BUDGET_EXHAUSTED",
        "CANCELLED",
    }

    def __init__(
        self,
        decision_query,
        snapshot_store,
        tenant_scope_provider=None,
        utc_now=None,
        clock=None,
    ):
        self.decision_query = decision_query
        self.snapshot_store = snapshot_store
        self.tenant_scope_provider = (
            tenant_scope_provider or get_current_tenant_user_id
        )
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.clock = clock or monotonic
        self._view_tokens = OrderedDict()
        self._plan_actions = OrderedDict()
        self._price_plan_selections = OrderedDict()
        self._token_lock = RLock()

    def create_snapshot(
        self,
        selectors,
        page=1,
        page_size=None,
        filter_by="all_selected",
        sort_by="priority",
        direction=None,
    ):
        page_size = self.DEFAULT_PAGE_SIZE if page_size is None else page_size
        validation_error = self._validate_request(
            selectors, page, page_size, filter_by, sort_by, direction
        )
        if validation_error:
            return self._error(validation_error)

        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)

        generation_result = self.snapshot_store.begin_generation(
            owner_id,
            store_id,
            self.SNAPSHOT_KIND,
        )
        if generation_result.get("error"):
            return self._error(generation_result.get("code"))
        generation = generation_result.get("generation")

        try:
            result = self.decision_query.query_selected_products(selectors)
        except Exception:
            return self._error("PRODUCT_OVERVIEW_SOURCE_UNAVAILABLE")
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(
                (result or {}).get("code")
                if isinstance(result, dict)
                else "PRODUCT_OVERVIEW_SOURCE_RESULT_INVALID"
            )
        raw_rows = result.get("rows")
        if not isinstance(raw_rows, list):
            return self._error("PRODUCT_OVERVIEW_SOURCE_RESULT_INVALID")

        return self._persist_query_result(
            result,
            owner_id,
            store_id,
            generation,
            page,
            page_size,
            filter_by,
            sort_by,
            direction,
        )

    def create_catalog_group_snapshot(
        self,
        offset=0,
        limit=20,
        page=1,
        page_size=None,
        filter_by="all_selected",
        sort_by="priority",
        direction=None,
    ):
        page_size = self.DEFAULT_PAGE_SIZE if page_size is None else page_size
        validation_error = self._validate_request_options(
            page, page_size, filter_by, sort_by, direction
        )
        if validation_error:
            return self._error(validation_error)
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= self.MAX_SELECTION
        ):
            return self._error("PRODUCT_OVERVIEW_CATALOG_GROUP_INVALID")

        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        generation_result = self.snapshot_store.begin_generation(
            owner_id,
            store_id,
            self.SNAPSHOT_KIND,
        )
        if generation_result.get("error"):
            return self._error(generation_result.get("code"))
        try:
            result = self.decision_query.query_catalog_group(
                offset=offset,
                limit=limit,
            )
        except Exception:
            return self._error("PRODUCT_OVERVIEW_SOURCE_UNAVAILABLE")
        if not isinstance(result, dict) or result.get("error") is True:
            return self._error(
                (result or {}).get("code")
                if isinstance(result, dict)
                else "PRODUCT_OVERVIEW_SOURCE_RESULT_INVALID"
            )
        return self._persist_query_result(
            result,
            owner_id,
            store_id,
            generation_result.get("generation"),
            page,
            page_size,
            filter_by,
            sort_by,
            direction,
        )

    def _persist_query_result(
        self,
        result,
        owner_id,
        store_id,
        generation,
        page,
        page_size,
        filter_by,
        sort_by,
        direction,
    ):
        raw_rows = result.get("rows")
        if not isinstance(raw_rows, list):
            return self._error("PRODUCT_OVERVIEW_SOURCE_RESULT_INVALID")
        captured_at = self._captured_at()
        rows, duplicate_identity_count = self._project_rows(
            raw_rows,
            owner_id=owner_id,
            store_id=store_id,
            captured_at=captured_at,
        )
        coverage = self._coverage(rows, duplicate_identity_count)
        selection_scope = result.get("selection_scope")
        if isinstance(selection_scope, dict):
            coverage["selection_scope"] = {
                key: value
                for key, value in selection_scope.items()
                if key in {
                    "mode",
                    "sort_by",
                    "selected_count",
                    "catalog_identity_count",
                    "offset",
                    "has_previous_group",
                    "has_next_group",
                    "limit",
                }
            }
        source_freshness = self._source_freshness(rows, captured_at)
        stored = self.snapshot_store.put_snapshot(
            owner_id=owner_id,
            store_id=store_id,
            kind=self.SNAPSHOT_KIND,
            generation=generation,
            version=1,
            source_freshness=source_freshness,
            coverage=coverage,
            rows=rows,
        )
        if stored.get("error"):
            return self._error(stored.get("code"))
        result = self._page_result(
            stored["snapshot"], page, page_size, filter_by, sort_by, direction
        )
        if result.get("error") is not True:
            token = self._register_view(stored["snapshot"])
            if token is None:
                return self._error("PRODUCT_OVERVIEW_VIEW_TOKEN_UNAVAILABLE")
            result["snapshot"]["view_token"] = token
        return result

    def get_page_by_token(
        self,
        token,
        page=1,
        page_size=None,
        filter_by="all_selected",
        sort_by="priority",
        direction=None,
    ):
        view = self._load_view(token)
        if view.get("error"):
            return view
        result = self.get_page(
            snapshot_id=view["snapshot_id"],
            generation=view["generation"],
            version=view["version"],
            page=page,
            page_size=page_size,
            filter_by=filter_by,
            sort_by=sort_by,
            direction=direction,
        )
        if result.get("code") in {
            "TRANSIENT_SNAPSHOT_STALE",
            "TRANSIENT_SNAPSHOT_EXPIRED",
            "TRANSIENT_SNAPSHOT_GENERATION_STALE",
        }:
            return self._error("PRODUCT_OVERVIEW_VIEW_STALE")
        if result.get("error") is False:
            result["snapshot"]["view_token"] = str(token)
        return result

    def get_export_snapshot_by_token(
        self, token, filter_by="all_selected", sort_by="priority", direction=None
    ):
        """Return every filtered row in the exact stored overview snapshot."""
        return self.get_page_by_token(
            token,
            page=1,
            page_size=self.MAX_SELECTION,
            filter_by=filter_by,
            sort_by=sort_by,
            direction=direction,
        )

    def get_row_by_token(self, token, row_id):
        if not isinstance(row_id, str) or not row_id:
            return self._error("PRODUCT_OVERVIEW_ROW_INVALID")
        result = self.get_page_by_token(
            token,
            page=1,
            page_size=self.MAX_SELECTION,
        )
        if result.get("error"):
            return result
        row = next(
            (row for row in result["rows"] if row.get("row_id") == row_id),
            None,
        )
        if row is None:
            return self._error("PRODUCT_OVERVIEW_ROW_STALE")
        return {"error": False, "row": row, "read_only": True, "executed": False}

    def refresh_by_token(self, token, **options):
        view = self._load_view(token)
        if view.get("error"):
            return view
        loaded = self.snapshot_store.get_snapshot(
            snapshot_id=view["snapshot_id"],
            owner_id=view["owner_id"],
            store_id=view["store_id"],
            kind=self.SNAPSHOT_KIND,
            generation=view["generation"],
            version=view["version"],
        )
        if loaded.get("error"):
            return self._error(loaded.get("code"))
        snapshot = loaded["snapshot"]
        group = (snapshot.get("coverage") or {}).get("selection_scope") or {}
        if group.get("mode") == "FIRST_SORTED_CATALOG_GROUP":
            return self.create_catalog_group_snapshot(
                offset=group.get("offset", 0),
                limit=group.get("limit", self.MAX_SELECTION),
                **options,
            )
        selectors = [row["selector"] for row in snapshot.get("rows") or [] if row.get("selector")]
        return self.create_snapshot(selectors, **options)

    def next_catalog_group(self, token, direction=1, **options):
        options.pop("limit", None)
        if direction not in (-1, 1):
            return self._error("PRODUCT_OVERVIEW_CATALOG_GROUP_INVALID")
        view = self._load_view(token)
        if view.get("error"):
            return view
        loaded = self.snapshot_store.get_snapshot(
            snapshot_id=view["snapshot_id"],
            owner_id=view["owner_id"],
            store_id=view["store_id"],
            kind=self.SNAPSHOT_KIND,
            generation=view["generation"],
            version=view["version"],
        )
        if loaded.get("error"):
            return self._error(loaded.get("code"))
        group = (loaded["snapshot"].get("coverage") or {}).get("selection_scope") or {}
        if group.get("mode") != "FIRST_SORTED_CATALOG_GROUP":
            return self._error("PRODUCT_OVERVIEW_CATALOG_GROUP_UNAVAILABLE")
        offset = group.get("offset", 0) + direction * group.get("limit", self.MAX_SELECTION)
        if offset < 0 or (direction > 0 and not group.get("has_next_group")):
            return self._error("PRODUCT_OVERVIEW_CATALOG_GROUP_OUT_OF_RANGE")
        if direction < 0 and not group.get("has_previous_group"):
            return self._error("PRODUCT_OVERVIEW_CATALOG_GROUP_OUT_OF_RANGE")
        return self.create_catalog_group_snapshot(
            offset=offset,
            limit=group.get("limit", self.MAX_SELECTION),
            **options,
        )

    def add_row_to_price_plan(self, token, row_id):
        resolved = self.get_row_by_token(token, row_id)
        if resolved.get("error"):
            return resolved
        row = resolved["row"]
        identity = row.get("identity") or {}
        if not identity.get("catalog_sku"):
            return self._error("PRODUCT_OVERVIEW_EXACT_CATALOG_ID_REQUIRED")
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        key = (owner_id, store_id)
        now = self.clock()
        item_key = tuple(identity.get(field) for field in (
            "product_id", "offer_id", "catalog_sku"
        ))
        with self._token_lock:
            current = self._price_plan_selections.get(key)
            if not isinstance(current, dict) or now - current.get("created_at", 0) > self.VIEW_TOKEN_TTL_SECONDS:
                current = {"created_at": now, "items": []}
            else:
                self._price_plan_selections.move_to_end(key)
            items = list(current["items"])
            if any(item.get("identity_key") == item_key for item in items):
                return {
                    "error": False,
                    "code": "PRODUCT_OVERVIEW_PLAN_ITEM_ALREADY_SELECTED",
                    "selected_count": len(items),
                    "row": row,
                    "read_only": True,
                    "executed": False,
                }
            if len(items) >= self.MAX_PRICE_PLAN_ITEMS:
                return self._error("PRODUCT_OVERVIEW_PLAN_SELECTION_LIMIT_EXCEEDED")
            items.append({"identity": identity, "identity_key": item_key})
            self._price_plan_selections[key] = {
                "created_at": now,
                "items": items,
            }
            self._price_plan_selections.move_to_end(key)
            while len(self._price_plan_selections) > self.MAX_PRICE_PLAN_SCOPES:
                self._price_plan_selections.popitem(last=False)
        return {
            "error": False,
            "code": None,
            "selected_count": len(items),
            "row": row,
            "read_only": True,
            "executed": False,
        }

    def get_price_plan_selection(self):
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        key = (owner_id, store_id)
        with self._token_lock:
            current = self._price_plan_selections.get(key)
            if not isinstance(current, dict):
                items = []
            elif self.clock() - current.get("created_at", 0) > self.VIEW_TOKEN_TTL_SECONDS:
                self._price_plan_selections.pop(key, None)
                items = []
            else:
                self._price_plan_selections.move_to_end(key)
                items = current.get("items", [])
            return {
                "error": False,
                "items": [{"identity": dict(item["identity"])} for item in items],
                "selected_count": len(items),
                "read_only": True,
                "executed": False,
            }

    def register_price_plan_action(
        self, view_token, row_id, callback, expected_scenario
    ):
        resolved = self.get_row_by_token(view_token, row_id)
        if resolved.get("error"):
            return resolved
        if not isinstance(callback, str) or len(callback.encode("utf-8")) > 64:
            return self._error("PRODUCT_OVERVIEW_ACTION_INVALID")
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        with self._token_lock:
            action_token = self._unique_token_locked(self._plan_actions)
            self._plan_actions[action_token] = {
                "owner_id": owner_id,
                "store_id": store_id,
                "view_token": view_token,
                "row_id": row_id,
                "callback": callback,
                "expected_scenario": expected_scenario,
                "created_at": self.clock(),
            }
            self._plan_actions.move_to_end(action_token)
            while len(self._plan_actions) > self.MAX_VIEW_TOKENS:
                self._plan_actions.popitem(last=False)
        return {
            "error": False,
            "callback": "pov:x:" + action_token,
            "row": resolved["row"],
            "read_only": True,
            "executed": False,
        }

    def consume_price_plan_action(self, action_token):
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        with self._token_lock:
            action = self._plan_actions.pop(str(action_token or ""), None)
        if (
            not isinstance(action, dict)
            or action.get("owner_id") != owner_id
            or action.get("store_id") != store_id
            or self.clock() - action.get("created_at", 0) > self.VIEW_TOKEN_TTL_SECONDS
        ):
            return self._error("PRODUCT_OVERVIEW_ACTION_STALE")
        resolved = self.get_row_by_token(action["view_token"], action["row_id"])
        if resolved.get("error"):
            return self._error("PRODUCT_OVERVIEW_ACTION_STALE")
        return {
            "error": False,
            "callback": action["callback"],
            "expected_scenario": action.get("expected_scenario"),
            "row": resolved["row"],
            "read_only": True,
            "executed": False,
        }

    def _register_view(self, snapshot):
        owner_id = str(snapshot.get("owner_id") or "")
        store_id = str(snapshot.get("store_id") or "")
        if not owner_id or not store_id:
            return None
        with self._token_lock:
            token = self._unique_token_locked(self._view_tokens)
            self._view_tokens[token] = {
                "owner_id": owner_id,
                "store_id": store_id,
                "snapshot_id": snapshot.get("snapshot_id"),
                "generation": snapshot.get("generation"),
                "version": snapshot.get("version"),
                "created_at": self.clock(),
            }
            self._view_tokens.move_to_end(token)
            while len(self._view_tokens) > self.MAX_VIEW_TOKENS:
                self._view_tokens.popitem(last=False)
        return token

    @staticmethod
    def _unique_token_locked(entries):
        token = token_hex(4)
        while token in entries:
            token = token_hex(4)
        return token

    def _load_view(self, token):
        if not isinstance(token, str) or len(token) != 8 or any(
            char not in "0123456789abcdef" for char in token
        ):
            return self._error("PRODUCT_OVERVIEW_VIEW_STALE")
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        with self._token_lock:
            view = self._view_tokens.get(token)
            if isinstance(view, dict):
                view = dict(view)
                if self.clock() - view.get("created_at", 0) > self.VIEW_TOKEN_TTL_SECONDS:
                    self._view_tokens.pop(token, None)
                    view = None
                else:
                    self._view_tokens.move_to_end(token)
        if (
            not isinstance(view, dict)
            or view.get("owner_id") != owner_id
            or view.get("store_id") != store_id
        ):
            return self._error("PRODUCT_OVERVIEW_VIEW_STALE")
        return {"error": False, **view}

    def get_page(
        self,
        snapshot_id,
        generation,
        version,
        page=1,
        page_size=None,
        filter_by="all_selected",
        sort_by="priority",
        direction=None,
    ):
        page_size = self.DEFAULT_PAGE_SIZE if page_size is None else page_size
        validation_error = self._validate_request_options(
            page, page_size, filter_by, sort_by, direction
        )
        if validation_error:
            return self._error(validation_error)
        owner_id, store_id, scope_error = self._active_scope()
        if scope_error:
            return self._error(scope_error)
        loaded = self.snapshot_store.get_snapshot(
            snapshot_id=snapshot_id,
            owner_id=owner_id,
            store_id=store_id,
            kind=self.SNAPSHOT_KIND,
            generation=generation,
            version=version,
        )
        if loaded.get("error"):
            return self._error(loaded.get("code"))
        return self._page_result(
            loaded["snapshot"], page, page_size, filter_by, sort_by, direction
        )

    def _project_rows(self, raw_rows, owner_id, store_id, captured_at):
        rows = []
        seen_row_ids = set()
        duplicate_identity_count = 0
        for raw in raw_rows[: self.MAX_SELECTION]:
            if not isinstance(raw, dict):
                continue
            identity = self._safe_identity(raw.get("identity"))
            selector = self._safe_text(raw.get("selector"), limit=128)
            status = self._safe_status(raw.get("status"))
            code = self._safe_code(raw.get("code"))
            decision = raw.get("decision")
            if status in {"READY", "INCOMPLETE"} and (
                identity is None or not isinstance(decision, dict)
            ):
                status = "SOURCE_UNAVAILABLE"
                code = "PRODUCT_OVERVIEW_ROW_INVALID"
                decision = None
            row_id = self._stable_row_id(
                owner_id,
                store_id,
                identity,
                selector,
                status,
            )
            if row_id in seen_row_ids:
                duplicate_identity_count += 1
                continue
            seen_row_ids.add(row_id)

            row = {
                "row_id": row_id,
                "selector": selector,
                "identity": identity,
                "status": status,
                "decision": self._project_decision(decision),
                "metrics": self._project_metrics(decision),
                "source_freshness": self._project_sources(
                    decision,
                    captured_at,
                ),
                "missing_data": self._safe_string_list(
                    decision.get("missing_data")
                    if isinstance(decision, dict)
                    else None
                ) + (["identity"] if code == "PRODUCT_OVERVIEW_ROW_INVALID" else []),
                "error": code,
            }
            candidate_count = raw.get("candidate_count")
            if type(candidate_count) is int and candidate_count > 0:
                row["candidate_count"] = candidate_count
            rows.append(row)
        return rows, duplicate_identity_count

    def _project_sources(self, decision, captured_at):
        decision = decision if isinstance(decision, dict) else {}
        sources = {}
        for source_name, fields in self._SOURCE_FIELDS.items():
            source = {}
            for field in fields:
                value = self._safe_text(decision.get(field), limit=80)
                if value is not None:
                    source[field] = value
            observed_field = source_name + "_observed_at"
            recorded_field = source_name + "_source_recorded_at"
            observed_at = source.get(observed_field)
            recorded_at = source.get(recorded_field)
            if observed_at:
                source["freshness_status"] = "OBSERVED"
                source["age_seconds"] = self._age_seconds(
                    observed_at,
                    captured_at,
                )
            elif recorded_at:
                source["freshness_status"] = "SOURCE_TIMESTAMP_ONLY"
                source["age_seconds"] = None
            else:
                source["freshness_status"] = "UNKNOWN"
                source["age_seconds"] = None
            sources[source_name] = source
        cache = decision.get("unit_economics_cache")
        if isinstance(cache, dict):
            cache_status = self._safe_text(cache.get("status"), limit=16)
            if cache_status in {"hit", "miss", "stale"}:
                sources["unit_economics"].update({
                    "cache_status": cache_status,
                    "cache_stale": cache_status == "stale",
                    "cache_age_seconds": self._safe_non_negative_number(
                        cache.get("age_seconds")
                    ),
                    "cache_ttl_seconds": self._safe_non_negative_number(
                        cache.get("ttl_seconds")
                    ),
                })
        return sources

    def _project_metrics(self, decision):
        decision = decision if isinstance(decision, dict) else {}
        metrics = {}
        for name, unit in self._METRIC_UNITS.items():
            value = decision.get(name)
            if name in {"sales_trend", "stock_priority"}:
                value = self._safe_text(value, limit=32)
            else:
                value = self._safe_number(value)
            metrics[name] = {"value": value, "unit": unit}
        return metrics

    def _project_decision(self, decision):
        if not isinstance(decision, dict):
            return None
        reasons = self._safe_string_list(decision.get("reasons"), limit=64)
        return {
            "decision_type": self._safe_code(decision.get("decision_type")),
            "priority": self._safe_code(decision.get("priority")),
            "confidence": self._safe_code(decision.get("confidence")),
            "reasons": reasons,
        }

    def _source_freshness(self, rows, captured_at):
        source_summary = {}
        for source_name in self._SOURCE_FIELDS:
            observed = 0
            timestamp_missing = 0
            latest_observed = None
            for row in rows:
                source = row["source_freshness"].get(source_name) or {}
                observed_at = source.get(source_name + "_observed_at")
                if observed_at:
                    observed += 1
                    if latest_observed is None or observed_at > latest_observed:
                        latest_observed = observed_at
                else:
                    timestamp_missing += 1
            source_summary[source_name] = {
                "observed_count": observed,
                "timestamp_missing_count": timestamp_missing,
                "latest_observed_at": latest_observed,
            }
        return {
            "captured_at": captured_at,
            "freshness_policy": "EXPLICIT_SOURCE_CACHE_STALE_ONLY",
            "sources": source_summary,
        }

    def _coverage(self, rows, duplicate_identity_count):
        statuses = [row["status"] for row in rows]
        processed_statuses = {"READY", "INCOMPLETE", "SOURCE_UNAVAILABLE"}
        return {
            "selected_count": len(rows),
            "requested_selector_count": len(rows) + duplicate_identity_count,
            "duplicate_identity_count": duplicate_identity_count,
            "processed_count": sum(
                status in processed_statuses for status in statuses
            ),
            "decision_ready_count": statuses.count("READY"),
            "incomplete_count": statuses.count("INCOMPLETE"),
            "source_unavailable_count": statuses.count("SOURCE_UNAVAILABLE"),
            "not_found_count": statuses.count("NOT_FOUND"),
            "identity_conflict_count": statuses.count("IDENTITY_AMBIGUOUS"),
            "budget_unprocessed_count": statuses.count("BUDGET_EXHAUSTED"),
            "cancelled_count": statuses.count("CANCELLED"),
        }

    def _page_result(
        self,
        snapshot,
        page,
        page_size,
        filter_by,
        sort_by,
        direction,
    ):
        all_rows = list(snapshot.get("rows") or [])
        filtered = [
            row for row in all_rows if self._matches_filter(row, filter_by)
        ]
        rows = self._sort_rows(filtered, sort_by, direction)
        total_rows = len(rows)
        total_pages = (total_rows + page_size - 1) // page_size
        if page > max(total_pages, 1):
            return self._error("PRODUCT_OVERVIEW_PAGE_OUT_OF_RANGE")
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return {
            "error": False,
            "code": None,
            "snapshot": {
                key: snapshot.get(key)
                for key in (
                    "snapshot_id",
                    "kind",
                    "owner_id",
                    "store_id",
                    "generation",
                    "version",
                    "created_at",
                    "expires_at",
                )
            },
            "coverage": snapshot.get("coverage") or {},
            "source_freshness": snapshot.get("source_freshness") or {},
            "rows": page_rows,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "scope_rows": len(all_rows),
                "filter": filter_by,
                "sort_by": sort_by,
                "direction": self._effective_direction(sort_by, direction),
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
            "read_only": True,
            "executed": False,
        }

    def _matches_filter(self, row, filter_by):
        status = row.get("status")
        decision = row.get("decision") or {}
        reasons = set(decision.get("reasons") or [])
        metrics = row.get("metrics") or {}
        profit = self._metric_value(metrics, "decision_profit_per_unit")
        if filter_by == "all_selected":
            return True
        if filter_by == "existing_priority":
            return decision.get("priority") in {
                "CRITICAL", "HIGH", "NORMAL", "LOW"
            }
        if filter_by == "negative_unit_profit":
            return (
                status == "READY"
                and profit is not None
                and profit < 0
                and "NEGATIVE_UNIT_PROFIT" in reasons
            )
        if filter_by == "low_margin_decision":
            return (
                status == "READY"
                and (
                    "LOW_MARGIN" in reasons
                    or decision.get("decision_type") == "WATCH_LOW_MARGIN"
                )
            )
        if filter_by == "stock_without_sales":
            stock = self._metric_value(metrics, "current_stock")
            velocity = self._metric_value(metrics, "sales_velocity")
            stock_priority = self._metric_value(metrics, "stock_priority")
            return (
                status == "READY"
                and stock is not None
                and stock > 0
                and velocity == 0
                and stock_priority == "NO_SALES"
            )
        if filter_by == "incomplete_or_stale":
            sources = row.get("source_freshness") or {}
            source_unknown = any(
                source.get("freshness_status") == "UNKNOWN"
                for source in sources.values()
                if isinstance(source, dict)
            )
            unit_economics = sources.get("unit_economics") or {}
            explicit_stale = unit_economics.get("cache_stale") is True
            return (
                status in {"INCOMPLETE", "SOURCE_UNAVAILABLE"}
                or bool(row.get("missing_data"))
                or source_unknown
                or explicit_stale
            )
        return False

    def _sort_rows(self, rows, sort_by, direction):
        descending = self._effective_direction(sort_by, direction) == "DESC"
        identity_key = lambda row: self._stable_identity_sort_key(row)
        if sort_by == "priority":
            stable_rows = sorted(rows, key=identity_key)
            return sorted(
                stable_rows,
                key=lambda row: self.PRIORITY_ORDER.get(
                    (row.get("decision") or {}).get("priority"), 5
                ),
                reverse=descending,
            )

        known = []
        unknown = []
        for row in rows:
            value = self._metric_value(row.get("metrics") or {}, sort_by)
            if type(value) in (int, float) and isfinite(float(value)):
                known.append((row, value))
            else:
                unknown.append(row)
        known.sort(key=lambda item: identity_key(item[0]))
        known.sort(key=lambda item: item[1], reverse=descending)
        unknown.sort(key=identity_key)
        return [row for row, _value in known] + unknown

    @staticmethod
    def _metric_value(metrics, key):
        metric = metrics.get(key)
        return metric.get("value") if isinstance(metric, dict) else None

    @staticmethod
    def _stable_identity_sort_key(row):
        identity = row.get("identity") or {}
        return (
            str(identity.get("offer_id") or ""),
            str(identity.get("catalog_sku") or ""),
            str(identity.get("product_id") or ""),
            str(row.get("row_id") or ""),
        )

    @classmethod
    def _effective_direction(cls, sort_by, direction):
        if direction is not None:
            return direction
        return "ASC" if sort_by == "priority" else "DESC"

    def _active_scope(self):
        try:
            tenant = str(self.tenant_scope_provider() or "").strip()
        except Exception:
            tenant = ""
        owner_id, store_id = split_store_tenant_scope(tenant)
        if not owner_id or not store_id:
            return None, None, "PRODUCT_OVERVIEW_TENANT_REQUIRED"
        return str(owner_id), str(store_id), None

    @classmethod
    def _validate_request(
        cls, selectors, page, page_size, filter_by, sort_by, direction
    ):
        if not isinstance(selectors, (list, tuple)):
            return "PRODUCT_OVERVIEW_SELECTION_INVALID"
        if len(selectors) > cls.MAX_SELECTION:
            return "PRODUCT_OVERVIEW_SELECTION_LIMIT_EXCEEDED"
        for selector in selectors:
            if (
                not isinstance(selector, str)
                or not selector.strip()
                or len(selector.strip()) > 128
                or any(ord(char) < 32 or ord(char) == 127 for char in selector)
            ):
                return "PRODUCT_OVERVIEW_SELECTION_INVALID"
        return cls._validate_request_options(
            page, page_size, filter_by, sort_by, direction
        )

    @classmethod
    def _validate_request_options(
        cls, page, page_size, filter_by, sort_by, direction
    ):
        page_error = cls._validate_page(page, page_size)
        if page_error:
            return page_error
        if not isinstance(filter_by, str) or filter_by not in cls.FILTERS:
            return "PRODUCT_OVERVIEW_FILTER_INVALID"
        if not isinstance(sort_by, str) or sort_by not in cls.SORT_FIELDS:
            return "PRODUCT_OVERVIEW_SORT_INVALID"
        if direction not in (None, "ASC", "DESC"):
            return "PRODUCT_OVERVIEW_DIRECTION_INVALID"
        return None

    @classmethod
    def _validate_page(cls, page, page_size):
        if type(page) is not int or page < 1:
            return "PRODUCT_OVERVIEW_PAGE_INVALID"
        if (
            type(page_size) is not int
            or page_size < 1
            or page_size > cls.MAX_PAGE_SIZE
        ):
            return "PRODUCT_OVERVIEW_PAGE_SIZE_INVALID"
        return None

    def _stable_row_id(self, owner_id, store_id, identity, selector, status):
        if identity is not None:
            identity_key = identity
        else:
            identity_key = {"selector": selector, "status": status}
        canonical = json.dumps(
            [owner_id, store_id, self.SNAPSHOT_KIND, identity_key],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]
        return "overview_" + digest

    @staticmethod
    def _safe_identity(identity):
        if not isinstance(identity, dict):
            return None
        result = {}
        for field in ("product_id", "offer_id", "catalog_sku"):
            value = identity.get(field)
            if value is None:
                result[field] = None
                continue
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                text = str(value).strip()
                if text and len(text) <= 128 and not any(
                    ord(char) < 32 or ord(char) == 127 for char in text
                ):
                    result[field] = text
                    continue
            return None
        if not result["offer_id"] and not result["catalog_sku"]:
            return None
        return result

    @staticmethod
    def _safe_number(value):
        if type(value) not in (int, float):
            return None
        try:
            return value if isfinite(float(value)) else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _safe_non_negative_number(value):
        if type(value) not in (int, float):
            return None
        try:
            return value if isfinite(float(value)) and value >= 0 else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _safe_text(value, limit):
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text or len(text) > limit or any(
            ord(char) < 32 or ord(char) == 127 for char in text
        ):
            return None
        return text

    @classmethod
    def _safe_code(cls, value):
        return cls._safe_text(value, limit=96)

    @classmethod
    def _safe_status(cls, value):
        status = cls._safe_text(value, limit=40)
        return status if status in cls._ROW_STATUSES else "SOURCE_UNAVAILABLE"

    @classmethod
    def _safe_string_list(cls, values, limit=128):
        if not isinstance(values, (list, tuple)):
            return []
        result = []
        for value in values:
            text = cls._safe_text(value, limit)
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _age_seconds(observed_at, captured_at):
        try:
            observed = datetime.fromisoformat(
                observed_at.replace("Z", "+00:00")
            )
            captured = datetime.fromisoformat(
                captured_at.replace("Z", "+00:00")
            )
            if observed.tzinfo is None or captured.tzinfo is None:
                return None
            age = (captured - observed).total_seconds()
            return max(0, int(age)) if age >= 0 else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _captured_at(self):
        current = self.utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code or "PRODUCT_OVERVIEW_ERROR",
            "read_only": True,
            "executed": False,
        }

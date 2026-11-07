"""Fail-closed normalization of allowlisted FIFO stock and supply evidence.

This module is intentionally pure.  It never calls Seller API, persists raw
payloads, or turns a capture timestamp into a physical receipt/sale time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True)
class FifoStockSnapshot:
    status: str
    source_status: str
    store_id: str | None
    product_id: str | None
    offer_id: str | None
    sku: str | None
    captured_at: str | None
    source_as_of: str | None
    pagination_complete: bool
    pages_read: int | None
    total_items: int | None
    fbo_units: int | None
    reserved_units: int | None
    available_units: int | None
    transit_units: int | None
    transit_status: str
    source_fingerprint: str | None
    issue_codes: tuple[str, ...]
    anchor_eligible: bool = False


@dataclass(frozen=True)
class FifoSupplyActSnapshot:
    status: str
    source_status: str
    store_id: str | None
    supply_ref: str | None
    act_refs: tuple[str, ...]
    units_by_sku: tuple[tuple[str, int], ...] | None
    captured_at: str | None
    effective_at: None
    source_fingerprint: str | None
    issue_codes: tuple[str, ...]
    order_ref: str | None = None
    act_evidence: tuple["FifoSupplyActEvidence", ...] = ()
    evidence_fingerprint: str | None = None


@dataclass(frozen=True)
class FifoSupplyActEvidence:
    """Allowlisted, redacted per-act quantities; dates are documentary only."""

    act_ref: str
    act_type: str
    act_state: str
    created_date: str | None
    declared_quantity: int | None
    approved_quantity: int | None
    fact_quantity: int


class FifoCostSourceNormalizer:
    """Normalize only fields whose names and values are explicitly allowlisted."""

    MAX_ITEMS = 10_000
    MAX_UNITS = 1_000_000
    MAX_ID = 9_223_372_036_854_775_807
    _RESPONSE_ERRORS = frozenset({
        "OZON_HTTP_ERROR", "OZON_HTTP_404", "OZON_HTTP_429",
        "OZON_RATE_LIMITED", "OZON_TIMEOUT", "OZON_CANCELLED",
        "OZON_SOURCE_UNAVAILABLE",
    })

    def normalize_stock_snapshot(
        self,
        response: object,
        *,
        identity: Mapping[str, object],
        store_id: object,
        captured_at: object,
        pagination_complete: object,
        pages_read: object = 1,
        identity_mapping_confirmed: bool = False,
        field_semantics_confirmed: bool = False,
        transit_units: object = None,
        transit_complete: bool = False,
        transit_overlap_confirmed: bool = False,
    ) -> FifoStockSnapshot:
        """Normalize v4 stock observations without inventing a common cutoff.

        ``field_semantics_confirmed`` is an explicit caller evidence gate, not a
        default inferred from the API method name. ``present`` remains the
        physical FBO basis; ``reserved`` is a subset, never another location.
        """

        store = self._nonempty_text(store_id, 128)
        identity_values = self._normalize_identity(identity)
        captured = self._utc_timestamp(captured_at)
        pages = self._bounded_int(pages_read, minimum=1, maximum=100_000)
        complete = pagination_complete is True
        issues: list[str] = []
        if store is None:
            issues.append("STORE_ID_INVALID")
        if identity_values is None:
            issues.append("PRODUCT_IDENTITY_INVALID")
        if captured is None:
            issues.append("CAPTURE_TIMESTAMP_INVALID")
        if pages is None:
            issues.append("PAGE_COUNT_INVALID")
        if pagination_complete is not True and pagination_complete is not False:
            issues.append("PAGINATION_COMPLETENESS_INVALID")
        if type(field_semantics_confirmed) is not bool:
            issues.append("STOCK_SEMANTICS_FLAG_INVALID")
        if type(identity_mapping_confirmed) is not bool:
            issues.append("PRODUCT_SKU_MAPPING_FLAG_INVALID")
        if type(transit_complete) is not bool or type(transit_overlap_confirmed) is not bool:
            issues.append("TRANSIT_EVIDENCE_FLAGS_INVALID")
        if not isinstance(response, dict):
            issues.append("STOCK_RESPONSE_INVALID")
            return self._stock_result(
                "INVALID", store, identity_values, captured, complete, pages,
                None, None, None, None, "UNKNOWN", issues,
            )
        if response.get("error") is True:
            code = response.get("code")
            issue = code if isinstance(code, str) and code in self._RESPONSE_ERRORS else "STOCK_SOURCE_UNAVAILABLE"
            return self._stock_result(
                "UNAVAILABLE", store, identity_values, captured, False, pages,
                None, None, None, None, "UNKNOWN", [issue],
            )
        items = response.get("items")
        if not isinstance(items, list) or len(items) > self.MAX_ITEMS:
            issues.append("STOCK_ITEMS_INVALID")
            return self._stock_result(
                "INVALID", store, identity_values, captured, complete, pages,
                None, None, None, None, "UNKNOWN", issues,
            )
        if issues:
            return self._stock_result(
                "INVALID", store, identity_values, captured, complete, pages,
                None, None, None, None, "UNKNOWN", issues,
            )

        expected_product_id = identity_values[0]
        total_items = self._bounded_int(
            response.get("total_items"), minimum=0, maximum=self.MAX_ITEMS,
        ) if "total_items" in response else None
        if "total_items" in response and total_items is None:
            return self._stock_result(
                "INVALID", store, identity_values, captured, False, pages,
                None, None, None, None, "UNKNOWN", ["TOTAL_ITEMS_INVALID"],
            )
        if total_items is not None and total_items > len(items):
            complete = False
            issues.append("STOCK_PAGE_SET_INCOMPLETE")

        matching: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                issues.append("STOCK_ITEM_INVALID")
                continue
            product_id = self._identifier(item.get("product_id"))
            if product_id is None:
                issues.append("STOCK_PRODUCT_ID_MISSING_OR_INVALID")
                continue
            if product_id == expected_product_id:
                matching.append(item)
        if issues and any(code not in {"STOCK_PAGE_SET_INCOMPLETE"} for code in issues):
            return self._stock_result(
                "INVALID", store, identity_values, captured, complete, pages,
                total_items, None, None, None, "UNKNOWN", issues,
            )
        if len(matching) > 1:
            normalized = [self._stock_item_signature(item) for item in matching]
            if any(value is None for value in normalized):
                return self._stock_result(
                    "INVALID", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", ["STOCK_ITEM_INVALID"],
                )
            if len(set(normalized)) != 1:
                return self._stock_result(
                    "CONFLICT", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", ["DUPLICATE_PRODUCT_CONFLICT"],
                )
            matching = matching[:1]
        if items and not matching:
            return self._stock_result(
                "CONFLICT", store, identity_values, captured, complete, pages,
                total_items, None, None, None, "UNKNOWN", ["PRODUCT_SCOPE_MISMATCH"],
            )
        if any(
            isinstance(item, dict)
            and self._identifier(item.get("product_id")) != expected_product_id
            for item in items
        ):
            return self._stock_result(
                "CONFLICT", store, identity_values, captured, complete, pages,
                total_items, None, None, None, "UNKNOWN", ["PRODUCT_SCOPE_MISMATCH"],
            )
        if (
            total_items is not None
            and total_items < len(items)
            and total_items != len(matching)
        ):
            return self._stock_result(
                "CONFLICT", store, identity_values, captured, complete, pages,
                total_items, None, None, None, "UNKNOWN", ["TOTAL_ITEMS_BELOW_ROWS"],
            )

        if not complete:
            status = "PARTIAL"
        elif not matching:
            status = "EMPTY"
        else:
            stock_rows = matching[0].get("stocks")
            if not isinstance(stock_rows, list) or len(stock_rows) > self.MAX_ITEMS:
                return self._stock_result(
                    "INVALID", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", ["STOCK_ROWS_INVALID"],
                )
            present_values: list[int] = []
            reserved_values: list[int] = []
            unknown_stock_type = False
            for stock in stock_rows:
                if not isinstance(stock, dict):
                    issues.append("STOCK_ROW_INVALID")
                    continue
                stock_type = stock.get("type")
                if stock_type not in {"fbo", "fbs"}:
                    unknown_stock_type = True
                    continue
                if stock_type != "fbo":
                    continue
                present = self._bounded_int(stock.get("present"), minimum=0, maximum=self.MAX_UNITS)
                reserved = self._bounded_int(stock.get("reserved"), minimum=0, maximum=self.MAX_UNITS)
                if present is None or reserved is None:
                    issues.append("FBO_QUANTITY_INVALID")
                    continue
                present_values.append(present)
                reserved_values.append(reserved)
            if issues:
                return self._stock_result(
                    "INVALID", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", issues,
                )
            if not present_values:
                missing_fbo_issues = ["FBO_STOCK_ROW_MISSING"]
                if unknown_stock_type:
                    missing_fbo_issues.append("STOCK_TYPE_UNKNOWN")
                return self._stock_result(
                    "PARTIAL", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN",
                    [*issues, *missing_fbo_issues],
                )
            fbo_units = sum(present_values)
            reserved_units = sum(reserved_values)
            if fbo_units > self.MAX_UNITS or reserved_units > self.MAX_UNITS:
                return self._stock_result(
                    "INVALID", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", ["FBO_QUANTITY_LIMIT"],
                )
            if reserved_units > fbo_units:
                return self._stock_result(
                    "CONFLICT", store, identity_values, captured, complete, pages,
                    total_items, fbo_units, reserved_units, None, "UNKNOWN",
                    ["RESERVED_EXCEEDS_PRESENT"],
                )
            if unknown_stock_type:
                status = "PARTIAL"
                issues.append("STOCK_TYPE_UNKNOWN")
            elif identity_mapping_confirmed is not True:
                status = "PARTIAL"
                issues.append("PRODUCT_SKU_MAPPING_UNCONFIRMED")
            elif field_semantics_confirmed is not True:
                status = "PARTIAL"
                issues.append("STOCK_SEMANTICS_UNCONFIRMED")
            elif fbo_units == 0:
                status = "CONFIRMED_ZERO"
            else:
                status = "COMPLETE"

        transit_status = "UNKNOWN"
        normalized_transit = None
        if transit_units is not None:
            candidate = self._bounded_int(transit_units, minimum=0, maximum=self.MAX_UNITS)
            if candidate is None:
                return self._stock_result(
                    "INVALID", store, identity_values, captured, complete, pages,
                    total_items, None, None, None, "UNKNOWN", ["TRANSIT_QUANTITY_INVALID"],
                )
            if transit_complete is True and transit_overlap_confirmed is True:
                transit_status = "DISJOINT_CONFIRMED"
                normalized_transit = candidate
            else:
                issues.append("TRANSIT_OVERLAP_UNRESOLVED")
        elif transit_overlap_confirmed is not True:
            issues.append("TRANSIT_OVERLAP_UNRESOLVED")

        # Existing source audit has not established a shared stock/physical-sale
        # watermark. No stock snapshot alone can activate factual FIFO.
        issues.append("INVENTORY_CUTOFF_UNRECONCILED")
        return self._stock_result(
            status, store, identity_values, captured, complete, pages,
            total_items,
            fbo_units if "fbo_units" in locals() else None,
            reserved_units if "reserved_units" in locals() else None,
            normalized_transit,
            transit_status,
            issues,
        )

    def normalize_supply_act_snapshot(
        self,
        products_response: object,
        summary_response: object,
        *,
        store_id: object,
        expected_supply_id: object,
        expected_order_id: object = None,
        captured_at: object,
        products_complete: bool,
        summary_complete: bool,
    ) -> FifoSupplyActSnapshot:
        """Reconcile act SKU lines against summary totals; never add both."""

        store = self._nonempty_text(store_id, 128)
        supply_id = self._identifier(expected_supply_id)
        order_id = self._identifier(expected_order_id)
        captured = self._utc_timestamp(captured_at)
        if store is None or supply_id is None or captured is None:
            return self._supply_result(
                "INVALID", store, None, (), None, captured, ["SUPPLY_SCOPE_INVALID"],
            )
        if expected_order_id is not None and order_id is None:
            return self._supply_result(
                "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_ORDER_ID_INVALID"],
            )
        if products_complete is not True or summary_complete is not True:
            return self._supply_result(
                "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_SOURCE_INCOMPLETE"],
            )
        if self._is_error(products_response) or self._is_error(summary_response):
            return self._supply_result(
                "UNAVAILABLE", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_SOURCE_UNAVAILABLE"],
            )
        product_acts = products_response.get("supply_acts") if isinstance(products_response, dict) else None
        summary_groups = summary_response.get("supplies_acts") if isinstance(summary_response, dict) else None
        if not isinstance(product_acts, list) or not isinstance(summary_groups, list):
            return self._supply_result(
                "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_RESPONSE_INVALID"],
            )
        if len(product_acts) > self.MAX_ITEMS or len(summary_groups) > self.MAX_ITEMS:
            return self._supply_result(
                "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_RESPONSE_LIMIT"],
            )
        groups = [
            group for group in summary_groups
            if isinstance(group, dict) and self._identifier(group.get("supply_id")) == supply_id
        ]
        if len(groups) != 1:
            status = "EMPTY" if not groups and not product_acts and not summary_groups else "CONFLICT"
            code = "SUPPLY_ACT_NOT_FOUND" if status == "EMPTY" else "SUPPLY_ACT_GROUP_AMBIGUOUS"
            return self._supply_result(
                status, store, self._digest("SUPPLY", supply_id), (), None,
                captured, [code],
            )
        group = groups[0]
        if group.get("is_agreement_completed") is not True:
            return self._supply_result(
                "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_ACCEPTANCE_AGREEMENT_INCOMPLETE"],
            )
        summary_acts = group.get("supply_acts")
        if not isinstance(summary_acts, list):
            return self._supply_result(
                "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_ACCEPTANCE_ACTS_INVALID"],
            )

        product_by_act: dict[str, dict] = {}
        for act in product_acts:
            if not isinstance(act, dict):
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_PRODUCT_ACT_INVALID"],
                )
            if act.get("type") != "ACCEPTANCE":
                continue
            act_id = self._identifier(act.get("act_id"))
            if act_id is None:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_ID_INVALID"],
                )
            previous = product_by_act.get(act_id)
            if previous is not None:
                if self._canonical(previous) != self._canonical(act):
                    return self._supply_result(
                        "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                        captured, ["DUPLICATE_ACT_CONFLICT"],
                    )
                continue
            product_by_act[act_id] = act

        quantities_by_sku: dict[str, int] = {}
        seen_act_ids: set[str] = set()
        normalized_act_refs: list[str] = []
        act_evidence: list[FifoSupplyActEvidence] = []
        unresolved_act_state = False
        for summary_act in summary_acts:
            if not isinstance(summary_act, dict):
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_SUMMARY_ACT_INVALID"],
                )
            if summary_act.get("type") != "ACCEPTANCE":
                unresolved_act_state = True
                continue
            if summary_act.get("act_state") != "ACCEPTED":
                unresolved_act_state = True
                continue
            act_id = self._identifier(summary_act.get("act_id"))
            if act_id is None:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_ID_INVALID"],
                )
            if act_id in seen_act_ids:
                if self._canonical(summary_act) != self._canonical(next(
                    item for item in summary_acts
                    if isinstance(item, dict) and self._identifier(item.get("act_id")) == act_id
                )):
                    return self._supply_result(
                        "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                        captured, ["DUPLICATE_ACT_CONFLICT"],
                    )
                continue
            seen_act_ids.add(act_id)
            product_act = product_by_act.get(act_id)
            if product_act is None:
                return self._supply_result(
                    "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_PRODUCT_MISSING"],
                )
            summary = summary_act.get("summary")
            items = product_act.get("items")
            if not isinstance(summary, dict) or not isinstance(items, list) or not items:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_LINES_INVALID"],
                )
            if len(items) > self.MAX_ITEMS:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_ITEM_LIMIT"],
                )
            unidentified = self._bounded_int(summary.get("unidentified_quantity"), minimum=0, maximum=self.MAX_UNITS)
            summary_quantity = self._bounded_int(summary.get("fact_quantity"), minimum=0, maximum=self.MAX_UNITS)
            if unidentified is None or unidentified != 0:
                return self._supply_result(
                    "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_UNIDENTIFIED_QUANTITY"],
                )
            if summary_quantity is None:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_SUMMARY_QUANTITY_INVALID"],
                )
            act_quantities: dict[str, int] = {}
            declared_values: list[int | None] = []
            approved_values: list[int | None] = []
            for item in items:
                if not isinstance(item, dict):
                    return self._supply_result(
                        "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                        captured, ["SUPPLY_ITEM_INVALID"],
                    )
                sku_info = item.get("sku_info")
                sku = self._identifier(sku_info.get("sku") if isinstance(sku_info, dict) else None)
                quantity = self._bounded_int(item.get("fact_quantity"), minimum=0, maximum=self.MAX_UNITS)
                item_unidentified = item.get("unidentified_quantity", 0)
                item_unknown = self._bounded_int(item_unidentified, minimum=0, maximum=self.MAX_UNITS)
                if sku is None or quantity is None or item_unknown is None or item_unknown != 0:
                    return self._supply_result(
                        "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                        captured, ["SUPPLY_ITEM_IDENTITY_OR_QUANTITY_INVALID"],
                    )
                act_quantities[sku] = act_quantities.get(sku, 0) + quantity
                if act_quantities[sku] > self.MAX_UNITS:
                    return self._supply_result(
                        "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                        captured, ["SUPPLY_QUANTITY_LIMIT"],
                    )
                for field, values in (
                    ("declared_quantity", declared_values),
                    ("approved_quantity", approved_values),
                ):
                    raw_count = item.get(field)
                    if raw_count is None:
                        values.append(None)
                        continue
                    count = self._bounded_int(
                        raw_count, minimum=0, maximum=self.MAX_UNITS,
                    )
                    if count is None:
                        return self._supply_result(
                            "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                            captured, ["SUPPLY_ITEM_COMPARISON_QUANTITY_INVALID"],
                        )
                    values.append(count)
            if len(act_quantities) != 1:
                return self._supply_result(
                    "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS"],
                )
            line_total = sum(act_quantities.values())
            if line_total != summary_quantity:
                return self._supply_result(
                    "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_SUMMARY_LINE_MISMATCH"],
                )
            sku, quantity = next(iter(act_quantities.items()))
            quantities_by_sku[sku] = quantities_by_sku.get(sku, 0) + quantity
            act_ref = self._digest("ACT", act_id)
            normalized_act_refs.append(act_ref)
            created_date = self._date_only(summary_act.get("created_date"))
            if summary_act.get("created_date") is not None and created_date is None:
                return self._supply_result(
                    "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ACT_DOCUMENT_DATE_INVALID"],
                )
            declared_quantity = self._sum_optional_counts(declared_values)
            approved_quantity = self._sum_optional_counts(approved_values)
            if (
                declared_values and all(value is not None for value in declared_values)
                and declared_quantity is None
                or approved_values and all(value is not None for value in approved_values)
                and approved_quantity is None
            ):
                return self._supply_result(
                    "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_ITEM_COMPARISON_QUANTITY_LIMIT"],
                )
            act_evidence.append(FifoSupplyActEvidence(
                act_ref=act_ref,
                act_type="ACCEPTANCE",
                act_state="ACCEPTED",
                created_date=created_date,
                declared_quantity=declared_quantity,
                approved_quantity=approved_quantity,
                fact_quantity=quantity,
            ))
            if quantities_by_sku[sku] > self.MAX_UNITS:
                return self._supply_result(
                    "INVALID", store, self._digest("SUPPLY", supply_id), (), None,
                    captured, ["SUPPLY_QUANTITY_LIMIT"],
                )

        if unresolved_act_state:
            return self._supply_result(
                "PARTIAL", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_ACT_STATE_UNCONFIRMED"],
            )
        if not seen_act_ids and product_by_act:
            return self._supply_result(
                "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["UNMATCHED_ACCEPTANCE_ACT"],
            )
        if not seen_act_ids:
            return self._supply_result(
                "EMPTY", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["NO_ACCEPTED_SUPPLY_ACT"],
            )
        if set(product_by_act) != seen_act_ids:
            return self._supply_result(
                "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["UNMATCHED_ACCEPTANCE_ACT"],
            )
        if len(quantities_by_sku) != 1:
            return self._supply_result(
                "CONFLICT", store, self._digest("SUPPLY", supply_id), (), None,
                captured, ["SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS"],
            )
        status = "CONFIRMED_ZERO" if not any(quantities_by_sku.values()) else "COMPLETE"
        return self._supply_result(
            status,
            store,
            self._digest("SUPPLY", supply_id),
            tuple(sorted(normalized_act_refs)),
            tuple(sorted(quantities_by_sku.items())),
            captured,
            [],
            order_ref=self._digest("ORDER", order_id) if order_id else None,
            act_evidence=tuple(sorted(act_evidence, key=lambda item: item.act_ref)),
        )

    @classmethod
    def _stock_result(
        cls, status, store, identity, captured, pagination_complete, pages,
        total_items, fbo_units, reserved_units, transit_units, transit_status, issues,
    ):
        if status in {"INVALID", "PARTIAL", "EMPTY", "UNAVAILABLE", "CONFLICT"}:
            source_status = {
                "INVALID": "CONFLICT", "PARTIAL": "PARTIAL", "EMPTY": "COMPLETE",
                "UNAVAILABLE": "UNAVAILABLE", "CONFLICT": "CONFLICT",
            }[status]
        else:
            source_status = "COMPLETE"
        available = None
        if status in {"COMPLETE", "CONFIRMED_ZERO"} and fbo_units is not None and reserved_units is not None:
            available = fbo_units - reserved_units
        product_id, offer_id, sku = identity if identity is not None else (None, None, None)
        fingerprint = cls._fingerprint({
            "store_id": store,
            "identity": [product_id, offer_id, sku],
            "captured_at": captured,
            "status": status,
            "pagination_complete": pagination_complete is True,
            "pages_read": pages,
            "total_items": total_items,
            "fbo_units": fbo_units,
            "reserved_units": reserved_units,
            "transit_units": transit_units,
            "transit_status": transit_status,
            "issue_codes": list(dict.fromkeys(issues)),
        }) if store and identity and captured else None
        return FifoStockSnapshot(
            status=status,
            source_status=source_status,
            store_id=store,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
            captured_at=captured,
            source_as_of=None,
            pagination_complete=pagination_complete is True,
            pages_read=pages,
            total_items=total_items,
            fbo_units=fbo_units,
            reserved_units=reserved_units,
            available_units=available,
            transit_units=transit_units,
            transit_status=transit_status,
            source_fingerprint=fingerprint,
            issue_codes=tuple(dict.fromkeys(issues)),
            anchor_eligible=False,
        )

    @classmethod
    def _supply_result(
        cls, status, store, supply_ref, act_refs, units_by_sku, captured, issues,
        *, order_ref=None, act_evidence=(),
    ):
        source_status = {
            "INVALID": "CONFLICT", "PARTIAL": "PARTIAL", "EMPTY": "COMPLETE",
            "UNAVAILABLE": "UNAVAILABLE", "CONFLICT": "CONFLICT",
            "CONFIRMED_ZERO": "COMPLETE", "COMPLETE": "COMPLETE",
        }[status]
        evidence_payload = {
            "store_id": store,
            "order_ref": order_ref,
            "supply_ref": supply_ref,
            "act_refs": list(act_refs),
            "act_evidence": [
                {
                    "act_ref": item.act_ref,
                    "act_type": item.act_type,
                    "act_state": item.act_state,
                    "created_date": item.created_date,
                    "declared_quantity": item.declared_quantity,
                    "approved_quantity": item.approved_quantity,
                    "fact_quantity": item.fact_quantity,
                }
                for item in act_evidence
            ],
            "units_by_sku": [list(row) for row in units_by_sku] if units_by_sku is not None else None,
            "status": status,
        }
        evidence_fingerprint = cls._fingerprint(evidence_payload) if store and supply_ref else None
        fingerprint = cls._fingerprint({
            **evidence_payload,
            "captured_at": captured,
        }) if store and supply_ref and captured else None
        return FifoSupplyActSnapshot(
            status=status,
            source_status=source_status,
            store_id=store,
            supply_ref=supply_ref,
            act_refs=tuple(act_refs),
            units_by_sku=units_by_sku,
            captured_at=captured,
            effective_at=None,
            source_fingerprint=fingerprint,
            issue_codes=tuple(dict.fromkeys(issues)),
            order_ref=order_ref,
            act_evidence=tuple(act_evidence),
            evidence_fingerprint=evidence_fingerprint,
        )

    @classmethod
    def _sum_optional_counts(cls, values):
        if not values or any(value is None for value in values):
            return None
        result = sum(values)
        return result if result <= cls.MAX_UNITS else None

    @staticmethod
    def _date_only(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
        return parsed.isoformat()

    @classmethod
    def _normalize_identity(cls, value):
        if not isinstance(value, Mapping):
            return None
        product_id = cls._identifier(value.get("product_id"))
        offer_id = cls._nonempty_text(value.get("offer_id"), 128)
        sku = cls._identifier(value.get("sku"))
        if product_id is None or sku is None:
            return None
        return product_id, offer_id, sku

    @classmethod
    def _stock_item_signature(cls, item):
        stocks = item.get("stocks")
        if not isinstance(stocks, list):
            return None
        normalized = []
        for row in stocks:
            if not isinstance(row, dict):
                return None
            if row.get("type") != "fbo":
                continue
            present = cls._bounded_int(row.get("present"), minimum=0, maximum=cls.MAX_UNITS)
            reserved = cls._bounded_int(row.get("reserved"), minimum=0, maximum=cls.MAX_UNITS)
            if present is None or reserved is None:
                return None
            normalized.append((present, reserved))
        return tuple(sorted(normalized))

    @classmethod
    def _identifier(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip()
        if not raw or not raw.isascii() or not raw.isdigit():
            return None
        parsed = int(raw)
        return str(parsed) if 0 < parsed <= cls.MAX_ID else None

    @staticmethod
    def _nonempty_text(value, max_length):
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value if value and len(value) <= max_length else None

    @staticmethod
    def _bounded_int(value, *, minimum, maximum):
        if type(value) is not int or not minimum <= value <= maximum:
            return None
        return value

    @staticmethod
    def _utc_timestamp(value):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @classmethod
    def _digest(cls, kind, identifier):
        return hashlib.sha256(f"fifo-cost-ref-v1:{kind}:{identifier}".encode("ascii")).hexdigest()

    @staticmethod
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def _fingerprint(cls, payload):
        return hashlib.sha256(cls._canonical(payload).encode("utf-8")).hexdigest()

    @classmethod
    def _is_error(cls, value):
        return not isinstance(value, dict) or value.get("error") is True

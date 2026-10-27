"""Pure normalization of bounded unit-price observation evidence."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnitPriceObservationNormalizer:
    """Keep source money, quantity, date and advertising bases explicit.

    The current Q17 adapters return pre-aggregated finance totals and do not
    expose stable finance row identities or successful-sale quantities. This
    normalizer therefore preserves those totals, but deliberately does not
    promote them to per-unit profit or claim that aggregate rows were deduped.
    """

    MAX_ROWS = 10_000
    MONEY_QUANTUM = Decimal("0.01")
    PERCENT_QUANTUM = Decimal("0.01")
    _IDENTITY_KEYS = frozenset({
        "store_id", "product_id", "offer_id", "sku", "sale_schema",
    })
    _SAFE_SOURCE_FIELDS = frozenset({
        "name", "status", "complete", "row_count", "requested_at",
        "received_at", "as_of", "source_date_basis", "source_window_start",
        "source_window_end", "timezone", "reason", "unknown_field_count",
        "unknown_fields", "unsupported_types",
    })
    _DEDUP_ROW_VALUE_FIELDS = frozenset({
        "amount", "units", "seller_price_cents", "date", "date_basis",
        "revenue_basis", "scope", "sku", "is_correction",
        "correction_of", "correction_semantics",
    })

    @classmethod
    def normalize_collected(cls, evidence):
        """Normalize one Q17 collection package without doing I/O or inference."""
        if not isinstance(evidence, dict) or evidence.get("error") is not False:
            return cls._error("OBSERVATION_EVIDENCE_INVALID")
        identity = evidence.get("identity")
        if (
            not isinstance(identity, dict)
            or set(identity) != cls._IDENTITY_KEYS
            or any(not isinstance(identity.get(key), str) or not identity[key].strip()
                   for key in cls._IDENTITY_KEYS)
            or identity.get("sale_schema") != "FBO"
        ):
            return cls._error("OBSERVATION_IDENTITY_INVALID")
        price_cents = evidence.get("seller_price_cents")
        if type(price_cents) is not int or not 1 <= price_cents <= 999_999_999_999_999:
            return cls._error("OBSERVATION_PRICE_INVALID")
        window = cls._normalize_window(evidence.get("window"))
        if window is None:
            return cls._error("OBSERVATION_WINDOW_INVALID")
        metrics = evidence.get("metrics")
        sources = evidence.get("sources")
        if not isinstance(metrics, dict) or not isinstance(sources, list):
            return cls._error("OBSERVATION_EVIDENCE_INVALID")
        normalized_sources = cls._safe_sources(sources)
        finance = cls._source(normalized_sources, "FINANCE")
        performance = cls._source(normalized_sources, "PERFORMANCE")
        returns = cls._source(normalized_sources, "RETURNS")

        amounts = {}
        for name in (
            "gross_seller_revenue", "discount_points", "finance_net",
            "acquiring", "commission", "logistics", "other_fees", "cpc_spend",
        ):
            raw = metrics.get(name)
            amount = cls._decimal(raw) if raw is not None else None
            if raw is not None and amount is None:
                return cls._error("OBSERVATION_AMOUNT_INVALID")
            amounts[name] = amount

        finance_source_complete = finance is not None and finance.get("complete") is True
        finance_complete = (
            finance_source_complete
            and amounts["gross_seller_revenue"] is not None
            and amounts["discount_points"] is not None
            and amounts["finance_net"] is not None
        )
        performance_complete = (
            performance is not None and performance.get("complete") is True
            and amounts["cpc_spend"] is not None
        )
        gross = amounts["gross_seller_revenue"]
        points = amounts["discount_points"]
        taxable_revenue = None
        discount_points_complete = (
            finance_complete and metrics.get("discount_points_complete") is True
        )
        if discount_points_complete and gross is not None and points is not None:
            taxable_revenue = gross - points
            if taxable_revenue < 0:
                return cls._error("OBSERVATION_REVENUE_BASIS_INVALID")

        seller_drr = None
        if (
            performance_complete and finance_complete and gross is not None
            and gross > 0 and cls._same_source_window(finance, performance)
        ):
            seller_drr = cls._percent(amounts["cpc_spend"] / gross * Decimal("100"))

        raw_attributed_revenue = metrics.get("attributed_revenue")
        attributed_revenue = (
            cls._decimal(raw_attributed_revenue)
            if raw_attributed_revenue is not None else None
        )
        if raw_attributed_revenue is not None and attributed_revenue is None:
            return cls._error("OBSERVATION_AMOUNT_INVALID")
        attributed_drr = None
        if (
            performance_complete and attributed_revenue is not None
            and attributed_revenue > 0
        ):
            attributed_drr = cls._percent(
                amounts["cpc_spend"] / attributed_revenue * Decimal("100")
            )

        source_row_count = metrics.get("source_row_count")
        if type(source_row_count) is not int or source_row_count < 0:
            source_row_count = None
        sample_days = metrics.get("sample_days")
        if type(sample_days) is not int or sample_days < 0:
            sample_days = None

        ordered_units = cls._count(metrics.get("ordered_units"))
        delivered_units = cls._count(metrics.get("delivered_units"))
        cancelled_units = cls._count(metrics.get("cancelled_units"))
        returned_units = cls._count(metrics.get("returned_units"))
        buyout_sample_size = cls._count(metrics.get("buyout_sample_size"))
        buyout_rate = cls._decimal(metrics.get("buyout_rate_percent"))
        if buyout_rate is not None and not Decimal("0") <= buyout_rate <= Decimal("100"):
            return cls._error("OBSERVATION_BUYOUT_RATE_INVALID")
        raw_successful_units = cls._count(metrics.get("successful_sale_units"))
        return_window_valid = bool(
            returns is not None
            and returns.get("complete") is True
            and returns.get("source_date_basis") == "FBO_POSTING_AND_RETURN_CHANGE_WINDOW"
        )
        successful_units = None
        if (
            return_window_valid
            and ordered_units is not None
            and delivered_units is not None
            and cancelled_units is not None
            and ordered_units == delivered_units + cancelled_units
            and raw_successful_units == delivered_units
            and delivered_units > 0
        ):
            successful_units = delivered_units

        reasons = [
            "PRICE_HISTORY_UNCONFIRMED",
            "FINANCE_ROW_DEDUPLICATION_UNAVAILABLE",
            "CORRECTIONS_NOT_SEPARATELY_IDENTIFIED",
        ]
        if successful_units is None:
            reasons.append("SUCCESSFUL_UNIT_DENOMINATOR_UNKNOWN")
        if finance_complete and not discount_points_complete:
            reasons.append("DISCOUNT_POINTS_COMPLETENESS_NOT_CONFIRMED")
        if not finance_complete:
            reasons.append(
                "FINANCE_REQUIRED_METRICS_MISSING" if finance_source_complete
                else "FINANCE_SOURCE_INCOMPLETE"
            )
        if not performance_complete:
            reasons.append("PERFORMANCE_CPC_INCOMPLETE")
        warnings = [
            "FINANCE_NET_ALREADY_CONTAINS_FINANCE_ACCRUALS; DO_NOT_SUBTRACT_PERFORMANCE_CPC_AGAIN.",
            "FINANCE_COMPONENTS_ARE_A_BREAKDOWN_OF_FINANCE_NET; DO_NOT_SUBTRACT_THEM_AGAIN.",
            "PERFORMANCE_CPC_IS_SEPARATE_EVIDENCE_AND_DOES_NOT_PROVE_TOTAL_ADVERTISING_COST.",
            "SOURCE_ROW_COUNT_IS_NOT_A_UNIT_OR_ORDER_DENOMINATOR.",
            "SIGNED_FINANCE_TOTALS_ARE_PRESERVED; CORRECTION_ROWS_CANNOT_BE_DEDUPED_FROM_AGGREGATES.",
            "ACCOUNT_TOTALS_ARE_NOT_ALLOCATED_TO_THIS_SKU.",
            "OBSERVED_PROFIT_IS_NOT_COMPUTED_WITHOUT_COMPATIBLE_UNITS_PRICE_HISTORY_AND_COSTS.",
        ]
        if seller_drr is None:
            warnings.append("SELLER_REVENUE_DRR_UNAVAILABLE_OR_INCOMPATIBLE.")
        if attributed_drr is None:
            warnings.append("ATTRIBUTED_REVENUE_DRR_UNAVAILABLE; IT_IS_NOT_SELLER_REVENUE_DRR.")
        if "WINDOW_INCLUDES_EFFECTIVE_DATE" in evidence.get("warnings", []):
            reasons.append("WINDOW_MAY_CONTAIN_MIXED_PRICES_ON_EFFECTIVE_DATE")
        price_evidence_status = metrics.get("price_evidence_status")
        if price_evidence_status not in {"MIXED_PRICES", "PRICE_HISTORY_UNCONFIRMED"}:
            price_evidence_status = "PRICE_HISTORY_UNCONFIRMED"
        if price_evidence_status == "MIXED_PRICES":
            reasons.append("MULTIPLE_SELLER_PRICES_CONFIRMED_IN_WINDOW")

        normalized_metrics = {
            "gross_seller_revenue": cls._money(amounts["gross_seller_revenue"]),
            "discount_points": cls._money(amounts["discount_points"]),
            "net_seller_revenue": cls._money(taxable_revenue),
            "attributed_revenue": cls._money(attributed_revenue),
            "finance_net": cls._money(amounts["finance_net"]),
            "acquiring": cls._money(amounts["acquiring"]),
            "commission": cls._money(amounts["commission"]),
            "logistics": cls._money(amounts["logistics"]),
            "other_fees": cls._money(amounts["other_fees"]),
            "cpc_spend": cls._money(amounts["cpc_spend"]),
            "seller_revenue_drr_percent": cls._money(seller_drr),
            "attributed_revenue_drr_percent": cls._money(attributed_drr),
            "successful_sale_units": successful_units,
            "ordered_units": ordered_units,
            "delivered_units": delivered_units,
            "cancelled_units": cancelled_units,
            "returned_units": returned_units,
            "buyout_rate_percent": cls._money(buyout_rate) if return_window_valid else None,
            "buyout_sample_size": buyout_sample_size if return_window_valid else None,
            "weighted_ad_spend_numerator": cls._money(amounts["cpc_spend"]),
            "successful_unit_denominator": successful_units,
            "source_row_count": source_row_count,
            "duplicate_row_count": None,
            "correction_count": None,
            "sample_days": sample_days,
            "revenue_basis": "GROSS_SELLER_REVENUE_FOR_DRR; TAX_BASE_IS_GROSS_MINUS_DISCOUNT_POINTS",
            "date_basis": "OZON_ACCRUAL_DATE; PERFORMANCE_REPORT_DATE",
            "price_evidence_status": price_evidence_status,
            "advertising_status": "CPC_ONLY" if performance_complete else "INCOMPLETE",
        }
        status = (
            "SOURCE_UNAVAILABLE"
            if finance is None or finance.get("status") == "SOURCE_UNAVAILABLE"
            else "INCOMPARABLE"
        )
        completeness = {
            "price_history": price_evidence_status,
            "successful_units": "CONFIRMED" if successful_units is not None else "UNKNOWN",
            "finance": "CONFIRMED" if finance_complete else (
                "SOURCE_UNAVAILABLE" if finance is None or finance.get("status") == "SOURCE_UNAVAILABLE" else "PARTIAL"
            ),
            "advertising": "PARTIAL" if performance_complete else (
                "UNKNOWN" if performance is None or performance.get("status") == "NOT_REQUESTED"
                else "SOURCE_UNAVAILABLE"
            ),
            "tariff": "UNKNOWN",
            "tax": "UNKNOWN",
            "unit_cost": "UNKNOWN",
            "returns": "CONFIRMED" if return_window_valid else (
                "SOURCE_UNAVAILABLE" if returns is not None and returns.get("status") == "SOURCE_UNAVAILABLE"
                else "PARTIAL" if returns is not None and returns.get("status") in {"PARTIAL", "RATE_LIMITED"}
                else "UNKNOWN"
            ),
            "analytics": "UNKNOWN",
            "window": "CONFIRMED",
            "deduplication": "UNKNOWN",
        }
        return {
            "error": False,
            "status": status,
            "kind": "NORMALIZED_OBSERVATION_EVIDENCE",
            "identity": {key: identity[key].strip() for key in cls._IDENTITY_KEYS},
            "seller_price_cents": price_cents,
            "window": window,
            "sources": normalized_sources,
            "metrics": normalized_metrics,
            "completeness": completeness,
            "reasons": reasons[:32],
            "warnings": warnings[:32],
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def weighted_ratio(cls, records, *, numerator_field, denominator_field):
        """Return sum(numerators)/sum(denominators), never an average of rates."""
        if not isinstance(records, list) or not records or len(records) > cls.MAX_ROWS:
            return {"status": "INSUFFICIENT_DATA", "value": None}
        numerator_total = Decimal("0")
        denominator_total = 0
        for record in records:
            if not isinstance(record, dict):
                return {"status": "INVALID", "value": None}
            numerator = cls._decimal(record.get(numerator_field))
            denominator = record.get(denominator_field)
            if numerator is None or type(denominator) is not int or denominator < 0:
                return {"status": "INCOMPLETE", "value": None}
            numerator_total += numerator
            denominator_total += denominator
        if denominator_total == 0:
            return {
                "status": "ZERO_DENOMINATOR",
                "numerator": cls._money(numerator_total),
                "denominator": 0,
                "value": None,
            }
        return {
            "status": "COMPLETE",
            "numerator": cls._money(numerator_total),
            "denominator": denominator_total,
            "value": cls._money(numerator_total / Decimal(denominator_total)),
        }

    @classmethod
    def deduplicate_rows(cls, rows, *, expected_sku=None):
        """Deduplicate exact stable IDs and project safe values without IDs.

        Rows must be SKU-scoped, carry a signed amount and an explicit date and
        revenue basis. A correction is accepted only as a referenced signed
        delta and may not change the unit denominator.
        """
        if not isinstance(rows, list) or len(rows) > cls.MAX_ROWS:
            return {"status": "INVALID", "rows": [], "duplicate_count": 0}
        unique = {}
        duplicate_count = 0
        for row in rows:
            if not isinstance(row, dict):
                return {"status": "INVALID", "rows": [], "duplicate_count": duplicate_count}
            row_id = row.get("row_id")
            if not isinstance(row_id, str) or not row_id or len(row_id) > 160:
                return {"status": "INCOMPLETE", "rows": [], "duplicate_count": duplicate_count}
            if set(row) - cls._DEDUP_ROW_VALUE_FIELDS - {"row_id"}:
                return {"status": "INVALID", "rows": [], "duplicate_count": duplicate_count}
            if (
                row.get("scope") != "SKU"
                or not isinstance(row.get("sku"), str)
                or not row["sku"].strip()
                or (expected_sku is not None and row["sku"].strip() != str(expected_sku))
            ):
                return {"status": "OUT_OF_SCOPE", "rows": [], "duplicate_count": duplicate_count}
            amount = cls._decimal(row.get("amount"))
            units = row.get("units")
            if (
                amount is None or type(units) is not int or units < 0
                or not isinstance(row.get("date"), str)
                or not isinstance(row.get("date_basis"), str) or not row["date_basis"]
                or not isinstance(row.get("revenue_basis"), str) or not row["revenue_basis"]
                or type(row.get("is_correction")) is not bool
            ):
                return {"status": "INCOMPLETE", "rows": [], "duplicate_count": duplicate_count}
            if row.get("seller_price_cents") is not None and (
                type(row["seller_price_cents"]) is not int
                or row["seller_price_cents"] <= 0
            ):
                return {"status": "INVALID", "rows": [], "duplicate_count": duplicate_count}
            try:
                date.fromisoformat(row["date"])
            except ValueError:
                return {"status": "INVALID", "rows": [], "duplicate_count": duplicate_count}
            if row["is_correction"] and (
                not isinstance(row.get("correction_of"), str)
                or not row["correction_of"]
                or row.get("correction_semantics") != "SIGNED_DELTA"
                or units != 0
            ):
                return {"status": "INCOMPLETE", "rows": [], "duplicate_count": duplicate_count}
            signature = tuple(sorted(
                (key, cls._signature_value(value)) for key, value in row.items()
                if key != "row_id"
            ))
            previous = unique.get(row_id)
            if previous is None:
                unique[row_id] = (signature, {
                    "amount": cls._money(amount),
                    "units": units,
                    "seller_price_cents": row.get("seller_price_cents"),
                    "date": row["date"],
                    "date_basis": row["date_basis"],
                    "revenue_basis": row["revenue_basis"],
                    "is_correction": row["is_correction"],
                    "correction_semantics": (
                        row.get("correction_semantics") if row["is_correction"] else None
                    ),
                })
            elif previous[0] == signature:
                duplicate_count += 1
            else:
                return {"status": "CONFLICT", "rows": [], "duplicate_count": duplicate_count}
        # Deliberately expose safe financial dimensions only, never source IDs.
        return {
            "status": "COMPLETE",
            "unique_row_count": len(unique),
            "duplicate_count": duplicate_count,
            "rows": [item[1] for item in unique.values()],
        }

    @staticmethod
    def _signature_value(value):
        if value is None:
            return ("none",)
        if type(value) is bool:
            return ("bool", value)
        if type(value) is int:
            return ("int", value)
        if isinstance(value, float):
            return ("float", repr(value))
        if isinstance(value, str):
            return ("string", value)
        if isinstance(value, Decimal):
            return ("decimal", str(value))
        if isinstance(value, list):
            return ("list", tuple(UnitPriceObservationNormalizer._signature_value(item) for item in value))
        if isinstance(value, dict):
            return ("object", tuple(sorted(
                (str(key), UnitPriceObservationNormalizer._signature_value(item))
                for key, item in value.items()
            )))
        return ("unsupported", repr(type(value)))

    @classmethod
    def _normalize_window(cls, value):
        if not isinstance(value, dict):
            return None
        try:
            start = date.fromisoformat(value["from"])
            end = date.fromisoformat(value["to"])
        except (KeyError, TypeError, ValueError):
            return None
        timezone_name = value.get("timezone")
        date_basis = value.get("date_basis")
        if (
            end < start or (end - start).days >= 56
            or not isinstance(timezone_name, str) or not timezone_name
            or not isinstance(date_basis, str) or not date_basis
        ):
            return None
        try:
            ZoneInfo(timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return None
        return {
            "from": start.isoformat(), "to": end.isoformat(),
            "timezone": timezone_name, "date_basis": date_basis,
        }

    @classmethod
    def _safe_sources(cls, sources):
        safe = []
        for source in sources[:20]:
            if not isinstance(source, dict) or source.get("name") not in {
                "FINANCE", "PERFORMANCE", "ANALYTICS", "RETURNS", "TARIFF",
                "COST", "TAX", "OWNER_DECLARED_PRICE", "SELLER_PRICE",
            }:
                continue
            safe.append({
                key: source[key] for key in cls._SAFE_SOURCE_FIELDS if key in source
            })
        return safe

    @staticmethod
    def _source(sources, name):
        return next((item for item in sources if item.get("name") == name), None)

    @staticmethod
    def _same_source_window(finance, performance):
        return (
            finance.get("source_window_start") == performance.get("source_window_start")
            and finance.get("source_window_end") == performance.get("source_window_end")
            and finance.get("source_date_basis") == performance.get("source_date_basis")
            and finance.get("timezone") == performance.get("timezone")
        )

    @staticmethod
    def _count(value):
        if type(value) is int and 0 <= value <= 1_000_000_000:
            return value
        return None

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not result.is_finite() or len(result.as_tuple().digits) > 15
            or result.adjusted() > 12 or result.adjusted() < -12
        ):
            return None
        return result

    @classmethod
    def _money(cls, value):
        if value is None:
            return None
        return format(value.quantize(cls.MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")

    @classmethod
    def _percent(cls, value):
        return value.quantize(cls.PERCENT_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}

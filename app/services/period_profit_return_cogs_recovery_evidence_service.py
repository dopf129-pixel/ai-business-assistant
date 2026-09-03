from math import isfinite


class PeriodProfitReturnCogsRecoveryEvidenceService:
    """Conservative read-only evidence for potential return COGS recovery."""

    CUSTOMER_RETURN_TYPES = {
        "clientreturn",
        "fullreturn",
    }
    RETURN_PLACE_STATUS = (
        "ArrivedAtReturnPlace"
    )
    COMPENSATED_STATUS = "Received"

    def __init__(
        self,
        cost_service,
        sale_lineage_evidence_service=None,
    ):
        self.cost_service = cost_service
        self.sale_lineage_evidence_service = (
            sale_lineage_evidence_service
        )

    def analyze(
        self,
        return_evidence,
        products,
    ):
        source = dict(
            return_evidence or {}
        )

        if source.get("error") is True:
            return self._unavailable(
                "RETURN_EVIDENCE_UNAVAILABLE"
            )

        if source.get("status") not in {
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
            "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL",
        }:
            return self._unavailable(
                "RETURN_EVIDENCE_REQUIRED"
            )

        records = source.get("records")
        if not isinstance(records, list):
            return self._unavailable(
                "RETURN_RECORDS_INVALID"
            )

        cost_index = self._cost_index(
            products
        )

        candidate_units = 0
        candidate_value = 0.0
        compensated_units = 0
        unresolved_units = 0
        customer_return_units = 0
        candidate_records = []
        compensated_records = []
        unresolved_records = []

        for record in records:
            if not isinstance(record, dict):
                continue

            quantity = self._quantity(
                record.get("quantity")
            )
            if quantity is None:
                unresolved_records.append({
                    "reason": "QUANTITY_INVALID",
                    "return_id": (
                        record.get("id")
                        or record.get("return_id")
                    ),
                })
                continue

            return_type = str(
                record.get("type") or ""
            ).strip().lower()

            if (
                return_type
                not in self.CUSTOMER_RETURN_TYPES
            ):
                continue

            customer_return_units += (
                quantity
            )

            compensation_status = str(
                record.get(
                    "compensation_status_sys_name"
                )
                or ""
            ).strip()

            if (
                compensation_status
                == self.COMPENSATED_STATUS
            ):
                compensated_units += (
                    quantity
                )
                compensated_records.append(
                    self._record_summary(
                        record,
                        quantity,
                        "COMPENSATED",
                    )
                )
                continue

            visual_status = str(
                record.get(
                    "visual_status_sys_name"
                )
                or ""
            ).strip()

            if (
                visual_status
                != self.RETURN_PLACE_STATUS
            ):
                unresolved_units += (
                    quantity
                )
                unresolved_records.append(
                    self._record_summary(
                        record,
                        quantity,
                        "RECOVERY_STATUS_UNPROVEN",
                    )
                )
                continue

            cost = self._record_cost(
                record,
                cost_index,
            )
            if cost is None:
                unresolved_units += (
                    quantity
                )
                unresolved_records.append(
                    self._record_summary(
                        record,
                        quantity,
                        "CURRENT_COST_UNAVAILABLE",
                    )
                )
                continue

            value = cost * quantity
            if not isfinite(value):
                return self._unavailable(
                    "RETURN_COGS_VALUE_INVALID"
                )

            candidate_units += quantity
            candidate_value += value

            row = self._record_summary(
                record,
                quantity,
                "RETURN_PLACE_CANDIDATE",
            )
            row["current_cost_per_unit"] = (
                round(cost, 2)
            )
            row[
                "candidate_value_at_current_cost"
            ] = round(value, 2)
            candidate_records.append(row)

        complete_return_sample = (
            source.get("complete") is True
            and source.get(
                "return_record_count_exact"
            )
            is True
        )

        sale_lineage_evidence = (
            self._sale_lineage_evidence(
                source
            )
        )
        lineage_index = (
            self._sale_lineage_index(
                sale_lineage_evidence
            )
        )
        matched_lineage_records = 0
        unmatched_lineage_records = 0
        ambiguous_lineage_records = 0
        unresolved_lineage_records = 0

        for row in candidate_records:
            lineage = lineage_index.get(
                self._lineage_key(
                    row
                )
            )
            if lineage is None:
                row[
                    "originating_sale_lineage_status"
                ] = (
                    "LINEAGE_EVIDENCE_UNAVAILABLE"
                    if not lineage_index
                    else "LINEAGE_RECORD_NOT_FOUND"
                )
                row[
                    "originating_sale_accrual_date"
                ] = None
                unresolved_lineage_records += 1
                continue

            status = str(
                lineage.get(
                    "lineage_status"
                )
                or ""
            )
            row[
                "originating_sale_lineage_status"
            ] = status
            row[
                "originating_sale_accrual_date"
            ] = lineage.get(
                "matched_sale_accrual_date"
            )

            if (
                status
                == "MATCHED_IN_SELECTED_PERIOD"
            ):
                matched_lineage_records += 1
            elif (
                status
                == "MULTIPLE_SALE_DATES_AMBIGUOUS"
            ):
                ambiguous_lineage_records += 1
            elif (
                status
                == "SALE_NOT_FOUND_IN_SELECTED_PERIOD"
            ):
                unmatched_lineage_records += 1
            else:
                unresolved_lineage_records += 1

        sale_lineage_ready = (
            isinstance(
                sale_lineage_evidence,
                dict,
            )
            and sale_lineage_evidence.get(
                "error"
            )
            is False
            and sale_lineage_evidence.get(
                "status"
            )
            in {
                "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_READY",
                "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_PARTIAL",
            }
        )
        originating_sale_period_confirmed = (
            complete_return_sample
            and sale_lineage_ready
            and sale_lineage_evidence.get(
                "finance_period_complete"
            )
            is True
            and bool(
                candidate_records
            )
            and matched_lineage_records
            == len(candidate_records)
        )

        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
            ),
            "customer_return_units": (
                customer_return_units
            ),
            "candidate_recovery_units": (
                candidate_units
            ),
            "candidate_value_at_current_cost": (
                round(candidate_value, 2)
            ),
            "compensated_units": (
                compensated_units
            ),
            "unresolved_units": (
                unresolved_units
            ),
            "candidate_records": (
                candidate_records
            ),
            "compensated_records": (
                compensated_records
            ),
            "unresolved_records": (
                unresolved_records
            ),
            "return_sample_complete": (
                complete_return_sample
            ),
            "current_cost_basis_only": True,
            "historical_cost_basis_confirmed": False,
            "originating_sale_period_confirmed": (
                originating_sale_period_confirmed
            ),
            "originating_sale_quantity_confirmed": False,
            "sale_lineage_evidence_available": (
                sale_lineage_ready
            ),
            "sale_lineage_finance_period_complete": (
                sale_lineage_evidence.get(
                    "finance_period_complete"
                )
                is True
                if sale_lineage_ready
                else False
            ),
            "sale_lineage_candidate_record_count": (
                len(candidate_records)
            ),
            "sale_lineage_matched_candidate_record_count": (
                matched_lineage_records
            ),
            "sale_lineage_unmatched_candidate_record_count": (
                unmatched_lineage_records
            ),
            "sale_lineage_ambiguous_candidate_record_count": (
                ambiguous_lineage_records
            ),
            "sale_lineage_unresolved_candidate_record_count": (
                unresolved_lineage_records
            ),
            "sale_lineage_matching_basis": (
                sale_lineage_evidence.get(
                    "matching_basis"
                )
                if sale_lineage_ready
                else None
            ),
            "saleable_inventory_recovery_confirmed": False,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "compensation_accounting_treatment_confirmed": False,
            "compensation_profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }

    def _sale_lineage_evidence(
        self,
        return_evidence,
    ):
        service = (
            self.sale_lineage_evidence_service
        )
        if service is None:
            return None

        analyzer = getattr(
            service,
            "analyze",
            None,
        )
        if not callable(analyzer):
            return None

        try:
            result = analyzer(
                return_evidence
            )
        except Exception:
            return {
                "error": True,
                "status": (
                    "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_UNAVAILABLE"
                ),
                "finance_period_complete": False,
            }

        if not isinstance(
            result,
            dict,
        ):
            return {
                "error": True,
                "status": (
                    "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_UNAVAILABLE"
                ),
                "finance_period_complete": False,
            }

        return dict(result)

    @classmethod
    def _sale_lineage_index(
        cls,
        evidence,
    ):
        source = dict(
            evidence
            or {}
        )
        if source.get("error") is True:
            return {}

        records = source.get(
            "lineage_records"
        )
        if not isinstance(
            records,
            list,
        ):
            return {}

        result = {}
        for record in records:
            if not isinstance(
                record,
                dict,
            ):
                continue
            result[
                cls._lineage_key(
                    record
                )
            ] = dict(record)
        return result

    @staticmethod
    def _lineage_key(record):
        return (
            str(
                record.get(
                    "return_id"
                )
                or ""
            ),
            str(
                record.get(
                    "posting_number"
                )
                or ""
            ).strip(),
            str(
                record.get("sku")
                or ""
            ).strip(),
        )

    def _cost_index(self, products):
        result = {}

        for product in products or []:
            normalized = self._normalize_product(
                product
            )
            if normalized is None:
                continue

            product_id = normalized.get(
                "product_id"
            )
            cost = self._resolve_cost(
                normalized
            )
            if cost is None:
                continue

            for value in (
                normalized.get("sku"),
                normalized.get("offer_id"),
                product_id,
            ):
                key = str(
                    value or ""
                ).strip()
                if key:
                    result[key] = cost

        return result

    def _resolve_cost(self, product):
        for field in (
            "cost",
            "cost_price",
        ):
            if product.get(field) is not None:
                return self._cost_number(
                    product.get(field)
                )

        product_id = product.get(
            "product_id"
        )
        if product_id is None:
            return None

        getter = getattr(
            self.cost_service,
            "get_cost",
            None,
        )
        if not callable(getter):
            return None

        try:
            row = getter(product_id)
        except Exception:
            return None

        if isinstance(row, dict):
            value = row.get("cost_price")
            if value is None:
                value = row.get("cost")
        elif isinstance(row, (tuple, list)):
            value = (
                row[3]
                if len(row) > 3
                else None
            )
        else:
            value = row

        return self._cost_number(value)

    @staticmethod
    def _normalize_product(product):
        if isinstance(product, dict):
            return dict(product)

        if (
            isinstance(product, (tuple, list))
            and len(product) >= 3
        ):
            return {
                "product_id": product[0],
                "offer_id": product[1],
                "sku": product[2],
            }

        return None

    @staticmethod
    def _record_cost(
        record,
        cost_index,
    ):
        for value in (
            record.get("sku"),
            record.get("offer_id"),
        ):
            key = str(
                value or ""
            ).strip()
            if key in cost_index:
                return cost_index[key]

        return None

    @staticmethod
    def _quantity(value):
        if isinstance(value, bool):
            return None

        try:
            number = int(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

        if number <= 0:
            return None

        return number

    @staticmethod
    def _cost_number(value):
        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if (
            not isfinite(number)
            or number < 0
        ):
            return None

        return number

    @staticmethod
    def _record_summary(
        record,
        quantity,
        reason,
    ):
        return {
            "return_id": (
                record.get("id")
                or record.get("return_id")
            ),
            "posting_number": (
                record.get("posting_number")
            ),
            "sku": record.get("sku"),
            "offer_id": (
                record.get("offer_id")
            ),
            "quantity": quantity,
            "type": record.get("type"),
            "visual_status_sys_name": (
                record.get(
                    "visual_status_sys_name"
                )
            ),
            "compensation_status_sys_name": (
                record.get(
                    "compensation_status_sys_name"
                )
            ),
            "reason": reason,
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_UNAVAILABLE"
            ),
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }

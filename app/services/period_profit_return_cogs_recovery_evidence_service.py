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

    def __init__(self, cost_service):
        self.cost_service = cost_service

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
            "saleable_inventory_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "compensation_already_expected_in_account_net_accrual": True,
            "read_only": True,
            "executed": False,
        }

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

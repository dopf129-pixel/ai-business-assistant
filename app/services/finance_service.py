from decimal import Decimal, InvalidOperation

from api.ozon_client import OzonClient


class FinanceService:

    def __init__(self):

        self.ozon = OzonClient()
        self.accrual_types = {}
        self._daily_accrual_cache = {}

    def begin_read_session(self):

        self._daily_accrual_cache = {}


    def to_decimal(
        self,
        value
    ):

        try:
            return Decimal(
                str(value or "0")
            )
        except (
            InvalidOperation,
            TypeError,
            ValueError
        ):
            return Decimal("0")

    def load_accrual_types(self):

        response = (
            self.ozon
            .get_accrual_types()
        )

        if response.get("error"):

            return response

        self.accrual_types = {
            int(item.get("id")): {
                "name": item.get("name"),
                "description": item.get(
                    "description"
                )
            }
            for item in response.get(
                "accrual_types",
                []
            )
            if item.get("id") is not None
        }

        return {
            "error": False,
            "count": len(
                self.accrual_types
            )
        }

    def get_type_description(
        self,
        type_id
    ):

        try:
            type_id = int(type_id)
        except (
            TypeError,
            ValueError
        ):
            return "Неизвестный тип"

        type_info = (
            self.accrual_types
            .get(type_id)
        )

        if not type_info:
            return f"Тип {type_id}"

        return (
            type_info.get(
                "description"
            )
            or type_info.get(
                "name"
            )
            or f"Тип {type_id}"
        )

    def get_daily_account_finance(
        self,
        accrual_date
    ):

        return self.get_daily_finance(
            accrual_date,
            sku=None
        )


    def get_daily_finance(
        self,
        accrual_date,
        sku=None
    ):

        if not self.accrual_types:

            load_result = (
                self.load_accrual_types()
            )

            if load_result.get("error"):
                return load_result

        response = self._get_accruals_by_day(
            accrual_date
        )

        if response.get("error"):

            return response

        result = {
            "error": False,
            "date": str(
                accrual_date
            ),
            "sku": (
                str(sku)
                if sku is not None
                else None
            ),
            "operations": 0,
            "sales_count": 0,
            "gross_sales": Decimal("0"),
            "net_accrual": Decimal("0"),
            "commission": Decimal("0"),
            "logistics": Decimal("0"),
            "acquiring": Decimal("0"),
            "other_fees": Decimal("0"),
            "fee_breakdown": {}
        }

        for accrual in response.get(
            "accruals",
            []
        ):

            if not self._matches_sku(
                accrual,
                sku
            ):
                continue

            result["operations"] += 1

            total_amount = (
                self.to_decimal(
                    accrual
                    .get(
                        "total_amount",
                        {}
                    )
                    .get("amount")
                )
            )

            result["net_accrual"] += (
                total_amount
            )

            category = accrual.get(
                "accrued_category"
            )

            if category == "POSTING":

                self._process_posting(
                    accrual,
                    sku,
                    result
                )

            self._process_item_fees(
                accrual,
                sku,
                result
            )

        result["other_fees"] = (
            result["net_accrual"]
            - result["gross_sales"]
            - result["commission"]
            - result["logistics"]
            - result["acquiring"]
        )

        return self._serialize_result(
            result
        )

    def _get_accruals_by_day(
        self,
        accrual_date
    ):

        cache_key = str(
            accrual_date
        )

        if (
            cache_key
            in self._daily_accrual_cache
        ):
            return (
                self._daily_accrual_cache[
                    cache_key
                ]
            )

        response = (
            self.ozon
            .get_accruals_by_day(
                accrual_date
            )
        )

        if (
            isinstance(
                response,
                dict
            )
            and response.get(
                "error"
            ) is not True
        ):
            self._daily_accrual_cache[
                cache_key
            ] = response

        return response


    def _matches_sku(
        self,
        accrual,
        sku
    ):

        if sku is None:
            return True

        target_sku = str(sku)

        posting = accrual.get(
            "posting"
        ) or {}

        for product in posting.get(
            "products",
            []
        ):

            if str(
                product.get("sku")
            ) == target_sku:
                return True

        item_fees = accrual.get(
            "item_fees"
        ) or {}

        for item in item_fees.get(
            "fees",
            []
        ):

            if str(
                item.get("sku")
            ) == target_sku:
                return True

        return False

    def _process_posting(
        self,
        accrual,
        sku,
        result
    ):

        posting = accrual.get(
            "posting"
        ) or {}

        target_sku = (
            str(sku)
            if sku is not None
            else None
        )

        for product in posting.get(
            "products",
            []
        ):

            product_sku = str(
                product.get("sku")
            )

            if (
                target_sku is not None
                and product_sku
                != target_sku
            ):
                continue

            commission_data = (
                product.get(
                    "commission"
                )
                or {}
            )

            sale_amount = (
                self.to_decimal(
                    commission_data
                    .get(
                        "sale_amount",
                        {}
                    )
                    .get("amount")
                )
            )

            sale_commission = (
                self.to_decimal(
                    commission_data
                    .get(
                        "sale_commission",
                        {}
                    )
                    .get("amount")
                )
            )

            result["sales_count"] += 1
            result["gross_sales"] += (
                sale_amount
            )
            result["commission"] += (
                sale_commission
            )

            delivery = (
                product.get(
                    "delivery"
                )
                or {}
            )

            for service in delivery.get(
                "services",
                []
            ):

                self._add_fee(
                    result,
                    service.get("type_id"),
                    self.to_decimal(
                        service
                        .get(
                            "accrued",
                            {}
                        )
                        .get("amount")
                    )
                )

    def _process_item_fees(
        self,
        accrual,
        sku,
        result
    ):

        item_fees = accrual.get(
            "item_fees"
        ) or {}

        target_sku = (
            str(sku)
            if sku is not None
            else None
        )

        for item in item_fees.get(
            "fees",
            []
        ):

            item_sku = str(
                item.get("sku")
            )

            if (
                target_sku is not None
                and item_sku
                != target_sku
            ):
                continue

            for fee in item.get(
                "fees",
                []
            ):

                self._add_fee(
                    result,
                    fee.get("type_id"),
                    self.to_decimal(
                        fee
                        .get(
                            "accrued",
                            {}
                        )
                        .get("amount")
                    )
                )

    def _add_fee(
        self,
        result,
        type_id,
        amount
    ):

        description = (
            self.get_type_description(
                type_id
            )
        )

        result["fee_breakdown"][
            description
        ] = (
            result["fee_breakdown"]
            .get(
                description,
                Decimal("0")
            )
            + amount
        )

        try:
            type_id = int(type_id)
        except (
            TypeError,
            ValueError
        ):
            return

        if type_id == 1:

            result["acquiring"] += (
                amount
            )

        elif type_id in (
            29,
            32,
            98
        ):

            result["logistics"] += (
                amount
            )

        elif type_id == 69:

            result["commission"] += (
                amount
            )

    def _serialize_result(
        self,
        result
    ):

        decimal_fields = (
            "gross_sales",
            "net_accrual",
            "commission",
            "logistics",
            "acquiring",
            "other_fees"
        )

        for field in decimal_fields:

            result[field] = float(
                result[field]
                .quantize(
                    Decimal("0.01")
                )
            )

        result["fee_breakdown"] = {
            key: float(
                value.quantize(
                    Decimal("0.01")
                )
            )
            for key, value
            in result[
                "fee_breakdown"
            ].items()
        }

        return result
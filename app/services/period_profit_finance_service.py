from decimal import Decimal, InvalidOperation

from services.finance_service import FinanceService


class PeriodProfitSellerRevenueUnavailable(Exception):
    """Raised when Ozon does not provide authoritative seller revenue."""


class PeriodProfitFinanceService(FinanceService):
    """Period Profit finance view with strict seller-price revenue semantics."""

    def get_daily_finance(self, accrual_date, sku=None):
        try:
            return super().get_daily_finance(accrual_date, sku=sku)
        except PeriodProfitSellerRevenueUnavailable:
            return {
                "error": True,
                "code": "FINANCE_SELLER_REVENUE_UNAVAILABLE",
                "date": str(accrual_date),
                "sku": str(sku) if sku is not None else None,
                "complete": False,
            }

    @staticmethod
    def _required_money(money):
        if not isinstance(money, dict):
            return None

        raw_amount = money.get("amount")
        if raw_amount is None:
            return None

        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError, ValueError):
            return None

        if not amount.is_finite():
            return None

        return amount

    def _process_posting(self, accrual, sku, result):
        posting = accrual.get("posting") or {}
        target_sku = str(sku) if sku is not None else None

        for product in posting.get("products", []):
            product_sku = str(product.get("sku"))

            if target_sku is not None and product_sku != target_sku:
                continue

            commission_data = product.get("commission") or {}
            seller_price = self._required_money(
                commission_data.get("seller_price")
            )
            if seller_price is None:
                raise PeriodProfitSellerRevenueUnavailable()

            sale_commission = self.to_decimal(
                commission_data.get("sale_commission", {}).get("amount")
            )

            result["sales_count"] += 1
            result["gross_sales"] += seller_price
            result["commission"] += sale_commission

            delivery = product.get("delivery") or {}
            for service in delivery.get("services", []):
                self._add_fee(
                    result,
                    service.get("type_id"),
                    self.to_decimal(
                        service.get("accrued", {}).get("amount")
                    ),
                )

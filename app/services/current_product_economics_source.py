from datetime import datetime, timezone


class CurrentProductEconomicsSource:
    """Loads current Ozon commercial facts without calculating profit."""

    def __init__(self, ozon_client, finance_service=None):
        self.ozon_client = ozon_client
        self.finance_service = finance_service

    def get(self, sku, product_id=None, accrual_dates=None):
        response = self.ozon_client.get_product_prices(
            product_id=product_id,
            offer_id=sku
        )
        if response.get("error"):
            return {
                "error": True,
                "sku": str(sku),
                "product_id": self._text(product_id),
                "message": response.get("message"),
                "missing_data": ["current_price"]
            }

        item = self._find_item(
            response.get("items") or [], sku, product_id
        )
        if not item:
            return self._empty_result(sku, product_id)

        price = item.get("price") or {}
        seller_price = self._number(
            price.get("marketing_seller_price")
        )
        if seller_price is None:
            seller_price = self._number(price.get("price"))

        commission = self._fbo_commission(
            item.get("commissions") or [], seller_price
        )
        acquiring = self._acquiring_average(
            sku, accrual_dates or []
        )
        values = {
            "current_price": seller_price,
            "commission": commission["amount"],
            "logistics": commission["logistics"],
            "last_mile": None,
            "acquiring": acquiring,
            "buyout_rate": None
        }

        return {
            "error": False,
            "sku": str(item.get("offer_id") or sku),
            "product_id": self._text(
                item.get("product_id") or product_id
            ),
            "seller_price": seller_price,
            "commission_rate": commission["rate"],
            "commission_amount": commission["amount"],
            "logistics": commission["logistics"],
            "last_mile": None,
            "acquiring_average": acquiring,
            "buyout_rate": None,
            "buyout_sample_size": None,
            "as_of": self._now(),
            "missing_data": [
                name for name, value in values.items()
                if value is None
            ]
        }

    def _empty_result(self, sku, product_id):
        return {
            "error": False,
            "sku": str(sku),
            "product_id": self._text(product_id),
            "seller_price": None,
            "commission_rate": None,
            "commission_amount": None,
            "logistics": None,
            "last_mile": None,
            "acquiring_average": None,
            "buyout_rate": None,
            "buyout_sample_size": None,
            "as_of": self._now(),
            "missing_data": [
                "current_price", "commission", "logistics",
                "last_mile", "acquiring", "buyout_rate"
            ]
        }

    def _find_item(self, items, sku, product_id):
        target_product_id = self._text(product_id)
        for item in items:
            if str(item.get("offer_id")) != str(sku):
                continue
            if (
                target_product_id is not None
                and self._text(item.get("product_id"))
                != target_product_id
            ):
                continue
            return item
        return None

    def _fbo_commission(self, commissions, seller_price):
        for item in commissions:
            schema = str(item.get("sale_schema") or "").upper()
            if schema and schema != "FBO":
                continue
            rate = self._number(item.get("percent"))
            amount = (
                round(seller_price * rate / 100, 2)
                if seller_price is not None and rate is not None
                else None
            )
            return {
                "rate": rate,
                "amount": amount,
                "logistics": self._number(
                    item.get("fbo_deliv_to_customer_amount")
                )
            }
        return {"rate": None, "amount": None, "logistics": None}

    def _acquiring_average(self, sku, accrual_dates):
        if not self.finance_service or not accrual_dates:
            return None
        total = 0.0
        sales = 0
        for accrual_date in accrual_dates:
            result = self.finance_service.get_daily_finance(
                accrual_date, sku=sku
            )
            if result.get("error"):
                continue
            count = int(result.get("sales_count") or 0)
            if count <= 0:
                continue
            total += abs(float(result.get("acquiring") or 0))
            sales += count
        return round(total / sales, 2) if sales else None

    def _number(self, value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _text(self, value):
        return str(value) if value is not None else None

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

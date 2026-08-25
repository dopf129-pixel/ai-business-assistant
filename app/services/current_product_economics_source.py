from datetime import datetime, timezone


class CurrentProductEconomicsSource:
    """Loads current Ozon commercial facts without calculating profit."""

    LAST_MILE_LABELS = (
        "Последняя миля",
        "Доставка до места выдачи",
        "Выдача товара"
    )

    def __init__(self, ozon_client, finance_service=None):
        self.ozon_client = ozon_client
        self.finance_service = finance_service

    def get(
        self,
        sku,
        product_id=None,
        accrual_dates=None,
        buyout_since=None,
        buyout_to=None,
        buyout_sample_size=50
    ):
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
            response.get("items") or [],
            sku,
            product_id
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
            item.get("commissions") or {},
            seller_price
        )
        finance = self._finance_averages(
            sku,
            accrual_dates or []
        )
        buyout = self._buyout_rate(
            sku=sku,
            since=buyout_since,
            to=buyout_to,
            sample_size=buyout_sample_size
        )

        logistics = finance["logistics"]
        last_mile = finance["last_mile"]
        acquiring = finance["acquiring"]

        values = {
            "current_price": seller_price,
            "commission": commission["amount"],
            "logistics": logistics,
            "last_mile": last_mile,
            "acquiring": acquiring
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
            "logistics": logistics,
            "last_mile": last_mile,
            "acquiring_average": acquiring,
            "current_delivery_tariff": commission[
                "delivery_to_customer"
            ],
            "finance_sample_sales": finance["sales_count"],
            "finance_sample_days": finance["days"],
            "buyout_rate": buyout["rate"],
            "buyout_sample_size": buyout["sample_size"],
            "buyout_delivered": buyout["delivered"],
            "buyout_cancelled": buyout["cancelled"],
            "buyout_basis": (
                "last_completed_fbo_postings"
                if buyout["rate"] is not None
                else None
            ),
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
            "current_delivery_tariff": None,
            "finance_sample_sales": 0,
            "finance_sample_days": 0,
            "buyout_rate": None,
            "buyout_sample_size": None,
            "buyout_delivered": None,
            "buyout_cancelled": None,
            "buyout_basis": None,
            "as_of": self._now(),
            "missing_data": [
                "current_price",
                "commission",
                "logistics",
                "last_mile",
                "acquiring"
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
        if isinstance(commissions, dict):
            rate = self._number(
                commissions.get("sales_percent_fbo")
            )
            return {
                "rate": rate,
                "amount": self._commission_amount(
                    seller_price,
                    rate
                ),
                "delivery_to_customer": self._number(
                    commissions.get("fbo_deliv_to_customer_amount")
                )
            }

        if isinstance(commissions, list):
            for item in commissions:
                if not isinstance(item, dict):
                    continue
                schema = str(
                    item.get("sale_schema") or ""
                ).upper()
                if schema and schema != "FBO":
                    continue
                rate = self._number(item.get("percent"))
                return {
                    "rate": rate,
                    "amount": self._commission_amount(
                        seller_price,
                        rate
                    ),
                    "delivery_to_customer": self._number(
                        item.get("fbo_deliv_to_customer_amount")
                    )
                }

        return {
            "rate": None,
            "amount": None,
            "delivery_to_customer": None
        }

    def _commission_amount(self, seller_price, rate):
        if seller_price is None or rate is None:
            return None
        return round(seller_price * rate / 100, 2)

    def _finance_averages(self, sku, accrual_dates):
        empty = {
            "acquiring": None,
            "logistics": None,
            "last_mile": None,
            "sales_count": 0,
            "days": 0
        }
        if not self.finance_service or not accrual_dates:
            return empty

        acquiring_total = 0.0
        logistics_total = 0.0
        last_mile_total = 0.0
        acquiring_seen = False
        logistics_seen = False
        last_mile_seen = False
        sales_count = 0
        days = 0

        for accrual_date in accrual_dates:
            result = self.finance_service.get_daily_finance(
                accrual_date,
                sku=sku
            )
            if result.get("error"):
                continue

            day_sales = int(result.get("sales_count") or 0)
            if day_sales <= 0:
                continue

            days += 1
            sales_count += day_sales
            breakdown = result.get("fee_breakdown") or {}

            if "Эквайринг" in breakdown:
                acquiring_seen = True
                acquiring_total += abs(
                    float(breakdown.get("Эквайринг") or 0)
                )

            if "Логистика" in breakdown:
                logistics_seen = True
                logistics_total += abs(
                    float(breakdown.get("Логистика") or 0)
                )

            for label in self.LAST_MILE_LABELS:
                if label not in breakdown:
                    continue
                last_mile_seen = True
                last_mile_total += abs(
                    float(breakdown.get(label) or 0)
                )

        if sales_count <= 0:
            return empty

        return {
            "acquiring": (
                round(acquiring_total / sales_count, 2)
                if acquiring_seen
                else None
            ),
            "logistics": (
                round(logistics_total / sales_count, 2)
                if logistics_seen
                else None
            ),
            "last_mile": (
                round(last_mile_total / sales_count, 2)
                if last_mile_seen
                else None
            ),
            "sales_count": sales_count,
            "days": days
        }

    def _buyout_rate(self, sku, since, to, sample_size):
        empty = {
            "rate": None,
            "sample_size": None,
            "delivered": None,
            "cancelled": None
        }

        if not since or not to:
            return empty

        result = self.ozon_client.get_fbo_postings(
            since=since,
            to=to,
            limit=1000,
            offset=0,
            direction="DESC"
        )
        if result.get("error"):
            return empty

        completed = []
        for posting in result.get("result") or []:
            status = str(posting.get("status") or "").lower()
            if status not in ("delivered", "cancelled"):
                continue
            if not self._posting_has_sku(posting, sku):
                continue
            completed.append(status)
            if len(completed) >= int(sample_size):
                break

        if not completed:
            return empty

        delivered = completed.count("delivered")
        cancelled = completed.count("cancelled")
        total = len(completed)

        return {
            "rate": round(delivered / total * 100, 2),
            "sample_size": total,
            "delivered": delivered,
            "cancelled": cancelled
        }

    def _posting_has_sku(self, posting, sku):
        target = str(sku)
        for product in posting.get("products") or []:
            if str(product.get("offer_id")) == target:
                return True
            if str(product.get("sku")) == target:
                return True
        return False

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

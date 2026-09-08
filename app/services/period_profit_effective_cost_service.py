from services.cost_service import ProductCostService


class PeriodProfitEffectiveCostService(ProductCostService):
    """Resolve bounded seller-confirmed cost evidence for Period Profit."""

    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        historical = self.get_historical_cost_evidence(
            at_date,
            product_id=product_id,
            sku=sku,
            offer_id=offer_id,
        )
        if not isinstance(historical, dict):
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_HISTORY_RESPONSE_INVALID"
            )
        if historical.get("error") is True:
            return self._effective_unavailable(
                historical.get("code") or "PERIOD_PROFIT_COST_HISTORY_UNAVAILABLE"
            )
        if historical.get("status") == "PRODUCT_COST_HISTORY_AMBIGUOUS":
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_HISTORY_AMBIGUOUS"
            )

        if historical.get("historical_cost_confirmed") is True:
            effective_from = self._date(historical.get("effective_from"))
            effective_through = self._date(historical.get("effective_through"))
            target = self._date(at_date)
            if effective_through is None:
                return self._effective_unavailable(
                    "PERIOD_PROFIT_COST_HISTORY_UNBOUNDED"
                )
            if (
                effective_from is None
                or target is None
                or target < effective_from
                or target > effective_through
            ):
                return self._effective_unavailable(
                    "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
                )

            result = dict(historical)
            result["effective_cost_confirmed"] = True
            result["cost_basis"] = "SELLER_CONFIRMED_BOUNDED_PERIOD"
            return result

        timeline = self._has_history_timeline(
            product_id=product_id,
            sku=sku,
            offer_id=offer_id,
        )
        if timeline is None:
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_HISTORY_UNAVAILABLE"
            )
        if timeline:
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE"
            )
        return self._effective_unavailable(
            "PERIOD_PROFIT_COST_HISTORY_MISSING"
        )

    def _has_history_timeline(self, product_id=None, sku=None, offer_id=None):
        clauses, values = self._identity_where(product_id, sku, offer_id)
        if not clauses:
            return None
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM product_cost_history WHERE ("
                + " OR ".join(clauses)
                + ") LIMIT 1",
                tuple(values),
            )
            return cursor.fetchone() is not None
        except Exception:
            return None
        finally:
            conn.close()

    @classmethod
    def _identity_where(cls, product_id=None, sku=None, offer_id=None):
        product_key = cls._text(product_id)
        sku_key = cls._text(sku)
        offer_key = cls._text(offer_id)
        if product_key:
            return ["product_id = ?"], [product_key]
        clauses = []
        values = []
        if sku_key:
            clauses.append("sku = ?")
            values.append(sku_key)
        if offer_key:
            clauses.append("offer_id = ?")
            values.append(offer_key)
        return clauses, values

    @staticmethod
    def _effective_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
            "effective_cost_confirmed": False,
            "historical_cost_confirmed": False,
            "cost_price": None,
        }

from math import isfinite

from services.cost_service import ProductCostService


class PeriodProfitEffectiveCostService(ProductCostService):
    """Resolve seller-confirmed cost versions for Period Profit without rewriting history.

    Once any historical version exists for a product identity, Period Profit uses only
    versions effective on or before the sale accrual date. A current product_costs row
    remains a compatibility fallback only while no historical timeline exists at all.
    """

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
        if historical.get("historical_cost_confirmed") is True:
            result = dict(historical)
            result["effective_cost_confirmed"] = True
            result["cost_basis"] = "SELLER_CONFIRMED_EFFECTIVE_DATE"
            return result
        if historical.get("status") == "PRODUCT_COST_HISTORY_AMBIGUOUS":
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_HISTORY_AMBIGUOUS"
            )

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
            return {
                "error": True,
                "code": "PERIOD_PROFIT_COST_HISTORY_NOT_EFFECTIVE",
                "status": "PERIOD_PROFIT_EFFECTIVE_COST_UNAVAILABLE",
                "effective_cost_confirmed": False,
                "historical_cost_confirmed": False,
                "cost_price": None,
                "at_date": str(at_date),
            }

        current = self._resolve_unique_current_cost(
            product_id=product_id,
            sku=sku,
            offer_id=offer_id,
        )
        if current is None:
            return self._effective_unavailable(
                "PERIOD_PROFIT_CURRENT_COST_UNAVAILABLE"
            )

        cost = self._cost_number(current[3])
        if cost is None or not isfinite(cost):
            return self._effective_unavailable(
                "PERIOD_PROFIT_CURRENT_COST_INVALID"
            )

        return {
            "error": False,
            "status": "PERIOD_PROFIT_EFFECTIVE_COST_READY",
            "product_id": str(current[0]),
            "sku": str(current[1]) if current[1] is not None else None,
            "offer_id": str(current[2]) if current[2] is not None else None,
            "cost_price": round(cost, 2),
            "currency": str(current[4]),
            "effective_from": None,
            "source": "LEGACY_CURRENT_COST",
            "historical_cost_confirmed": False,
            "effective_cost_confirmed": True,
            "cost_basis": "LEGACY_CURRENT_COST_NO_HISTORY",
            "at_date": str(at_date),
        }

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

    def _resolve_unique_current_cost(self, product_id=None, sku=None, offer_id=None):
        product_key = self._text(product_id)
        if product_key:
            try:
                return self.get_cost(product_key)
            except Exception:
                return None

        sku_key = self._text(sku)
        offer_key = self._text(offer_id)
        if not sku_key and not offer_key:
            return None
        try:
            rows = self.get_all_costs()
        except Exception:
            return None

        matched = []
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) < 6:
                continue
            row_sku = self._text(row[1])
            row_offer = self._text(row[2])
            if (sku_key and row_sku == sku_key) or (offer_key and row_offer == offer_key):
                matched.append(row)
        return matched[0] if len(matched) == 1 else None

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

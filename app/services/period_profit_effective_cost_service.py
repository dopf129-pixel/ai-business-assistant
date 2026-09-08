from services.cost_service import ProductCostService


class PeriodProfitEffectiveCostService(ProductCostService):
    """Resolve seller-confirmed cost evidence for Period Profit.

    Two evidence forms are intentionally distinct:
    - bounded historical evidence proves a closed past interval;
    - an explicit seller cost switch proves a new operational cost from its
      effective date until the seller records another switch.

    Mutable ``product_costs`` rows are never historical Period Profit authority.
    """

    def __init__(self):
        super().__init__()
        self._create_switch_table()

    def _create_switch_table(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_cost_switch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                sku TEXT,
                offer_id TEXT,
                cost_price REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'RUB',
                effective_from TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED_BOT',
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, effective_from)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_switch_sku_effective
            ON product_cost_switch_history (sku, effective_from)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_cost_switch_offer_effective
            ON product_cost_switch_history (offer_id, effective_from)
            """
        )
        conn.commit()
        conn.close()

    def record_cost_switch(
        self,
        product_id,
        sku,
        offer_id,
        cost_price,
        effective_from,
        currency="RUB",
        source="SELLER_CONFIRMED_BOT",
    ):
        product_key = self._text(product_id)
        sku_key = self._text(sku)
        offer_key = self._text(offer_id)
        cost = self._cost_number(cost_price)
        effective_date = self._date(effective_from)
        currency_key = self._text(currency)
        source_key = self._text(source)
        if (
            not product_key
            or (not sku_key and not offer_key)
            or cost is None
            or effective_date is None
            or not currency_key
            or not source_key
        ):
            return self._switch_record_unavailable(
                "PRODUCT_COST_SWITCH_INPUT_INVALID"
            )

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO product_cost_switch_history (
                    product_id,
                    sku,
                    offer_id,
                    cost_price,
                    currency,
                    effective_from,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_key,
                    sku_key or None,
                    offer_key or None,
                    cost,
                    currency_key,
                    effective_date.isoformat(),
                    source_key,
                ),
            )
            switch_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO product_costs (
                    product_id, sku, offer_id, cost_price, currency
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    sku = excluded.sku,
                    offer_id = excluded.offer_id,
                    cost_price = excluded.cost_price,
                    currency = excluded.currency,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    product_key,
                    sku_key or None,
                    offer_key or None,
                    cost,
                    currency_key,
                ),
            )
        except Exception as exc:
            conn.rollback()
            conn.close()
            if exc.__class__.__name__ == "IntegrityError":
                return self._switch_record_unavailable(
                    "PRODUCT_COST_SWITCH_VERSION_CONFLICT"
                )
            return self._switch_record_unavailable(
                "PRODUCT_COST_SWITCH_STORAGE_UNAVAILABLE"
            )

        conn.commit()
        conn.close()
        return {
            "error": False,
            "status": "PRODUCT_COST_SWITCH_RECORDED",
            "switch_id": switch_id,
            "product_id": product_key,
            "sku": sku_key or None,
            "offer_id": offer_key or None,
            "cost_price": round(cost, 2),
            "currency": currency_key,
            "effective_from": effective_date.isoformat(),
            "source": source_key,
            "seller_confirmed": True,
            "read_only_ozon": True,
        }

    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        switched = self._get_switch_evidence(
            at_date,
            product_id=product_id,
            sku=sku,
            offer_id=offer_id,
        )
        if not isinstance(switched, dict):
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_SWITCH_RESPONSE_INVALID"
            )
        if switched.get("error") is True:
            return self._effective_unavailable(
                switched.get("code") or "PERIOD_PROFIT_COST_SWITCH_UNAVAILABLE"
            )
        if switched.get("status") == "PRODUCT_COST_SWITCH_AMBIGUOUS":
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_SWITCH_AMBIGUOUS"
            )
        if switched.get("switch_cost_confirmed") is True:
            result = dict(switched)
            result["effective_cost_confirmed"] = True
            result["historical_cost_confirmed"] = True
            result["cost_basis"] = "SELLER_CONFIRMED_OPERATIONAL_SWITCH"
            return result

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

    def _get_switch_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        target = self._date(at_date)
        clauses, values = self._identity_where(product_id, sku, offer_id)
        if target is None or not clauses:
            return self._switch_unavailable(
                "PRODUCT_COST_SWITCH_QUERY_INVALID"
            )

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, product_id, sku, offer_id, cost_price, currency,
                       effective_from, source, recorded_at
                FROM product_cost_switch_history
                WHERE effective_from <= ? AND ("""
                + " OR ".join(clauses)
                + ") ORDER BY effective_from DESC, id DESC",
                (target.isoformat(), *values),
            )
            rows = cursor.fetchall()
        except Exception:
            conn.close()
            return self._switch_unavailable(
                "PRODUCT_COST_SWITCH_STORAGE_UNAVAILABLE"
            )
        conn.close()

        if not rows:
            return {
                "error": False,
                "status": "PRODUCT_COST_SWITCH_MISSING",
                "switch_cost_confirmed": False,
                "cost_price": None,
                "effective_from": None,
                "at_date": target.isoformat(),
            }

        latest_by_product = {}
        for row in rows:
            key = str(row[1])
            if key not in latest_by_product:
                latest_by_product[key] = row
        if len(latest_by_product) != 1:
            return {
                "error": False,
                "status": "PRODUCT_COST_SWITCH_AMBIGUOUS",
                "switch_cost_confirmed": False,
                "cost_price": None,
                "candidate_product_ids": sorted(latest_by_product),
                "at_date": target.isoformat(),
            }

        row = next(iter(latest_by_product.values()))
        cost = self._cost_number(row[4])
        effective_from = self._date(row[6])
        if cost is None or effective_from is None or effective_from > target:
            return self._switch_unavailable(
                "PRODUCT_COST_SWITCH_ROW_INVALID"
            )
        return {
            "error": False,
            "status": "PRODUCT_COST_SWITCH_READY",
            "switch_id": row[0],
            "product_id": str(row[1]),
            "sku": str(row[2]) if row[2] is not None else None,
            "offer_id": str(row[3]) if row[3] is not None else None,
            "cost_price": round(cost, 2),
            "currency": str(row[5]),
            "effective_from": effective_from.isoformat(),
            "effective_through": None,
            "source": str(row[7]),
            "recorded_at": row[8],
            "at_date": target.isoformat(),
            "switch_cost_confirmed": True,
            "seller_confirmed": True,
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
    def _switch_record_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_COST_SWITCH_RECORD_UNAVAILABLE",
            "seller_confirmed": False,
            "read_only_ozon": True,
        }

    @staticmethod
    def _switch_unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_COST_SWITCH_UNAVAILABLE",
            "switch_cost_confirmed": False,
            "cost_price": None,
        }

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

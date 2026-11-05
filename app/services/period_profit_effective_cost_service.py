from datetime import date, datetime

from services.cost_service import ProductCostService


class PeriodProfitEffectiveCostService(ProductCostService):
    """Resolve seller-confirmed cost evidence for Period Profit.

    Two evidence forms are intentionally distinct:
    - bounded historical evidence proves a closed past interval;
    - an explicit seller cost switch proves a new operational cost from its
      effective date until the seller records another switch.

    Mutable ``product_costs`` rows are never historical Period Profit authority.
    """

    def __init__(self, today_provider=None):
        self.today_provider = today_provider or date.today
        super().__init__()
        self._create_switch_table()

    def get_current_cost_date(self):
        """Return the date used by current-cost readers without caching it."""
        try:
            value = self.today_provider()
        except Exception:
            return None
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        parsed = self._date(value)
        return parsed.isoformat() if parsed is not None else None

    def get_cost(self, product_id):
        """Preserve the legacy row shape while resolving the value as of today."""
        product_key = self._text(product_id)
        current_date = self.get_current_cost_date()
        if not product_key or current_date is None:
            return None
        evidence = self.get_effective_cost_evidence(
            current_date,
            product_id=product_key,
        )
        if (
            not isinstance(evidence, dict)
            or evidence.get("error") is True
            or evidence.get("effective_cost_confirmed") is not True
        ):
            return None
        amount = self._cost_number(evidence.get("cost_price"))
        currency = self._text(evidence.get("currency"))
        if amount is None or not currency:
            return None
        return (
            product_key,
            evidence.get("sku"),
            evidence.get("offer_id"),
            amount,
            currency,
            evidence.get("effective_from"),
        )

    def get_all_costs(self):
        """Return current effective values for menu/export compatibility."""
        current_date = self.get_current_cost_date()
        if current_date is None:
            return []
        try:
            rows = super().get_all_costs()
            product_ids = {
                self._text(row[0])
                for row in rows
                if isinstance(row, (tuple, list)) and len(row) >= 1
            }
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT product_id FROM product_cost_switch_history"
                )
                product_ids.update(
                    self._text(row[0])
                    for row in cursor.fetchall()
                    if isinstance(row, (tuple, list)) and row
                )
            finally:
                conn.close()
        except Exception:
            return []

        effective_rows = []
        for product_key in sorted(value for value in product_ids if value):
            row = self.get_cost(product_key)
            if row is not None:
                effective_rows.append(row)
        return effective_rows

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
        current_date = self.get_current_cost_date()
        if (
            not product_key
            or (not sku_key and not offer_key)
            or cost is None
            or effective_date is None
            or not currency_key
            or not source_key
            or current_date is None
        ):
            return self._switch_record_unavailable(
                "PRODUCT_COST_SWITCH_INPUT_INVALID"
                if current_date is not None
                else "PRODUCT_COST_CURRENT_DATE_UNAVAILABLE"
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
            if not self._sync_current_projection(cursor, product_key, current_date):
                conn.rollback()
                conn.close()
                return self._switch_record_unavailable(
                    "PRODUCT_COST_CURRENT_PROJECTION_UNAVAILABLE"
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

    def record_cost_switches(self, switches):
        """Atomically persist dated cost switches, allowing exact replays.

        All inputs and same-date conflicts are checked before the first insert.
        The mutable product-cost projection is recalculated from the latest
        effective switch, so importing an older dated row cannot roll it back.
        """
        if not isinstance(switches, (list, tuple)) or not switches:
            return self._switch_record_unavailable(
                "PRODUCT_COST_SWITCH_INPUT_INVALID"
            )
        current_date = self.get_current_cost_date()
        if current_date is None:
            return self._switch_record_unavailable(
                "PRODUCT_COST_CURRENT_DATE_UNAVAILABLE"
            )

        normalized = []
        seen = set()
        for item in switches:
            if not isinstance(item, dict):
                return self._switch_record_unavailable(
                    "PRODUCT_COST_SWITCH_INPUT_INVALID"
                )
            product_key = self._text(item.get("product_id"))
            sku_key = self._text(item.get("sku"))
            offer_key = self._text(item.get("offer_id"))
            cost = self._cost_number(item.get("cost_price"))
            effective_date = self._date(item.get("effective_from"))
            currency_key = self._text(item.get("currency") or "RUB")
            source_key = self._text(item.get("source"))
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
            effective_text = effective_date.isoformat()
            identity = (product_key, effective_text)
            if identity in seen:
                return self._switch_record_unavailable(
                    "PRODUCT_COST_SWITCH_INPUT_DUPLICATE"
                )
            seen.add(identity)
            normalized.append(
                {
                    "product_id": product_key,
                    "sku": sku_key or None,
                    "offer_id": offer_key or None,
                    "cost_price": cost,
                    "currency": currency_key,
                    "effective_from": effective_text,
                    "source": source_key,
                }
            )

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            existing_by_identity = {}
            for item in normalized:
                cursor.execute(
                    """
                    SELECT sku, offer_id, cost_price, currency, source
                    FROM product_cost_switch_history
                    WHERE product_id = ? AND effective_from = ?
                    """,
                    (item["product_id"], item["effective_from"]),
                )
                existing = cursor.fetchone()
                if existing is None:
                    continue
                same = (
                    (existing[0] or None) == item["sku"]
                    and (existing[1] or None) == item["offer_id"]
                    and abs(float(existing[2]) - item["cost_price"]) < 0.000001
                    and str(existing[3]) == item["currency"]
                    and str(existing[4]) == item["source"]
                )
                if not same:
                    conn.rollback()
                    return self._switch_record_unavailable(
                        "PRODUCT_COST_SWITCH_VERSION_CONFLICT"
                    )
                existing_by_identity[
                    (item["product_id"], item["effective_from"])
                ] = True

            inserted = 0
            for item in normalized:
                identity = (item["product_id"], item["effective_from"])
                if identity in existing_by_identity:
                    continue
                cursor.execute(
                    """
                    INSERT INTO product_cost_switch_history (
                        product_id, sku, offer_id, cost_price, currency,
                        effective_from, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["product_id"],
                        item["sku"],
                        item["offer_id"],
                        item["cost_price"],
                        item["currency"],
                        item["effective_from"],
                        item["source"],
                    ),
                )
                inserted += 1

            touched_products = sorted({item["product_id"] for item in normalized})
            for product_key in touched_products:
                if not self._sync_current_projection(
                    cursor,
                    product_key,
                    current_date,
                ):
                    conn.rollback()
                    return self._switch_record_unavailable(
                        "PRODUCT_COST_CURRENT_PROJECTION_UNAVAILABLE"
                    )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            code = (
                "PRODUCT_COST_SWITCH_VERSION_CONFLICT"
                if exc.__class__.__name__ == "IntegrityError"
                else "PRODUCT_COST_SWITCH_STORAGE_UNAVAILABLE"
            )
            return self._switch_record_unavailable(code)
        finally:
            conn.close()

        return {
            "error": False,
            "status": "PRODUCT_COST_SWITCHES_RECORDED",
            "inserted": inserted,
            "unchanged": len(existing_by_identity),
            "count": len(normalized),
            "seller_confirmed": True,
            "read_only_ozon": True,
        }

    def get_seller_cost_identities(self):
        """Return seller-confirmed identity only, without cost values."""

        queries = (
            (
                "product_cost_history",
                "SELECT product_id, sku, offer_id "
                "FROM product_cost_history",
            ),
            (
                "product_cost_switch_history",
                "SELECT product_id, sku, offer_id "
                "FROM product_cost_switch_history",
            ),
            (
                "product_costs",
                "SELECT product_id, sku, offer_id "
                "FROM product_costs",
            ),
        )
        conn = self.get_connection()
        records = set()
        try:
            cursor = conn.cursor()
            for source, query in queries:
                cursor.execute(query)
                for row in cursor.fetchall():
                    if not isinstance(row, (tuple, list)) or len(row) < 3:
                        return {
                            "error": True,
                            "code": "PRODUCT_COST_IDENTITY_ROW_INVALID",
                            "records": [],
                        }
                    product_id = self._text(row[0])
                    sku = self._text(row[1])
                    offer_id = self._text(row[2])
                    if not product_id or (not sku and not offer_id):
                        continue
                    records.add((product_id, sku, offer_id, source))
        except Exception:
            return {
                "error": True,
                "code": "PRODUCT_COST_IDENTITY_STORAGE_UNAVAILABLE",
                "records": [],
            }
        finally:
            conn.close()

        return {
            "error": False,
            "status": "PRODUCT_COST_IDENTITIES_READY",
            "records": [
                {
                    "product_id": product_id,
                    "sku": sku or None,
                    "offer_id": offer_id or None,
                    "source": source,
                }
                for product_id, sku, offer_id, source in sorted(records)
            ],
            "cost_values_included": False,
            "read_only": True,
            "executed": False,
        }

    def get_effective_cost_evidence(
        self,
        at_date,
        product_id=None,
        sku=None,
        offer_id=None,
    ):
        """Resolve evidence using stable identity fallbacks without weakening gates.

        A product id may change in Ozon while the seller offer remains stable.  Period
        Profit therefore tries the strongest identities in order: product id, offer
        id, then SKU.  Only a pure "missing" result may fall through.  Ambiguous,
        stale/not-effective, malformed, or unavailable evidence remains fail-closed.
        Every candidate is evaluated at the original historical ``at_date``.
        """
        candidates = self._identity_candidates(
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
        )
        if not candidates:
            return self._effective_unavailable(
                "PERIOD_PROFIT_COST_IDENTITY_MISSING"
            )

        last_missing = None
        for identity in candidates:
            evidence = self._get_effective_cost_evidence_for_identity(
                at_date,
                **identity,
            )
            if (
                isinstance(evidence, dict)
                and evidence.get("code") == "PERIOD_PROFIT_COST_HISTORY_MISSING"
            ):
                last_missing = evidence
                continue
            return evidence

        return last_missing or self._effective_unavailable(
            "PERIOD_PROFIT_COST_HISTORY_MISSING"
        )

    @staticmethod
    def _sync_current_projection(cursor, product_id, current_date):
        """Keep the mutable compatibility row at the latest switch effective today.

        A future-only timeline intentionally does not create or replace the
        mutable row. Reads use the date resolver, so the effective value still
        advances at the boundary without a writer or process restart.
        """
        cursor.execute(
            """
            SELECT sku, offer_id, cost_price, currency
            FROM product_cost_switch_history
            WHERE product_id = ? AND effective_from <= ?
            ORDER BY effective_from DESC, id DESC
            LIMIT 1
            """,
            (product_id, current_date),
        )
        latest = cursor.fetchone()
        if latest is None:
            return True

        cursor.execute(
            """
            SELECT sku, offer_id, cost_price, currency
            FROM product_costs
            WHERE product_id = ?
            """,
            (product_id,),
        )
        current = cursor.fetchone()
        if current is not None and (
            (current[0] or None) == (latest[0] or None)
            and (current[1] or None) == (latest[1] or None)
            and abs(float(current[2]) - float(latest[2])) < 0.000001
            and str(current[3]) == str(latest[3])
        ):
            return True

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
            (product_id, latest[0], latest[1], latest[2], latest[3]),
        )
        return True

    def _get_effective_cost_evidence_for_identity(
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
            if historical.get("legacy_current_cost_evidence") is True and (
                self._legacy_current_cost_may_be_future_projection(
                    historical,
                    target,
                )
            ):
                return self._effective_unavailable(
                    "PERIOD_PROFIT_COST_LEGACY_PROVENANCE_AMBIGUOUS"
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

    def _legacy_current_cost_may_be_future_projection(self, evidence, target):
        product_key = self._text(evidence.get("product_id"))
        evidence_cost = self._cost_number(evidence.get("cost_price"))
        evidence_currency = self._text(evidence.get("currency"))
        evidence_timestamp = str(evidence.get("recorded_at") or "")
        if (
            not product_key
            or evidence_cost is None
            or not evidence_currency
            or not evidence_timestamp
        ):
            return False

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT cost_price, currency, recorded_at
                FROM product_cost_switch_history
                WHERE product_id = ? AND effective_from > ?
                ORDER BY effective_from ASC, id ASC
                """,
                (product_key, target.isoformat()),
            )
            future_rows = cursor.fetchall()
        except Exception:
            # If provenance cannot be checked, do not claim that it is safe.
            return True
        finally:
            conn.close()

        for row in future_rows:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return True
            future_cost = self._cost_number(row[0])
            if (
                future_cost is not None
                and abs(future_cost - evidence_cost) < 0.000001
                and str(row[1]) == evidence_currency
                and str(row[2] or "") == evidence_timestamp
            ):
                return True
        return False

    @classmethod
    def _identity_candidates(cls, product_id=None, offer_id=None, sku=None):
        candidates = []
        product_key = cls._text(product_id)
        offer_key = cls._text(offer_id)
        sku_key = cls._text(sku)
        if product_key:
            candidates.append({"product_id": product_key})
        if offer_key:
            candidates.append({"offer_id": offer_key})
        if sku_key:
            candidates.append({"sku": sku_key})
        return candidates

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

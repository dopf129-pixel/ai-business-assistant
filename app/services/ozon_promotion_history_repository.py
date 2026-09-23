"""Store imported SKU promotion totals, scoped to the connected seller account.

Imported reports are immutable evidence for exact date ranges. The service
never prorates aggregate report totals into smaller periods.
"""
import sqlite3
from decimal import Decimal
from services.ozon_account_repository import OzonAccountRepository, split_store_tenant_scope
from services.ozon_promotion_report_import import combine_reports, PromotionReportError


class PromotionHistoryRepository(OzonAccountRepository):
    def _create_table(self):
        super()._create_table()
        conn = self._connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ozon_promotion_history (
                    telegram_user_id TEXT NOT NULL,
                    seller_client_id TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    expense TEXT NOT NULL,
                    PRIMARY KEY (telegram_user_id, seller_client_id, date_from,
                                 date_to, sku, instrument)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _scope(self, tenant):
        user, seller = split_store_tenant_scope(tenant)
        seller = seller or self.active_client_id(user)
        if not user or not seller:
            raise PromotionReportError("Active seller store is required")
        return user, seller

    def import_reports(self, tenant, reports, date_from, date_to, accepted_skus):
        user, seller = self._scope(tenant)
        # Validate coverage and all numeric values before writing anything.
        summary = combine_reports(reports, date_from, date_to, accepted_skus)
        selected = {str(s) for s in accepted_skus}
        totals = {}
        for report in reports:
            for row in report["rows"]:
                if row["sku"] not in selected:
                    continue
                key = (row["sku"], row["instrument"])
                totals[key] = totals.get(key, Decimal("0")) + row["expense"]
        conn = self._connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Overwriting exact coverage is intentional; never accumulate the
            # same report again after a retry.
            conn.execute("""DELETE FROM ozon_promotion_history WHERE
                telegram_user_id=? AND seller_client_id=? AND date_from=? AND date_to=?""",
                (user, seller, date_from, date_to))
            for (sku, instrument), expense in totals.items():
                conn.execute("""INSERT INTO ozon_promotion_history
                    (telegram_user_id,seller_client_id,date_from,date_to,sku,instrument,expense)
                    VALUES (?,?,?,?,?,?,?)""",
                    (user, seller, date_from, date_to, sku, instrument, str(expense)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return summary

    def load_exact(self, tenant, date_from, date_to, accepted_skus):
        try:
            user, seller = self._scope(tenant)
        except PromotionReportError:
            return None
        selected = {str(s) for s in accepted_skus}
        if not selected:
            return None
        conn = self._connection()
        try:
            rows = conn.execute("""SELECT sku,instrument,expense FROM ozon_promotion_history
                WHERE telegram_user_id=? AND seller_client_id=? AND date_from=? AND date_to=?""",
                (user, seller, date_from, date_to)).fetchall()
        finally:
            conn.close()
        if not rows:
            return None
        totals = {"Оплата за клик": Decimal("0"), "Оплата за заказ: выбранные товары": Decimal("0")}
        for sku, instrument, expense in rows:
            if sku in selected:
                if instrument not in totals:
                    return None
                totals[instrument] += Decimal(expense)
        return {"error": False, "configured": True, "complete": True,
                "scope": "OZON_PROMOTION_REPORT_SKU",
                "expense": round(float(sum(totals.values())), 2),
                "cpc_expense": round(float(totals["Оплата за клик"]), 2),
                "order_expense": round(float(totals["Оплата за заказ: выбранные товары"]), 2),
                "matched_row_count": len(rows), "campaign_count": 0,
                "external_call_count": 0, "source": "IMPORTED_OZON_PROMOTION_REPORT"}

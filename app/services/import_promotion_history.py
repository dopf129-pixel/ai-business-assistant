"""Import Ozon historical promotion XLSX reports for a single seller store.

Example:
  PYTHONPATH=app python -m services.import_promotion_history \\
    --user-id USER --seller-client-id SELLER --sku SKU \\
    --from-date 2026-05-03 --to-date 2026-09-23 report1.xlsx report2.xlsx
"""
import argparse
from pathlib import Path
from services.ozon_account_repository import make_store_tenant_scope
from services.ozon_promotion_report_import import parse_promotion_report
from services.ozon_promotion_history_repository import PromotionHistoryRepository


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--seller-client-id", required=True)
    parser.add_argument("--sku", required=True, action="append")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    reports = [parse_promotion_report(Path(p).read_bytes()) for p in args.files]
    tenant = make_store_tenant_scope(args.user_id, args.seller_client_id)
    result = PromotionHistoryRepository().import_reports(
        tenant, reports, args.from_date, args.to_date, args.sku
    )
    print("Imported complete historical reports for selected SKU(s).")
    print("CPC:", result["cpc_expense"], "Order:", result["order_expense"])
    print("Total:", result["total_expense"])
    print("Historical data are used only for an exact matching date range.")


if __name__ == "__main__":
    main()

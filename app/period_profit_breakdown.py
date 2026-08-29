from copy import deepcopy


def build_period_profit_breakdown(summary):
    source = deepcopy(dict(summary or {}))
    if source.get("status") != "PERIOD_PROFIT_SUMMARY_READY" or source.get("error") is not False:
        return {"error": True, "code": "PERIOD_PROFIT_BREAKDOWN_SUMMARY_REQUIRED", "status": "PERIOD_PROFIT_BREAKDOWN_UNAVAILABLE"}

    products = source.get("products")
    if not isinstance(products, list):
        return {"error": True, "code": "PERIOD_PROFIT_BREAKDOWN_PRODUCTS_REQUIRED", "status": "PERIOD_PROFIT_BREAKDOWN_UNAVAILABLE"}

    ranked = sorted(
        [deepcopy(item) for item in products if isinstance(item, dict)],
        key=lambda item: (-float(item.get("profit") or 0), str(item.get("offer_id") or item.get("sku") or "")),
    )
    for index, item in enumerate(ranked, start=1):
        item["profit_rank"] = index

    return {
        "error": False,
        "status": "PERIOD_PROFIT_BREAKDOWN_READY",
        "date_from": source.get("date_from"),
        "date_to": source.get("date_to"),
        "revenue": source.get("revenue"),
        "net_accrual": source.get("net_accrual"),
        "product_cost": source.get("product_cost"),
        "tax": source.get("tax"),
        "profit": source.get("profit"),
        "margin_percent": source.get("margin_percent"),
        "products_by_profit": ranked,
        "best_product": ranked[0] if ranked else None,
        "worst_product": ranked[-1] if ranked else None,
        "profit_scope": source.get("profit_scope"),
        "returns_included": source.get("returns_included") is True,
        "advertising_included": source.get("advertising_included") is True,
        "storage_included": source.get("storage_included") is True,
    }

# Period Profit critical finance validation audit

This feature branch audit distinguishes formula-critical Ozon finance data from ancillary decomposition data for the seller-facing Period Profit path.

Formula-critical and fail-closed:
- account `total_amount` on every accrual;
- signed `sale_amount` for POSTING products, with recovery allowed only from exact `sale_price + bonus + coinvestment` when all three are valid;
- POSTING/product/commission structure required to determine revenue and sale count;
- API/transport, pagination, accrual-type and malformed core-response failures.

Ancillary and explicitly incomplete rather than fatal:
- diagnostic `seller_price`;
- `sale_commission`;
- delivery-service accrued amounts;
- item-fee accrued amounts and ancillary fee containers.

Unknown ancillary values are never treated as authoritative zero: parser-safe zero values are paired with an internal completeness marker, propagated through the Period Profit finance adapter, and the summary reports `fee_components_included=False`. Canonical profit continues to use authoritative account `net_accrual`, verified seller revenue, product cost, and configured tax.

Ozon remains strictly READ-ONLY. No Telegram fields are added. Return COGS gates are unchanged.

Failed feature verification SHAs `32af1c7c5e922f4cac63b123f1e739cbf8039be6` and `bc9005d2456094c82505d2ab1b1a68924525b48a` are permanently failed and are not release evidence.

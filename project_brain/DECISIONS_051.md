# Decision 051: Historical Finance SKU May Outlive Current Catalog

## Decision

A SKU observed in Ozon finance for the selected period remains valid product-participation evidence even when that SKU is absent from the current Ozon catalog.

Period Profit must not treat the current catalog as historical truth. For a finance SKU missing from the current catalog, product-cost identity may be recovered only from exact local cost evidence for that SKU: confirmed historical cost effective by the selected period end, or one unique existing local cost record.

## Safety constraints

- account-level Ozon finance remains monetary authority;
- product/account revenue reconciliation remains mandatory;
- ambiguous SKU-to-product cost evidence fails closed;
- invalid, non-RUB or unknown cost is not inferred;
- current catalog absence is not interpreted as zero cost or zero revenue;
- Ozon remains read-only;
- no compensation or Return COGS double counting is introduced.

## Rationale

Historical sales can legitimately reference products no longer present in a current product-list response. Requiring current catalog membership would incorrectly make valid historical finance periods unreportable. Local cost history already provides the durable accounting identity needed to recover those historical rows safely.

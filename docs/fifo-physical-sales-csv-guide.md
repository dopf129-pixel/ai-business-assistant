# FIFO physical-sales CSV

This is an owner-entered evidence format for recording **physical outbound sales** when the historical cost transition is being reconstructed. It is not an Ozon report and does not become complete evidence merely because a file was uploaded.

Use the empty [CSV template](templates/fifo_physical_sales_template.csv). Keep its exact five-column header and save as UTF-8 CSV; UTF-8 with BOM is also accepted. The separator is a semicolon.

| Column | Required value |
| --- | --- |
| `posting_number` | Exact posting reference used to match the finance identity later. |
| `finance_sku` | Exact numeric finance SKU for the selected FIFO case. Every row in one file must use that same SKU. |
| `quantity` | Positive whole number of units physically sent out. Decimals and zero are invalid. |
| `physical_effective_date` | The date the units physically left the seller, in `YYYY-MM-DD`. Do not substitute an order, posting-created, accrual, payment, or delivery date. |
| `row_reference` | A unique, safe reference to the owner’s source row, such as a local row number. It must not contain spreadsheet formulas. |

The parser rejects a duplicate row reference, a repeated posting/SKU identity, a different SKU, missing or extra columns, malformed quotes, invalid dates, invalid quantities, and files exceeding the size or row limits. A repeated posting/SKU with different row content is treated as a conflict; it is not merged automatically.

The parser and empty template are implemented in FR13. Telegram upload, separate period/timezone/semantics confirmation, encryption of the saved document, restart recovery, and full bridge coverage belong to later FR14–FR18 stages. Until those stages are complete and the whole finance identity set is reconciled, this CSV alone must not authorize a FIFO change or a profit result.

The raw posting and row references are sensitive. They may be sent only through the isolated parser and, after durable evidence storage is implemented, encrypted storage. Do not paste these identifiers into logs, exports, or user-facing previews.

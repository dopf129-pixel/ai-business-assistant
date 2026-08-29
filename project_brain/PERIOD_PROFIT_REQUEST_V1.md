# Period Profit Request v1

Normalizes user-facing period selection into exact `date_from` / `date_to` values for Period Profit Summary.

Supported presets: TODAY, 7D, 28D, 56D, 90D. Explicit custom date ranges are also supported.

The contract can build an immediately preceding comparable period with the same number of calendar days.

Read-only request normalization. It does not fetch data, calculate profit, mutate Product Decisions, or execute actions.

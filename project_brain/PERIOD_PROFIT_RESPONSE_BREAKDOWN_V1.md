# Period Profit Response Breakdown v1

The user-facing period-profit response now renders the Ozon fee components exposed by the summary contract when `fee_components_included=True`:

- commission;
- logistics;
- acquiring;
- other accruals/withholdings.

Source accounting values may be negative; the response displays their absolute magnitude as a cost/withholding for readability. The underlying summary values remain unchanged.

The breakdown is hidden unless the summary explicitly confirms fee component coverage. Existing warnings for returns, advertising, and storage remain unchanged.

No Ozon mutation, Product Decision mutation, Action Executor use, or automatic execution path is introduced.

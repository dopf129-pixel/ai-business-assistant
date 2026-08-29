# Period Profit Telegram Contract v1

Defines a read-only Telegram-facing menu for period profit with preset buttons: Today, 7, 28, 56, and 90 days.

Callbacks use `period_profit:<CODE>` and request comparison with the immediately preceding comparable period. Custom date entry remains supported by the underlying v61 request contract.

This module only defines UI/callback contracts. It does not perform Ozon mutation, Product Decision mutation, or execution.

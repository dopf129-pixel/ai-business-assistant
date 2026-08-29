# Period Profit Assistant App Wiring v1

`create_assistant()` now creates the production period-profit query through `create_period_profit_query()`, wraps it in `AssistantPeriodProfitRuntimeService`, and injects that runtime into `AssistantEntryService`.

As a result, explicit text requests such as `сколько я заработал за 7 дней` can use the real read-only product, finance, cost, tax, comparison, and response chain through the standard assistant entry point.

No Telegram framework dependency is introduced because no Telegram runtime/library is present in this repository. The existing framework-neutral `period_profit:<CODE>` callback contract remains available for an external UI host.

No Product Decision execution or Ozon mutation path is added.

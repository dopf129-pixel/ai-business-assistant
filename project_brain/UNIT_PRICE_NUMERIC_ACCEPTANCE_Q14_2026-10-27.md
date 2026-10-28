# Q14 — числовая приёмка модуля C

Дата: 2026-10-27
Статус: VERIFIED

## Выполнение

В изоляции запущены 21 unit-price, tariff, sensitivity, batch, Telegram, saved-plan и export test modules. Результат на Windows/Python 3.12.10: **389 passed in 7.84s**.

| Приёмка | Покрытие | Результат |
|---|---|---|
| N01/N02 | Synthetic 100 ₽/95 ₽ canonical profit, ROUND_HALF_UP, equality-vs-strictly-better thresholds at 0.01 percentage point | PASS |
| N03 | Synthetic 11%→22% tariff jump at 100.00/100.01 ₽, segmented search and adjacent-cent verification | PASS |
| N04 | Gaps, overlaps/conflicts, explicit 0%, invalid numeric values, exact-price point scope and identity/date/scheme mismatch | PASS |
| N05 | Manual point/range preview/confirmation/reopen, idempotency, tenant/store/SKU/stale callback scope | PASS |
| N06 | Legacy saved plan versions, frozen tariff revision, explicit refresh and protection from applying a stale rate at another price | PASS |
| N08 | 100 ₽ ad spend against 1,000 ₽ seller revenue vs 400 ₽ attributed revenue yields distinct 10% and 25% bases | PASS |
| N10 | Rank by ₽/successful unit, independent of total volume; ties, negative/zero baseline and no invalid growth percentage | PASS |
| N11 | Existing TaxService regimes/minimum tax, ad-dependent threshold via canonical forward, effective-date cost, and no duplicate cross-docking/last-mile charge | PASS |

## Пределы рассчитанного результата

- Candidate comparison is limited to 2–10 seller prices.
- Price grid is limited to 200 candidates and 20 tariff rules. It reports the best tested price only.
- Tariff-aware target search is limited to 20 rules and 1,024 canonical forward evaluations; unresolved tariff gaps remain unknown.
- Advertising threshold search is limited to 64 forwards per candidate and 1,024 per comparison. Thresholds are scenario results, not demand/conversion forecasts.
- These boundaries describe the checked domain; none of the outputs claims a global optimum beyond observed/tested values.

## Изоляция и отклонения

- Новый `%TEMP%` root для тестового storage и отдельный pytest basetemp; `PYTHONPATH=app`, dotenv/plugin autoload/bytecode writes disabled.
- Credential/provider-named environment variables removed from the test process without printing their values.
- Сеть, Ozon/Telegram API, `.env`, реальный бот, owner DB и реальные тарифные данные не использовались.
- Числовых расхождений и исправлений в коде по итогам приёмки не потребовалось.

Следующий этап — Q15: определить контракт задекларированной цены и проверяемой истории цены, временных окон, количества и часов источников.

# E00 — связанная приёмка модулей A–D

Status: `VERIFIED_LOCAL_ISOLATED`. Windows / Python 3.12. Все тестовые storage roots созданы для этого прогона. Реальный бот, Ozon API, live credentials, пользовательская БД и `.env` не использовались.

## Связанные пользовательские пути

- Периодная прибыль → детали/полнота/диагностика → расходы и подтверждение покрытия → возврат к исходному снимку → явное обновление точного периода → CSV/JSON — проверяется `test_public_report_flow_opens_exact_period_expenses_returns_refreshes_and_exports`.
- Synthetic calculation → сохранённый план → себестоимость и расход → verified backup → read-only restore dry-run → восстановление в новый root → чтение плана, стоимости и расхода в той же tenant scope — проверяется `tests/test_daily_use_end_to_end_restore.py`.
- После restore отдельный магазин не видит план, себестоимость или расход другого магазина; исходные проект и storage остаются на месте.
- D01–D06 проверки охватывают backup integrity, interrupted archive publication, failed restore staging, exact-target updater, stop timeout, status/readiness и bounded process lifecycle.
- A04 подтверждён на доступной выгрузке начислений: August net accrual `177282.17 ₽`, period/source coverage complete. Текущий точный bot JSON и весь 56-дневный cross-docking snapshot владельцем ещё не возвращены; фактическая приёмка остаётся pending.

## Проверка

Связанный профиль: **350 passed in 22.70s**. Он объединял два offline reconciliation tools, completeness/return/tax/reporting tests, Telegram report/expense flow, saved planning and exports, cross-docking source/checkpoint cases, lifecycle/updater/backup/restore, bounded soak и new-root restore acceptance.

Команда запускалась с отдельными `AI_ASSISTANT_STORAGE_ROOT` и `--basetemp` в свежем worktree-local каталогe. Первый запуск дал 349 passed / 1 failed из-за точного старого expected object без нового allowlisted `application.mode`; assertion обновлён, полный профиль повторён и завершился зелёным. Значение `UNAVAILABLE` соответствует старому fixture, который не задаёт mode.

## Границы

Это не полный `pytest` и не exact-head CI; некоторые ACL-sensitive tests не входят в этот профиль. E01 должен запустить стандартные Windows/Linux tests из `tests` и `app/tests`, compile и Docker build/runtime smoke на каждом публикуемом head. Merge, deploy и реальный bot run не выполнялись.

# W16 — parity расширенной экономики в плановых потребителях

Дата: 29.10.2026. Статус: DONE.

## Результат

Один и тот же versioned extended expense/strict retained-cohort контракт теперь сопровождает SKU-сценарии в sensitivity, пакетном плане, sales mix, сравнении сохранённых планов и сохранении/восстановлении. Потребители повторно используют canonical `UnitPriceScenarioService`; они не пересчитывают дополнительные расходы отдельной формулой.

- Sensitivity context включает extension и strict evidence в снимок/staleness signature; каждая ценовая ячейка передаёт те же доказательства в canonical forward.
- Batch builder принимает только per-SKU evidence для выбранного состава; build, price solver, ручные правки, advertising preview/application и refresh пересчитывают строку с тем же контрактом. Открытие выбранного batch candidate локально повторно проверяет контракт и рассчитанные расходы, не вызывает источник повторно.
- Sales mix умножает canonical per-unit additional expense на quantity и включает его до единственного агрегированного вызова `TaxService`. Строгие доказательства передаются с точной identity строки.
- Single и batch saved-plan capture сохраняют только allowlisted projections. Restore и comparison восстанавливают нужные owner/store/product/offer/SKU/sale-schema поля для строгого evidence и выполняют offline canonical calculation.
- `PlanningExtendedScenarioAdapter` ограничивает схему, JSON-объём, количества, суммы, даты и identity; raw API IDs/response и неизвестные поля не переносятся в persistence.
- Payload schema расширена до v4. Поддержка schema 1–3 сохранена; версия SQLite/DB и миграции не менялись. Calc version остаётся v2.

## Проверки

Windows, Python 3.12, синтетические fixtures, изолированный временный storage:

- Связанный профиль из 14 suites: **319 passed in 5.43s**.
- Полный репозиторий: **4,158 passed in 47.62s**.
- `py_compile` изменённых Python modules: PASS.
- `git diff --check`: PASS.
- Реальные Ozon/Telegram запросы, запуск бота, credentials, `.env` и пользовательская БД не использовались. Старый тест полного набора временно изменил tracked demo `data/tasks.json` и создал lock-файл; файл восстановлен из чистого исходного состояния, lock удалён, итоговый `git diff -- data` пуст.

## Дополнительная проверка существующей целевой цены

Общий тест проверяет ввод `11.110`, который нормализуется к `11.11`. Его старое ожидание `11.08` не соответствовало каноническому cent-exact forward. В тестовой крайности с переменными удержаниями 99.99% цена `0.11` даёт прибыль `0.01 ₽` и достигает цели 0.01%; предыдущий цент цель не достигает. Алгоритм solver в W16 не менялся — исправлено только устаревшее ожидание теста.

## Архитектурное влияние

Классификация: **Architecture Review Required**. Добавлен отдельный сериализационный adapter, изменён payload contract репозитория и протянуты доказательства через несколько существующих сервисов. Новая SQLite-схема, Ozon/API contract и Telegram production route не вводились. Независимое review и точные CI проверки выполняются на поздних этапах W38–W39.

Следующий этап: W17 — provider/source contracts; W18 отдельно отвечает за lifecycle и версии durable evidence snapshots.

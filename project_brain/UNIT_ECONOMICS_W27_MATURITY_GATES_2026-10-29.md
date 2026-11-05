# W27 — maturity gates и поздние факты фазы эксперимента

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Code commit: `927c3d05` — Gate experiment results on mature phase evidence
Зависимость: W26 immutable phase collection.

## Изменение

- Добавлены `UnitEconomicsExperimentPhaseMaturityService` и `UnitEconomicsExperimentPhaseReadinessService`. Оценка читает только последнюю сохранённую collection и не делает сетевых запросов или повторного расчёта прибыли.
- Collection должна быть полной, не превышать собственный HTTP/time budget и содержать подтверждённые finance, returns и CPC источники. Отсутствующее значение не трактуется как ноль.
- Минимальный срок — семь полностью прошедших локальных календарных дней после конца окна фазы. Проверены граница полуночи Europe/Moscow и другой timezone (America/Los_Angeles). Это операционная задержка, не статистическая гарантия.
- Eligibility gate требует не менее 30 пригодных единиц. Отдельный sold-unit gate проверяет denominator: `successful_sale_units` должен быть подтверждён и согласован с delivered quantity. Подтверждённый ноль блокирует расчёт на единицу; отсутствующее значение остаётся UNKNOWN. Никакой baseline/candidate profit не создаётся в W27; денежное сравнение реализуется в W28.
- Владелец подтверждает заданную цену, но источник не доказывает историческую цену в Ozon и не исключает несколько фактических цен внутри окна. Эти ограничения отображаются отдельным предупреждением и limitation.
- Все страницы owner-reported control events читаются с ограничением 100 записей. Изменённые/неизвестные условия сохраняют предупреждение. Результат привязывается к exact snapshot hashes/references.
- Позднее обновление источника требует новой immutable collection и нового result revision; старые revisions остаются неизменными. Точный idempotent replay возвращает созданную revision без дублирования.

## Регрессии

`tests/test_unit_economics_experiment_phase_readiness_service.py` проверяет:

- 6/7 дней и точную границу семи полных дней в локальном часовом поясе;
- зрелость при другом timezone, не совпадающем с UTC-календарём;
- меньше 30, ровно 30, Q0 и достаточную выборку с нулём выкупов;
- отсутствие количества как UNKNOWN и запрет деления на ноль;
- incomplete CPC не считается нулевым расходом;
- missing price history/mixed-price limitation;
- owner-reported changed conditions после 11 events и второй страницы истории;
- повторную оценку с тем же idempotency key;
- поздний возврат: новая collection/result revision с сохранением предыдущего результата.

## Проверки

Связанный изолированный Windows/Python профиль, 10 файлов W25–W27: **148 passed in 5.15s**.

Также:

- `py_compile` для двух новых сервисов и тестового модуля — PASS;
- `git diff --check` по staged code — PASS;
- `git diff -- data` — пусто;
- тесты использовали synthetic fixtures и временную SQLite-базу. Нет реальных Ozon-запросов, Telegram bot launch, owner database или tracked user-data изменений.

## Результат

W27 завершён. Следующий зависимый этап — W28: сравнение совместимых фаз, расчёт ₽/unit delta, tie/threshold и предупреждения о confounders без заявления причинности.

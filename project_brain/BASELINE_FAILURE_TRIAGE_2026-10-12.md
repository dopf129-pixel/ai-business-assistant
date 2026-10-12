# Разбор baseline тестов — 12.10.2026

## Исходный прогон

- Снимок: рабочая копия на HEAD `acbbabb5ee610998a336fa41496600560bc64243` с локальными изменениями комиссии, перечисленными в аудите.
- Windows / Python 3.12; временный каталог изолирован; учётные данные Ozon и Telegram отключены.
- Команда: `python -m pytest -q tests app/tests`.
- Результат: **2 849 passed, 137 failed, 0 skipped из 2 986**. Тесты не были ретушированы для получения зелёного результата.
- После изменений P00 команда стандартного `python -m pytest -q` собрала те же 2 986 проверок и тот же набор из 137 падений: 2 849 passed / 137 failed / 0 skipped. Это подтверждает, что добавление `app/tests` в `testpaths` само по себе не добавило новых ошибок.

## Группы падений

| Количество | Где | Наблюдаемая причина | Действие |
|---:|---|---|---|
| 90 | `tests` | `TASK_FILE_WRITE_LOCK_ERROR` или `TASK_FILE_KERNEL_LOCK_UNAVAILABLE` на Windows, где backend `fcntl.flock` отсутствует | P01: реализовать поддерживаемую межпроцессную блокировку Windows и проверить реальные сценарии несколькими процессами. После этого повторить весь зависимый набор. |
| 2 | `tests` | ожидание POSIX shutdown сигналов и успешного directory fsync в Windows | Развести критерии по платформе; сохранить durability контракт и подтвердить эквивалентное поведение Windows. |
| 10 | `tests/test_task_persistence_*` | readiness, capability и release assertions; часть получает BLOCKED после недоступности lock capability | Перепроверить после P01. Не менять expected, пока не установлено, что контракт устарел. Имена: `test_v383_legacy_orphan_coordination_file_never_requires_manual_deletion`, `test_v358_absent_lock_is_read_only_and_not_stale`, `test_v359_coordination_file_presence_never_infers_active_owner_or_staleness`, `test_v360_lock_check_error_preserves_unknown_presence`, `test_v367_telegram_core_composes_read_only_persistence_runtime_with_injected_owner`, `test_v463_clean_exact_sha_evidence_is_ready_for_manual_release_review`, `test_v469_runbook_ready_case_ends_in_manual_review_not_deploy`, `test_v394_clean_runtime_snapshot_is_release_ready`, `test_v400_telegram_factory_composes_authorized_release_route`, `test_v401_forged_snapshot_and_incident_are_rejected_before_audit`. |
| 6 | `app/tests`, authorization/commit diagnostics | ожидаемые строки, блоки или exact blocker-gate отсутствуют в компактном отчёте | Сверить тестовую фикстуру с поддерживаемой canonical evidence chain; не раскрывать чужие идентификаторы и не добавлять бухгалтерское применение. |
| 2 | `app/tests`, общая Return COGS диагностика | ожидаемые пояснения состояния commit-ready и первого blocker | Сверить presentation contract со стадиями; оставить отчёт read-only. |
| 4 | `app/tests`, recognition diagnostics | candidate identity/amount/date не выводятся в ожидаемом blocker-разделе | Проверить безопасную диагностическую проекцию и пределы приватных полей; stale evidence остаётся не подтверждённым. |
| 1 | `app/tests`, Return COGS inventory warning | ожидание формулировки о non-saleable кандидате | Проверить приоритет blocker и источник факта; сохранить различие статуса Ozon и подтверждённого восстановления. |
| 2 | `app/tests`, physical quantity / identity | исторический SKU или posting identity расходятся с ожидаемыми доказательствами | Сверить временную идентичность и quantity contract на fixtures; не угадывать связь SKU. |
| 4 | `app/tests`, historical COGS | fallback пробует другой SKU, а timeline/reaccrual выдаёт другой blocker либо результат | Проверить bounded identity, даты и physical sale/reaccrual; сохранить неизвестную себестоимость при неоднозначности. |
| 3 | `app/tests`, June reversal | fixtures создают `PeriodProfitFinanceService` через `__new__` без нового request-cache атрибута | Обновить создание сервиса до поддерживаемой фабрики/инициализации или доказать обратную совместимость; не добавлять runtime fallback только ради устаревшей фикстуры. |
| 7 | `app/tests`, related SKU | старые ожидаемые диагностические коды/успех расходятся с multi-blocker fail-closed поведением | Сверить контракты ответа, tenant identity и безопасное разрешение кандидата. Обновлять assertion только при подтверждённом контракте. |
| 1 | `app/tests`, Return COGS final application | тест ожидает старую финальную цепочку применения | Сверить тест с canonical chain и правом final application; read-only статус сохранять, пока доказательная цепочка не завершена. |
| 1 | `app/tests`, duplicate sale quantity | получен общий unavailable вместо специфичного duplicate-evidence кода | Проверить сначала классификацию доказательств, затем диагностическую точность; обе ветви должны fail closed. |
| 2 | `app/tests`, seller-cost UI | изменились текст меню и подтверждения артикула/SKU | Сверить актуальный Telegram flow и исправить только устаревшие ожидания/реальную потерю информации. |
| 2 | `app/tests`, first-cost onboarding | реализация применяет `date.min`, тесты ожидают сегодняшнюю дату | Решение владельца от 12.10.2026: предложить дату и применить её; всю историю — только после отдельного подтверждения. Реализовать в P02, включая CSV. |

Последние 15 строк для `app/tests` дают **35 падений**. 90 + 2 + 10 падений из `tests` дают **102**; итог 102 + 35 = 137. «Платформенная причина» здесь описывает первый наблюдаемый отказ на текущей Windows, а не доказывает, что все зависящие тесты исправятся одним изменением. После P01/P02 пересчитать остаток.

## Чего этот разбор не доказывает

- Не подтверждает production-готовность или работу с live Ozon/Telegram.
- Не разрешает удалять tests, массово добавлять `skip/xfail` или менять финансовые правила.
- Не заменяет независимые проверки Linux CI и Windows запуска.
- Полные XML/traceback результаты остались в локальном игнорируемом каталоге `.runtime-data/luna-audit-20261012/`; секреты и данные продавца в документ не копировались.

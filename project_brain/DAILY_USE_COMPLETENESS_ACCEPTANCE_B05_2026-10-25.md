# B05: матрица полноты и согласованность снимка — 25.10.2026

## Область

Проверен путь успешного отчёта Period Profit: основной компактный ответ, подробная полнота, отдельная диагностика, support JSON и пользовательские CSV/JSON. Все представления должны относиться к одному owner/store/period scoped снимку и не выполнять повторных запросов к Ozon при чтении.

## Матрица приёмки

| Случай | Экран полноты | Диагностика/support JSON | Обычные CSV/JSON | Поведение |
|---|---|---|---|---|
| Полный | Показывает подтверждённые суммы и provenance по компонентам; отдельная диагностическая причина отсутствует | Коды причин пусты; статусы источников сохраняются | То же пустое множество причин и те же статусы в metadata | Ноль остаётся наблюдаемым нулём; повторное чтение не обновляет источники |
| Частичный/неизвестный | Показывает сумму или неизвестно, источник, период/date basis, покрытие и причину | Показывает те же canonical reason codes и source status codes | Те же allowlisted reason/status codes попадают в JSON и в `metadata_json` CSV | Частичная наблюдаемая сумма не объявляется полным итогом |
| Недоступный/невалидный результат | Экран полноты не создаётся без успешного результата с согласованным периодом | Диагностика и support export возвращают unavailable; callback не восстанавливает источник | Экспорт недоступен без сохранённого успешного снимка | Бот предлагает сформировать корректный отчёт; ошибка источника не превращается в ноль |

## Исправленный пробел

Обычный аналитический CSV/JSON экспортировал comparison, bridge и SKU coverage, но терял полноту компонентов и коды причин. Теперь runtime сохраняет в существующем `analytics_snapshot.completeness` период, статус, allowlisted source statuses и canonical reason codes. Экспорт переносит их в metadata JSON и в строку `metadata_json` CSV. Старые снимки без нового optional-поля остаются совместимы: экспорт показывает `completeness: null`.

Короткий ответ показывает одну приоритетную причину и число дополнительных причин, чтобы не раздувать первый экран. Экран полноты и диагностика показывают все человекочитаемые причины, совпадающие с canonical reason codes. В cached completeness/diagnostics responses также отдаются безопасные status/reason maps. Все эти поля создаются при сохранении исходного результата; export/read callbacks читают deepcopy сохранённого снимка.

Support diagnostic остаётся отдельным strict allowlist форматом: в нём сохраняются только даты, коды причин/статусов, bounded counters и маскированные ссылки. Денежные суммы, raw provider payload и произвольные строки в этот export не добавлены.

## Проверки

- `tests/test_period_profit_analytics_runtime.py`, `tests/test_analytics_export_service.py`, `tests/test_period_profit_support_diagnostic_export_service.py`, `tests/test_period_profit_diagnostic_view_service.py`, `tests/test_period_profit_completeness_view.py`: **41 passed, 1 deselected in 2.39s**.
- Deselected: `test_production_factory_routes_period_analytics_without_requery`, поскольку его `tmp_path` fixture в этой Windows ACL среде не проходит setup; такой storage-backed тест должен пройти exact-head CI.
- Интеграционная regression сравнивает reason codes в компактном ответе, полноте, диагностике, support JSON и CSV/JSON; проверяет ровно один вызов query service после всех detail/export callbacks.
- Pure export regression проверяет allowlist при malformed status/date, пропускает секретные коды и посторонние значения.
- Матрица confirmed/partial/unavailable: `test_support_diagnostic_matrix_keeps_confirmed_partial_and_unavailable_distinct`.
- In-memory compile изменённых Python modules и `git diff --check`: **passed**.
- Полный `pytest` локально не запускался из-за ранее задокументированного Windows ACL/shared-storage ограничения. Exact-head CI ещё не запущен; новый PR не создан.

## Ограничения

Официальные ответы владельца по Analytics, Returns и начислениям остаются источниковым evidence; этап B05 их не пересчитывал и не менял financial formulas. B05 не создаёт новый источник, registry, callback family или изменение базы данных.

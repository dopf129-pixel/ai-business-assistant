# Повторный review цепочки PR #697–#702 после слияния #703

Дата: 18.10.2026. Решение: **перед слиянием в main исправить R9 и R10**.

## 1. Проверенная версия и результат

- Текущий PR #702: `3b41ab718f7d9157be00f09bc23c995e4ed58ca9`, base `codex/product-workbench-module-e`.
- PR #703 уже слит в ветку F. GitHub compare `c38d90599b917b7d9ae75cbe143fd67f43849e2b...3b41ab718f7d9157be00f09bc23c995e4ed58ca9` возвращает **0 изменённых файлов**: локальная версия G и текущий PR #702 имеют одинаковое содержимое.
- Локальная ветка: `codex/product-workbench-module-g`, commit `c38d90599b917b7d9ae75cbe143fd67f43849e2b`, сообщение `Record A-G review and CI results`.
- Прочитаны предыдущий review R1–R8, исправляющий commit `664a370a`, границы production Telegram adapter/handler, batch mutations/refresh, sensitivity lifecycle и экспорт.
- Новые находки: две P2. Исправления в production code этим review не внесены; новых коммитов нет.

## 2. Подтверждённые замечания

### R9 — P2: поздняя локальная правка перезаписывает результат успешного refresh

Файл: `app/services/telegram_unit_price_batch_plan_runtime_service.py`.
Границы: `_publish_refresh`, строки 739–745; `_finish_mutation`, строки 887–895.

Refresh защищает свою публикацию от уже сохранённой новой версии, однако при успешной публикации не отзывает ранее запущенную правку. `_finish_mutation` проверяет только pending ticket и текущий tenant, затем вызывает безусловный `_save_batch`. Исходная версия batch из pending повторно не сопоставляется с текущей сохранённой версией.

Подтверждённый interleaving:

1. Создать V1 с исходной ценой 500 ₽ и открыть редактирование себестоимости первой строки.
2. В отдельном worker запустить ввод 250 ₽. Настоящий `UnitPriceBatchPlanService.edit_row_assumption` уже построил результат из V1; остановить его возврат через `Event`.
3. Пока worker остановлен, выполнить публичный callback «Обновить источники». Fake source возвращает новую цену 750 ₽; настоящий batch service и runtime сохраняют V2 с 750 ₽.
4. Освободить worker редактирования.
5. Получить `UNIT_PRICE_BATCH_PLAN_READY`; сохранённый batch снова содержит цену **500 ₽**, себестоимость 250 ₽ и всё тот же номер **V2**.

Проверка использовала настоящие `UnitPriceBatchPlanService`, `UnitPriceScenarioService`, `UnitPriceTargetPlanningService` и `TaxService`; fake ограничен каталогом/источником. Синхронизация — `Event`/`Thread`, без сетевых запросов и timing sleeps. Это нарушение объявленного контракта конкурентного runtime; обычная последовательная обработка Telegram сама по себе такой interleaving не создаёт.

Требуемая правка: единая атомарная условная публикация всех изменений batch. Перед сохранением сопоставить pending ticket, batch id, исходную version, owner/store и срок жизни с текущим состоянием под одним lock. Публикация refresh должна отозвать несовместимые pending/mutation workers. Аналогичную проверку использовать для подтверждения общей рекламной доли, которое также сохраняет подготовленную копию batch.

Необходимые регрессии:

- поздняя правка после успешного refresh не возвращает прежние source facts;
- поздняя правка после более новой правки/замены batch не перезаписывает её;
- две разные версии содержимого не получают один и тот же batch id/version;
- существующие отмена и edit-during-refresh из R2 продолжают проходить.

### R10 — P2: выгрузка чувствительности теряет текущую отметку об устаревании

Файлы: `app/services/telegram_unit_price_sensitivity_runtime_service.py:199–204` и `app/services/analytics_export_service.py:229–279`.

Экран `_render` перечитывает актуальный origin, проверяет его signature и возраст. Export callback передаёт исходные `session.result` и `session.context` напрямую в serializer, минуя эту оценку. В metadata чувствительности нет текущего возраста/TTL или отметки, что исходный план уже изменён либо устарел. Аналогичная проблема исправлена R7 только для batch export.

Подтверждённый сценарий через реальные single/sensitivity runtimes и `AnalyticsExportService`:

1. При fake clock=100 открыть одиночный сценарий и построить sweep цен 500/550/600 ₽ на свежем источнике.
2. Перевести часы на 701; sensitivity session ещё действительна, источник уже истёк.
3. Открыть экран: он предупреждает об устаревании, кнопок переноса ячеек нет.
4. Нажать JSON: все три строки файла имеют **AVAILABLE**, metadata не содержит текущего freshness status, возраста/TTL или предупреждения об истёкшем origin.
5. Число source calls остаётся **1**.

Требуемая правка: общий projection для экрана и CSV/JSON, оценивающий актуальный origin/signature и текущую свежесть без повторного source query. Исходные суммы и статусы снимка можно сохранить как исторические, но нужно отдельно передавать текущие freshness/validity, время или возраст оценки и причину запрета переноса. Проверять как истёкший источник, так и новую версию исходного плана.

Необходимые регрессии:

- fresh → TTL → экран и CSV/JSON содержат одинаковое ограничение;
- изменение origin при ещё свежем источнике отражается в выгрузке;
- исходные суммы сохраняются, повторного Ozon query нет;
- тесты покрывают происхождение sweep из single и batch.

## 3. Файлы и архитектурное влияние этого review

- Добавлен только этот отчёт; production code и штатные тесты не изменены.
- Архитектурное влияние самого review: **No architectural impact**.
- Проверяемый пакет A–G сохраняет классификацию **Architecture Review Required**.
- Для R9 требуется согласовать существующие runtime locks/tickets; новый слой хранения или иной framework не нужен.
- Для R10 следует расширить существующую границу projection/export, сохранив snapshot-only контракт.

## 4. Сохранённые компоненты и данные

Канонические расчёты прибыли и налога, постоянная себестоимость, цены в Ozon, Return COGS, task execution и пользовательские `data/tasks.json`/`data/users.json` этим review не изменялись. Слияние и развёртывание не выполнялись.

## 5. Фактические проверки

Локально выполнен следующий fake-only профиль:

```text
tests/test_product_overview_service.py
tests/test_scoped_transient_snapshot_store.py
tests/test_telegram_unit_price_batch_plan_runtime_service.py
tests/test_telegram_unit_price_sensitivity_runtime_service.py
tests/test_unit_price_batch_plan_service.py
tests/test_unit_price_sensitivity_service.py
tests/test_analytics_export_service.py
tests/test_product_workbench_acceptance.py

94 passed in 1.95s
```

Использованы `PYTHONPATH=app`, `PYTHON_DOTENV_DISABLED=1`, отключённые pytest cache/temp plugins. Выбранный профиль не требует временных файлов и не исключал отдельные тесты.

R9 и R10 дополнительно воспроизведены изолированными исполняемыми probes с настоящими сервисами и fake source/clock; probes не добавлялись в штатный suite. При исправлении необходимы постоянные регрессии корректного поведения.

Текущий PR #702 имеет новый успешный [Verify run 39162744235](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39162744235) именно на `3b41ab718f7d9157be00f09bc23c995e4ed58ca9`:

- Windows/Python 3.12: **3 420 passed in 56.98s**;
- Linux/Python 3.11: **3 420 passed in 12.24s**;
- compileall и production Docker build/runtime smoke: success.

Полный pytest локально повторно не запускался: реализация этим review не менялась, полный текущий suite уже проверен чистыми Windows/Linux CI, а дополнительные probes проверяли отсутствующие сценарии.

## 6. Документация

Этот файл фиксирует текущий SHA, новые R9/R10, воспроизведения, требуемые регрессии и фактические проверки. Исторические CURRENT_STATE/TEST_MAP/CHANGELOG не переписаны: новый production milestone review не реализовал, предыдущая приёмка R1–R8 остаётся историческим результатом.

## 7. Решение о готовности

**Требуются исправления перед слиянием в main.** Зелёный CI текущего кода не закрывает R9/R10: этих сценариев нет в штатных проверках.

## 8. Следующий шаг

Исправить R9/R10, добавить указанные регрессии, получить CI нового SHA и пройти повторный review. При интеграции учитывать, что #703 слит в F, а #697–#702 остаются открытыми: исправления должны войти в итоговую цепочку до выпуска. Решение по слиянию новых изменений и deployment этим review не исполнялось.

## 9. Результат исправлений R9–R10

Дата: 18.10.2026. Реализация внесена после review; merge/deploy не выполнялись.

- R9: начальная публикация плана сверяет ticket и базовую версию; локальные правки и подтверждение рекламы выполняют атомарный compare-and-swap по batch id/version, owner/store и ticket ввода. Успешный refresh удаляет pending-правку от базовой версии. Новая сборка не может переиспользовать batch id/version 1; обновления меняют версию строго на `+1`.
- R10: экран, действие переноса и выгрузка используют общий freshness projection без повторного чтения Ozon. Экспорт различает статус исторической ячейки и актуальную свежесть: при stale он сообщает `SOURCE_STALE`, сохраняет исходный status в `snapshot_status`, указывает причину, возраст/TTL и блокирует перенос.
- Добавлены пять concurrency/staleness regressions. Связанный профиль **99 passed**; `compileall -q app tests` и `git diff --check` прошли.
- Exact-head CI и независимый повторный review пока не проведены. Нужны после публикации нового SHA.

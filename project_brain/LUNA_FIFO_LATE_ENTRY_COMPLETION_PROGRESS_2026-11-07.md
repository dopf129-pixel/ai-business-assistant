# Luna FIFO late entry — журнал

Дата подготовки: 2026-11-07.
ТЗ: LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md.
Матрица: FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md.
База спецификации: main d8d4ba00c85acf14ba9a960f56a755fbe30b555c.
Это план исполнения, не отчёт о выполненной реализации.

## Resume

Следующий этап: FL00.
Выполненных этапов:0/36. Реализация NOT_STARTED.
IMPLEMENTATION_VERIFIED: нет. OWNER_CASE_VERIFIED: нет.
Рабочая ветка подготовки: codex/fifo-late-entry-completion-spec-20261107.
Если спецификация ещё в отдельном PR, создать foundation branch от его последней головы, сохранив документы; base foundation PR — main. Не начинать от старой ветки реализации #726.
Реальные Ozon/Telegram запросы, запуск бота, изменение owner DB, merge/deploy не выполнялись и не разрешены этим заданием.

Перед продолжением читать git status, актуальный HEAD и последние записи ниже. Не подменять результаты тестов плановыми ожиданиями.

## Этапы

| Этап | Содержание | Статус | Commit / checks |
|---|---|---|---|
| FL00 | Baseline и безопасная ветка | NOT_STARTED | — |
| FL01 | Карта интеграции | NOT_STARTED | — |
| FL02 | Контракты и часы | NOT_STARTED | — |
| FL03 | Миграция13 и cipher | NOT_STARTED | — |
| FL04 | Repository cases/evidence | NOT_STARTED | — |
| FL05 | До-FIFO хранение и fault tests | NOT_STARTED | — |
| FL06 | Полная стоимость | NOT_STARTED | — |
| FL07 | Lifecycle случая | NOT_STARTED | — |
| FL08 | Конкретные поставки | NOT_STARTED | — |
| FL09 | Наблюдения и missing | NOT_STARTED | — |
| FL10 | Частичная приёмка | NOT_STARTED | — |
| FL11 | Бюджеты/checkpoints | NOT_STARTED | — |
| FL12 | Ведомость parser | NOT_STARTED | — |
| FL13 | Остатки parser | NOT_STARTED | — |
| FL14 | Контекстный XLSX import | NOT_STARTED | — |
| FL15 | Сверка поставок | NOT_STARTED | — |
| FL16 | Proposal opening | NOT_STARTED | — |
| FL17 | Readiness и missing evidence | NOT_STARTED | — |
| FL18 | Cutoff bridge | NOT_STARTED | — |
| FL19 | Начальная активация proposal | NOT_STARTED | — |
| FL20 | Deterministic replay | NOT_STARTED | — |
| FL21 | Возвраты/выбытия | NOT_STARTED | — |
| FL22 | Period impact | NOT_STARTED | — |
| FL23 | Atomic apply | NOT_STARTED | — |
| FL24 | Меню доFIFO | NOT_STARTED | — |
| FL25 | Durable мастер | NOT_STARTED | — |
| FL26 | Разные подтверждения | NOT_STARTED | — |
| FL27 | Current/plans/cache | NOT_STARTED | — |
| FL28 | Period Profit | NOT_STARTED | — |
| FL29 | History/refresh/cancel | NOT_STARTED | — |
| FL30 | Числовая матрица | NOT_STARTED | — |
| FL31 | Security/isolation/navigation | NOT_STARTED | — |
| FL32 | Backup/migration/restart | NOT_STARTED | — |
| FL33 | Owner guide | NOT_STARTED | — |
| FL34 | Полный CI | NOT_STARTED | — |
| FL35 | Review handoff | NOT_STARTED | — |

## Незакрытые данные реального случая

- Полный per-supply список пока не передан; известна общая отправка6982 и отдельная Беларусь148.
- Ведомость доступна владельцу только до05.11. Наблюдение исчезающих148 не является официальным описанием всех API.
- reserved, cross-source cutoff и привязка физических продаж ещё требуют proof/validation.
- Новая домашняя закупка не пересчитана — допустимый UNKNOWN, не blocker создания case.

## Формат записи после этапа

~~~text
Этап:
Статус: IMPLEMENTED / VERIFIED / DATA_PENDING / BLOCKED
Изменённые файлы:
Commit:
Команды и фактические результаты:
Сохранность данных (manifest/путь изолированных fixtures):
Source readiness:
Что не доказано:
Следующий этап:
~~~

## Результаты подготовки

- Зафиксированы архитектура, scope, DTO, schema13, state machine, транзакционная граница, UX и36 этапов.
- Составлена независимая матрицаN01–N40.
- Runtime код и реальные записи не изменялись.
- Статическая проверка подготовки:36 уникальных этаповFL00–FL35,36 строк журнала,40 уникальных сценариевN01–N40 и7 независимых числовых контролей — PASS. git diff --check — PASS. Runtime tests локально не повторялись: изменения только Markdown; полный Verify документационного PR фиксируется на точном SHA в описании PR.
- Проверка документационного PR не считается реализациейFL00–FL35 или проверкой источников реального магазина.

## PR delivery

| PR | Этапы | Ветка | Base | HEAD | CI |
|---|---|---|---|---|---|
| 1 | FL00–FL11 | codex/fifo-late-entry-foundation-20261107 | main | — | NOT_RUN |
| 2 | FL12–FL23 | codex/fifo-late-entry-reconciliation-20261107 | branchPR1 | — | NOT_RUN |
| 3 | FL24–FL35 | codex/fifo-late-entry-integration-20261107 | branchPR2 | — | NOT_RUN |

# Журнал выполнения — предварительный FIFO

Основа: `project_brain/LUNA_FIFO_PROVISIONAL_LEDGER_TASK_2026-11-22.md`, PR #740.
Начат: 2026-11-23 (Europe/Moscow).

## PF00 — база и сохранность

- PR #740: открыт; source branch `codex/fifo-provisional-ledger-spec-20261122`; head `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; base `main` `b14658c80c9feef4f8595547eb489dde984cb59c`.
- CI PR #740 на точном head: два successful runs `45024247975`, `45024273483` (Windows и full-verification); текущая голова подтверждена диагностикой.
- Выделенная рабочая копия: `C:\Users\gelashvilee\.codex\worktrees\fifo-provisional-ledger-pr-a\fifo-provisional-ledger-spec-20261122`.
- Ветка создана: `codex/fifo-provisional-summary`, начальный SHA `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; `git status --porcelain` чист.
- Рабочая копия Desktop `C:\Users\gelashvilee\Desktop\Ai ассистент` и её пользовательские правки не изменялись; рабочий бот не запускался и не останавливался.
- Базовые SHA файлов `data/` из `git ls-tree -r HEAD data`:
  - `data/history.json` — `d537fb1e49b920a91fb6ab7704e91978b670e56b`
  - `data/profiles.json` — `185607c3dd54ca8418934189c688765e58024559`
  - `data/tasks.json` — `38637702206478ab3c08d7ae1c4ac87f1f1c6354`
  - `data/tax_configuration.json` — `60c0f31405fd47d591367b673ffaf1080988caab`
  - `data/users.json` — `dd06c3aa18fcf3510bf39dbf3a1e5b5c8bd81784`
- Команды проверки: `git status --short --branch`, `git rev-parse HEAD`, `git rev-parse origin/main`, `git ls-tree -r HEAD data`; результат соответствует чистой изолированной основе.
- Что не проверялось на этом этапе: поведение кода (это этап PF01+); реальные Ozon/Telegram вызовы запрещены задачей.

## Resume

- Последний завершённый этап: PF00.
- Следующий этап: PF01 — сверить Decision 066/067, руководство FIFO, импорт документов, contracts и действующие точки подключения.
- PR A: ветка `codex/fifo-provisional-summary`, база `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf` (spec PR #740).
- PR B: `codex/fifo-provisional-timeline`, поверх PR A после публикации.
- PR C: `codex/fifo-provisional-saved-estimates`, поверх PR B после публикации.
- Блокеров нет. Неизвестность реального дела владельца не блокирует синтетическую разработку.

## PF01 — архитектурные границы и интерфейсы

- Прочитаны Decision 066/067, `FIFO_COST_CONTRACTS_2026-11-06.md`, руководство владельца по поставкам и спецификация текущего отчётного импортера.
- Подтверждён путь документов: `FifoCostReportImportService` создаёт redacted `ReportEvidence`; существующий `TelegramFifoCostReportImportService` записывает только после явного подтверждения периода/сохранения; `FifoCostTransitionService._read_saved_transition_report` восстанавливает typed evidence; `FifoCostRepository.read_transition_evidence` — scoped read-only список документов по точному case/store/product/offer/SKU.
- `FifoCostTransitionEvidenceService.load` подтверждает только фактический путь и содержит строгие cutoff/finance/movement требования; предварительная оценка не будет его вызывать и не ослабит его gates.
- Проверены `TelegramFifoCostTransitionRuntimeService` callbacks/session/revision, карточка `_show_summary`, `SellerCostTelegramAdapter` и factory wiring. PR A добавит отдельный `TelegramFifoCostProvisionalService` и безопасную ветвь `provisional_*`; фактические prepare/apply, `FifoCostAllocationService`, Period Profit/Return COGS и existing report evidence contracts остаются без изменений.
- Проверка: `rg` по точкам входа и сигнатурам; выборочное чтение contracts/importer/repository/runtime/factory. Результат: новая оценка может читать только подтверждённые отчёты текущего дела; filename candidate/partial report не подходит. Реальные запросы не выполнялись.
- Не выполнялось: тесты кода (этапы реализации впереди); фактический запуск Telegram и проверка Ozon.

## PF02 — тестовые числовые данные

- До реализации выписана synthetic контрольная матрица §4.3: `A=3712`, `L=12959`, `R=12`, `S=5931`, `D=22`, `B=10730`; восемь bucket snapshot `1988/0/2/6/0/0/70/1646`; сумма snapshot `3712`, opening/closing receipts/expenses контроль равен нулю.
- Ожидания заранее закреплены: closing old `[21,21]` → old sold `3669..3703`, new sold `2228..2262`, COGS `110187.30..110403.20`; `[31,31]` сдвигает оба конца вниз на `63.50`; неизвестный close → `0..3724` старых и COGS `86889.15..110536.55`; условная прибыль от базы `130000` → `19596.80..19812.70`.
- Включены негативные контроли: перенос одной единицы между bucket на стыке, неподдержанные категории, несовпадающие period/SKU, невалидный balance и пустое пересечение.
- Контрольные и негативные fixtures созданы в `tests/test_fifo_cost_provisional_summary_service.py`; все synthetic, без рабочих файлов/ID/данных.

## PF03–PF06 — расчётные контракты и контроль

- Добавлены `fifo_cost_provisional_contracts.py`, чистый `FifoCostProvisionalSummaryService` и scoped read-only `FifoCostProvisionalEvidenceReader`. Только полные, owner-confirmed, exact-scope оборотные ведомости; filename candidate, partial, другой case/store/SKU, нестыкованные окна и контрольные ошибки fail closed.
- Реализованы checks восьми bucket на границе дня, балансы всех компонент, неподдержанные L–R/U–Z блокируют деньги; S/AA остаются исключёнными компенсациями. Формулы и Decimal/ROUND_HALF_UP дали матрицу §4.3: `[21,21]` → старые `3669..3703`, новые `2228..2262`, COGS `110187.30..110403.20`; неизвестный closing — широкие границы.
- Проверки: `pytest tests/test_fifo_cost_provisional_summary_service.py tests/test_fifo_cost_provisional_evidence_reader.py -q` — **18 passed** после добавления invalid timezone и ненулевых компенсаций S/AA; `compileall -q` для новых контрактов/сервисов — успешно. При первом прогоне крайняя пара COGS обнаружила ошибочную связку старых/новых границ; формула исправлена и профиль повторно зелёный.
- Не проверялось: сохранённые документы рабочего магазина и внешние источники; ничего из них не читалось.

## PF07–PF08 — предварительный экран в обычном Telegram FIFO-пути

- Добавлен `TelegramFifoCostProvisionalService`, инъекция в общий transition runtime/factory и кнопка карточки партии. Callback проходит обычные owner/tenant/case/revision/flow_revision проверки; выбор отчёта хранит только внутренний отпечаток в ограниченной in-memory сессии.
- В мастер входят выбор однодневного снимка, соседней ведомости движений, подтверждение двух явных допущений, выбор широкого неизвестного остатка или ручного сценарного числа/диапазона и просмотр диапазона COGS. Повтор старой кнопки получает STALE. Импорт используется существующий и только после выбора «Загрузить оборотную ведомость»; частичные и неподтверждённые ведомости исключены reader.
- Никакой вызов factual readiness/prepare/apply; сценарий не пишет кейс, FIFO layers/allocations/events, Period Profit/Return COGS и пока не сохраняет сценарий.
- Импорт FBO CSV и сверка дельты +1 намеренно не входят в PR A: это PF11–PF13 PR B. Матрица A12 будет закрыта там, не имитируется в этой сводной оценке.
- Synthetic ordinary-callback regression проверяет контроль `[21,21]`, границы и отсутствие FIFO writes. Расширенный связанный профиль (provisional summary/evidence/Telegram, production workflow, transition runtime/contracts и оба импортера) — **113 passed in 16.53s**. Предыдущий полный изолированный suite на `f967f7aa` прошёл **5,489 passed in 111.85s**; добавлены две регрессии после него, поэтому повторный full run обязателен. `compileall -q app tests`, `git diff --check` и `git diff --exit-code -- data` успешно проходили до добавленных тестов; после обновления будут повторены.
- Что не проверялось: реальные Telegram callbacks/сообщения и документы владельца (запрещены задачей).

## Resume (обновлено)

- Последний завершённый этап: PF09; PF00–PF09 закрыты локально.
- PF10 в работе: code commit `f967f7aa` прошёл полный изолированный suite и compileall; после добавления двух test-only regressions нужно повторить полный прогон на следующем commit.
- Следующий шаг: повторный full isolated pytest, compileall/diff/data checks, review packet, push PR A и exact-head CI.
- PR A `codex/fifo-provisional-summary` на базе опубликованного PR #740 SHA `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; текущая ветка пока локальная.
- PR B/C начнутся только после exact-head зелёного CI PR A. Блокеров нет.

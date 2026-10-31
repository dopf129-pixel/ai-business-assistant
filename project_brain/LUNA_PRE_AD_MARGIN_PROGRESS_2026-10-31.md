# Журнал: маржа SKU до рекламы

Дата подготовки: 31.10.2026. ТЗ: `LUNA_PRE_AD_MARGIN_TASK_2026-10-31.md`. Аудит: `PRE_AD_MARGIN_AUDIT_2026-10-31.md`.

База подготовки: `aad70b572b7f3bc37aaf79df302abe2eaa8b87d8`, проверенный PR #722. Ветка ТЗ: `codex/pre-ad-margin-spec-20261031`. Подготовка документации не является реализацией MA00–MA29.

## Resume

- Все этапы NOT_STARTED. Начать с MA00 и перепроверки live main/PR/spec статусов.
- Подтверждено владельцем: before-ad после налога и прочих расходов, процент от общей выручки продавца до вычета баллов.
- Новый отдельный before-ad расчёт не требует известной рекламы; неизвестный after-ad остаётся неизвестным.
- Сценарий использует налог при нулевой рекламе; historical add-back сохраняет налог исходного периода. Основания не смешиваются.
- Сохранить canonical calculator/TaxService, legacy outputs/history, W42–W44 guards и crossdock denominator restriction.
- Реальные Ozon/Telegram запросы, запуск бота, merge и deploy запрещены. Итог исполнения — готовый PR с зелёным CI текущего SHA и независимым review packet.

## Этапы

| Этап | Зависимости | Статус | Фактические результаты |
|---|---|---|---|
| MA00 | — | NOT_STARTED | — |
| MA01 | MA00 | NOT_STARTED | — |
| MA02 | MA00 | NOT_STARTED | — |
| MA03 | MA01,MA02 | NOT_STARTED | — |
| MA04 | MA01,MA02,MA03 | NOT_STARTED | — |
| MA05 | MA04 | NOT_STARTED | — |
| MA06 | MA05 | NOT_STARTED | — |
| MA07 | MA06 | NOT_STARTED | — |
| MA08 | MA05 | NOT_STARTED | — |
| MA09 | MA06,MA08 | NOT_STARTED | — |
| MA10 | MA07,MA08,MA09 | NOT_STARTED | — |
| MA11 | MA10 | NOT_STARTED | — |
| MA12 | MA03,MA07,MA09 | NOT_STARTED | — |
| MA13 | MA11 | NOT_STARTED | — |
| MA14 | MA13 | NOT_STARTED | — |
| MA15 | MA10,MA11,MA12 | NOT_STARTED | — |
| MA16 | MA15 | NOT_STARTED | — |
| MA17 | MA16 | NOT_STARTED | — |
| MA18 | MA12,MA15 | NOT_STARTED | — |
| MA19 | MA13,MA17,MA18 | NOT_STARTED | — |
| MA20 | MA14,MA19 | NOT_STARTED | — |
| MA21 | MA20 | NOT_STARTED | — |
| MA22 | MA20,MA21 | NOT_STARTED | — |
| MA23 | MA17,MA22 | NOT_STARTED | — |
| MA24 | MA20,MA21,MA22 | NOT_STARTED | — |
| MA25 | MA06,MA07,MA08,MA09,MA12,MA14 | NOT_STARTED | — |
| MA26 | MA19,MA23,MA24,MA25 | NOT_STARTED | — |
| MA27 | MA26 | NOT_STARTED | — |
| MA28 | MA27 | NOT_STARTED | — |
| MA29 | MA28 | NOT_STARTED | — |

## Правила исполнения

1. По завершении этапа: дата, входной/выходной SHA, изменённые файлы, точный результат проверок и ограничения; обновить Resume.
2. Статусы: NOT_STARTED, IN_PROGRESS, DONE, VERIFIED_EXISTING, BLOCKED. VERIFIED_EXISTING требует доказательства приёмки; BLOCKED — внешнее условие, выполненные попытки и независимая работа, которую можно продолжить.
3. Неподтверждённый live источник не мешает доказать честное UNAVAILABLE поведение; он не превращается в полный результат. Owner acceptance остаётся отдельно.
4. Не переносить тестовый PASS между изменившимися версиями. Не скрывать сбои/пропуски. Сохранять исходные owner data hashes; восстанавливать только доказанные тестовые побочные файлы.
5. После сокращения контекста продолжить с первого незавершённого этапа с удовлетворёнными зависимостями.

## Проверки подготовки ТЗ

- Граф: **30 уникальных упорядоченных этапов**, все dependencies существуют и направлены назад, граф ацикличен. Task и journal полностью совпадают; все 30 статусов NOT_STARTED.
- **20 групп N01–N20**, 17 явно указанных repo-relative code/docs paths существуют; файлы task/journal/audit существуют.
- Числовые проверки через действующий UnitPriceScenarioService/TaxService: N01 до 33.50/после 21.50/налог 4.50; N03 after −86.50; N04 до 32.30/после 22.10, налог 5.70/3.90; N05 до 38.00/после 26.00. Отдельный legacy crossdock rate2 дал before 34.50, сочетание с incompatible extended scope осталось unavailable.
- Decimal-oracles historical add-back 645+360=1005; 33.50 ₽/шт. и 33.50%; historical tax basis N11 34.10 против no-ad 32.30; weighted aggregate 27.50% — PASS.
- Первый числовой запуск без Windows IANA database вернул EXTENDED_SCOPE_INVALID. Повтор с установленной локальной базой через PYTHONTZPATH прошёл; код/зависимости для этого не менялись.
- `git diff --check`: PASS. `data/tasks.json` hash `38637702206478ab3c08d7ae1c4ac87f1f1c6354` сохранён; lock отсутствует. Новые runtime tests не добавлены. Полный локальный pytest не повторялся для документационной подготовки; полный CI спецификации проверяется на её опубликованном SHA.

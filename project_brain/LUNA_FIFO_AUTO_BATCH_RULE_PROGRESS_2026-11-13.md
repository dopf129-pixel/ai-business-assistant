# Журнал Luna: автоматическая принадлежность поставок партии

Дата создания: 13.11.2026. Стартовый шаблон, реализация не начата.

## Resume

- ТЗ: LUNA_FIFO_AUTO_BATCH_RULE_TASK_2026-11-13.md.
- Spec branch: codex/fifo-auto-batch-rule-spec-20261113.
- Product baseline: main 7965dcddffa50bd4e0f175cd18c32929b6a845d0.
- Implementation branch/HEAD: ещё не созданы; заполнить в FB00.
- Следующий этап: FB00. Выполненных implementation stages нет.
- Прежняя untracked .fl12-deps/ сохранена, не добавлять в Git.
- При подготовке спецификации owner data и работающий бот не изменялись.
- R1: полного поддержанного журнала движений пока нет; owner case не верифицирован.
- Source: bundle для состава SKU подтверждён официальным гайдом. Полная JSON schema, raw states и фактическая dispatch date подлежат проверке FB02.
- CI спецификации указывается в описании spec PR и не является implementation CI.

## Этапы

| Этап | Статус | Коммит / файлы | Проверки и фактический результат |
|---|---|---|---|
| FB00 | NOT_STARTED | — | — |
| FB01 | NOT_STARTED | — | — |
| FB02 | NOT_STARTED | — | — |
| FB03 | NOT_STARTED | — | — |
| FB04 | NOT_STARTED | — | — |
| FB05 | NOT_STARTED | — | — |
| FB06 | NOT_STARTED | — | — |
| FB07 | NOT_STARTED | — | — |
| FB08 | NOT_STARTED | — | — |
| FB09 | NOT_STARTED | — | — |
| FB10 | NOT_STARTED | — | — |
| FB11 | NOT_STARTED | — | — |
| FB12 | NOT_STARTED | — | — |
| FB13 | NOT_STARTED | — | — |
| FB14 | NOT_STARTED | — | — |
| FB15 | NOT_STARTED | — | — |
| FB16 | NOT_STARTED | — | — |
| FB17 | NOT_STARTED | — | — |
| FB18 | NOT_STARTED | — | — |
| FB19 | NOT_STARTED | — | — |
| FB20 | NOT_STARTED | — | — |
| FB21 | NOT_STARTED | — | — |
| FB22 | NOT_STARTED | — | — |
| FB23 | NOT_STARTED | — | — |
| FB24 | NOT_STARTED | — | — |
| FB25 | NOT_STARTED | — | — |
| FB26 | NOT_STARTED | — | — |
| FB27 | NOT_STARTED | — | — |
| FB28 | NOT_STARTED | — | — |
| FB29 | NOT_STARTED | — | — |
| FB30 | NOT_STARTED | — | — |
| FB31 | NOT_STARTED | — | — |

## Содержание каждой записи

Дата, branch/HEAD/base, изменённые функции/контракты, команды и результаты проверок,
Bxx→test mapping, source gaps, data integrity, PR/CI URL, следующий этап.
Не писать DONE для непроверенной функции.

## Отдельные ограничения

- Ошибка резервирования assistant_session.json (list против ожидаемого dict) вне scope FB.
- RULE_CONFIRMED не означает SUPPLY_COVERAGE_COMPLETE или FIFO_READY.
- Не выполнять merge/deploy/live Ozon/Telegram/startbot.

# Журнал Luna: автоматическая принадлежность поставок партии

Дата создания: 13.11.2026. Стартовый шаблон, реализация не начата.

## Resume

- ТЗ: LUNA_FIFO_AUTO_BATCH_RULE_TASK_2026-11-13.md.
- Spec branch: codex/fifo-auto-batch-rule-spec-20261113.
- Product baseline: main 7965dcddffa50bd4e0f175cd18c32929b6a845d0.
- Implementation branch/HEAD: codex/fifo-auto-batch-foundation-20261113 at 0fa8b7835829a710bf86adda1c3737d8286c42de (FB00 checkpoint in progress).
- Следующий этап: FB00. Выполненных implementation stages нет.
- Прежняя untracked .fl12-deps/ сохранена, не добавлять в Git.
- Рабочая копия: изолированный Codex worktree; Desktop-папка с работающим ботом не открывалась для разработки.
- Исходный `git status`: только `?? .fl12-deps/`; staged и tracked diff отсутствовали. Каталог .fl12-deps содержит 6 элементов, сохранён и исключён из изменений.
- Исходные SHA-256 tracked data (без чтения/вывода содержимого): `data/history.json` 520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C; `data/profiles.json` 8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51; `data/tasks.json` 6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F; `data/tax_configuration.json` F8EB3295F353060EAE65632A4E64B8711C3F9E2BC42004BD; `data/users.json` 2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2.
- Spec branch and origin/main were fetched and verified: spec HEAD 0fa8b783; its merge-base with main is exactly 7965dcdd. PR A is based on the published spec branch.
- Existing architecture reviewed: Decision 066, current state, test map, FR/FL progress, transition runtime/contracts/store/reconciliation/readiness and v16 migration tests. No code changed at FB00 start.
- No contents of owner data were read or printed. R1 remains independent and unverified.
- R1: полного поддержанного журнала движений пока нет; owner case не верифицирован.
- Source: bundle для состава SKU подтверждён официальным гайдом. Полная JSON schema, raw states и фактическая dispatch date подлежат проверке FB02.
- CI спецификации указывается в описании spec PR и не является implementation CI.

## Этапы

| Этап | Статус | Коммит / файлы | Проверки и фактический результат |
|---|---|---|---|
| FB00 | IN_PROGRESS | spec SHA 0fa8b783; new A branch; progress journal | Working tree had no tracked/staged edits; .fl12-deps preserved; five tracked data hashes recorded; base/main=7965dcdd; Desktop bot untouched. |
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

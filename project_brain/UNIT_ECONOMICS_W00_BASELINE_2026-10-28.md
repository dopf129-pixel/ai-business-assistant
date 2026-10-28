# W00 baseline — расширенная экономика SKU и ценовые эксперименты

Дата: 2026-10-28  
Этап: W00 — безопасная база и ветка реализации  
Задание: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`

## Git и интеграционная база

- PR #721 открыт и не слит.
- Проверенный HEAD задания: `f76d2dd90e4298113c037278666532715974e4a8`.
- Целевая ветка PR #721 — `main`; проверенный `main` на старте: `9315046cf29c9e8c68da1cab027cb2568040f142`.
- Implementation branch: `codex/full-unit-economics-experiments-implementation-20261028`, создана локально прямо от проверенного HEAD PR #721.
- На исходной ветке `git status --porcelain=v1` был пуст; незакоммиченных и untracked изменений в checkout не обнаружено.
- Ветку PR #721 не меняли, не сливались в `main`, историю не переписывали.

## Изоляция пользовательских данных

- До переключения и после него проверено состояние `data/`; изменений и untracked файлов в `data/` нет.
- Git отслеживает baseline JSON-файлы `data/history.json`, `data/profiles.json`, `data/tasks.json`, `data/tax_configuration.json`, `data/users.json`. Их содержимое не читалось и не включалось в W00 commit.
- `data/tenants/` присутствует как ignored runtime data; файлы и содержимое не читались и не менялись.
- `.env`, runtime databases, backups, logs, caches и pytest scratch не добавлялись и не менялись.
- Последующие storage-тесты должны использовать временный synthetic root. Перед каждым commit проверять `git status`, `git diff -- data` и staged paths; owner data не восстанавливать и не включать в PR.

## Проверки и ограничения

- GitHub API подтвердил PR #721: `open`, `merged=false`, `mergeable=true`, base SHA совпадает с `main`.
- Локальная ветка реализации начинается с exact spec HEAD; `git status --porcelain=v1` после переключения пуст.
- `git ls-files data` и `git status --short --ignored data` использованы только для инвентаризации путей и состояния; содержимое пользовательских JSON не выводилось.
- Runtime tests не запускались: W00 не меняет исполняемый код; baseline тестов и числовые oracles предусмотрены этапом W04.
- Реальный бот, Ozon API, `.env` и owner database не использовались.

## Итог

W00: **DONE**. Следующий этап — W01: аудит маршрутов, источников, дат, scope, полноты и потребителей для каждой категории затрат и наблюдений.

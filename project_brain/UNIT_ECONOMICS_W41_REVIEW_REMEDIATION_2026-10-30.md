# W41 — исправления повторного review PR #722

Дата: 30.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Базовая голова до исправлений: `a84da1a111d63b98e3fc33a4c28a9bb7f69c8050`
Статус: исправления и локальные проверки готовы; CI и независимое review должны быть привязаны к точной опубликованной голове.

## Исправленные замечания

| ID | Проблема | Изменение |
|---|---|---|
| R1 | Повторная оценка старого снимка со временем считала его зрелым, хотя поздние возвраты не могли попасть в immutable evidence. | Maturity рассчитывается по локальной дате `collected_at` снимка. Старый снимок остаётся pending; новый сбор фиксирует новую дату источника и может пройти gate. |
| R2 | После рестарта PLANNED baseline/candidate нельзя было безопасно продолжить или отменить, потому что одноразовый token жил только в памяти. | На сохранённой фазе доступны продолжение подтверждения и двухшаговая отмена незапущенного эксперимента. Возобновление заново требует точную цену и время, затем показывает preview/confirmation; история не удаляется. |
| R3 | Поздние финансовые корректировки и возвраты не принимались после Finish. | Завершённая фаза может получить bounded append-only collection/result revision в допустимых состояниях эксперимента. Фаза остаётся FINISHED, экспериментная state revision повышается. Прошлые snapshot/result неизменны. Устаревшее сравнение не показывает кнопки решения и атомарно отклоняется repository до новой evaluation/comparison. |
| R4 | Старый Telegram Finish callback повторно загружал текущий READY результат и мог завершить фазу с результатом, которого владелец не видел при нажатии. | Callback содержит ожидаемые experiment state, phase state и result revisions; handler сверяет все три до завершения и отказывает для устаревшего действия. |
| R5 | При частичном покрытии окна компонент мог помечаться COMPLETE и влиять на удельную ставку. | COMPLETE требует coverage каждого запрошенного дня и компонента. Наблюдаемая частичная ставка остаётся диагностикой; применённая ставка неизвестна. |

## Изменённые области

- `PlanningWorkspaceRepository`: транзакционная append-only поздняя коррекция и repository guard от решений по устаревшему сравнению.
- Unit economics maturity, phase collection и window snapshot services: snapshot-time clock, ограниченная коллекция после Finish, полный coverage gate.
- Telegram experiment runtime: восстановление PLANNED confirmation, cancel, late-correction flow, exact-revision Finish callback и скрытие решений на устаревшем сравнении.
- Regression coverage в readiness, collection, repository decision, window snapshot и Telegram runtime suites.

## Проверки

- Связанный профиль из 8 модулей: **113 passed in 6.73s**.
- Полный Windows `pytest`: **4,351 passed in 44.59s**.
- `git diff --check`: PASS.
- Полный suite временно изменил демонстрационный `data/tasks.json` и создал `data/tasks.json.lock`; tracked JSON восстановлен, lock удалён. Итоговый `git diff -- data` пустой.
- Запуски без `AI_ASSISTANT_STORAGE_ROOT`, credentials, реальных Ozon API-запросов и Telegram-бота.

## Review boundary и следующий шаг

Изменения расширяют lifecycle и persistence/revision guards и затрагивают более пяти исходных файлов; классификация — **Architecture Review Required**. После commit/push требуется CI точной головы и повторное независимое review. PR #722 не сливать до их завершения. Deployment, live API/bot и owner acceptance не входят в эту проверку.

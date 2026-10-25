# B02: сверка заказанных, отменённых и возвращённых единиц — 25.10.2026

## Фактические данные владельца

### Ozon Analytics, 01–31.08.2026

- Ответ содержит 31 дневную строку, даты покрывают весь период.
- `ordered_units`: total и сумма дневных значений равны **6 117**.
- `cancellations` и `returns`: totals отсутствуют, все 31 дневная строка без значения. Это отсутствие метрики, а не наблюдаемый ноль.

### Seller API `/v1/returns/list`, выборка по периоду

- Диагностика прочитала FBO и FBS полностью: FBO — 1 страница, **272 строки / 272 уникальных ID**; FBS — 1 пустая страница, выборка полная.
- FBO types: `Cancellation` — **270 строк, quantity 270**; `ClientReturn` — **2 строки, quantity 2**. Статусы движения являются отдельными полями и не заменяют тип записи.
- `visual.change_moment` в ответах: 01.08.2026 01:15:16Z — 31.08.2026 20:53:08Z. SKU, названия, ID и raw rows в Git не сохраняются.
- Источник описывает пагинацию через `last_id`/`has_next`, предел `limit=500`, и разрешает ровно один date filter из `logistic_return_date`, `storage_tariffication_start_date`, `visual_status_change_moment`. Бот использует `visual_status_change_moment` для окна смены статуса; исходное описание было предоставлено владельцем, контракт transport проверен тестами. [Официальная документация Seller API](https://docs.ozon.ru/api/seller/?__rr=1&abt_att=1#operation/returnsList).

## Сопоставление с кодом

| Показатель | Текущий источник | Зерно и date basis | Вывод / ограничение |
|---|---|---|---|
| Заказанные единицы | Analytics `ordered_units`; существующая постраничная загрузка daily rows | Дневные метрики аналитики | 6 117 подтверждено: totals совпали с суммой дневных значений. Не равно реализованным единицам из realization и не обязано совпасть с ним. |
| Отменённые единицы Analytics | Analytics `cancellations`, если значения действительно присутствуют | Дневные метрики Analytics | За август значения отсутствуют в totals и каждой строке: сохранять unknown. |
| Резервная оценка отмен | `/v3/posting/fbs/list` и FBO posting list со статусом cancelled | Отправления, попавшие в date filter API, имеющие status cancelled на момент запроса; суммируется `product.quantity` | В подписи это ограничено отправлениями фильтра периода; не историческое число событий отмены за период. Доля с `ordered_units` скрыта, потому что когорты несовместимы. Неполная страница/ошибка оставляет unknown. |
| Возвраты клиентов | `/v1/returns/list`, только `type=ClientReturn`, `product.quantity` | `visual_status_change_moment` в фильтре; статусы движения остаются атрибутом | По предоставленному полному августовскому ответу: 2 записи/2 единицы. `Cancellation` не добавляется в клиентские возвраты. Не доказывает фактическое восстановление saleable inventory или Return COGS. |

В `_load_return_units` неизвестный ID, конфликтный duplicate, malformed quantity для `ClientReturn`, ошибка, пустая страница с `has_next=true` либо исчерпание page budget не публикуются как полный итог. В возвратном источнике повтор одного ID со вторым payload не суммируется молча. Бот скрывает долю cancellation/return к `ordered_units`, пока date cohort не подтверждён.

## Gap-решение

- Подтверждённого дефекта B02 не найдено; production-код не менялся. Ранее видимая проблема `Analytics не вернул отмены/возвраты` — ограничение источника, не повод показывать ноль.
- В отчёте нужно сохранить различие между `ordered_units`, текущим cancelled posting fallback и `ClientReturn` quantity по дате смены статуса. Нельзя суммировать 270 Cancellation в клиентские возвраты или выводить из них восстановленный товар.
- A04 сможет сверить деньги и количество по реальным файлам, но месячный отчёт реализации и один акт не заменяют полный источник заказа/отмены за август. Пригодного бесплатного отчёта для исторической даты отмены в имеющихся материалах не обнаружено; ограничения остаются видимыми.

## Проверки B02

- `tests/test_experimental_store_economics.py`, `tests/test_returns_buyout_facts_source.py`, `tests/test_period_profit_returns_timestamp_v1191_v1200.py`, `tests/test_period_profit_return_evidence_service.py` — **73 passed in 2.48s** с отдельным storage root.
- Покрытие включает пропущенные Analytics metrics, FBO+FBS, `quantity > 1`, исключение `Cancellation` из ClientReturn, ID duplicates/conflicts, full pagination и fail-closed partial page, UTC full-day filter и скрытие процента при несовместимой когорте.
- Никаких live Ozon запросов не выполнялось в рамках разработки; использовался ранее вручную запущенный владельцем обезличенный diagnostic result. Бот и пользовательские DB не запускались.

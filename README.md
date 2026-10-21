# AI Assistant

Telegram-бот для аналитики магазина Ozon: прибыль по периоду и товару, экономика магазина, себестоимость, возвраты и товарные решения. Доступ к Ozon используется для чтения данных; бот не меняет цены, рекламу, поставки или карточки товаров.

## Локальный запуск на Windows

Нужен Python 3.12. Скрипт создаёт виртуальную среду и локальный `.env` при первом запуске. Добавьте токен своего Telegram-бота в `.env` и запустите скрипт повторно.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_bot.ps1
```

### Управление экземпляром бота

Обычный запуск остаётся видимым в текущем окне PowerShell. Для фонового запуска используйте:

```powershell
.\start_bot.ps1 -Background
```

Проверить, что Telegram polling действительно готов, и штатно остановить свой экземпляр можно так:

```powershell
.\status_bot.ps1
```

```powershell
.\stop_bot.ps1
```

Бот не запускает второй polling с тем же токеном в другом окне или checkout. Разные токены имеют независимые экземпляры. Команда остановки ждёт подтверждения до 15 секунд и не завершает процессы Python принудительно; если срок истёк, проверьте состояние повторной командой `status_bot.ps1`.

Для запуска проверок установите зависимости разработчика:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Проверки

```powershell
$env:PYTHONPATH = Join-Path $PWD 'app'
```

```powershell
.\.venv\Scripts\python.exe -m compileall -q app
```

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Стандартная команда `pytest` охватывает тесты из `tests` и `app/tests`. GitHub Verify запускает тот же набор на Linux/Python 3.11 и собирает Docker-образ.

## Документация

- [Текущее состояние](project_brain/CURRENT_STATE.md)
- [Карта тестов](project_brain/TEST_MAP.md)
- [Архитектурные решения](project_brain/DECISIONS.md)
- [Архитектура проекта](ARCHITECTURE.md)
- [План развития](project_brain/ROADMAP.md)
- [Руководство Telegram-бота](docs/telegram-user-guide.md)
- [Аудит и ТЗ на 12.10.2026](project_brain/PROJECT_AUDIT_2026-10-12.md)
- [Очередь заданий для GPT Luna](project_brain/LUNA_DEVELOPMENT_TASK_2026-10-12.md)

## Планы юнит-экономики

Текущая юнит-экономика и новый сценарий цены могут автоматически учитывать
средний расход кросс-докинга за 56 завершённых дней. Бот делит фактические
начисления Ozon с корректировками на реально принятые cross-dock единицы,
используя данные по SKU, а при общих начислениях — отдельную оценку по магазину.
Если финансовый или поставочный источник неполон, сумма не подставляется как
ноль: экран явно сообщает, что расчёт показан без кросс-докинга. Исторические
отчёты магазина этим компонентом не переписываются.

Сохранённые одиночные и пакетные планы фиксируют ставку и безопасные сведения
об источнике в своей версии. Открытие плана использует этот снимок и не делает
запрос к Ozon; явное обновление источников позволяет сохранить новые данные в
следующей ревизии или отдельной копии. Старые планы остаются на прежней формуле
и не получают новые поставки задним числом. В плане объёма историческая ставка
умножается на заданное число успешных продаж по каждому SKU. Если хотя бы для
одного товара ставка не подтверждена, бот показывает частичный subtotal и не
выдаёт общую прибыль и маржу как полные. Сверка с фактом остаётся без вычета
планового кросс-докинга.

Полностью собранное 56-дневное окно само по себе не означает, что ставка для
SKU доступна. Если у товара нет подходящих фактически поставленных единиц,
сохранённый снимок отмечает полное окно и недоступную ставку отдельно; числовой
расход не подставляется.

В калькуляторе цены можно сохранить текущие допущения как локальный план и
открыть его позже в `📚 Мои планы`. Просмотр показывает сохранённый исторический
снимок и не обращается к Ozon. Обновление источников — отдельное действие;
после него можно сохранить новую ревизию исходного плана через проверку версии
или создать отдельную копию. Это планирование, не запись факта магазина.

В single и batch планах доступен расчёт допустимой рекламной доли для
безубыточности и заданной маржи. Это предел на одну успешную продажу от цены
продавца, а не прогноз эффективности кампании. Подстановка возможна только в
текущую локальную версию после повторной проверки; сохранённая историческая
версия остаётся только для просмотра.

Saved plans can also calculate a manually specified mix of successful sales for
one period. Enter an explicit quantity per SKU (unknown is different from
zero) and confirm the list of additional period expenses, including an empty
list when applicable. Rounded per-sale components are multiplied by quantity;
the existing tax service calculates one tax for the aggregate. Partial inputs
show a confirmed subtotal without presenting a final group profit or margin.
The result is a scenario for the selected SKUs, not a demand forecast or total
store profit.

Saved sales mixes can be explicitly compared with finalized facts for the same
period and exact selected SKUs. The bot displays only compatible quantity and
gross-revenue measures, gives their arithmetic bridge, and marks group profit
as not comparable when advertising, external expenses, or return COGS do not
share a proven scope. One immutable short-lived result powers the screen and
CSV/JSON. `Готовность плана` separates calculation status, historical
assumptions, and fact-comparison status, with direct links to a missing SKU
input or sales quantity. Updating a saved sales-mix quantity creates a new
revision only after preview and confirmation.

В `📚 Мои планы` можно сравнить две сохранённые версии одного магазина. Бот
показывает, какие допущения изменились — например, цена, количество продаж или
расходы — и рассчитывает разницу результата только если период, SKU и версия
расчёта совместимы. Историческое сравнение не обращается к Ozon. Из открытой
карточки доступны CSV/JSON выгрузки плана, лимита рекламы, sales mix и
сравнения; выгрузка повторяет тот же снимок, который показан в сообщении.

Реальное окружение продавца хранится локально. Не добавляйте `.env`, базы SQLite, резервные копии или сырые ответы Ozon в Git.

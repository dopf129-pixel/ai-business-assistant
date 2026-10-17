# Telegram bot: quick user guide

The bot is designed so routine seller actions are available from inline buttons.
Send `/start` to resume required setup or open the main menu. Use
`❓ Помощь и команды` at any time to open the in-bot guide.

## Main actions

- `💵 Прибыль за период` — account Period Profit and profit for a selected SKU;
- `💰 Себестоимость` — guided current seller-cost update;
- `💰 Юнит-экономика товаров` — per-product economics;
- `🎯 Решения по товарам` — read-only product recommendations;
- `↩️ Расходы на возвраты` — return finance impact;
- `🧠 Память` — seller facts explicitly saved for the assistant;
- `❓ Помощь и команды` — complete command memo and valid phrase examples;
- `ℹ️ О боте / версия` — revision captured by the running process and its UTC start time.

If no validated build revision is available, the bot labels itself as a local build
with no version set. The version display is read-only and reflects the running
process; updating files on disk does not change it until that process is restarted.

## Аналитика прибыли магазина

После отчёта `Прибыль за период` нажмите `📊 Аналитика периода`. Там доступны
сравнение с предыдущим равным периодом, разбор подтверждённых изменений прибыли,
вклад однозначно сопоставленных товаров и полнота данных. Кнопка `↩️ К расчёту`
возвращает исходный отчёт; из вклада SKU можно открыть уже существующий выбор
товара.

Все экраны показывают тот же расчёт и ту же выбранную пару периодов. Открытие
деталей не обновляет данные Ozon. Снимок доступен 10 минут и привязан к магазину
и пользователю; после истечения срока нужно заново запросить прибыль. Если
сопоставление периодов или SKU неполное, бот явно сообщает об этом и не считает
отсутствующие значения нулевыми.

В отчёте периода доступны `⬇️ CSV` и `⬇️ JSON`. Для обзора товаров, пакетного
плана и чувствительности отдельные кнопки выгружают весь открытый снимок и его
текущий scope, а не только видимую страницу. Открытие и скачивание используют
уже рассчитанные данные; обновление источников выполняется только отдельным
действием. Плановые выгрузки описывают сценарий и не меняют цену в Ozon.

На экране полноты данных выберите \`❓ Почему расчёт неполный?\`, чтобы увидеть
подтверждённые причины неполноты, состояние источников и счётчики операции.
Экран использует тот же снимок, не обновляет Ozon автоматически и предлагает
доступные действия, например заполнить себестоимость, проверить SKU или явно
пересчитать отчёт.

Кнопка «📦 Сохранить диагностику» создаёт обезличенный JSON для поддержки.
В нём остаются только коды, типы полей, счётчики, период и псевдонимы SKU;
суммы, названия товаров, исходные идентификаторы и ответы API не добавляются.
Файл доступен только владельцу исходного отчёта, в том же магазине и пока не
истёк снимок. Экспорт использует кэш и не повторяет запросы к Ozon.
Диагностический JSON также содержит revision и время старта процесса, если они
прошли проверку формата.

## Планирование цены SKU

В существующем калькуляторе выберите товар и задайте недостающие допущения
(например, рекламу). Кнопка `Цена для целевой маржи` принимает процент от 0 до
100 и показывает проверенный ориентир безубыточности и цену для цели. Кнопка
`Сравнить цены` принимает от двух до пяти разных цен через `;` или с новой
строки; например, `499,90; 549,90; 599,90`. Если ранее в этом сценарии была
введена целевая маржа, таблица показывает, достигнута ли она каждой ценой.
Кнопка под строкой подставляет её цену только в текущий расчёт; кнопка в
результате цели подставляет цену, прошедшую проверку целевой маржи.

Это локальный сценарий одной успешной продажи FBO: цена Ozon не меняется,
себестоимость и расходы не сохраняются. Неизвестные обязательные расходы нужно
задать отдельно; бот не считает их нулём. Комиссия может измениться при новой
цене; FBS, постоянные расходы, хранение и возвраты не моделируются.

## Text commands

- `/start` — setup/main menu;
- `/help` — in-bot guide;
- `/memory` — saved facts;
- `/ozon_connect CLIENT_ID API_KEY` — connect a seller account;
- `/ozon_status` — connection status;
- `/ozon_disconnect` — remove the locally stored API key;
- `/costsku SKU AMOUNT` — technical current-cost fallback; normal users should
  prefer the guided `Себестоимость` button.

## Free-text examples

- `запомни цена sky = 1290`
- `прибыль с 01.08.2026 по 31.08.2026`
- `SKU 123: себестоимость 450 ₽ с 01.01.2026`
- `SKU 111 и SKU 222 — один товар`

Historical cost requires an explicit effective date. Product identity and cost
are separate facts. Unknown financial data is never converted to zero or false.
Ozon access remains strictly read-only, and API keys are never echoed.

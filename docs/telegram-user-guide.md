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
- `❓ Помощь и команды` — complete command memo and valid phrase examples.

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

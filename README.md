# AI Assistant

Telegram-бот для аналитики магазина Ozon: прибыль по периоду и товару, экономика магазина, себестоимость, возвраты и товарные решения. Доступ к Ozon используется для чтения данных; бот не меняет цены, рекламу, поставки или карточки товаров.

## Локальный запуск на Windows

Нужен Python 3.12. Скрипт создаёт виртуальную среду и локальный `.env` при первом запуске. Добавьте токен своего Telegram-бота в `.env` и запустите скрипт повторно.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_bot.ps1
```

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

Реальное окружение продавца хранится локально. Не добавляйте `.env`, базы SQLite, резервные копии или сырые ответы Ozon в Git.

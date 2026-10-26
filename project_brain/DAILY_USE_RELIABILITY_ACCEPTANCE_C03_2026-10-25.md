# C03: ожидание, повторы и поздний результат — 25.10.2026

## Результат

Сохранены существующие inflight guards и общий request/time budget. Одинаковые callback расчёта не запускают вторую копию; одинаковые callback нового точного refresh также классифицируются как расчёт и используют оба уровня дедупликации. Даты/текущий источник повторно запрашиваются только по явному callback обновления. Повтор после лимита не скрывает ошибку под успешным состоянием: HTTP 429 показывается как недоступные финансовые данные с безопасным diagnostic code; timeout и исчерпанный бюджет остаются fail-closed. Retry 503 ограничен существующим бюджетом Ozon client.

Подтверждён дефект конкурентного пользовательского состояния: долгий read-only расчёт мог завершиться после переключения активного магазина и вернуть отчёт старого магазина в текущий чат. `TelegramBotService` теперь сравнивает tenant scope после callback-расчёта и read-only текстового запроса. Если scope изменился, старый результат заменяется сообщением о переключении магазина. Сам API запрос не отменяется насильно; его границы остаются текущими cooperative time/request budgets. Custom period prompt можно отменить до выполнения; старый callback после переключения магазина не получает валидный cached view.

## Проверки

Связанный профиль (`test_telegram_calculation_inflight_dedup.py`, `test_period_profit_operation_diagnostics.py`, `test_period_profit_finance_safe_diagnostics.py`, `test_period_profit_finance_retry_v1441_v1450.py`, `test_period_profit_previous_period_single_pass.py`, `test_telegram_loading_feedback_v1451_v1460.py`): **44 passed, 1 deselected in 3.04s**.

- Новые regressions моделируют переключение магазина во время callback и во время read-only текстового расчёта; оба результата старого scope подавляются.
- Существующие проверки подтверждают same-scope duplicate rejection, независимость разных магазинов/периодов, освобождение inflight key после exception, ограниченный retry 503, fail-closed после retry budget, 429/timeout diagnostics, точные request/time budget, progress before result, error replacement и keyboard на последнем сообщении.
- Исключён `test_long_running_trace_writes_secret_free_worker_snapshot`: его fixture обращается к заблокированному Windows pytest `tmp_path`. Exact-head CI должен выполнить его.
- In-memory compile 3 изменённых Python файлов и `git diff --check`: **passed**. Полный pytest локально не выполнялся.

Статус C03: `DONE_LOCAL`. Exact-head CI и PR ещё предстоят; merge, deploy и запуск настоящего бота не выполнялись.

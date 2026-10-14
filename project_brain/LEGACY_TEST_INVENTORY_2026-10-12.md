# Инвентарь корневых legacy-тестов — 12.10.2026

Обнаружено статическим обходом: **90 файлов**, **206 методов `test_*`**. Все модули импортируют `unittest`; прямых импортов `requests`, `httpx`, `urllib` или `socket` не найдено. pytest по умолчанию не собирает их, потому что `pytest.ini` ограничивает discovery каталогами `tests` и `app/tests`.

Классификация в таблице — предварительная, по форме теста и имени модуля: тесты одного сервиса отмечены unit-кандидатами; сценарии с flow/pipeline/runner — integration-кандидатами. Сетевые/live/demo вызовы не обнаружены прямым поиском импорта, однако безопасность вызываемых production-клиентов не доказана. Все файлы **не запускались** и остаются вне CI до изолированной проверки зависимостей и fixture setup. Не добавлять broad skip/xfail ради обхода этой инвентаризации.

`test_telegram_bot_service_flow.py` и `test_telegram_runner_flow.py` отдельно проверить на Telegram polling/network side effects. `test_assistant.py` в показанных finance tests подменяет клиента fake; остальные ветви всё ещё требуют review.

Предварительный итог: **unit-кандидаты — 34; integration-кандидаты — 56**. Эти числа не являются подтверждением offline-поведения.

| Файл | Методов `test_*` | Предварительная классификация |
|---|---:|---|
| `test_action_dashboard_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_action_dashboard_service.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_action_full_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_action_history_persistence.py` | 1 | Кандидат unit; внешние зависимости проверить |
| `test_action_history_service.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_action_history_update.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_action_lifecycle_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_action_pipeline_service.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_action_query_service.py` | 3 | Кандидат unit; внешние зависимости проверить |
| `test_action_status_service.py` | 3 | Кандидат unit; внешние зависимости проверить |
| `test_action_storage_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_action_workflow_service.py` | 3 | Кандидат integration; внешние зависимости проверить |
| `test_analysis_period.py` | 11 | Кандидат unit; внешние зависимости проверить |
| `test_assistant.py` | 12 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_action_execution_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_action_generator_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_action_plan_executor_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_autonomous_action_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_business_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_business_planner_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_button_handler_flow.py` | 5 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_command_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_command_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_context_resolver_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_conversation_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_core_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_end_to_end_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_entry_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_full_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_intent_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_intent_service.py` | 3 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_keyboard_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_main_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_memory_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_memory_integration.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_memory_service.py` | 3 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_memory_storage_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_orchestrator_business_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_orchestrator_service.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_orchestrator_v2_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_planning_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_priority_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_real_scenarios.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_recommendation_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_request_context_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_response_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_response_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_assistant_session_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_telegram_adapter_flow.py` | 3 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_user_context_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_user_memory_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_assistant_user_profile_flow.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_business_analytics.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_business_profit.py` | 6 | Кандидат unit; внешние зависимости проверить |
| `test_conversation_history_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_finance_analytics.py` | 6 | Кандидат unit; внешние зависимости проверить |
| `test_period_comparison.py` | 6 | Кандидат unit; внешние зависимости проверить |
| `test_profit.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_recommendation_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_analytics.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_store_comparison_report.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_analytics.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_insight_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_profit.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_report.py` | 3 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_runner.py` | 3 | Кандидат integration; внешние зависимости проверить |
| `test_store_period_summary.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_store_period_summary_formatter.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_profit.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_store_report_dashboard_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_dashboard_service.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_full_persistent_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_history_service.py` | 4 | Кандидат unit; внешние зависимости проверить |
| `test_store_report_history_storage_integration.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_manager.py` | 1 | Кандидат unit; внешние зависимости проверить |
| `test_store_report_manager_validation.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_store_report_orchestrator.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_orchestrator_error.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_orchestrator_service_errors.py` | 2 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_persistent_pipeline_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_pipeline_errors.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_pipeline_service.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_presentation_service.py` | 1 | Кандидат unit; внешние зависимости проверить |
| `test_store_report_real_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |
| `test_store_report_storage_service.py` | 2 | Кандидат unit; внешние зависимости проверить |
| `test_tax.py` | 6 | Кандидат unit; внешние зависимости проверить |
| `test_telegram_bot_service_flow.py` | 3 | Кандидат integration; внешние зависимости проверить |
| `test_telegram_runner_flow.py` | 3 | Кандидат integration; внешние зависимости проверить |
| `test_telegram_user_memory_flow.py` | 1 | Кандидат integration; внешние зависимости проверить |

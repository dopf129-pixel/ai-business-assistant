# Test Map


## Current Status


Total:

63 passed


---


# Stabilization Checkpoint


Tests:


- test_action_context.py


Проверяет:


- сохранение Action schema
- сохранение priority
- сохранение context
- сохранение reason внутри context
- совместимость Action Generator и Action Executor



Result:


63 passed



---


# Core Flow


## Main assistant flow


Tests:


- test_full_dependency_flow.py
- test_replanning_integration.py
- test_full_memory_agent_loop.py


Проверяет:


- полный путь пользователя
- создание плана
- выполнение действий
- зависимости
- replanning
- memory cycle



---


# Intent System


Service:


AssistantIntentService


Tests:


- test_intent*.py


Проверяет:


- команды пользователя
- подтверждение
- отмену
- паузу
- продолжение



---


# Task Lifecycle


Service:


AssistantTaskService


Tests:


- test_task_flow.py
- test_task_lifecycle_flow.py
- test_task_state_integration.py
- test_task_state_machine.py
- test_task_states.py


Проверяет:


- создание задачи
- состояния
- переходы
- завершение
- отмену
- паузу
- возобновление



---


# Action System


Services:


- AssistantActionGeneratorService
- AssistantActionPlanExecutorService
- AssistantActionExecutionService


Tests:


- test_action_context.py
- test_action_dependencies.py
- test_memory_guided_actions.py


Проверяет:


- генерацию действий
- priority
- context
- зависимости
- использование опыта при генерации действий
- сохранение Action contract



---


# Executors


Services:


- AssistantSalesExecutorService
- AssistantStockExecutorService
- AssistantMarketingExecutorService
- AssistantActionRouterService


Tests:


- test_action_dependencies.py
- test_full_dependency_flow.py


Проверяет:


- выбор исполнителя
- выполнение действия
- маршрутизацию



---


# Conditions


Tests:


- test_condition_skip.py


Проверяет:


- condition.contains
- блокировку действия
- статус SKIPPED
- skip_reason



---


# History


Services:


- ActionHistoryService
- AssistantTaskService


Tests:


- test_history.py
- test_history_response_skip.py
- test_history_failure.py
- test_retry_history.py
- test_retry_blocked_history.py


Проверяет:


- сохранение истории
- вывод пользователю
- причины пропуска
- ошибки выполнения
- retry события



---


# FAILED Execution Handling


Services:


- AssistantActionExecutionService
- RetryPolicyService


Tests:


- test_action_execution_failure.py
- test_retry_execution.py
- test_retry_policy.py
- test_retry_policy_integration.py
- test_retry_limit.py
- test_retry_limit_integration.py


Проверяет:


- перехват ошибок
- FAILED статус
- сохранение ошибки
- повторное выполнение
- retry policy
- ограничение количества попыток



---


# Smart Planning


Services:


- AssistantPlanningService
- AssistantReplanningService


Tests:


- test_multi_level_dependencies.py
- test_dependency_chain_validation.py
- test_dependency_validation.py
- test_dependency_cycle.py
- test_auto_replanning.py
- test_replanning_service.py
- test_replanning_execution_flow.py
- test_replanning_updates_task.py
- test_automatic_replanning_engine.py
- test_plan_correction.py


Проверяет:


- многоуровневые зависимости
- проверку плана
- обнаружение конфликтов
- автоматическое перепланирование
- корректировку плана



---


# Feedback Loop


Services:


- AssistantFeedbackService


Tests:


- test_feedback_loop.py
- test_feedback_auto_record.py
- test_feedback_execution_hook.py


Проверяет:


- получение результата выполнения
- анализ результата
- создание feedback события



---


# Memory System


Services:


- AssistantMemoryService


Tests:


- test_memory_service.py
- test_memory_integration.py
- test_feedback_memory_integration.py
- test_feedback_to_memory_flow.py


Проверяет:


- сохранение опыта
- получение опыта
- связь Feedback → Memory
- хранение результатов выполнения



---


# Memory-driven Planning


Services:


- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_memory_planning_integration.py
- test_memory_driven_planning.py
- test_memory_context_in_plan.py
- test_memory_guided_actions.py


Проверяет:


- поиск прошлого опыта
- передачу памяти в планирование
- использование опыта при генерации действий



---


# Full Autonomous Memory Loop


Tests:


- test_full_memory_agent_loop.py


Проверяет:


- выполнение задачи
- создание feedback
- сохранение опыта
- использование памяти в будущем



---


# Context


Services:


- AssistantUserContextService
- AssistantRequestContextService
- AssistantTaskContextService


Tests:


- test_action_context.py


Проверяет:


- передачу контекста
- сохранение данных пользователя



---


# Development Autopilot


Service:


AssistantChangeImpactService


Tests:


- test_change_impact.py


Проверяет:


- анализ изменяемого файла
- поиск затронутых сервисов
- поиск связанных тестов
- поиск связанной документации



---


# Development Rule


Новый функционал обязан:


1. иметь тест


2. быть добавлен в эту карту


3. обновить CURRENT_STATE.md


4. обновить CHANGELOG.md при завершении этапа


5. добавить архитектурное решение в DECISIONS.md при изменении структуры системы



---


# Development Autopilot


Service:


AssistantDocumentationManager


Tests:


- test_documentation_manager.py


Проверяет:


- безопасное добавление CHANGELOG записей
- безопасное добавление DECISIONS записей
- сохранение существующей истории
- append-only правило документации


---



# Development Autopilot


Service:


AssistantDocumentationDriftService


Tests:


- test_documentation_drift.py


Проверяет:


- поиск сервисов без документации
- контроль связи app/services и TEST_MAP.md
- обнаружение простого documentation drift

---

# Development Autopilot


Service:


AssistantDevelopmentWorkflowService


Tests:


- test_development_workflow.py


Проверяет:


- запуск development workflow
- создание последовательности шагов
- контроль состояния workflow
- завершение отдельных этапов

---

# Development Autopilot


Service:


AssistantGitCheckpointService


Tests:


- test_git_checkpoint.py


Проверяет:


- подготовку Git checkpoint
- анализ изменённых файлов
- создание checkpoint metadata
- подготовку commit message
- отсутствие автоматического commit

---

# Development Autopilot


Service:


AssistantProjectBrainManager


Tests:


- test_project_brain_manager.py


Проверяет:


- безопасное добавление записей в Project Brain
- сохранение существующей истории
- append-only обновления документации
- подготовку документационных изменений агентом

---

# Sales Intelligence


Service:


SalesIntelligenceService


Tests:


- test_sales_intelligence_service.py


Проверяет:


- constructor injection аналитического сервиса
- нормализацию sales metrics
- передачу previous period context
- формирование sales decline insight
- безопасный проброс ошибки аналитического слоя
- отсутствие зависимости от Action/Executor orchestration

---

# Sales Intelligence Integration


Services:


- SalesIntelligenceService
- AssistantSalesExecutorService


Tests:


- test_sales_intelligence_executor_integration.py


Проверяет:


- constructor injection Sales Intelligence в Sales Executor
- передачу profits и previous_result из Action context
- сохранение существующего executor contract
- преобразование metrics и insights в details
- проброс ошибки Sales Intelligence
- обратную совместимость executor без injected service

---

# Sales Intelligence Context Propagation


Services:


- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_sales_intelligence_context_propagation.py


Проверяет:


- перенос sales_context из report в sales recommendation
- сохранение profits и previous_result при построении plan
- сохранение sales context при генерации Action
- отсутствие обратной мутации recommendation context при enrichment Action
- отсутствие изменений Task Service и Executor pipeline

---

# Sales Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- StoreAnalyticsService
- SalesIntelligenceService
- AssistantSalesExecutorService


Tests:


- test_sales_intelligence_production_wiring.py


Проверяет:


- создание StoreAnalyticsService в production composition root
- constructor injection analytics service в SalesIntelligenceService
- constructor injection SalesIntelligenceService в AssistantSalesExecutorService
- доступ production-wired Sales Executor через существующий Router
- выполнение sales action через production wiring
- отсутствие изменений Task Service, Action Execution и Router

---

# Sales Intelligence Business Data Input


Services:


- AssistantEntryService
- ProductService
- StorePeriodProfitService
- StoreAnalyticsService


Tests:


- test_sales_intelligence_business_data_input.py


Проверяет:


- пользовательский запрос начинается с AssistantEntryService
- загрузку product data через injected ProductService
- расчёт profits текущего и предыдущего периода через injected StorePeriodProfitService
- формирование sales_down из реального period comparison contract
- добавление profits и previous_result в report.sales_context
- сохранение sales_context через recommendation → planning → action generation
- нормализацию существующего SQLite product tuple на data-input boundary
- обратную совместимость AssistantEntryService без data dependencies
- отсутствие изменений Task/Action/Executor pipeline

---

# Stock Intelligence Foundation


Service:


StockIntelligenceService


Tests:


- test_stock_intelligence_service.py


Проверяет:


- расчёт current_stock из подготовленных stock data
- расчёт sales_velocity по sales_count и period_days
- расчёт days_of_stock
- классификацию CRITICAL/HIGH/MEDIUM/LOW reorder priority
- no sales case без деления на ноль
- empty/missing data contract
- отсутствие API clients, repositories и Action pipeline dependencies внутри domain service

---

# Stock Intelligence Integration


Services:


- StockIntelligenceService
- AssistantStockExecutorService


Tests:


- test_stock_intelligence_executor_integration.py


Проверяет:


- constructor injection Stock Intelligence в Stock Executor
- передачу stock_data, sales_data и period_days из Action context
- вызов StockIntelligenceService через существующий Stock Executor
- сохранение существующего executor response contract
- преобразование Stock Intelligence результата в details
- обратную совместимость executor без injected service
- отсутствие изменений Task Service, Action Execution, Router, Planning и Action Generator

---

# Stock Intelligence Context Propagation


Services:


- AssistantEntryService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_stock_intelligence_context_propagation.py


Проверяет:


- перенос подготовленного stock_context из request context в report
- передачу stock_context в stock recommendation
- сохранение stock_data, sales_data и period_days при построении plan
- сохранение stock context при генерации Action
- отсутствие обратной мутации recommendation context при Action enrichment
- отсутствие изменений Task Service, Action Execution, Router, Stock Executor и Stock Intelligence Service

---

# Stock Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- StockIntelligenceService
- AssistantStockExecutorService


Tests:


- test_stock_intelligence_production_wiring.py


Проверяет:


- create_telegram_core() создаёт production Stock executor
- constructor injection StockIntelligenceService в AssistantStockExecutorService
- default reorder policy конфигурацию StockIntelligenceService
- доступ production-wired Stock Executor через существующий Router
- отсутствие изменений Task Service, Action Execution, Router, Planning и Action Generator
- отсутствие преждевременного Business Data Input / Ozon stock ingestion

---

# Stock Intelligence Business Data Input


Services:


- AssistantEntryService
- ProductService
- MetricsService
- StoreAnalyticsService
- FinanceService


Tests:


- test_stock_intelligence_business_data_input.py


Проверяет:


- получение FBO current stock через injected MetricsService
- получение sales_count за текущий period через StoreAnalyticsService.analyze_finance()
- формирование report.stock_context с stock_data, sales_data и period_days
- передачу stock_context в stock recommendation
- сохранение stock_context до Action Generator
- безопасный fallback без stock recommendation при недоступных stock data
- отсутствие изменений Task Service, Action Execution, Router, Stock Executor и StockIntelligenceService

---

# Finance Intelligence Foundation


Service:


FinanceIntelligenceService


Tests:


- test_finance_intelligence_service.py


Проверяет:


- нормализацию revenue, expenses, profit и margin
- вычисление profit и margin из подготовленных finance data
- insight для положительной прибыли
- обнаружение падения прибыли относительно предыдущего периода
- обнаружение роста расходов относительно предыдущего периода
- безопасный contract при отсутствии данных
- отсутствие dependencies на repositories, API clients и Action/Task/Executor pipeline

---

# Finance Intelligence Executor Integration


Services:


- FinanceIntelligenceService
- AssistantFinanceExecutorService


Tests:


- test_finance_intelligence_executor_integration.py


Проверяет:


- constructor injection FinanceIntelligenceService в Finance Executor
- передачу finance_data и previous_data из Action context
- вызов FinanceIntelligenceService через Finance Executor
- сохранение существующего executor response contract
- преобразование finance metrics и insights в details
- fallback без injected FinanceIntelligenceService
- отсутствие изменений Task Service, Action Execution, Router, Planning, Sales и Stock workflow

---

# Finance Intelligence Context Propagation


Services:


- AssistantEntryService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_finance_intelligence_context_propagation.py


Проверяет:


- перенос prepared finance_context из request context в report
- передачу finance_context в finance recommendation
- сохранение finance_data и previous_data при построении plan
- сохранение finance context при генерации Action
- отсутствие обратной мутации исходного и recommendation context
- отсутствие изменений Task Service, Action Execution, Router, Finance Executor и FinanceIntelligenceService

---

# Finance Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- FinanceIntelligenceService
- AssistantFinanceExecutorService
- AssistantActionRouterService


Tests:


- test_finance_intelligence_production_wiring.py


Проверяет:


- create_telegram_core() создаёт production Finance executor
- constructor injection FinanceIntelligenceService в AssistantFinanceExecutorService
- наличие finance executor в существующем Router registry
- сохранение sales и stock executor mappings
- отсутствие Finance Data Input и новых finance data dependencies

---

# Finance Intelligence Business Data Input


Services:


- AssistantEntryService
- StorePeriodProfitService
- FinanceAnalyticsService
- ProfitService


Tests:


- test_finance_intelligence_business_data_input.py


Проверяет:


- использование existing current/previous period boundaries
- получение реальных по contract period profits через StorePeriodProfitService
- формирование finance_data и previous_data из gross_sales/gross_profit
- расчёт expenses как revenue - profit и margin для каждого периода
- сохранение finance_context в report
- передачу finance_context через recommendation → planning → action.context
- безопасное отсутствие finance recommendation при пустых finance data
- отсутствие новых repositories, API clients и orchestration layers

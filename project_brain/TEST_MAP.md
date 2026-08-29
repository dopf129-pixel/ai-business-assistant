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

---

# Product-Level Finance Metrics


Services:


- StorePeriodProfitService
- ProfitService
- ProductProfitabilityProvider
- FinanceContextProvider


Tests:


- test_product_level_finance_metrics.py


Проверяет:


- сохранение product_id и sku на существующей period-profit data boundary
- подготовку product-level sales_count, revenue, cost, profit и margin без повторного расчёта прибыли
- безопасный пустой результат при отсутствии profits
- пропуск неполных sales/cost records вместо формирования вводящих в заблуждение metrics
- сохранение существующего FinanceContextProvider contract без product-level расширения
- отсутствие новых repositories, API clients, workflow и Cross-Domain logic

---

# Product Unit Economics Foundation v1.1


Services:


- ProductUnitEconomicsProvider
- TaxService
- ProductProfitabilityProvider
- ProfitService
- StorePeriodProfitService


Tests:


- test_product_unit_economics.py


Проверяет:


- расчёт SKU-level marketplace fees из revenue и net_accrual
- использование существующего TaxService для product-level tax
- расчёт net_profit, profit_per_unit и margin_percent после налога
- явный incomplete contract при отсутствии tax policy
- безопасный пропуск SKU без cost data
- поддержку нескольких SKU
- сохранение существующего ProductProfitabilityProvider contract
- отсутствие изменений Entry/Recommendation/Planning/Action/Executor workflow

---

# Product Unit Economics Query v1


Services:


- ProductUnitEconomicsQueryService
- ProductService
- StorePeriodProfitService
- ProductUnitEconomicsProvider
- TaxService


Tests:


- test_product_unit_economics_query.py


Проверяет:


- поиск SKU через существующий ProductService contract
- выбор только запрошенного SKU для period-profit calculation
- преобразование aggregate product economics в показатели на одну проданную единицу
- unit_price, cost, marketplace_fees, tax, net_profit_per_unit и margin_percent
- SKU_NOT_FOUND при отсутствии товара
- безопасный unavailable contract при отсутствии finance/cost data или продаж
- missing_fields без подстановки неизвестных расходов нулями
- форматирование advertising, storage, returns и неизвестного tax как «—»
- сохранение ProductProfitabilityProvider contract
- отсутствие изменений Entry/Recommendation/Planning/Action/Executor workflow
- отсутствие Cross-Domain логики и нового data layer

---

# Tax Configuration Foundation v1


Services:


- TaxConfigurationService
- TaxService
- ProductUnitEconomicsProvider


Composition Root:


- telegram_core_factory.py


Tests:


- test_tax_configuration_foundation.py


Проверяет:


- сохранение и загрузку tax policy в data/tax_configuration.json
- различие между отсутствующей конфигурацией и явным NONE
- USN_INCOME с configurable tax_rate
- USN_INCOME_MINUS_EXPENSES с minimum tax rate
- явный NONE как сохранённую пользовательскую policy
- безопасный unconfigured contract без скрытого tax=0
- ProductUnitEconomicsProvider возвращает tax/net profit как None при неизвестной policy
- production factory получает tax policy через DI вместо hardcoded tax_mode=NONE
- сохранение sales, stock и finance executor mappings

---

# Product Unit Economics Production Wiring v1


Composition Root:


- telegram_core_factory.py


Services:


- TaxConfigurationService
- TaxService
- ProductUnitEconomicsProvider
- ProductUnitEconomicsQueryService


Tests:


- test_product_unit_economics_production_wiring.py


Проверяет:


- production factory создаёт ProductUnitEconomicsProvider и ProductUnitEconomicsQueryService
- tax policy передаётся из TaxConfigurationService через constructor injection
- запрос SKU использует USN_INCOME
- запрос SKU использует USN_INCOME_MINUS_EXPENSES
- explicit NONE сохраняет настоящий tax=0
- отсутствие tax configuration сохраняет tax/net profit/margin как None
- существующие sales, stock и finance executor mappings не изменяются
- Telegram UI и Action/Executor workflow не затрагиваются

---

# Product Unit Economics Telegram UI v1


UI Boundary:


- AssistantKeyboardService
- AssistantButtonHandlerService
- telegram_assistant_factory.py
- telegram_api_bot.py


Backend:


- ProductUnitEconomicsQueryService


Tests:


- tests/test_product_unit_economics_telegram_ui.py
- test_assistant_keyboard_flow.py


Проверяет:


- кнопку «💰 Юнит-экономика товаров» в существующем main keyboard
- открытие меню выбора SKU
- получение SKU через существующий ProductService внутри query boundary
- callback unit_economics:<sku>
- вызов существующего ProductUnitEconomicsQueryService.query(sku)
- использование существующего format_response() без UI-расчётов
- отображение advertising, storage и returns как «—»
- отсутствие формулировки «Чистая прибыль»
- безопасный ответ при отсутствии товаров или SKU
- сохранение существующих analyze/plan/history/memory callbacks
- отсутствие изменений Sales/Stock/Finance и Action/Executor workflow
---

# Current Unit Economics Integration / Polish

Services:

- CurrentProductEconomicsSource
- ProductUnitEconomicsProvider
- ProductUnitEconomicsQueryService
- TaxConfigurationService

Production wiring:

- current_unit_economics_factory.py
- telegram_assistant_factory.py

Tests:

- test_current_product_economics_source.py
- test_current_unit_economics_finance_sku.py
- test_current_unit_economics_integration.py
- test_current_unit_economics_polish.py
- test_current_unit_economics_production_wiring.py
- test_unit_economics_offer_id_lookup.py

Проверяет:

- актуальную цену продавца из Ozon Price API
- разделение offer_id и внутреннего Ozon SKU
- получение свежих finance expenses
- отдельные logistics / last mile / acquiring
- отсутствие подстановки неизвестных данных нулём
- расчёт налога по TaxConfigurationService
- расчёт прибыли одной текущей единицы
- отображение расходов в рублях и процентах от цены
- production wiring в Telegram
- сохранение старого historical contract
- безопасный fallback

Full suite result:

217 passed

---

# Product Decisions v3 — Assortment Overview

Services:

- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py
- tests/test_product_business_decision_production_wiring.py

Проверяет:

- использование артикула продавца для сводного запроса;
- устранение дубликатов товаров;
- сортировку по приоритету, дням запаса и артикулу;
- подсчёт решений для Telegram-сводки;
- кнопки с приоритетом, артикулом и действием;
- совместимость существующих callbacks карточки товара.

---

# Product Decisions v4 — Cache and Pagination

Services:

- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- повторное использование успешного решения в течение 10 минут;
- истечение TTL и повторный расчёт;
- защиту кэша от внешней мутации;
- отсутствие кэширования ошибок и недостаточных данных;
- восемь товаров на странице Telegram;
- переходы между страницами без изменения callback товара.

---

# Product Decision Memory v1

Services:

- ProductDecisionHistoryService
- ProductDecisionHistoryStorageService
- ProductBusinessDecisionQueryService

Composition:

- product_business_decision_factory.py
- telegram_assistant_factory.py

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py
- tests/test_product_business_decision_production_wiring.py

Проверяет:

- сохранение первой успешной базовой точки;
- отсутствие дубликата неизменившегося решения;
- фиксацию изменения типа решения или приоритета;
- игнорирование ошибок и недостаточных данных;
- ограничение истории на один артикул;
- восстановление истории из JSON;
- передачу истории через query cache;
- понятный переход между решениями в Telegram.

---

# Product Decision Feedback v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- сохранение USEFUL и NOT_RELEVANT в последнем снимке;
- идемпотентность повторной оценки;
- отказ при неизвестном feedback;
- отказ при отсутствии истории решения;
- Telegram-кнопки ручной оценки;
- корректную обработку feedback callback.

---

# Product Decision Outcome Correlation v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- связь feedback предыдущего снимка со следующим изменением;
- распознавание снижения и роста срочности;
- нейтральную смену решения при прежнем приоритете;
- отсутствие вывода без feedback;
- сохранение source_feedback и outcome;
- наблюдательную, не причинную формулировку Telegram.

---

# Product Decision Learning Summary v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- агрегацию товаров, снимков, feedback и outcomes;
- ссылку на итоги обучения из обзора ассортимента;
- вывод фактических количеств без причинных выводов;
- доступ к истории из карточки товара;
- ограничение истории пятью последними снимками в UI;
- перевод решений, приоритетов, feedback и наблюдений.

---

# Safe Product Action Proposals v1

Services:

- ProductDecisionActionProposalService
- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_decision_action_proposal_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- безопасное сопоставление каждого типа решения с proposal;
- обязательное подтверждение для операционных проверок;
- monitoring-only без обязательного действия;
- постоянный execution_allowed=False;
- сохранение proposal в query cache;
- подсчёт предложений по ассортименту;
- русское представление следующего шага без технических кодов.

---

# Product Action Proposal Confirmation v1

Services:

- ProductActionProposalConfirmationService
- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_proposal_confirmation_service.py
- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- сохранение подтверждения и отклонения как намерения;
- идемпотентность повторного статуса;
- отклонение устаревшего и monitoring-only proposal;
- production wiring confirmation-service;
- Telegram callbacks и явный executed=False;
- отсутствие зависимости от Action Executor.

---

# Confirmed Product Task Drafts v1

Services:

- ProductActionTaskDraftService
- ProductActionTaskDraftStorageService
- ProductActionProposalConfirmationService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_action_proposal_confirmation_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- создание одного черновика на снимок решения;
- постоянное хранение и восстановление;
- закрытие черновика после отклонения;
- отсутствие выполнений и разрешения на выполнение;
- Telegram-сводку и переход из меню решений;
- production wiring отдельного draft-service.

---

# Product Task Draft Review Lifecycle v1

Services:

- ProductActionTaskDraftService
- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- устаревание черновика после изменения снимка или proposal;
- сохранение актуального черновика при полном совпадении;
- идемпотентный терминальный архив;
- миграцию legacy-записей с назначением draft_id;
- reconcile в decision query pipeline;
- Telegram-сводку состояний и безопасную кнопку архива;
- постоянный executed=False.

---

# Product Draft Review Queue Prioritization v1

Services:

- ProductTaskDraftReviewQueueService
- AssistantButtonHandlerService
- AssistantKeyboardService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_task_draft_review_queue_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- порядок по актуальности, исходному приоритету и типу review;
- исключение DISMISSED и ARCHIVED;
- oldest-first tie breaker и ограничение выдачи;
- counts по полной очереди до limit;
- русские причины и иконки Telegram;
- постоянный read-only и executed_count=0.

---

# Product Task Draft Detail and Audit v1

Services:

- ProductActionTaskDraftService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- CREATED при создании черновика;
- полный порядок реальных lifecycle events;
- отсутствие событий от idempotent-команд;
- терминальность ARCHIVED;
- безопасное чтение legacy-записи без вымышленного аудита;
- detail callback, source metrics и русские event labels;
- отсутствие archive-кнопки у терминального черновика;
- executed=False во всех audit/detail результатах.

---

# Product Task Draft Readiness Checklist v1

Services:

- ProductTaskDraftReadinessService
- ProductDecisionHistoryService
- ProductActionTaskDraftService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_task_draft_readiness_service.py
- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- готовность полных данных к ручной проверке;
- missing fields без подстановки оценок;
- блокировку устаревшего черновика;
- отдельные policy blockers для каждого proposal;
- summary counts и нулевую execution readiness;
- перенос исходных фактов в draft snapshot;
- Telegram detail и queue presentation.

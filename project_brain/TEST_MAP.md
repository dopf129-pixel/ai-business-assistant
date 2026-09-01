# Test Map


## Current Status


Verification model:

SHA-bound.

Latest confirmed full-suite baseline:

1841 passed on `9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`.

GitHub Actions push Verify #652 completed successfully for this exact main SHA.

Canonical status:

`project_brain/VERIFICATION_STATUS.md`


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


---

# Product Decision Learning Coverage Navigation v1

Services:

- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_learning_coverage_v493_v502.py

Проверяет:

- state-specific переход только в существующий `product_decision:<sku>`;
- отсутствие прямых feedback callbacks из coverage queue;
- отсутствие Product Decision query при открытии очереди;
- fail-closed обработку forged/malformed navigation;
- ограничение навигации видимыми top-10 SKU;
- сохранение `executed=False`.


---

# Store Period Default Composition Hardening

Services:

- StorePeriodRunnerService
- StorePeriodReportService
- StorePeriodSummaryService

Tests:

- test_store_period_runner.py
- test_store_period_report.py
- test_store_period_summary.py

Проверяет:

- отсутствие duplicate runner initialization;
- fail-closed результат при отсутствии period profit dependency;
- сохранение injected report-service path;
- fail-closed malformed summary runner output;
- отсутствие AttributeError на default summary composition.


---

# Unknown Advertising Financial Evidence v1

Services / composition:

- telegram_core_factory.create_telegram_core
- BusinessAnalyticsService
- SalesIntelligenceService
- AssistantSalesExecutorService
- AdvertisingDashboardService
- BusinessProfitDashboardService

Tests:

- tests/test_unknown_advertising_financial_evidence_v514_v520.py
- test_business_analytics.py
- tests/test_sales_intelligence_production_wiring.py

Проверяет:

- production default advertising evidence остаётся unknown;
- explicit zero остаётся известным нулём;
- unknown advertising блокирует business_profit и margin;
- unknown tax + advertising перечисляются как missing evidence;
- tax error не маскируется;
- Sales Intelligence не нормализует unknown profit в zero;
- seller-facing analysis/dashboard presentation показывает «—», а не 0/None.


---

# Finance Context Evidence Hardening v1

Services:

- FinanceContextProvider
- FinanceIntelligenceService
- AssistantFinanceExecutorService

Tests:

- tests/test_finance_context_evidence_v521_v526.py
- tests/test_finance_intelligence_business_data_input.py
- tests/test_finance_intelligence_executor_integration.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- fail-closed malformed/missing/non-finite financial facts;
- explicit zero remains valid;
- backward-compatible FinanceContextProvider output shape;
- no optimistic zero normalization;
- neutral gross-result insight wording;
- evidence-scoped Finance Executor labels;
- existing complete-evidence context propagation.


---

# Stock Evidence Availability Hardening v1

Services:

- StockContextProvider
- StockIntelligenceService
- AssistantRecommendationService

Tests:

- tests/test_stock_evidence_availability_v527_v533.py
- tests/test_stock_intelligence_business_data_input.py
- tests/test_stock_intelligence_service.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- unavailable stock evidence != verified safe stock;
- complete safe assortment evidence;
- preserved confirmed low-stock action context;
- partial/missing metrics and sales evidence;
- malformed/non-finite/boolean/negative values;
- cross-product evidence rejection;
- explicit zero sales / NO_SALES;
- non-clean general fallback wording under incomplete stock evidence.


---

# Sales Evidence Availability Hardening v1

Services:

- SalesContextProvider
- AssistantEntryService
- AssistantRecommendationService
- SalesIntelligenceService
- AssistantSalesExecutorService

Tests:

- tests/test_sales_evidence_availability_v534_v540.py
- tests/test_sales_intelligence_business_data_input.py
- tests/test_sales_intelligence_service.py
- tests/test_sales_intelligence_executor_integration.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- configured unavailable sales evidence != verified no-decline;
- preserved legacy no-data Entry fallback;
- preserved confirmed decline action context;
- malformed products / profit rows / comparison evidence;
- explicit zero change and zero sales metrics;
- malformed action context rejection before analytics;
- required revenue/gross-profit facts;
- unknown business-profit/margin preservation;
- no false stable insight from missing change;
- «—» presentation for unknown sales metrics.


---

# Marketing Evidence Integrity v1

Services:
- AssistantRecommendationService
- AssistantMarketingExecutorService
- AssistantActionRouterService

Tests:
- tests/test_marketing_executor.py
- tests/test_marketing_recommendation.py
- tests/test_marketing_evidence_integrity_v548_v553.py

Проверяет explicit evidence gating, malformed evidence fail-closed, no invented marketing facts и FAILED lifecycle через router.run().

---

# Finance Evidence Availability Propagation v1

Services:

- AssistantEntryService
- FinanceContextProvider
- AssistantRecommendationService

Tests:

- tests/test_finance_evidence_availability_v554_v560.py
- tests/test_finance_context_evidence_v521_v526.py

Проверяет:

- derived finance success -> available;
- derived finance failure with period evidence -> unavailable;
- no invented availability without period data;
- explicit finance context precedence;
- unavailable finance evidence blocks clean fallback;
- contradictory unavailable context does not create finance action;
- legacy finance_context-only callers remain compatible;
- no finance formula/provider-shape change.

---

# Business Planner Result Integrity v1

Services:

- AssistantBusinessPlannerService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionPlanExecutorService
- AssistantTaskService

Tests:

- tests/test_business_planner_result_integrity_v575_v581.py
- tests/test_action_plan_result_integrity_v568_v574.py

Проверяет:

- сохранение explicit downstream error=True без перепаковки в success;
- fail-closed malformed recommendation/planning/execution/task-create payloads;
- exact boolean error contracts;
- actions/count consistency;
- отсутствие task creation после downstream failure;
- сохранение valid plan result и general-only non-actionable path.

---

# Business Flow Result Integrity v1

Services:

- AssistantBusinessFlowService
- AssistantIntentService
- AssistantBusinessPlannerService
- AssistantActionExecutionService
- AssistantTaskService

Tests:

- tests/test_business_flow_result_integrity_v582_v590.py
- tests/test_business_planner_result_integrity_v575_v581.py
- tests/test_action_plan_result_integrity_v568_v574.py

Проверяет:

- malformed intent/result contracts fail closed;
- planner error=True не перепаковывается в success;
- malformed planner actions/count не становятся пустым successful plan;
- execute error/malformed result не получает текст «Действие выполнено»;
- cancel/pause/resume failure не получает success wording;
- task read malformed payloads fail closed;
- skip next-action error не маскируется как “нет шага”;
- malformed skip target блокируется до mutation;
- committed skip + later next-read failure reports partial state without fake rollback;
- continue validates next-action and pending-action persistence result;
- valid seller-facing shapes remain compatible.


---

# Top-Level Result Integrity v1

Services:

- AssistantOrchestratorBusinessService
- AssistantMainFlowService
- AssistantResponseBuilderService

Tests:

- tests/test_top_level_result_integrity_v591_v596.py
- tests/test_cancel_execution_block.py

Проверяет:

- malformed top-level Business Flow results fail closed instead of becoming success or raising KeyError;
- explicit execution error=True remains a top-level failure with a safe seller-facing message;
- malformed execution payloads cannot receive success wording;
- nested task-read error payloads cannot be repackaged as successful status/history/details/next results;
- business-plan actions/count consistency is validated at the upper orchestration boundary;
- malformed business-service and response-service payloads fail closed;
- explicit upstream errors are preserved by the response builder;
- cancelled-task execution remains error=True rather than a false successful state;
- no new business mutation, Product Decision execution, or Ozon mutation path is enabled.


---

# Entry/Core Result Integrity v1

Services:

- AssistantEntryService
- AssistantCoreService

Tests:

- tests/test_entry_core_result_integrity_v597_v603.py
- tests/test_assistant_entry_freshness_operational_route.py
- tests/test_assistant_entry_period_profit_route.py
- tests/test_task_persistence_operator_access_v368_v377.py
- tests/test_task_persistence_operator_readiness_v358_v367.py

Проверяет:

- direct runtime success/failure payloads require an explicit boolean error marker;
- malformed direct runtime payloads fail closed with deterministic non-secret codes;
- valid explicit runtime failures are preserved;
- malformed orchestrator results fail closed before context attachment;
- legacy fixtures match the actual explicit-success production contract;
- no new mutation or business execution path is enabled.


---

# Context Provider Result Integrity v1

Service:

- AssistantEntryService

Tests:

- tests/test_context_provider_result_integrity_v604_v611.py

Проверяет:

- malformed stock-provider results cannot reach report.update;
- unavailable stock evidence is explicit and does not prove a clean state;
- malformed sales reports cannot be converted/merged as success;
- unavailable sales evidence remains explicit;
- malformed or partial finance-provider output cannot reach report.update;
- unavailable finance evidence remains explicit;
- valid stock/sales/finance context shapes remain compatible;
- no business mutation or execution path is enabled.


---

# User Context Result Integrity v1

Services:

- AssistantUserContextService
- AssistantCoreService

Tests:

- tests/test_user_context_result_integrity_v612_v619.py

Проверяет:

- malformed profile get_user results fail closed before user/context access;
- malformed context and memory payloads are rejected;
- context/memory save result contracts are validated;
- malformed initial user context blocks orchestration before business execution;
- post-execution context persistence/refresh failures do not falsely imply rollback;
- already-produced business result semantics are preserved with a separate context persistence issue marker;
- data/users.json is not modified by the package.


---

# User Storage Load Integrity v1

Service:

- AssistantUserStorageService

Tests:

- tests/test_user_storage_load_integrity_v620_v628.py

Проверяет:

- malformed/unreadable JSON storage becomes explicit unavailable state;
- invalid top-level storage roots fail closed;
- load errors block create/memory/history mutation and preserve the original file;
- malformed existing user records are not replaced;
- save failures return explicit errors;
- uncommitted in-memory user/memory/history mutations roll back when save fails;
- absent-store creation and valid persistence remain compatible;
- regression tests use temporary paths and do not modify repository data/users.json.


---

# Memory Persistence Result Integrity v1

Services:

- AssistantMemoryService
- AssistantMemoryIntegrationService
- AssistantFeedbackService

Tests:

- tests/test_memory_persistence_result_integrity_v652_v659.py

Проверяет:

- storage save `False` no longer becomes memory success;
- explicit boolean rejection rolls back only the uncommitted in-memory mutation;
- storage exceptions and malformed results fail closed without fabricated rollback;
- ambiguous persistence state remains explicit;
- memory integration stops after the first failed save;
- a second-save failure reports partial memory state instead of full success;
- feedback already recorded before memory failure is reported as partial state;
- default in-memory production behavior remains compatible;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled.


---

# Telegram Memory Clear Integrity v1

Service:

- AssistantTelegramMemoryService

Production composition:

- telegram_assistant_factory.create_telegram_assistant
- AssistantUserStorageService

Tests:

- tests/test_telegram_memory_clear_integrity_v660_v667.py

Проверяет:

- clear mutates the canonical nested user record instead of the get_user result wrapper;
- explicit user-storage errors are preserved and block save;
- malformed user and memory payloads fail closed before mutation;
- explicit pre-commit save failures restore the previous in-memory memory object;
- malformed or exceptional save outcomes do not fabricate rollback and report unknown persistence state;
- post-commit durability warning keeps the clear committed;
- exception details are not leaked through stable error codes;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# History Clear Integrity v1

Service:

- AssistantHistoryService

Production composition:

- telegram_assistant_factory.create_telegram_assistant
- AssistantUserStorageService

Tests:

- tests/test_history_clear_integrity_v668_v676.py

Проверяет:

- clear mutates the canonical nested user history instead of the get_user result wrapper;
- canonical history remains a list and is cleared to an empty list;
- explicit user-storage errors are preserved and block save;
- malformed user and history payloads fail closed before mutation;
- explicit pre-commit save failures restore the previous in-memory history list;
- malformed or exceptional save outcomes do not fabricate rollback and report unknown persistence state;
- post-commit durability warning keeps the clear committed;
- exception details are not leaked through stable error codes;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram TypeError Retry Integrity v1

Runtime boundaries:

- TelegramRunner
- TelegramBotService
- AssistantTelegramAdapter
- telegram_call_compat.call_with_legacy_arity

Tests:

- tests/test_telegram_dispatch_typeerror_integrity_v677_v686.py

Проверяет:

- legacy one-argument Telegram callables remain supported;
- callable arity is selected before invocation;
- internal handler TypeError is never treated as an arity mismatch after the handler has started;
- Runner message/callback dispatch does not retry a failing bot handler;
- BotService message/callback dispatch does not retry a failing adapter;
- AssistantTelegramAdapter does not retry a failing button handler;
- a partially started handler cannot be invoked a second time by the compatibility fallback;
- no business rule, persistence owner, Product Decision execution, Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram User Admission Integrity v1

Runtime boundary:

- AssistantTelegramAdapter

Production persistence:

- AssistantUserStorageService via telegram_assistant_factory.create_telegram_assistant

Tests:

- tests/test_telegram_user_admission_integrity_v687_v695.py

Проверяет:

- explicit create_user error blocks successful /start UI;
- explicit profile errors stop text before memory-command and assistant dispatch;
- explicit profile errors stop button callbacks before button-handler dispatch;
- malformed profile results fail closed;
- profile exceptions become stable non-secret errors;
- successful canonical user admission preserves start/text/button behavior;
- no-user-id legacy flows remain compatible;
- no persistence owner/layer, Product Decision execution, Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram Command Result Integrity v1

Services / boundaries:

- AssistantMemoryCommandService
- AssistantTelegramAdapter
- TelegramBotService

Tests:

- tests/test_telegram_command_result_integrity_v696_v705.py
- tests/test_telegram_user_admission_integrity_v687_v695.py

Проверяет:

- unrecognized memory text is explicit handled=False, not an operational failure;
- recognized memory commands remain handled=True;
- storage failures from recognized memory commands stop before assistant fallback;
- malformed/exceptional memory-command results fail closed;
- TelegramBotService rejects malformed non-None command results;
- explicit command failures are preserved;
- successful /start now has explicit error=False;
- failed intermediate SHA acc3eb4023aa046544056eea2c634e0906bc00b3 remains failed evidence;
- no business execution authorization, Product Decision/Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram Adapter Downstream Result Integrity v1

Boundary:

- AssistantTelegramAdapter

Tests:

- tests/test_telegram_adapter_downstream_result_integrity_v706_v713.py

Проверяет:

- assistant.ask result must be dict with explicit boolean error;
- malformed assistant results fail closed;
- explicit assistant failures are preserved;
- button_handler.handle result must be dict with explicit boolean error;
- malformed button results fail closed;
- explicit button failures are returned without freshness enrichment;
- valid draft-button successes keep existing freshness enrichment;
- internal exceptions are not caught or retried, preserving the no-duplicate-dispatch contract;
- failed intermediate SHA f990a7cc9abf8b2fd587e8339329d7d3a29e497a remains failed evidence;
- no business execution authorization, Product Decision/Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Decision overview/detail Telegram paths

Tests:

- tests/test_product_decision_telegram_result_integrity_v714_v721.py

Проверяет:

- explicit query_all error=True is not rewritten as empty assortment success;
- malformed overview results fail closed;
- overview success requires explicit decisions/counts/total/actionable_proposals_count;
- overview total must match decisions length;
- malformed decision items fail closed before keyboard construction;
- valid empty overview remains a legitimate empty success;
- malformed detail results fail closed instead of using optimistic error=False;
- explicit detail failures remain failures without feedback navigation;
- valid read-only Product Decision cards/navigation remain compatible;
- failed intermediate SHA d804b6d89fdee8457dd8473ce6923b9c426d29d4 remains failed evidence;
- no Product Decision rules, thresholds, persistence, Product Task Draft execution, business execution authorization, or Ozon mutation changed;
- repository data/users.json remains untouched.


---

# Financial Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Unit Economics / Returns Finance Impact detail paths

Tests:

- tests/test_financial_telegram_result_integrity_v722_v730.py
- tests/test_product_unit_economics_telegram_ui.py
- tests/test_observed_returns_impact_production_wiring.py

Проверяет:

- Unit Economics query result requires dict + explicit boolean error;
- successful Unit Economics result requires availability/source/SKU/missing-fields evidence;
- legitimate available=False remains evidence-limited success;
- malformed Unit Economics result fails closed before formatter access;
- Returns Finance Impact result requires explicit boolean error and safe period/category/missing-data shape;
- malformed returns categories fail closed before formatter access;
- explicit financial downstream errors remain errors;
- valid incomplete observed-return evidence remains seller-visible without false adjusted-profit claims;
- failed intermediate SHA 64d34b244f790065acb0a636542a5684bd598dec remains failed evidence;
- cancelled intermediate SHA fdd90ff6368178bf14896cc2d02f3aa57af90291 remains unknown/cancelled evidence and is not reused;
- no financial formula, tax/fee arithmetic, Product Decision rule, persistence, Product Task Draft execution, business execution authorization, or Ozon mutation changed;
- repository data/users.json remains untouched.


---

# Product Task Draft Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Task Draft summary/detail/archive Telegram paths

Tests:

- tests/test_product_task_draft_telegram_result_integrity_v731_v742.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- summary result requires explicit boolean error and exact DRAFT/STALE/DISMISSED/ARCHIVED counts;
- missing lifecycle counts cannot become seller-facing zero evidence;
- raw task-draft list is validated before review-queue prioritization;
- review queue requires exact priority counts, valid reviewable items and executed_count=0;
- readiness summary and per-draft readiness require explicit non-executable contracts;
- malformed detail result fails closed before rendering task-draft/audit data;
- malformed detail readiness fails closed;
- archive cannot claim success without matching ARCHIVED draft, explicit saved bool, executed=False and execution_allowed=False;
- idempotent saved=False archive remains a legitimate non-executable success;
- failed intermediate SHA fb64d3deeb5d7bd9a6e42772fe7614630ad6ed03 remains failed evidence;
- cancelled intermediate SHA 61db8a964cfeed77e0b5caf451c705c6a77e3b51 remains cancelled/unknown evidence;
- no Product Task Draft execution, Action Executor connection, business execution authorization or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Interaction Persistence Integrity v1

Services / boundaries:

- ProductDecisionHistoryService
- ProductActionProposalConfirmationService
- AssistantButtonHandlerService Product Decision feedback / proposal confirmation Telegram paths

Tests:

- tests/test_product_decision_interaction_persistence_result_integrity_v743_v754.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- explicit storage save=False for feedback/proposal status is treated as a proven non-commit and only that local interaction mutation is rolled back;
- storage exceptions and malformed save results remain ambiguous persistence state with saved=None and no fabricated rollback;
- exception text is not leaked through interaction persistence errors;
- Product Action Proposal Confirmation validates history-write results before any Task Draft create/dismiss side effect;
- rejected, ambiguous or malformed history-write results cannot create or dismiss Product Task Drafts;
- seller-facing Telegram feedback and proposal confirmation require dict + explicit boolean error contracts;
- successful Telegram interaction results require matching SKU/status/type plus real boolean saved;
- proposal confirmation success requires explicit executed=False and execution_allowed=False;
- malformed Task Draft result payloads are not promoted into successful created-draft presentation;
- valid idempotent saved=False feedback/proposal semantics remain supported;
- Product Decision rules, thresholds, feedback meaning, proposal meaning and Product Task Draft execution policy are unchanged;
- no Action Executor connection, business execution authorization, quantity/price inference or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Learning Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Decision learning summary/history Telegram paths

Tests:

- tests/test_product_decision_learning_telegram_result_integrity_v755_v765.py

Проверяет:

- learning summary result must be a dict with explicit real boolean `error`;
- successful summary counts must be non-negative non-booleans;
- feedback and outcome subtotal counts must be internally consistent;
- missing summary evidence cannot become seller-facing zero through optimistic defaults;
- a structurally valid all-zero summary remains legitimate read-only success;
- decision history must be a real list; `None` or malformed payload cannot become empty success;
- history records must match the requested SKU and use known decision/priority values plus a non-empty recorded timestamp;
- optional feedback/outcome values are validated before label formatting;
- unknown feedback is not mislabeled as `NOT_RELEVANT`;
- a structurally valid empty history remains legitimate read-only success;
- stable failures do not expose internal exception text;
- production evidence is exact-SHA bound: entering main #440, feature #442, PR merge-ref #443, squash-main #444;
- no Product Decision rule/threshold, persistence behavior, Product Task Draft execution, Action Executor connection, business mutation authorization, quantity/price inference, or Ozon mutation changed;
- repository data/users.json remains untouched;
- `externally_verified=False`.


---

# Telegram Analyze / Plan History Integrity v1

Boundary:

- `AssistantButtonHandlerService` Telegram `analyze` / `plan` buttons
- canonical history persistence result boundary

Tests:

- `tests/test_telegram_analyze_plan_history_integrity_v766_v773.py`

Проверяет:

- explicit assistant `error=True` is preserved and does not write success history;
- malformed assistant result fails closed before history persistence;
- valid assistant success records the exact event once;
- explicit history failure is surfaced after assistant completion;
- malformed history result preserves unknown persistence state;
- history exceptions are sanitized and do not fabricate rollback;
- no-user / absent-history-service compatibility is preserved;
- exact-SHA evidence: main #449, feature #451, PR merge-ref #452, squash-main #453;
- no execution authorization, Ozon mutation, quantity/price inference, or new persistence layer;
- `data/users.json` untouched; `externally_verified=False`.


---

# Telegram History / Memory Read Integrity v1

Boundary:

- `AssistantButtonHandlerService` History / Memory Telegram reads

Tests:

- `tests/test_telegram_history_memory_read_integrity_v774_v783.py`

Проверяет:

- unavailable service cannot become clean empty data;
- missing user context cannot become zero/clean evidence;
- read exceptions return stable non-secret failures;
- result must be dict with exact boolean `error`;
- History success requires list `history`;
- Memory success requires dict `memory`;
- explicit downstream failures are preserved;
- legitimate empty and non-empty read-only data remain success;
- exact-SHA evidence: main #457, feature #459, PR merge-ref #460, squash-main #461;
- no execution authorization, Ozon mutation, quantity/price inference, or persistence-layer change;
- `data/users.json` untouched; `externally_verified=False`.


---

# Telegram Context Preparation Integrity v1

Boundary:

- `AssistantButtonHandlerService.prepare_context`
- Telegram analyze / plan orchestration before assistant execution
- existing `AssistantUserContextService.update` / `AssistantTaskContextService.update_task` result contracts

Tests:

- `tests/test_telegram_context_preparation_integrity_v784_v792.py`

Проверяет:

- first context update failure/malformed result stops downstream task update and assistant/history side effects;
- context exceptions return stable non-secret failures and are not retried;
- second update failure after proven first success reports partial context state instead of fabricated rollback;
- malformed/exceptional second update preserves unknown current-task state;
- valid context preparation invokes assistant once and records history once;
- absent context service and absent user ID preserve optional-context behavior;
- exact-SHA evidence: entering main #465, cancelled #466, final feature #468, PR merge-ref #469, squash-main #470;
- cancelled #466 is not green evidence even though its test/artifact steps completed;
- no Product Decision/Product Task Draft execution, Action Executor connection, business mutation authorization, quantity/price inference, Ozon mutation, or persistence-layer addition;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Task Draft Freshness Telegram Presentation Integrity v1

Boundary:

- `AssistantTelegramAdapter` Product Task Draft list/detail freshness enrichment
- read-only presentation only; Product Task Draft execution remains disabled

Tests:

- `tests/test_product_task_draft_freshness_telegram_presentation_integrity_v793_v802.py`

Проверяет:

- malformed readiness summary containers fail closed;
- partial/negative/boolean freshness count maps cannot invent zero categories;
- valid all-zero freshness counts remain legitimate success;
- malformed optional coverage/source-timestamp/refresh maps fail closed when present;
- absent optional presentation evidence is omitted rather than synthesized;
- malformed detail readiness/freshness/status/age/reason fails closed before formatter use;
- malformed coverage components and refresh guidance targets fail closed;
- legitimate UNKNOWN freshness, observed-only evidence and refresh guidance remain read-only success;
- exact-SHA evidence: entering main #474, feature #476, PR merge-ref #477, squash-main #478;
- no Product Decision rule/threshold, Task Draft readiness rule, persistence behavior, Action Executor connection, execution authorization, quantity/price inference, or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Telegram Adapter Runtime Exception Containment v1

Boundary:

- `AssistantTelegramAdapter` assistant/button/keyboard runtime exception boundary

Tests:

- `tests/test_telegram_adapter_runtime_exception_containment_v803_v810.py`

Проверяет:

- internal assistant/button/keyboard exceptions are contained;
- TypeError is not retried after invocation;
- legacy handler arity remains pre-call selection only;
- exception text is sanitized;
- one invocation remains one invocation;
- exact-SHA evidence: entering main #482, cancelled #483, failed #484, final feature #485, PR merge-ref #486, squash-main #487;
- no Product Decision/Product Task Draft execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Post-Decision Observation Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_observation`
- user-reported completion evidence to later Product Decision observation

Tests:

- `tests/test_product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v811_v820.py`

Проверяет:

- malformed containers fail closed;
- explicit checklist error=False and USER_REPORT semantics are required;
- numeric identity coercion is rejected;
- explicit later-decision failure is preserved;
- canonical decision/priority/confidence values are required;
- reasons cannot be synthesized from malformed strings;
- valid observations remain non-causal, non-executable and not externally verified;
- exact-SHA evidence: entering main #492, feature #494, PR merge-ref #495, squash-main #496;
- no Product Decision recomputation, Product Task Draft execution, Action Executor connection or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Task Persistence Operator Presentation Integrity v1

Boundary:

- `TaskPersistenceOperatorPresentationService`
- operator-only operational / release / provenance presentation

Tests:

- `tests/test_task_persistence_operator_presentation_integrity_v821_v830.py`
- existing task-persistence operator readiness/access/release/provenance regression suites

Проверяет:

- explicit error=False before presenting trusted operator state;
- blockers/warnings/categories must be real unique string lists;
- operational state/count/attention consistency;
- release-ready/incident/human-review consistency;
- provenance revision and CI binding shape;
- external-verification, mutation and execution overclaims fail closed;
- valid messages never expose paths, user IDs, inferred lock owner or inferred lock age;
- failed SHA `41c289221c100ce4dc1462603b42349434f2f406` / Verify #498 remains failed evidence;
- final exact-SHA evidence: feature #499, PR merge-ref #500, squash-main #501;
- no persistence owner change, automatic retry, lock removal, business execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Persistence Verification Integrity v1

Boundary:

- `ProductDecisionPersistenceVerificationService`
- durable Product Decision read-back trust boundary before downstream user-action guidance

Tests:

- `tests/test_product_decision_persistence_verification_service.py`
- `tests/test_product_decision_persistence_verification_integrity_v831_v840.py`

Проверяет:

- non-mapping application input fails closed;
- lineage IDs, draft ID and SKU require real non-empty strings;
- numeric identity coercion cannot create verified lineage;
- explicit persisted-preview error markers, when present, must be boolean;
- decision type, priority and confidence are canonical;
- reasons are a real non-empty list of non-empty strings;
- malformed durable history snapshots cannot be promoted to verification success;
- recorded-at binding requires a real string;
- matching malformed expected/history values do not become valid through coercive normalization;
- valid output remains read-only, non-executable and `externally_verified=False`;
- exact-SHA evidence: entering main #509, feature #516, PR merge-ref #517, squash-main #518;
- cancelled duplicate branch-creation Verify #514 remains cancelled evidence and is not used as green evidence;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched.


---

# Product Decision User Action Guidance Integrity v1

Boundary:

- `build_product_decision_user_action_guidance`
- verified Product Decision persistence lineage to seller manual-action guidance

Tests:

- `tests/test_product_decision_user_action_guidance.py`
- `tests/test_product_decision_user_action_guidance_integrity_v841_v850.py`

Проверяет:

- non-mapping verification input fails closed;
- verification/application IDs and SKU require real non-empty strings;
- explicit verifier `error=False`, verified status and decision-persistence verification are required;
- non-empty mismatch evidence cannot be presented as trusted guidance;
- external-verification and execution/persistence overclaims fail closed;
- verified recorded-at must match the durable snapshot timestamp;
- priority and confidence require canonical values;
- reasons cannot be synthesized from malformed strings;
- valid guidance carries read-only verified lineage and remains user-executed/non-automatic;
- exact-SHA evidence: entering main #528, feature #532, PR merge-ref #533, squash-main #534;
- no failed intermediate production SHA occurred in v841-v850;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Integrity v1

Boundary:

- `build_product_decision_user_action_checklist`
- verified Product Decision seller guidance to manual user checklist

Tests:

- `tests/test_product_decision_user_action_checklist.py`
- `tests/test_product_decision_user_action_checklist_integrity_v851_v860.py`

Проверяет:

- non-mapping guidance input fails closed;
- guidance / verification / application IDs, SKU and verified-recorded-at require real non-empty strings;
- explicit guidance `error=False`, ready status and decision-persistence verification are required;
- verification ID remains bound to the persistence application ID;
- external-verification and persistence/execution overclaims fail closed;
- decision/action pairing, priority, confidence, title and reasons are canonical;
- manual checklist steps cannot be synthesized through `str(...)` coercion;
- valid checklist carries the verified persistence lineage forward and remains user-owned/non-executable;
- exact-SHA evidence: entering main #544, feature #548, PR merge-ref #549, squash-main #550;
- no failed intermediate production SHA occurred in v851-v860;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Evidence Integrity v1

Boundary:

- `build_product_decision_user_action_completion_evidence`
- verified Product Decision user checklist to explicit USER_REPORT completion evidence

Tests:

- `tests/test_product_decision_user_action_completion_evidence.py`
- `tests/test_product_decision_user_action_completion_evidence_integrity_v861_v870.py`

Проверяет:

- non-mapping checklist input fails closed;
- checklist / guidance / verification / application IDs, SKU, item ID and verified-recorded-at require real non-empty strings;
- exact guidance → verification → application lineage is retained;
- explicit checklist `error=False`, ready status and decision-persistence verification are required;
- non-string completion decisions are not coercively normalized;
- external-verification and persistence/execution overclaims fail closed;
- item count, completed count, positions, user ownership and instructions are structurally validated;
- valid completion evidence remains USER_REPORT, non-persistent before its dedicated persistence step and non-executable;
- exact-SHA evidence: entering main #560, feature #565, PR merge-ref #566, squash-main #567;
- no failed intermediate production SHA occurred in v861-v870;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Persistence Integrity v1

Boundary:

- `ProductDecisionUserActionCompletionPersistenceService`
- explicit USER_REPORT completion evidence to durable completion storage
- revision producer lineage propagation compatibility

Tests:

- `tests/test_product_decision_user_action_completion_persistence_service.py`
- `tests/test_product_decision_user_action_completion_persistence_integrity_v871_v880.py`
- `tests/test_product_decision_user_action_completion_revision.py`

Проверяет:

- non-mapping evidence fails closed;
- completion / checklist / guidance / verification / application lineage remains exact;
- source `error=False`, decision-persistence verification and USER_REPORT source are required;
- completion status/decision/user boolean consistency;
- canonical root and revision evidence ID lineage;
- malformed load result and malformed existing records fail closed;
- explicit `save(False)` cannot become durable success;
- root→revision persistence keeps verified lineage, item/instruction and revision metadata;
- exact-SHA evidence: entering main #577, feature #582, PR merge-ref #583, squash-main #584;
- no failed intermediate production SHA occurred in v871-v880;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Revision Predecessor Integrity v1

Boundary:

- `ProductDecisionUserActionCompletionPersistenceService`
- durable completion revision chain predecessor existence and lineage

Tests:

- `tests/test_product_decision_user_action_completion_predecessor_integrity_v881_v890.py`

Проверяет:

- revision 2+ cannot persist without an actually stored predecessor;
- duplicate predecessor IDs are ambiguous and fail closed;
- predecessor exact checklist/guidance/verification/application/SKU/item/instruction lineage;
- predecessor verified Product Decision and USER_REPORT safety semantics;
- predecessor status/decision/report consistency;
- canonical predecessor revision/root/previous-ID lineage for revision 3+;
- duplicate current revision IDs fail closed;
- valid root → revision 2 → revision 3 durable chain;
- exact-SHA evidence: entering main #594, feature #597, PR merge-ref #598, squash-main #599;
- no failed intermediate production SHA occurred in v881-v890;
- no runtime execution or Ozon mutation wiring changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Status Persistence Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_checklist_status`
- verified Product Decision checklist + persisted USER_REPORT completion receipts → aggregate seller checklist status

Tests:

- `tests/test_product_decision_user_action_checklist_status.py`
- `tests/test_product_decision_user_action_checklist_status_integrity_v891_v900.py`

Проверяет:

- non-mapping checklist and non-list report collection fail closed;
- exact checklist/guidance/verification/application/SKU/timestamp lineage;
- checklist success, verification, item shape and safety contract;
- matching persisted receipt success/source/persistence/safety contract;
- matching receipt item/instruction and verified lineage binding;
- exact integer completion revision without coercion;
- canonical root/evidence/previous revision IDs;
- duplicate item+revision ambiguity;
- contiguous revision chain from 1 through latest;
- malformed matching report cannot become no-report success;
- valid aggregate carries persisted-decision verification lineage and remains externally unverified/non-executable;
- exact-SHA evidence: entering main #610, feature #614, PR merge-ref #615, squash-main #616;
- no failed intermediate production SHA occurred in v891-v900;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Observation Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_observation`
- verified checklist-status → read-only later Product Decision observation

Tests:

- `tests/test_product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v811_v820.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v901_v910.py`

Проверяет:

- non-mapping checklist status and later-decision payloads fail closed;
- canonical checklist-status/checklist/guidance/verification/application/SKU/timestamp lineage;
- explicit persisted Product Decision verification;
- exact complete-report count and item-ID consistency;
- no numeric/coercive item identity;
- explicit later-decision success marker and canonical fields;
- matching SKU;
- safe read-only/non-causal/non-executable observation output;
- exact-SHA evidence: entering main #620, failed intermediate #623, final feature #624, PR merge-ref #625, squash-main #626;
- failed intermediate `0896d8112971966aec9fb61c7a2250436f19d76a` remains failed evidence at 1804 passed / 7 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Outcome Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_outcome`
- verified post-decision observation + prior Product Decision → non-causal outcome classification

Tests:

- `tests/test_product_decision_user_action_post_decision_outcome.py`
- `tests/test_product_decision_user_action_post_decision_outcome_integrity_v911_v920.py`

Проверяет:

- non-mapping observation/prior inputs fail closed;
- exact observation/checklist-status/checklist/guidance/verification/application/SKU/timestamp lineage;
- explicit observation success and persisted Product Decision verification;
- complete USER_REPORT count/item evidence;
- no identity/priority coercion;
- canonical prior/later Product Decision type, priority, confidence and reasons;
- exact prior SKU binding;
- rejection of noncanonical MEDIUM priority;
- support for canonical NONE priority;
- safe non-causal/non-executable outcome;
- exact-SHA evidence: entering main #630, feature #632, PR merge-ref #633, squash-main #634;
- no failed intermediate production SHA occurred in v911-v920;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Learning Summary Outcome Integrity v1

Boundary:

- `build_product_decision_user_action_learning_summary`
- verified post-decision outcome list → descriptive learning summary

Tests:

- `tests/test_product_decision_user_action_learning_summary.py`
- `tests/test_product_decision_user_action_learning_summary_integrity_v921_v930.py`

Проверяет:

- non-list input cannot become a clean empty summary;
- every row must be a mapping;
- exact v911-v920 outcome lineage and explicit success;
- persisted Product Decision verification and complete USER_REPORT evidence;
- unsafe outcomes fail closed instead of disappearing;
- canonical prior/later Product Decision classification;
- contradictory outcome classification;
- duplicate outcome-ID inflation protection;
- canonical NONE priority support and MEDIUM rejection;
- deterministic safe empty/non-empty summary semantics;
- exact-SHA evidence: entering main #638, failed intermediate #640, final feature #641, PR merge-ref #642, squash-main #643;
- failed intermediate `21051b20acdfc0036a15d875d01b488283791ff3` remains failed evidence at 1830 passed / 1 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Learning Evidence Quality Summary Integrity v1

Boundary:

- `build_product_decision_user_action_learning_evidence_quality`
- canonical learning summary → descriptive evidence-quality classification

Tests:

- `tests/test_product_decision_user_action_learning_evidence_quality.py`
- `tests/test_product_decision_user_action_learning_evidence_quality_integrity_v931_v940.py`

Проверяет:

- non-mapping/missing-success summary fails closed;
- exact integer observation/SKU counts without coercion;
- canonical outcome/priority/SKU aggregate maps;
- aggregate sum and SKU-count consistency;
- exact unique outcome-ID count;
- strict zero-evidence semantics;
- unchanged quality thresholds;
- safe externally-unverified/non-executable output;
- exact-SHA evidence: entering main #647, failed intermediate #649, final feature #650, PR merge-ref #651, squash-main #652;
- failed `849b0d0e78e441f3080631419ecbc0ea192890ec` remains failed evidence;
- `data/users.json` untouched.

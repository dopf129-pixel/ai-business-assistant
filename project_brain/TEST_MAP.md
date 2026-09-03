# Test Map


## Current Status


Verification model:

SHA-bound.

Latest confirmed full-suite baseline:

2195 passed on `9ca4497dda61615076b8203d0404502630ab7e81`.

GitHub Actions push Verify #1105 completed successfully for this exact main SHA.

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


---

# Product Decision User Action Learning Confidence Evidence Integrity v1

Boundary:

- `build_product_decision_user_action_learning_confidence`
- canonical evidence-quality result → descriptive confidence classification

Tests:

- `tests/test_product_decision_user_action_learning_confidence.py`
- `tests/test_product_decision_user_action_learning_confidence_integrity_v941_v950.py`

Проверяет:

- non-mapping/missing-success quality fails closed;
- exact integer observation/SKU counts without coercion;
- canonical quality name/score;
- quality/score/sample consistency;
- canonical outcome/priority/SKU aggregate maps;
- aggregate sum and SKU-count consistency;
- exact unique outcome-ID count;
- unchanged confidence thresholds;
- safe externally-unverified/non-executable output;
- exact-SHA evidence: entering main #656, feature #658, PR merge-ref #659, squash-main #660;
- no failed intermediate production SHA occurred in v941-v950;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Action Proposal Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_action_proposal`
- seller-facing Product Decision → action proposal → task-draft lifecycle / Telegram presentation

Tests:

- `tests/test_product_decision_action_proposal_result_integrity_v951_v960.py`

Проверяет:

- non-mapping proposal fails closed;
- proposal exceptions fail closed without exception detail leakage;
- missing boolean markers cannot become success;
- execution overclaim is blocked;
- exact SKU identity;
- exact proposal type ↔ Product Decision semantics;
- exact canonical reasons;
- confirmation/action-required consistency;
- assortment query fails closed on invalid nested proposal;
- valid proposal remains non-executable and Telegram-safe;
- exact-SHA evidence: entering main #664, feature #666, PR merge-ref #667, squash-main #668;
- no failed intermediate production SHA occurred in v951-v960;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision History Context Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_decision_history`
- `AssistantButtonHandlerService._with_latest_proposal_status`
- Product Decision → history interaction context → cache / draft lifecycle / Telegram

Tests:

- `tests/test_product_decision_history_context_integrity_v961_v970.py`

Проверяет:

- history record context cannot overwrite Product Decision identity;
- non-mapping history context is unknown, not clean success;
- required history booleans are exact;
- history count is exact integer or unknown, never coerced;
- history exceptions are sanitized;
- valid history context remains cacheable;
- invalid history context blocks task-draft lifecycle;
- Telegram skips latest reads for invalid history context;
- malformed/cross-SKU/unknown-status latest history cannot enter card;
- valid safe latest proposal status and task draft remain available;
- failed intermediate `bfcc3551166431288f38ba0c06912133bed56818`: Verify #674, 1870 passed / 1 failed;
- final feature `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`: Verify #675, 1871 passed / 0 failed;
- PR #328 synthetic `85e808a3dcc04ef9197bc673950546445ee15749`: Verify #676, 1871 passed / 0 failed;
- squash main `10977368ac4179f1f7168943a38fcdbc01ecfd78`: Verify #677, 1871 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Unit Economics Returns Finance Impact Integrity v1

Boundary:

- `ProductUnitEconomicsQueryService._attach_returns_impact`
- `ProductUnitEconomicsQueryService._estimate_returns_impact`
- returns-finance evidence → unit economics confirmed/estimated returns adjustment

Tests:

- `tests/test_unit_economics_returns_impact_integrity_v971_v980.py`
- updated canonical cache fixture in `tests/test_product_unit_economics_query_cache.py`

Проверяет:

- non-mapping returns impact remains unknown;
- returns impact exceptions are sanitized;
- missing explicit error marker is invalid;
- string `complete="false"` cannot become truthy confirmed completeness;
- categories and required category records must be mappings;
- counts are exact integers and never string/missing coercions;
- observed count cannot exceed matched/event counts;
- complete finance requires complete finance/category state;
- invalid evidence does not create zero observed cost or confirmed profit;
- valid estimated and confirmed calculations remain unchanged;
- failed intermediate `b4f0d33d163ee0a81d0252e466519169c55fd1f2`: Verify #683, 1880 passed / 1 failed;
- final feature `0a2ece03b60e019b264b5ecda8a010bca873e7bb`: Verify #684, 1881 passed / 0 failed;
- PR #330 synthetic `d8e9c3f5fb978cb4ae2d3675d229ad6bbc48b358`: Verify #685, 1881 passed / 0 failed;
- squash main `db5ab92503f499dfe470402ffefc00b15b9c6e59`: Verify #686, 1881 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_product`
- Product Decision service output → history / proposal / cache / task-draft lifecycle / Telegram

Tests:

- `tests/test_product_decision_result_integrity_v981_v990.py`
- canonicalized legacy fixture in `tests/test_product_decision_freshness_evidence_propagation.py`

Проверяет:

- non-mapping decision result fails closed;
- decision exceptions are sanitized;
- injected error/code fields are rejected;
- exact SKU/product identity;
- exact decision type → priority contract;
- canonical unique reason list;
- canonical unique missing-data list;
- invalid decision has no history/proposal/cache side effects;
- valid decision remains seller-safe and non-executable;
- Telegram invalid-decision response has no keyboard;
- cancelled intermediate #693/#694 have no transferable verification claim;
- failed intermediate `8a286947bdc5862834a05794e330d87ef370ffe7`: Verify #695, 1889 passed / 2 failed;
- final feature `8b90c11763622cc413802a488171738cf2332a1a`: Verify #696, 1891 passed / 0 failed;
- PR #332 synthetic `da5e7689cc87a0597944f371dfe4246082d92806`: Verify #697, 1891 passed / 0 failed;
- squash main `5f0534bb72dba2471c3c339a69cd7041552dfb4a`: Verify #698, 1891 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Assortment Overview Integrity v1

Boundary:

- `AssistantButtonHandlerService._validate_product_decisions_overview`
- Product Decision assortment overview → counts / proposal statistics / pagination / Telegram keyboard

Tests:

- `tests/test_product_decision_assortment_overview_integrity_v991_v1000.py`
- canonicalized legacy overview fakes in Product Decision Telegram/learning tests

Проверяет:

- exact decision-count recomputation;
- exact positive integer count semantics;
- unknown count-key rejection;
- duplicate SKU rejection;
- canonical decision type → priority pairing;
- exact proposal-count recomputation;
- exact actionable proposal count;
- nested proposal safety and known proposal types;
- valid mixed overview preserves seller statistics;
- validator is deterministic and non-mutating;
- failed intermediates #704/#705/#706 remain failed evidence;
- final feature `63870a305972f7b7e8f33cad251fc6f13235d1fc`: Verify #707, 1901 passed / 0 failed;
- PR #334 synthetic `1bbee7e03477b197a474a6807093d6ee344b7505`: Verify #708, 1901 passed / 0 failed;
- squash main `84d714909d5082958bf2bb21a30b7b097eb17955`: Verify #709, 1901 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Task Draft Lifecycle Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_task_draft_lifecycle`
- Product Task Draft reconcile result → cached/seller-facing Product Decision / assortment result

Tests:

- `tests/test_product_decision_task_draft_lifecycle_result_integrity_v1001_v1010.py`
- canonicalized lifecycle fake in `tests/test_product_business_decision_query_service.py`

Проверяет:

- non-mapping lifecycle result fails closed;
- missing or true error marker is not success;
- execution overclaim is rejected;
- stale count/list shape and cardinality are exact;
- cross-SKU stale drafts are rejected;
- current revision cannot be classified as stale;
- stale status/proposal type are canonical;
- stale drafts remain non-executable;
- reconcile exceptions are sanitized;
- invalid lifecycle state is not cached;
- assortment query propagates lifecycle integrity failure;
- valid lifecycle is copied defensively;
- final feature `12e4f1d4f38296b8f46680302478f377121644a8`: Verify #715, 1911 passed / 0 failed;
- PR #336 synthetic `005ac13b1fbb01bb6e95314d1f8c89b994ba85c6`: Verify #716, 1911 passed / 0 failed;
- squash main `288c6452703eee4082414d1ad36680b4ddf02caa`: Verify #717, 1911 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Unit Economics Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_product`
- `ProductBusinessDecisionQueryService._valid_unit_economics_result`
- Product Unit Economics result → Product Decision finance facts

Tests:

- `tests/test_product_decision_unit_economics_result_integrity_v1011_v1020.py`
- aligned canonical fixtures in Product Decision and freshness propagation tests

Проверяет:

- non-mapping/missing/non-boolean result markers fail closed;
- downstream exceptions are sanitized;
- explicit downstream errors remain unknown, not zero;
- unavailable economics cannot claim profit/margin;
- missing-field shape and uniqueness are enforced;
- NaN/infinity/bool finance values are rejected;
- confirmed returns-adjusted profit requires complete evidence;
- estimated returns profit requires exact readiness and evidence;
- invalid results are not cached;
- valid producer result still drives decisions;
- failed `c27b1fbfba804d36167855228f1881c08c4ef506`: Verify #723, 1917 passed / 4 failed;
- failed `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`: Verify #724, 1918 passed / 3 failed;
- final feature `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`: Verify #725, 1921 passed / 0 failed;
- PR #338 synthetic `8014a74ae903863da672ee4b82f9fb565ad3d6cc`: Verify #726, 1921 passed / 0 failed;
- squash main `982dc4f58fec6172a4fa99475ae72800c107981f`: Verify #727, 1921 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Operational Metrics Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_operational_metrics_source`
- `ProductBusinessDecisionQueryService._valid_operational_metrics_result`
- Sales/Stock operational metrics → Product Decision business facts

Tests:

- `tests/test_product_decision_operational_metrics_result_integrity_v1021_v1030.py`
- existing freshness propagation tests validate the supported `stock_priority` alias contract

Проверяет:

- sales/stock source exceptions are sanitized;
- non-mapping source results fail closed;
- non-boolean explicit error marker is rejected;
- explicit error=True remains unknown rather than zero;
- unsafe sales velocity is rejected;
- noncanonical sales trend is rejected;
- unsafe stock quantity/days values are rejected;
- stock priority/day relationship is canonical;
- `priority` and `stock_priority` aliases cannot contradict;
- malformed missing-data/evidence fields are rejected;
- invalid metrics are not cached;
- valid path still produces a Product Decision;
- failed `678739dea2fa85af3f71933f048f9bfb193fdc62`: Verify #733, 1929 passed / 2 failed;
- final feature `6af041c39b86791821249058d0632070f2f68685`: Verify #734, 1931 passed / 0 failed;
- PR #340 synthetic `7e64fcd23df9fb405c8c422359e3703b6a720f56`: Verify #735, 1931 passed / 0 failed;
- squash main `70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`: Verify #736, 1931 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Persistence Commit Receipt Integrity v1

Boundaries:

- `ProductDecisionHistoryService.record`
- `ProductDecisionHistoryService.record_persistent`
- `ProductDecisionPersistenceApplicationService.apply`
- `ProductDecisionPersistenceVerificationService.verify`

Tests:

- `tests/test_product_decision_persistence_commit_receipt_v1031_v1040.py`
- canonicalized persistence application/verification fixtures

Проверяет:

- storage save=False cannot become successful history;
- storage save state UNKNOWN cannot become successful history;
- failed history writes do not remain in in-memory state;
- durable persistence requires storage, not in-memory history;
- COMMITTED receipt carries exact SKU/recorded_at/count/context;
- application refuses missing receipt capability;
- rejected/unknown durable writes never claim product_decision_persisted;
- application carries defensive committed receipt;
- verification requires committed receipt before readback;
- valid receipt + readback verifies without execution;
- failed `14a0709209228310625dd91871e963a866ab6cc9`: Verify #742, 1940 passed / 1 failed;
- final feature `88372919c9275a51482703e59fe21d8c4d9c5682`: Verify #743, 1941 passed / 0 failed;
- PR #342 synthetic `7e54ca702706ad192eb70da63e351e96efdb31b5`: Verify #744, 1941 passed / 0 failed;
- squash main `7d53fecac126973122270eacfdfc122e50ae3de3`: Verify #745, 1941 passed / 0 failed;
- Telegram persistence wiring remains disabled;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Durable Application Lineage v1

Boundaries:

- `ProductDecisionPersistenceApplicationService.apply`
- `ProductDecisionHistoryService.record_persistent`
- `ProductDecisionHistoryService._snapshot`
- `ProductDecisionPersistenceVerificationService.verify`
- existing `ProductDecisionHistoryStorageService`

Tests:

- `tests/test_product_decision_durable_application_lineage_v1041_v1050.py`
- canonicalized persistence application/verification fixtures

Проверяет:

- exact application lineage is constructed before durable write;
- lineage binds application/readiness/authorization/eligibility/review/delta/preview IDs, draft_id and SKU;
- malformed lineage is rejected before save;
- cross-SKU lineage is rejected before save;
- durable snapshot and COMMITTED receipt carry the same lineage;
- forged receipt lineage blocks persistence application;
- forged receipt lineage blocks verification before readback;
- forged durable snapshot lineage blocks verification;
- JSON storage restart preserves lineage;
- feedback mutation preserves lineage;
- restart readback verifies without execution;
- failed `cfeb3528d5f902625819b6897db192bf794fddda`: Verify #751, 1915 passed / 36 failed;
- final feature `5e856591925d2288db871ac9632eab5ee7f7a649`: Verify #752, 1951 passed / 0 failed;
- PR #344 synthetic `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`: Verify #753, 1951 passed / 0 failed;
- squash main `19851b9d40827b3ca5e3889c3858ca32c5602f67`: Verify #754, 1951 passed / 0 failed;
- Telegram remains read-only and not persistence-wired;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Read-Only Persistence Verification v1

Boundaries:

- `ProductDecisionHistoryStorageService.read_durable`
- `ProductDecisionHistoryService.latest_persistent`
- `ProductDecisionPersistenceVerificationService.verify_latest`

Tests:

- `tests/test_product_decision_readonly_persistence_verification_v1051_v1060.py`

Проверяет:

- durable read receipt is explicit;
- corrupted JSON is invalid, not empty history;
- non-list/mixed durable data fails closed;
- latest_persistent reads durable storage rather than memory;
- in-memory history cannot verify persistence;
- malformed durable read receipt fails closed;
- missing/cross-SKU/broken application lineage fails closed;
- valid restart produces canonical verified persistence payload;
- verify_latest is read-only and does not mutate file or in-memory state;
- final feature `c0da07cbafeb1fe38001729eebca94648149d96b`: Verify #760, 1961 passed / 0 failed;
- PR #346 synthetic `0ccae174a2adfe5c650ca96bf7dcf90ceafaec80`: Verify #761, 1961 passed / 0 failed;
- squash main `b0bfdd5dd79349244ceaf64d1d4df9899211344a`: Verify #762, 1961 passed / 0 failed;
- no persistence application side effect;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Telegram Verified Product Decision Guidance / Checklist Wiring v1

Boundaries:

- `telegram_assistant_factory.create_telegram_assistant`
- `AssistantButtonHandlerService._show_product_decision`
- `AssistantButtonHandlerService._with_verified_product_decision_user_action`
- `ProductDecisionPersistenceVerificationService.verify_latest`
- existing Product Decision guidance/checklist builders

Tests:

- `tests/test_product_decision_verified_guidance_telegram_wiring_v1061_v1070.py`
- existing Product Decision Telegram UI/result-integrity tests

Проверяет:

- missing verified dependencies preserve the existing decision card;
- blocked or malformed durable verification never becomes verified UI;
- verified snapshot must match the current decision by SKU, recorded_at, decision_type, priority, confidence and reasons;
- malformed guidance prevents checklist presentation;
- malformed checklist prevents verified presentation;
- unsafe guidance flags cannot reach verified UI;
- verifier exceptions are contained without secret leakage;
- valid durable verification produces a seller-facing manual checklist;
- automatic execution remains explicitly prohibited;
- Telegram factory shares the exact Product Decision History owner with the read-only verifier;
- failed `f449e7d738b56fb72f39e0836eb2ea3464b899a9`: Verify #768, 1970 passed / 1 failed;
- final feature `09abed3a9db1c1cf90a13d4393bb3771f09c964d`: Verify #769, 1971 passed / 0 failed;
- PR #348 synthetic `400bbfa95038edd3876a2ea0eb4b2e28db65fefb`: Verify #770, 1971 passed / 0 failed;
- squash main `dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`: Verify #771, 1971 passed / 0 failed;
- no persistence application side effect;
- no execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Telegram Query Exception Containment v1

Boundaries:

- `AssistantButtonHandlerService._open_product_decisions_menu`
- `AssistantButtonHandlerService._show_product_decision`
- `AssistantTelegramAdapter.handle_button`

Tests:

- `tests/test_product_decision_telegram_query_exception_containment_v1071_v1080.py`
- existing Product Decision Telegram result-integrity tests
- existing Telegram adapter runtime exception-containment tests

Проверяет:

- overview RuntimeError is contained locally and does not leak exception text;
- overview TypeError is not retried;
- detail RuntimeError is contained locally and does not leak exception text;
- detail TypeError is not retried;
- local domain failure reaches Telegram adapter unchanged;
- generic `TELEGRAM_BUTTON_DISPATCH_FAILED` is not substituted for contained Product Decision query failure;
- explicit overview failure semantics remain unchanged;
- valid overview behavior remains unchanged;
- explicit detail failure semantics remain unchanged;
- valid detail behavior remains unchanged with defensive copy;
- failed `31902d6e4f1302a5fe221e091b54bd5e2c4a8f3d`: Verify #777, 1980 passed / 1 failed;
- final feature `30da677a1db0fdca3cd4ac2b0928859e0b9b81a8`: Verify #778, 1981 passed / 0 failed;
- PR #350 synthetic `a0bbb0059c67c3d4e0583f2b13883f5dd3f8857e`: Verify #779, 1981 passed / 0 failed;
- squash main `41473566a558bb09899f64d581010b72e4053fbd`: Verify #780, 1981 passed / 0 failed;
- no retry, persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Financial Telegram Query Exception Containment v1

Boundaries:

- `AssistantButtonHandlerService._open_unit_economics_menu`
- `AssistantButtonHandlerService._show_unit_economics`
- `AssistantButtonHandlerService._open_returns_finance_impact_menu`
- `AssistantButtonHandlerService._show_returns_finance_impact`
- `AssistantTelegramAdapter.handle_button`

Tests:

- `tests/test_financial_telegram_query_exception_containment_v1081_v1090.py`
- existing financial Telegram result-integrity/UI tests

Проверяет:

- Unit Economics product source exceptions fail closed without secret leakage;
- Returns Finance Impact product source exceptions fail closed;
- Unit Economics query exceptions are one-shot and skip formatting;
- Returns Finance Impact query exceptions are one-shot;
- Unit Economics formatter exceptions are contained locally;
- TypeError does not trigger retry;
- domain financial failure reaches Telegram adapter unchanged;
- valid Unit Economics menu/detail remains compatible;
- valid Returns Finance Impact menu/detail remains compatible;
- final feature `6cf579771939ceb765a996fa761a406175e003d3`: Verify #786, 1991 passed / 0 failed;
- PR #352 synthetic `69383b1fcfe87aab31dfb6bb29cd4f73bf051e13`: Verify #787, 1991 passed / 0 failed;
- squash main `0f484141713f2452f451e818caf600d113df6ad4`: Verify #788, 1991 passed / 0 failed;
- finance formulas unchanged;
- no retry, persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Tax Configuration Persistence & Result Integrity v1

Boundaries:

- `TaxConfigurationService.get_policy`
- `TaxConfigurationService.save_policy`
- `TaxConfigurationService._validate_policy`
- production `telegram_core_factory.create_telegram_core`

Tests:

- `tests/test_tax_configuration_persistence_result_integrity_v1091_v1100.py`
- existing `tests/test_tax_configuration_foundation.py`

Проверяет:

- non-mapping persisted root fails closed as unconfigured;
- non-numeric persisted tax rate fails closed;
- NaN and positive/negative infinity fail closed;
- negative, >100% and boolean tax rates are rejected before write;
- invalid minimum-tax rates are rejected before write;
- NONE preserves explicit zero-tax normalization;
- valid policy is normalized and atomically persisted;
- failed atomic replace preserves the previous durable policy and cleans the temp file;
- truncated JSON becomes unconfigured instead of a startup exception;
- production factory starts with malformed tax config while keeping tax unknown;
- final feature `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`: Verify #794, 2001 passed / 0 failed;
- PR #354 synthetic `5167b644bc53edc27a40c7b15c7068e0c669d2fc`: Verify #795, 2001 passed / 0 failed;
- squash main `38e54ddc6d289f0f75121cc63efa0268ef2784f8`: Verify #796, 2001 passed / 0 failed;
- TaxService formulas unchanged;
- no execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Tax Calculation Input & Result Integrity v1

Boundaries:

- `TaxService.calculate`
- `TaxService._normalize_amount`
- `TaxService._normalize_rate`
- `ProductUnitEconomicsProvider._calculate_tax`

Tests:

- `tests/test_tax_calculation_input_result_integrity_v1101_v1110.py`
- existing tax configuration/unit-economics tests

Проверяет:

- missing tax mode preserves the explicit unconfigured result;
- unsupported tax mode is rejected before numeric conversion;
- non-numeric revenue/gross-profit inputs fail closed;
- NaN/inf revenue/gross-profit inputs fail closed;
- boolean amounts are not accepted as numeric tax inputs;
- invalid USN_INCOME tax rates fail closed;
- invalid minimum-tax rates fail closed;
- overflow/non-finite tax result never returns NaN/inf;
- numeric-string compatibility and valid formula outputs remain unchanged;
- negative revenue/profit continue to clip tax base to zero;
- Unit Economics maps invalid TaxService result to unknown tax rather than fabricated profit;
- final feature `85fc4b76baa725cbc586ca39e8454e30a70fb168`: Verify #802, 2011 passed / 0 failed;
- PR #356 synthetic `7d070c91d97e811491849475ddcd65552eadd1c7`: Verify #803, 2011 passed / 0 failed;
- squash main `1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`: Verify #804, 2011 passed / 0 failed;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Advertising & Expense Finite Result Integrity v1

Boundaries:

- `AdvertisingService.calculate`
- `AdvertisingService.total`
- `ExpenseService.calculate`
- `ExpenseService.calculate_single`
- `BusinessAnalyticsService.calculate`

Tests:

- `tests/test_advertising_expense_finite_result_integrity_v1111_v1120.py`
- existing unknown-advertising financial evidence tests

Проверяет:

- advertising NaN/inf inputs fail closed;
- advertising boolean inputs fail closed;
- negative advertising preserves existing explicit error;
- campaign aggregation ignores invalid rows but stays finite;
- campaign aggregate overflow fails closed;
- expense aggregation ignores invalid rows but stays finite;
- expense aggregate overflow fails closed;
- single expense rejects boolean and NaN/inf inputs;
- valid numeric-string financial inputs remain compatible;
- Business Analytics does not emit business profit after invalid advertising or expense overflow;
- final feature `c45284c99d70a45b1bed2b5f62049a7bb5c40df6`: Verify #810, 2021 passed / 0 failed;
- PR #358 synthetic `8b8bcfda3b61518637637a05b1b60109a7907192`: Verify #811, 2021 passed / 0 failed;
- squash main `cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`: Verify #812, 2021 passed / 0 failed;
- finance formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Store Profit Aggregation Result Integrity v1

Boundaries:

- `StoreProfitService.calculate`
- `StoreProfitService._count`
- `StoreProfitService._number`
- `BusinessAnalyticsService.calculate`
- `SalesIntelligenceService.analyze`
- `AssistantSalesExecutorService.execute`

Tests:

- `tests/test_store_profit_aggregation_result_integrity_v1121_v1130.py`

Проверяет:

- non-list/tuple store-profit input fails closed;
- non-mapping product-profit rows fail closed;
- sales_count rejects bool, negative, fractional, non-numeric and non-finite values;
- financial aggregate fields reject bool, non-numeric and NaN/inf values;
- aggregate overflow and non-finite margin fail closed;
- failed product rows remain skipped;
- missing numeric fields retain zero defaults;
- valid numeric strings and loss classification remain compatible;
- BusinessAnalytics stops before tax/advertising/expense calculations on store-profit failure;
- Sales Intelligence and sales executor preserve that failure end-to-end;
- final feature `a888d3c4aa35aaba7526df186bfdbdd2902f9369`: Verify #818, 2031 passed / 0 failed;
- PR #360 synthetic `decce34f5a0cf348a4f9ab1ab80c50179d5e9d2b`: Verify #819, 2031 passed / 0 failed;
- squash main `87c95cf2eb139cd8782d8df79d43b2313939bba0`: Verify #820, 2031 passed / 0 failed;
- aggregation formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Business Profit Calculation Result Integrity v1

Boundaries:

- `BusinessProfitService.calculate`
- numeric/cost/result validation helpers
- `BusinessAnalyticsService.calculate`
- `SalesIntelligenceService.analyze`
- `AssistantSalesExecutorService.execute`

Tests:

- `tests/test_business_profit_calculation_result_integrity_v1131_v1140.py`

Проверяет:

- malformed store-profit/tax structures and markers fail closed;
- gross-sales/gross-profit are finite non-boolean numbers;
- advertising/other-expense costs are finite and non-negative;
- tax amount is finite and non-negative;
- unknown tax remains unknown;
- existing tax error message contract remains compatible;
- business-profit/margin overflow fails closed;
- numeric-string/formula compatibility remains;
- new integrity failures propagate to the sales executor;
- final feature `98edb5b5500c25e53b77237016afe3a223360ab8`: Verify #826, 2041 passed / 0 failed;
- PR #362 synthetic `6e335e508c07903d6e4488f1aac40d28a9e4152f`: Verify #827, 2041 passed / 0 failed;
- squash main `189455bb5b44c47bbf5abf188d1b456dad14b1ba`: Verify #828, 2041 passed / 0 failed;
- formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Finance Period Aggregation Result Integrity v1

Boundaries:

- `FinanceAnalyticsService.get_period_finance`
- `FinanceAnalyticsService._normalize_daily`
- finance count/number validation helpers
- period failed-day and aggregate-failure helpers
- `StoreAnalyticsService.analyze_finance`

Tests:

- `tests/test_finance_period_aggregation_result_integrity_v1141_v1150.py`

Проверяет:

- daily source exceptions are contained and sanitized as failed-day evidence;
- non-mapping daily results fail closed;
- malformed explicit error markers fail the day;
- operations/sales_count reject bool, negative, fractional, non-numeric and NaN/inf values;
- amount fields reject bool, non-numeric and NaN/inf values;
- malformed/non-finite fee breakdown fails the whole day;
- invalid days cannot partially commit period totals;
- valid partial-period behavior remains compatible;
- amount and fee-breakdown aggregate overflow fails closed;
- valid numeric strings and signed fees remain compatible;
- StoreAnalytics finance path preserves contained source failure;
- failed intermediate `f54132ebf109240242a87037a81b1db5ed052d5b`: Verify #834, 2050 passed / 1 failed; test-only false positive remains failed evidence;
- final feature `52661a7c37068759d20797644943a3b9e5e5ebcc`: Verify #835, 2051 passed / 0 failed;
- PR #364 synthetic `ef001cc855661041bd3987604496d03e55acaf30`: Verify #836, 2051 passed / 0 failed;
- squash main `d1655adf6719e6000f996b4635253c6b99193ba3`: Verify #837, 2051 passed / 0 failed;
- finance formulas and partial-period semantics unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.

---

# Period Profit Summary Input & Result Integrity v1

Boundaries:

- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._calculate_product`
- finance count/amount/fee normalization helpers
- cost resolution and tax-rate validation
- product/day/period aggregate finiteness
- `PeriodProfitQueryService.query`
- `AssistantPeriodProfitRuntimeService.handle_text`

Tests:

- `tests/test_period_profit_summary_input_result_integrity_v1151_v1160.py`

Проверяет:

- daily finance source exceptions are contained and sanitized;
- non-mapping finance results and malformed error markers fail closed;
- sales_count rejects bool, negative, fractional, non-numeric and NaN/inf values;
- finance amount fields reject bool, non-numeric and NaN/inf values;
- fee_breakdown requires finite numeric values;
- direct/stored cost inputs reject bool, negative, malformed and non-finite values;
- cost-source exceptions are contained;
- malformed/non-finite/negative tax rates fail closed without constructor exception;
- amount and fee aggregate overflow fails closed;
- valid numeric strings and signed fees remain compatible;
- existing period-profit formula remains unchanged;
- query/runtime preserve the integrity failure end-to-end;
- final feature `4ab53fe054504c633fbcd6fb708ccb7dc557eaa4`: Verify #847, 2061 passed / 0 failed;
- PR #367 synthetic `a9030acff2031b118c0c0600c008804c3d6ff08a`: Verify #848, 2061 passed / 0 failed;
- squash main `0ca4d226f3f75e2b20035a87a13b1a10d6c71581`: Verify #849, 2061 passed / 0 failed;
- no failed production SHA occurred in v1151-v1160;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.

---

# Telegram Period Profit Analyst Wiring v1

Boundaries:

- `telegram_core_factory.create_telegram_core`
- `telegram_assistant_factory.create_telegram_assistant`
- `AssistantKeyboardService.build_main_keyboard`
- `AssistantKeyboardService.build_period_profit_keyboard`
- `AssistantButtonHandlerService.handle`
- `AssistantButtonHandlerService._open_period_profit_menu`
- `AssistantButtonHandlerService._show_period_profit`
- `TelegramResponseFormatter.format`
- `AssistantPeriodProfitRuntimeService.handle_text`
- `AssistantPeriodProfitRuntimeService.handle_callback`

Tests:

- `tests/test_telegram_period_profit_analyst_wiring_v1161_v1170.py`
- compatibility update in `tests/test_product_unit_economics_telegram_ui.py`

Проверяет:

- main Telegram menu exposes period-profit analytics;
- period menu normalizes safe Today / 7 / 28 / 56 / 90-day callbacks;
- menu remains read-only and non-executing;
- callbacks delegate only to the period-profit read-only runtime;
- runtime exceptions are contained;
- malformed callback results fail closed;
- execution-adjacent success payloads fail closed;
- analytical `text` renders as Telegram text;
- Telegram core wires the production period-profit runtime/query;
- natural-language period-profit requests bypass the general action/execution flow;
- existing partial-core fixtures remain backward compatible;
- no Ozon mutation path is introduced;
- `data/users.json` untouched by this package;
- `externally_verified=False`.

Verification:

- failed intermediate `e7fce70c39f976e97bf78687621ace5125f9d30a`: Verify #866, 2069 passed / 2 failed;
- final feature `9c5d14f0220e5f13ee0a7d834855f7e07db58cab`: Verify #868, 2071 passed / 0 failed;
- PR #369 synthetic `04b20cc49a253bfb357626cf62a71b779a75112e`: Verify #869, 2071 passed / 0 failed;
- squash main `d06a5f8cc23814e3177f58f6182bef6fbceb0697`: Verify #870, 2071 passed / 0 failed.

---

# Telegram Custom Period Date Input v1

Boundaries:

- `AssistantPeriodProfitRuntimeService.handle_text`
- `AssistantPeriodProfitRuntimeService._extract_custom_dates`
- `AssistantPeriodProfitRuntimeService._invalid_custom_period`
- `AssistantEntryService.handle`

Tests:

- `tests/test_telegram_custom_period_date_input_v1171_v1180.py`

Проверяет:

- `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ` routes as normalized ISO dates;
- en dash and em dash separators;
- single-digit day/month input;
- existing ISO custom-period compatibility;
- mixed supported date formats normalize consistently;
- invalid calendar dates fail closed without query;
- incomplete custom date input fails closed;
- seller-facing missing-period prompt includes localized example;
- localized custom Period Profit bypasses general execution flow;
- all successful downstream Period Profit results remain read-only/non-executing;
- no Ozon mutation or finance formula changes.

Verification:

- feature `62b040e392514bc410b34d82eccb8e0385b9c548`: Verify #884, 2081 passed / 0 failed;
- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61`: Verify #885, 2081 passed / 0 failed;
- squash main `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`: Verify #886, 2081 passed / 0 failed;
- `externally_verified=False`.

---

# Tax Policy Production Availability v1

Boundaries:

- `TaxConfigurationService.get_policy`
- `TaxConfigurationService._get_environment_policy`
- `TaxConfigurationService._validate_policy`
- repository `data/tax_configuration.json`
- `telegram_core_factory.create_telegram_core`
- `ProductUnitEconomicsProvider.build_current`

Tests:

- `tests/test_tax_policy_production_availability_v1181_v1190.py`

Проверяет:

- repository production policy is explicit USN Income 6%;
- explicit env policy is used only when persisted file is absent;
- missing file + missing env remains unconfigured;
- invalid env policy fails closed;
- explicit NONE env is a real configured zero-tax policy;
- persisted policy wins over env;
- malformed persisted policy does not silently fall back;
- production Telegram core receives repository tax policy;
- hook-2-like current economics calculates 6.00 ₽ tax;
- hook-2-like base unit profit is 35.83 ₽ before return-risk adjustment;
- unconfigured tax still blocks profit instead of assuming zero;
- no Ozon mutation or execution changes.

Verification:

- feature `1d0df2799fb87b57d916843a96a080389e2ac07b`: Verify #900, 2091 passed / 0 failed;
- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1`: Verify #901, 2091 passed / 0 failed;
- squash main `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`: Verify #902, 2091 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Returns Protobuf Timestamp Compatibility v1

Boundaries:

- `OzonClient.get_returns`
- `OzonClient._returns_timestamp`
- `PeriodProfitReturnEvidenceService.load`
- `PeriodProfitQueryService.query`

Tests:

- `tests/test_period_profit_returns_timestamp_v1191_v1200.py`

Проверяет:

- date-only start/end normalize to RFC3339 protobuf timestamps;
- full RFC3339/offset timestamps remain unchanged;
- Returns filter/pagination/timeout contract remains unchanged;
- custom and preset Period Profit ranges use valid timestamps;
- return evidence remains read-only/non-financial;
- no Ozon mutation or execution changes.

Verification:

- feature `9e2c5b27a1df9f32c8e950766abc809ba93f7976`: Verify #918, 2101 passed / 0 failed;
- PR #375 synthetic `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`: Verify #919, 2101 passed / 0 failed;
- squash main `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`: Verify #920, 2101 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Data Completeness Integrity v1

Boundaries:

- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._normalize_product`
- `PeriodProfitReturnEvidenceService.load`
- `PeriodProfitReturnEvidenceService._has_next`
- `PeriodProfitReturnEvidenceService._next_id`
- `build_period_profit_response`

Tests:

- `tests/test_period_profit_data_completeness_v1201_v1210.py`

Проверяет:

- persisted SQLite tuple `(id, offer_id, sku)` is normalized and included in Period Profit;
- empty/malformed product sets fail closed instead of returning 0.00 ₽ success;
- existing dict product contract remains compatible;
- Returns evidence paginates past the first 500 records;
- `last_id` advances across pages;
- bounded pagination marks capped results incomplete;
- later-page failures preserve partial evidence without claiming exact totals;
- incomplete return counts are presented as `как минимум N`;
- exact return counts retain existing presentation;
- legacy READY response fixtures remain compatible;
- no finance formula, return-cost inference, execution or Ozon mutation changes.

Verification:

- failed `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`: Verify #935, 2103 passed / 2 failed;
- failed `49c02ae1790b7d395794932e7ac4fa95cbac1644`: Verify #936, 2109 passed / 2 failed;
- final feature `16c53622612b72bce2aa43fd97d5ff66d47466c3`: Verify #937, 2111 passed / 0 failed;
- PR #377 synthetic `f1593267f67339f2dd68d235056cdbc69960160a`: Verify #938, 2111 passed / 0 failed;
- squash main `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`: Verify #939, 2111 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Tax Rate Unit Integrity v1

Boundaries:

- `period_profit_factory._period_profit_tax_fraction`
- `period_profit_factory.create_period_profit_query`
- `PeriodProfitSummaryService._tax_fraction`
- production TaxConfigurationService policy

Tests:

- `tests/test_period_profit_tax_rate_unit_v1211_v1220.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- USN Income 6.0 percent converts to 0.06 fraction;
- NONE converts to 0.0;
- unconfigured/invalid/non-finite tax policy fails closed;
- unsupported USN Income Minus Expenses fails closed;
- summary rejects percent-scale multiplier 6.0;
- summary accepts 0.06 as six percent;
- live seller sample produces tax 80 902.27 ₽, profit 310 701.55 ₽, margin 23.04%;
- production factory reads repository tax policy and exposes 0.06 to summary;
- Period Profit tax path remains read-only.

Verification:

- failed `a7d5cead4c7c49907d6d045b54a3cec30d48efad`: Verify #953, 2110 passed / 1 failed;
- failed `ee463cd1000113998ae5b895da02334bb5a5f495`: Verify #954, 2120 passed / 1 failed;
- final feature `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`: Verify #955, 2121 passed / 0 failed;
- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af`: Verify #956, 2121 passed / 0 failed;
- squash main `2f438bd6bb739938cee4fe56b83af8f4a563f942`: Verify #957, 2121 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Revenue Share Presentation v1

Boundaries:

- `build_period_profit_response`
- `_money_with_revenue_share`

Tests:

- `tests/test_period_profit_revenue_share_presentation_v1221_v1230.py`

Проверяет:

- revenue displays 100.00%;
- net Ozon accrual displays revenue share;
- commission/logistics/acquiring/other fees display absolute deduction shares;
- product cost, tax and profit display revenue shares;
- negative profit keeps negative share;
- zero revenue suppresses derived percentages;
- existing comparison percentage keeps previous-period meaning;
- existing margin and scope warning remain unchanged;
- no finance/tax formula or execution changes.

Verification:

- feature `77994ccb67c060f7c01694ac65eea5c8aec24e1d`: Verify #970, 2131 passed / 0 failed;
- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`: Verify #971, 2131 passed / 0 failed;
- squash main `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`: Verify #972, 2131 passed / 0 failed;
- `externally_verified=False`.

---

# Finance Accrual Pagination & Read Session Integrity v1

Boundaries:

- `OzonClient.get_accruals_by_day`
- `FinanceService.begin_read_session`
- `FinanceService._get_accruals_by_day`
- `FinanceService.get_daily_finance`
- `PeriodProfitSummaryService.calculate`

Tests:

- `tests/test_finance_accrual_pagination_read_session_v1231_v1240.py`

Проверяет:

- first accrual page sends required empty `last_id`;
- subsequent pages follow Ozon cursor until exhaustion;
- malformed accrual-page response fails closed;
- repeated cursor fails closed;
- max-page exhaustion does not return partial finance as complete;
- same day is downloaded once for multiple SKUs inside one read session;
- new read session clears day cache;
- Period Profit starts one fresh finance read session;
- read-session exceptions are contained;
- target SKU finance on the second accrual page is included.

Verification:

- failed `8d159ed09410ed978bef6cfdb5719a67bc5491b1`: Verify #990, 2140 passed / 1 failed;
- final feature `ad215b8d86c547e740dcb3583e7b7f580e9fb823`: Verify #991, 2141 passed / 0 failed;
- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08`: Verify #992, 2141 passed / 0 failed;
- squash main `e66125d5e2c737497762178bef86dd36a62721f3`: Verify #993, 2141 passed / 0 failed;
- `externally_verified=False`.

---

# Account-Level Ozon Profit Reconciliation v1

Boundaries:

- `FinanceService.get_daily_account_finance`
- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._calculate_account_period`
- `PeriodProfitSummaryService._amounts_reconcile`
- `build_period_profit_response`
- `build_period_profit_coverage`
- Decision 037

Tests:

- `tests/test_account_level_period_profit_reconciliation_v1241_v1250.py`

Проверяет:

- account-level Ozon net accrual is the authoritative period monetary total;
- account-level non-SKU money changes profit exactly once;
- SKU revenue must reconcile to account revenue;
- mismatched revenue coverage fails closed;
- account total corrects duplicated SKU-attributed posting net;
- account fee breakdown replaces summed SKU fee breakdown;
- account finance failure blocks Period Profit;
- Telegram explains account reconciliation and no-double-subtract semantics;
- coverage exposes account-level inclusion/reconciliation;
- legacy finance without account boundary keeps V1 compatibility;
- authorized mapped account expense remains evidence and is not deducted again.

Verification:

- feature `a0e528f36b1b4721af0e8d0b419c414d20fabea6`: Verify #1010, 2151 passed / 0 failed;
- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f`: Verify #1011, 2151 passed / 0 failed;
- squash main `a359e3d8e68784849caa659dec0123fb15dc6932`: Verify #1012, 2151 passed / 0 failed;
- `externally_verified=False`.

---

# Return COGS Recovery Evidence v1

Boundaries:

- `PeriodProfitReturnEvidenceService._normalize_record`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `PeriodProfitQueryService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`

Tests:

- `tests/test_return_cogs_recovery_evidence_v1251_v1260.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- nested Returns API product, visual, compensation and logistics fields are preserved;
- arrived customer-return units become candidate recovery only;
- candidate value uses current configured product cost;
- compensated units are separated from recovery candidates;
- unproven visual status remains unresolved;
- missing cost remains unknown instead of zero;
- partial return sample cannot become complete recovery evidence;
- historical cost basis remains unconfirmed;
- originating sale-period lineage remains unconfirmed;
- saleable inventory recovery remains unconfirmed;
- candidate recovery does not mutate Period Profit;
- response and coverage expose candidate evidence and limitations;
- factory wiring shares the ProductCostService dependency;
- legacy positional PeriodProfitQueryService constructor remains compatible.

Verification:

- failed `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`: Verify #1033, 2159 passed / 2 failed;
- final feature `30f3edafd9d2af603f2277701cb13492a334dd30`: Verify #1038, 2161 passed / 0 failed;
- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576`: Verify #1039, 2161 passed / 0 failed;
- squash main `d845c7183ef5a914853a15b788e18b0cebfd1c93`: Verify #1040, 2161 passed / 0 failed;
- `externally_verified=False`.

---

# External Operating Expense Coverage v1

Boundaries:

- `ExpenseRepository`
- `PeriodProfitExternalExpenseEvidenceService`
- `PeriodProfitQueryService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `confirm_expense_coverage.py`
- Decision 038

Tests:

- `tests/test_external_operating_expense_coverage_v1261_v1270.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- explicit external expense coverage intervals are persisted and read by period;
- coverage is complete only when confirmed intervals cover every requested calendar day;
- empty uncovered periods remain unknown rather than zero;
- empty fully covered periods are explicit confirmed zero expense;
- partial expense evidence is labelled incomplete;
- complete coverage permits a complete derived profit-after-external-expenses value;
- invalid dates are rejected;
- bool, NaN and infinite amounts are rejected;
- external expense evidence is wired into the production Period Profit query;
- Telegram distinguishes base profit from external-expense-adjusted views;
- coverage exposes external expense completeness and totals;
- comparison semantics stay on base Period Profit;
- Ozon-account expenses already included in account net accrual are not deducted again;
- return COGS recovery uncertainty and accounting-net-profit boundary remain unchanged;
- factory wiring includes the external expense evidence service.

Verification:

- failed `55d8f189dc170cc524aa8798aea42b1b7ae6251c`: Verify #1054, 2150 passed / 11 failed, artifact 9894680388, digest `sha256:49302f69375d247b9094b7a58f1a16c5671124eb894eef0153edd3dc1276c376`;
- failed `9f32163739d849dfe3681a9de6358fb64db40100`: Verify #1055, 2150 passed / 11 failed, artifact 9894698643, digest `sha256:e37593e820234269a9230e6be4f8c61fc591d7108f4093201bdb3192e09956d0`;
- failed `e788e5110109eb678767313278580989b192f689`: Verify #1060, 2160 passed / 1 failed, artifact 9894794990, digest `sha256:af0ffe3ef3fe9ddfce906ac6bbb3a33c10f5ac445f1884705aa3b85e483fb1fc`;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `07f9a35eb238280e95b52bc14d18cc6aba735703`: Verify #1062, 2171 passed / 0 failed, artifact 9894853461, digest `sha256:9d28a3a5ae753f1215fd042622fd62d7e4985fa96eeba0f2f140318166617298`;
- PR #389 synthetic `77dd43cfeb36ebe0066f8747c6c51580083848a6`: Verify #1063, 2171 passed / 0 failed, artifact 9894897854, digest `sha256:9111b865c015e95c360ba417c3ef68f82377e82f9e2eddfc7c7e7d8c61ae93a0`;
- squash main `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`: Verify #1064, 2171 passed / 0 failed, artifact 9894942156, digest `sha256:6ba30eda33b5a1315469e4fbf9253058d932cbc756e634b8996b2f31b2158e53`;
- `externally_verified=False`.

---

# Return Sale-Period Lineage Evidence v1

Boundaries:

- `FinanceService.get_daily_sale_posting_evidence`
- `PeriodProfitReturnSaleLineageEvidenceService`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`

Tests:

- `tests/test_return_sale_lineage_evidence_v1271_v1280.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- only positive POSTING sale accruals become sale-lineage evidence;
- malformed positive sale records keep finance evidence partial;
- finance failure stays unavailable rather than becoming an empty zero;
- return lineage matches by exact `posting_number + SKU`;
- same posting with another SKU does not match;
- one unique positive sale-accrual date is a selected-period match;
- multiple sale dates are ambiguous;
- missing finance days keep lineage partial even when another day matches;
- missing return identifiers remain unresolved;
- incomplete return sample cannot produce aggregate sale-period confirmation;
- compensated returns never become COGS recovery candidates because lineage exists;
- sale-lineage service exceptions are contained and do not destroy base candidate evidence;
- confirmed sale-period lineage does not confirm historical COGS;
- confirmed sale-period lineage does not prove saleable/restored inventory;
- `confirmed_cogs_recovery_amount` remains 0;
- profit adjustment remains forbidden;
- Telegram distinguishes confirmed lineage from remaining COGS blockers;
- coverage exposes lineage without accounting-net-profit claim;
- factory shares the exact FinanceService instance between Period Profit summary and sale-lineage evidence.

Verification:

- entering exact docs-reconciled main `356fa301a9025e15a5a9fbb94da706d10670416a`: Verify #1074, 2171 passed / 0 failed, artifact 9897945762, digest `sha256:9b883028d77316bcabd7634b934f9ab38664a84468eab5622195ff73929c7653`;
- failed `db2c6c0fa900720c303a8f8face32ef3eec3be11`: Verify #1081, 2170 passed / 1 failed, artifact 9898277377, digest `sha256:2e8365779ec323568d2be3649d17d7a79e8d5a5da745f128cc11555750cd7b2e`;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `e96fb63007647857045f226c9c41fd8157ae962e`: Verify #1083, 2185 passed / 0 failed, artifact 9898333361, digest `sha256:7ac52123e97a821e6fb65fcc7dc15dfb61d68a8be6fd40c9598b7505a174c3f5`;
- PR #391 synthetic `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`: Verify #1084, 2185 passed / 0 failed, artifact 9898386674, digest `sha256:a4ac6ad8520a2a0726aff061f5f579a74742f868e17e2ced9d89ac84c3798d47`;
- squash main `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`: Verify #1085, 2185 passed / 0 failed, artifact 9898420551, digest `sha256:4a187e0b83b0b5950e64aaf749d31b78d7d5435132a77fde2e044667fe06b864`;
- `externally_verified=False`.

---

# Historical Product Cost Evidence v1

Boundaries:

- `ProductCostService.create_table`
- `ProductCostService.record_historical_cost`
- `ProductCostService.get_historical_cost_evidence`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `record_product_cost_history.py`
- Decision 039

Tests:

- `tests/test_historical_product_cost_evidence_v1281_v1290.py`

Проверяет:

- mutable current cost does not backfill historical evidence;
- explicit effective-dated versions resolve for later sale dates;
- latest effective version applies without rewriting earlier versions;
- duplicate product/date version conflicts do not silently overwrite evidence;
- ambiguous product identity remains unconfirmed;
- dates before first historical version remain missing rather than falling back to current cost;
- Return COGS historical lookup uses the matched originating sale date;
- historical candidate value may differ from current-cost diagnostic value;
- all candidate rows must resolve for aggregate historical cost confirmation;
- missing one historical version keeps aggregate basis unconfirmed;
- Telegram shows confirmed historical cost while retaining inventory-recovery blocker;
- coverage exposes historical cost confirmation without accounting-net-profit claim;
- `confirmed_cogs_recovery_amount` remains 0;
- profit adjustment remains forbidden.

Verification:

- entering exact docs-reconciled main `212df575cc60a809032954d425902fad86623956`: Verify #1095, 2185 passed / 0 failed, artifact 9906001699, digest `sha256:a50fb08552d73f187bbacc608751655880f293578a7ac4408154808d82a16f79`;
- no failed production SHA occurred;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `f3fcb80588f394eb05e5944ca2812ed59adf7649`: Verify #1103, 2195 passed / 0 failed, artifact 9906200014, digest `sha256:c776260a5026572cbe27c2bab5212d2a64d92d95f7a9170a433a2d5b12b46af7`;
- PR #393 synthetic `672e18f904768742917df9c808c48ec476d9fd3e`: Verify #1104, 2195 passed / 0 failed, artifact 9906235551, digest `sha256:d849f4a6413df1de6c6b3e28ed4f5c45465b292266db2c31dbac3602251fcfb0`;
- squash main `9ca4497dda61615076b8203d0404502630ab7e81`: Verify #1105, 2195 passed / 0 failed, artifact 9906262083, digest `sha256:6bc9ab6699976e56572a216dab839e96c8921f484047c522eb00535163626987`;
- `externally_verified=False`.


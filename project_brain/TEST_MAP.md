Warning: truncated output (original token count: 39198)
Total output lines: 4703

# Test Map

## Ozon Performance transient request failures

Updated:

- `tests/test_ozon_performance_client.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers sanitized timeout/connection categories, one retry for idempotent GET
requests, no retry for report-creation POST, and Telegram propagation.

## Ozon Performance unknown CSV row labels

Updated:

- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers skipping an exact repeated full header row, rejecting any other unknown
SKU row label, and propagating only the report kind and safe column names into
the user-facing diagnostic.

## Historical Ozon Performance dependency stage diagnostics

Updated:

- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers safe stage labels for campaign discovery, CPC report creation/status, both
CPO order report creation/status paths, and propagation through the advertising
service into Telegram diagnostics; unexpected labels are suppressed.


## Current Status


Verification model:

SHA-bound.

Latest confirmed full-suite baseline:

2208 passed on `3f82b65054a2a7a48b9918803c197377bdb3557f`.

GitHub Actions push Verify #1131 completed successfully for this exact main SHA.

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

## Historical Performance SKU advertising reports

Test:

- `tests/test_ozon_performance_historical_reports.py`

Проверяет разбор SKU-level CPC/CPO reports, включая CPC-заголовок `Расход, ₽, с НДС`, выбор колонки рекламного расхода,
разбор итоговой строки `Bcero` с безопасным отказом для ненулевого или пустого
итога без SKU-разбивки, безопасную передачу этапа ошибки CSV/ZIP до выбранного
SKU, передачу ограниченных названий колонок без строк данных при неизвестном
заголовке и отказ от вывода небезопасных значений, разбиение периода на окна,
ожидание готовности отчёта дольше прежнего лимита и ограниченный таймаут,
пропуск известных CPM и CPO кампаний из явного CPC-отчёта, отбрасывание
кампаний вне периода по `fromDate`, `toDate` и `createdAt`, fail-closed реакцию
на отсутствующий или неизвестный `paymentType` у кампании, пересекающей период
или не имеющей дат, даже при `advObjectType=SKU`, а также разделение CPC и CPO
отчётов. Проверяет передачу безопасных `paymentType`
и ID кампании в сообщение ошибки выбранного SKU.

Проверяет CPO-отчёты по заказам для выбранных товаров и всех товаров, передачу `timeBounds.from/to` для второго отчёта, привязку расхода только к `SKU продвигаемого товара` и отказ от CSV со ставками без фактического расхода.

## Period Profit by selected SKU

Tests:

- tests/test_period_profit_sku_telegram_flow.py
- tests/test_telegram_period_profit_analyst_wiring_v1161_v1170.py
- tests/test_period_profit_selected_posting_offer_identity.py
- tests/test_period_profit_selected_scope_concurrency.py
- tests/test_period_profit_previous_period_single_pass.py
- tests/test_period_profit_operation_diagnostics.py

Проверяет Telegram SKU/period navigation, production factory wiring, aggregation of proven legacy/current SKU rows, configured tax recomputation, forged identity rejection, and fail-closed unknown money handling.
Также ограничивает количество Ozon posting-detail вызовов, проверяет однократный
previous-period pass, конкурентную изоляцию selected scope и автоматический stack dump.
Ошибка предзагрузки финансов проверяется на наличие безопасного кода диагностики
в Telegram-сообщении и на отсутствие сырого текста Ozon.
Проверяет восстановление offer identity по позднему posting через один месячный
realization request и fail-closed конфликт нескольких offers.
Проверяет rewritten realization SKU для однозначного posting и отклоняет тот же
fallback для multi-product posting.
Проверяет late-posting FBO snapshot без detail N+1 и возврат доказанной current
прибыли при недоступной identity только в previous comparison period.
Проверяет production-style scope с 200 посторонними finance SKU: один realization
request и отсутствие related/detail вызовов для чужих товаров.

## Period Profit parallel finance reads

Test:

- tests/test_period_profit_parallel_finance_reads.py

Проверяет bounded parallel accrual/posting reads and request-local daily-cache
isolation when two active store calculations overlap on the same date.

## Telegram guided onboarding

Tests:

- tests/test_telegram_guided_onboarding.py

Проверяет production callback path, resumable missing-step detection, secret non-disclosure, tenant-scoped pending input and factory wiring.


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
- tests/test_product_action_proposal_confirmati…19198 tokens truncated…nalytics does not emit business profit after invalid advertising or expense overflow;
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
---

# Ozon Store Selector Discoverability

Updated tests:

- `tests/test_telegram_help_discovery.py`
- `tests/test_product_unit_economics_telegram_ui.py`

Covers visibility of the main-menu selector action and its route into the
tenant-aware existing store list.

---

# Persistent Ozon Credential State Diagnostics

Updated tests:

- `tests/test_ozon_credential_production_persistence.py`
- `tests/test_multi_tenant_ozon_onboarding.py`
- `tests/test_telegram_guided_onboarding.py`

Covers missing and mismatched master keys, preserving the ciphertext, safe
onboarding diagnostics, tenant context reset, preservation of an existing key
when tenant storage initialization fails, and refusing to advance after a failed
read-only Ozon probe.

---

# Telegram Help and Feature Discovery

Tests:

- `tests/test_telegram_help_discovery.py`
- updated `tests/test_product_unit_economics_telegram_ui.py`
- existing `tests/test_period_profit_historical_sku_cost_input_v1421_v1430.py`

Covers:

- visible help entry in the real main keyboard;
- `/help` and inline callback parity;
- production Telegram bot/adapter/button-handler callback wiring;
- complete supported slash-command inventory;
- examples for memory, custom Period Profit, effective-dated cost, and SKU identity;
- navigation back to existing workflows and main menu;
- no Ozon execution from help responses.

---

# Return Inventory Recovery Evidence v1

Boundaries:

- `ReturnInventoryRecoveryRepository`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `record_return_inventory_recovery.py`
- Decision 040

Tests:

- `tests/test_return_inventory_recovery_evidence_v1291_v1300.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- explicit `SALEABLE_RESTORED` evidence is persisted and read by exact return identity;
- explicit `NON_SALEABLE` evidence is preserved as a blocking recovery state;
- invalid state and invalid/non-positive/boolean quantity fail closed;
- duplicate `return_id + confirmed_on` evidence is rejected;
- identity drift for one `return_id` becomes conflict/unconfirmed;
- missing recovery evidence remains unknown and never infers recovery from current stock or stock delta;
- exact evidence quantity must match candidate return quantity;
- quantity mismatch blocks saleable recovery confirmation;
- one explicit non-saleable candidate blocks aggregate saleable recovery confirmation;
- compensated returns stay outside saleable recovery candidacy;
- repository exceptions are contained and do not fabricate recovery evidence;
- complete explicit saleable recovery can confirm `saleable_inventory_recovery_confirmed=True` without changing Period Profit;
- response wording exposes explicit recovery state and remaining accounting blockers;
- coverage exposes inventory-recovery completeness/counts without an accounting-net-profit claim;
- `originating_sale_quantity_confirmed=False` remains explicit;
- `recovery_period_attribution_confirmed=False` remains explicit;
- `compensation_accounting_treatment_confirmed=False` remains explicit;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- current Ozon stock observations/deltas are never accepted as recovery proof.

Verification:

- entering exact docs-reconciled main `7f859d1073338c5c0144edea8fe15574460e5210`: Verify #1115, 2195 passed / 0 failed, artifact 9906440691, digest `sha256:42618c7cd0f12fdd9b1c49f2231c990c71c6931727af3a09e1035719f248929a`;
- failed `41b409edcd2a96016bf49e8e8303a7aec00c1886`: Verify #1125, compile failure (`SyntaxError`), no verification artifact;
- failed `4643126328c9e461712aae30f5f7a694a7549e89`: Verify #1126, compile failure at `app/period_profit_response.py:706`, no verification artifact;
- failed `d90549d21c8fb46b0a9012c205520c68e012dbfa`: Verify #1127, compile failure with unmatched `)` at `app/period_profit_response.py:744`, no verification artifact;
- failed `13e4cfbacf617bb60c5b897137b619f079c3d500`: Verify #1128, 2203 passed / 5 failed, artifact 9906768012, digest `sha256:59dd7f0d342951b258bdef1d45b934cd107a858fc986d9326d1f06df016c2944`;
- final feature `1a83e5466bfebd79370e9576ce00b43b79bb668d`: Verify #1129, 2208 passed / 0 failed, artifact 9906795648, digest `sha256:a20b8f66b8d28365b7c9d887250782e7ab01d7885ddcca75c5bfab90541bd875`;
- PR #395 synthetic `7d7b3a5e180a2505850345cc753a7d40ba391cbf`: Verify #1130, 2208 passed / 0 failed, artifact 9906847145, digest `sha256:36f7babc92f4f0d39e708927a61e95122eada8b76892dc4eb7da8912f3e01fa4`;
- squash main `3f82b65054a2a7a48b9918803c197377bdb3557f`: Verify #1131, 2208 passed / 0 failed, artifact 9906878610, digest `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`;
- failed SHAs remain failed evidence permanently and carry no transferable success claim;
- `externally_verified=False`.

---

# Period Profit Tenant Context Production Wiring

Tests:

- `tests/test_period_profit_tenant_context_production_wiring.py`

Covers:

- Telegram callback tenant binding for 7D, 28D, 56D, and 90D;
- Telegram text tenant binding for a custom date range;
- tenant credentials remain available inside concurrent Ozon finance worker threads;
- the real `PeriodProfitFinanceService`, `PeriodProfitRelatedSkuOzonClient`, `OzonCredentialProvider`, and `TelegramBotService` wiring;
- Ozon calls remain READ-ONLY and finance prefetch remains all-or-fail.

---

# Safe Period Profit Finance Diagnostics

Tests:

- `tests/test_period_profit_finance_safe_diagnostics.py`

Covers safe HTTP classification, canonical finance error preservation, payload removal, and read-only Telegram diagnostic presentation.

---

# Period Profit Monetary Validation Stage Diagnostics

Updated:

- `tests/test_period_profit_finance_safe_diagnostics.py`

Covers end-to-end propagation of a sanitized formula-critical money validation stage through prefetch and Telegram runtime.

---

# Period Profit Related-SKU Runtime Finance Regression

Updated:

- `app/tests/test_period_profit_related_sku_identity.py`

Covers the production factory assignment shape, absent/null non-sale commission normalization, retained account accrual evidence, and fail-closed malformed commission handling.

---

# Selected-SKU bounded reverse identity lookup

Updated:

- `tests/test_period_profit_selected_posting_offer_identity.py`

Covers one reverse related-SKU request for 500 unrelated finance SKUs, request-local
identity reuse, and zero account-wide FBO list calls both for a proven match and for
fail-closed missing identity.
Also covers an asymmetric historical → current relation across 501 finance SKUs,
with exact singleton confirmation and a bounded number of related-SKU calls.
Also covers one batched posting sample for each of 501 finance SKUs, request-local
identity reuse, and rejection of a rewritten SKU on a shared posting.

`tests/test_period_profit_operation_diagnostics.py` also verifies structured,
secret-free identity-stage evidence in persisted snapshots.
`tests/test_period_profit_selected_posting_offer_identity.py` runs the selected
production scope with an active trace and verifies final-stage counts.
It also covers 21 parallel representative posting probes, FBO-to-FBS fallback,
tenant ContextVar propagation, rewritten SKU acceptance by exact offer, request
cache reuse, bounded call count, and multi-offer rejection.

# Guided historical selected-SKU confirmation

Updated:

- `tests/test_period_profit_selected_posting_offer_identity.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers exposure of a nonmatching historical offer only from unique-owner,
single-offer posting evidence; Telegram candidate presentation; explicit
confirmation; fresh candidate revalidation; tenant-local mapping persistence;
automatic recalculation; and rejection of forged/stale candidates before storage.

# Seller-confirmed SKU identity revocation

Updated:

- `app/tests/test_period_profit_seller_confirmed_identity_mapping.py`
- `tests/test_telegram_help_discovery.py`

Covers exact-pair transactional revocation, mismatch fail-closed behavior, retained
audit evidence, immediate mapping absence, safe later remapping, Telegram text
routing without a profit query, invalidation wording, and help discoverability.
`tests/test_period_profit_sku_telegram_flow.py` also covers the visible report
button, explicit revocation confirmation, exact repository revalidation, one-click
recalculation, and rejection of a forged revocation callback before mutation.
It also covers ordinary later reports: only an alias actively confirmed for the
exact current product gets a revoke button. Repository coverage verifies deduplicated
batch loading of active aliases for the report surface.
Selected-SKU Telegram coverage also verifies revenue-share percentages for every
money line and suppression of undefined percentages when revenue is zero.

# Telegram custom Period Profit button

Updated:

- `tests/test_telegram_custom_period_date_input_v1171_v1180.py`

Covers menu discoverability, the date-only `ДД.ММ.ГГГГ-ДД.ММ.ГГГГ` response,
canonical ISO query arguments with previous-period comparison, invalid format and
calendar-date retry, per-user pending-state isolation, and explicit cancellation.

# Request-bound tax and onboarding cost completion

Updated:

- `tests/test_telegram_guided_onboarding.py`
- `tests/test_period_profit_request_bound_tax_policy.py`
- `tests/test_period_profit_factory.py`

Covers skipping the seller-cost prompt only for proven complete catalog coverage,
retaining the step for missing costs, production dependency wiring, and one
long-lived Period Profit service alternating between two active-store tenant scopes
with different tax rates without cross-store reuse.

# Store-wide Period Profit bounded identity recovery

Updated:

- `tests/test_period_profit_store_wide_no_fbo_snapshot.py`
- `tests/test_period_profit_selected_posting_offer_identity.py`
- `tests/test_period_profit_previous_period_single_pass.py`

Covers zero account-wide `/v3/posting/fbo/list` calls during unresolved store-wide
identity recovery, bounded exact posting fallback, and preservation of an already
proven current-period result when the optional previous period fails, without a
second current-period query.
Also covers safe Telegram presentation of multiple identity blockers, unresolved
finance SKU visibility, and guidance into the selected-SKU confirmation flow.
The same regression verifies the direct product-picker callback and the visible
seller-confirmation command template.

# Selected-SKU custom period

Updated:

- `tests/test_period_profit_sku_telegram_flow.py`

Covers button discoverability, the date-only input contract, selected-SKU retention,
per-user pending-state isolation, and canonical date-range query arguments.

# Period Profit before COGS

Added:

- `tests/test_period_profit_pre_cogs_mode.py`

Covers the separate menu and period picker, explicit incomplete-result contract,
missing-cost independence, request-local cost exclusion, custom dates, and per-user
pending-state isolation.

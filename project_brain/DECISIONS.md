# Architecture Decisions


## Decision 001

Date:

2026-08-13


Topic:

Service architecture


Decision:


Проект строится как набор независимых сервисов.


Причина:


Упрощение тестирования и расширения.


---


## Decision 002


Topic:

Dependency Injection


Decision:


Все сервисы получают зависимости через constructor injection.


Причина:


Уменьшение связанности.


---


## Decision 003


Topic:

Task based execution


Decision:


Бизнес-логика выполняется через задачи и действия.


Причина:


Поддержка:


- истории
- статусов
- повторов
- контроля выполнения



---


## Decision 004


Topic:

AI development workflow


Decision:


Разработка ведётся через Project Brain.


Каждое изменение сопровождается:


- тестом
- документацией
- обновлением состояния проекта



---


## Decision 005


Date:

2026-08-14


Topic:

Feedback and Memory Loop


Decision:


Опыт выполнения задач сохраняется через цепочку:


Execution

↓

Feedback

↓

Memory


Причина:


Агент должен не только выполнять действия,
но и накапливать опыт для будущих решений.



Результат:


Добавлены:


- Feedback Service
- Memory Service
- Feedback → Memory integration
- сохранение опыта выполнения



---


## Decision 006


Date:

2026-08-14


Topic:

Memory-aware Planning


Decision:


Планирование должно учитывать предыдущий опыт агента.


Архитектура:


Memory

↓

Planning

↓

Action Generation


Причина:


Прошлый опыт должен улучшать будущие планы,
а не просто храниться как история.



Результат:


Добавлены:


- memory lookup
- memory context in planning
- memory-guided action generation



---



## Decision 007


Date:

2026-08-14


Topic:

Project Brain as project memory


Decision:


Состояние проекта должно храниться в документации и Git,
а не только в контексте текущего диалога.


Причина:


Предотвращение потери контекста и documentation drift.


Правило:


Каждый значимый этап разработки должен фиксироваться:


- CURRENT_STATE.md
- ROADMAP.md
- CHANGELOG.md
- DECISIONS.md


Статус:


Implemented



---


## Decision 008


Date:

2026-08-14


Topic:

AI Development Agent purpose


Decision:


AI Development Agent является внутренним инструментом
ускорения разработки AI Business Assistant.


Главный продукт проекта:


AI Business Assistant


AI Development Agent используется для:


- уменьшения ручных действий при разработке
- ускорения создания новых возможностей
- автоматизации тестирования
- поддержания Project Brain
- контроля документационного drift


Причина:


Основная ценность проекта заключается в создании
AI Business Assistant для управления бизнесом.


Автоматизация разработки необходима для ускорения
создания и улучшения основного продукта.


Архитектура:


AI Development Agent

↓

Project Brain

↓

Development Workflow

↓

AI Business Assistant


Статус:


Implemented



---



## Decision 009


Date:

2026-08-14


Topic:

Development Autopilot Direction


Decision:


AI Development Agent развивается как внутренний слой
автоматизации разработки AI Business Assistant.


Архитектура:


AI Development Agent

↓

Development Workflow

↓

AI Business Assistant



Причина:


Создание AI Business Assistant требует большого количества
повторяющихся действий разработки:


- анализ изменений
- обновление документации
- запуск тестов
- подготовка checkpoint


AI Development Agent должен уменьшать ручное участие разработчика
и ускорять развитие основного продукта.



Результат:


Добавлены в roadmap:


- Change impact analysis
- Documentation drift detection
- Automated development workflow
- Git checkpoint assistant



Следующий этап:


Development Autopilot v0.1



---



## Decision 010


Date:

2026-08-14


Topic:

Change Impact Analysis


Decision:


Перед изменением кода AI Development Agent
обязан анализировать влияние изменения
на архитектуру, тесты и документацию.


Архитектура:


File Change

↓

Impact Analyzer

↓

Affected Components

↓

Test Map

↓

Documentation Update



Причина:


Изменение одного сервиса может влиять
на несколько слоёв системы.


Анализ влияния должен уменьшить риск
регрессий и потери архитектурного контекста.



Результат:


Создаётся первый компонент Development Autopilot:


- Change Impact Analysis Service



---



## Decision 011


Date:

2026-08-18


Topic:

Documentation Automation Layer


Decision:


AI Development Agent получает отдельный слой
автоматизации управления документацией проекта.


Архитектура:


AI Development Agent

↓

Documentation Manager

↓

Project Brain


Причина:


Изменения в коде требуют синхронного обновления:

- CURRENT_STATE.md
- CHANGELOG.md
- TEST_MAP.md
- DECISIONS.md


Ручное обновление документации приводит
к риску documentation drift.


Правило:


CHANGELOG.md работает в режиме append only.


Исторические записи не изменяются
и не удаляются.


Результат:


Создаётся основа для:

- автоматического обновления Project Brain
- контроля документационного состояния
- уменьшения ручного участия разработчика


Следующий этап:


AssistantDocumentationManager

---

## Decision 012


Date:

2026-08-18


Topic:

Automated Development Workflow


Decision:


AI Development Agent получает слой
автоматизации полного цикла разработки.


Архитектура:


Change Detection

↓

Change Impact Analysis

↓

Test Execution

↓

Documentation Update

↓

Git Checkpoint



Причина:


Развитие AI Business Assistant требует
уменьшения ручных действий разработчика:


- анализ изменений
- запуск тестов
- обновление Project Brain
- подготовка checkpoint


Development Autopilot должен объединять
существующие инструменты в единый workflow.



Результат:


Создаётся основа:

- Automated Development Workflow
- автоматической проверки изменений
- подготовки Git checkpoint


Следующий этап:


AssistantDevelopmentWorkflowService


---

## Decision 013


Date:

2026-08-18


Topic:

Git Checkpoint Assistant


Decision:


AI Development Agent получает слой
подготовки Git checkpoint в рамках
Automated Development Workflow.


Архитектура:


Development Workflow

↓

Git Checkpoint Assistant

↓

Commit Preparation


Причина:


Завершение цикла разработки требует
контролируемой фиксации изменений.


Git Checkpoint Assistant должен:


- анализировать состояние изменений
- определять изменённые файлы
- подготавливать commit message
- подтверждать готовность checkpoint


Правило:


Git операции должны выполняться
контролируемо и прозрачно.


Автоматический commit без проверки
состояния проекта запрещён.


Результат:


Создаётся основа для:

- автоматической подготовки checkpoint
- безопасной фиксации изменений
- интеграции Git workflow в Development Autopilot


Следующий этап:


AssistantGitCheckpointService

---

## Decision 014


Date:

2026-08-18


Topic:

Development Autopilot Agent Integration


Decision:


AI Development Agent получает
единый управляющий слой,
который объединяет существующие
Development Autopilot сервисы.


Архитектура:


User Task

↓

AssistantDevelopmentAgent

↓

Development Workflow

↓

Service Pipeline

↓

Development Report



Причина:


Текущие сервисы реализуют отдельные
этапы разработки, но требуют
единого координатора.


Development Agent должен управлять
полным циклом:


- анализ изменения
- проверка тестов
- проверка документации
- подготовка checkpoint



Результат:


Создаётся первый слой
автономного Development Agent.


Следующий этап:


AssistantDevelopmentAgent

---

## Decision 015


Date:

2026-08-18


Topic:

Agent Managed Project Brain Synchronization


Decision:


AI Development Agent получает отдельный слой
управления Project Brain.


Архитектура:


AssistantDevelopmentAgent

↓

AssistantProjectBrainManager

↓

Project Brain


↓

- CHANGELOG.md
- CURRENT_STATE.md
- TEST_MAP.md
- DECISIONS.md



Причина:


Ручное обновление документации ограничивает
автономность Development Agent.


Project Brain должен обновляться
как часть автоматического development workflow.



Правило:


Критические архитектурные решения
фиксируются через DECISIONS.md.


Операционные изменения проекта
могут обновляться автоматически
через AssistantProjectBrainManager.



Результат:


Создаётся основа для:

- автоматической синхронизации документации
- уменьшения ручных действий разработчика
- автономного развития Project Brain



Следующий этап:


AssistantProjectBrainManager

---

## Decision 016


Date:

2026-08-18


Topic:

Agent Workflow Execution Loop


Decision:


AI Development Agent получает
исполняющий цикл workflow,
который связывает существующие
Development Autopilot сервисы.


Архитектура:


User Task

↓

AssistantDevelopmentAgent

↓

Development Workflow Execution

↓

Service Pipeline

↓

Development Report



Причина:


Наличие отдельных сервисов недостаточно
для автономной разработки.


Agent должен уметь координировать
выполнение последовательности действий.



Workflow включает:


- анализ изменений
- проверку состояния проекта
- синхронизацию Project Brain
- подготовку Git checkpoint



Правило:


Agent выполняет только
контролируемые операции.


Каждый этап workflow должен
возвращать проверяемый результат.



Результат:


Создаётся первый исполнительный цикл
Development Autopilot.


Historical Next Step:


Agent Workflow Integration


Status:

Superseded by Decision 017

---

## Decision 017


Date:

2026-08-19


Topic:

GPT GitHub Development Workflow


Decision:

Development Infrastructure
переориентируется с автономного
исполнения задач на поддержку
разработки AI Assistant через
GPT + GitHub workflow.


Architecture:


Developer

↓

GPT

↓

GitHub Repository

↓

Tests

↓

Project Brain Update

↓

Review


Rules:

- Project Brain является источником контекста проекта
- GPT должен изучать документацию перед изменениями
- Кодовые изменения должны сопровождаться тестами
- Документация обновляется вместе с функционалом
- Архитектурные решения фиксируются отдельно


Reason:

Использование внешнего GPT через GitHub
позволяет ускорить разработку основного
AI Assistant проекта без создания отдельного
автономного разработчика.


Result:

Development Infrastructure становится
инструментом ускорения разработки
AI Assistant.

---

## Decision 018

Date:

2026-08-28

Topic:

Product Decision Memory

Decision:

История бизнес-решений по товарам хранится отдельно от технической
`product_memory` и общей памяти задач.

Architecture:

ProductBusinessDecisionQueryService

↓

ProductDecisionHistoryService

↓

ProductDecisionHistoryStorageService

Rules:

- сохраняются только успешные решения;
- первая запись является базовой точкой;
- новая запись создаётся только при изменении типа решения или приоритета;
- история ограничена 50 записями на артикул;
- память не влияет на решение и не запускает действия;
- путь хранилища передаётся через dependency injection.

Reason:

Развитие рекомендаций требует наблюдаемой истории изменений, но смешивание
её с техническими метриками товара или task memory нарушило бы границы
ответственности существующих компонентов.

Status:

Implemented

---

## Decision 019

Date:

2026-08-28

Topic:

Manual Product Decision Feedback

Decision:

Пользовательская оценка рекомендации сохраняется как атрибут последнего
снимка решения, а не как новое бизнес-решение или выполненное действие.

Allowed signals:

- USEFUL
- NOT_RELEVANT

Rules:

- feedback доступен только при наличии сохранённого решения;
- повторная одинаковая оценка идемпотентна;
- неизвестные значения отклоняются;
- feedback не изменяет правила, confidence или priority;
- feedback не запускает автоматические действия.

Reason:

Для обучения требуется явный пользовательский сигнал, но влияние такого
сигнала на рекомендации допустимо только после накопления и проверки
исторических результатов.

Status:

Implemented

---

## Decision 020

Date:

2026-08-28

Topic:

Product Decision Outcome Correlation

Decision:

После feedback следующее изменение решения получает наблюдаемый outcome по
изменению уровня срочности.

Outcomes:

- PRIORITY_DECREASED
- PRIORITY_INCREASED
- DECISION_CHANGED

Rules:

- outcome создаётся только при наличии feedback у предыдущего решения;
- сравнивается приоритет предыдущего и нового решения;
- одинаковый приоритет считается нейтральной сменой решения;
- outcome не влияет на будущие решения;
- пользовательский интерфейс не утверждает причинную связь.

Reason:

Связь обратной связи с последующим состоянием создаёт основу для обучения,
но текущих данных недостаточно, чтобы считать изменение следствием принятой
рекомендации или действия пользователя.

Status:

Implemented

---

## Decision 021

Date:

2026-08-28

Topic:

Safe Product Action Proposals

Decision:

Следующий шаг по товарному решению формируется отдельным proposal-service и
остаётся read-only до появления отдельного подтверждённого workflow.

Rules:

- все proposals имеют execution_allowed=False;
- операционные проверки требуют ручного подтверждения;
- monitoring-only не считается обязательным действием;
- количество пополнения и изменение цены не рассчитываются без политики;
- proposal-service не зависит от Action Executor;
- Telegram отображает proposal, но не выполняет его.

Reason:

Ассистент должен давать конкретный следующий шаг, сохраняя границу между
рекомендацией и изменением реального бизнеса.

Status:

Implemented

---

## Decision 022

Date:

2026-08-28

Topic:

Product Action Proposal Confirmation

Decision:

Подтверждение или отклонение proposal сохраняет намерение пользователя в
последнем снимке решения, но не является разрешением на выполнение действия.

Rules:

- подтверждается только proposal, соответствующий последнему решению;
- устаревший proposal отклоняется;
- повторный одинаковый статус идемпотентен;
- monitoring-only не подтверждается как операционное действие;
- любой результат содержит executed=False и execution_allowed=False;
- Action Executor и внешние API отсутствуют в confirmation workflow.

Reason:

Это позволяет собрать управляемую очередь намерений и проверить UX до
появления политик количества, цены, полномочий и отдельного безопасного
исполнителя.

Status:

Implemented

---

## Decision 023

Date:

2026-08-28

Topic:

Confirmed Product Task Drafts

Decision:

Подтверждённый proposal создаёт отдельный постоянный черновик задачи,
привязанный к конкретному снимку решения. Черновик не является задачей
существующего исполнительного контура.

Rules:

- ключ черновика включает артикул, тип proposal и время снимка решения;
- повторное подтверждение не создаёт дубликат;
- отклонение закрывает соответствующий черновик;
- черновик не содержит придуманного количества или новой цены;
- execution_allowed=False и executed=False сохраняются всегда;
- ProductActionTaskDraftService не зависит от Action Executor и Ozon API.

Reason:

Отдельный read-only слой позволяет накапливать подтверждённые намерения и
проверять их качество до проектирования полномочий, бизнес-политик и
исполнительного workflow.

Status:

Implemented

---

## Decision 024

Date:

2026-08-28

Topic:

Product Task Draft Review Lifecycle

Decision:

Черновик автоматически устаревает, если его снимок решения или actionable
proposal больше не совпадает с текущим решением товара. Пользователь может
перевести черновик в терминальный архив.

States:

- DRAFT — актуальный черновик для дальнейшей подготовки;
- STALE — исходное решение изменилось;
- DISMISSED — пользователь отклонил proposal;
- ARCHIVED — пользователь завершил работу с черновиком.

Rules:

- reconcile выполняется только в read/decision pipeline;
- архивирование идемпотентно;
- ARCHIVED не открывается повторным подтверждением той же карточки;
- старые записи получают компактный draft_id без потери данных;
- любое изменение lifecycle возвращает executed=False;
- lifecycle не зависит от Action Executor и внешних API.

Reason:

Черновики должны оставаться проверяемой очередью намерений, а не бесконечно
активными рекомендациями после изменения исходных данных.

Status:

Implemented

---

## Decision 025

Date:

2026-08-28

Topic:

Product Draft Review Queue Prioritization

Decision:

Приоритет очереди проверки рассчитывается отдельным детерминированным
read-service и не сохраняется как новое бизнес-решение.

Scoring order:

- актуальность черновика;
- приоритет исходного решения товара;
- тип ручной проверки;
- при равном score более старый черновик показывается первым.

Rules:

- в очередь входят только DRAFT и STALE;
- DISMISSED и ARCHIVED исключаются;
- каждый элемент содержит score, категорию и коды причин;
- presentation переводит причины, но не меняет формулу;
- приоритизация не меняет lifecycle и всегда executed=False;
- сервис не зависит от Action Executor и Ozon API.

Reason:

Пользователю нужна ограниченная и объяснимая очередь проверки, при этом
техническая сортировка не должна становиться скрытым автоматическим решением.

Status:

Implemented

---

## Decision 026

Date:

2026-08-28

Topic:

Product Task Draft Detail and Audit Trail

Decision:

Каждый новый черновик хранит append-only журнал фактических lifecycle
переходов и доступен через отдельную read-only карточку Telegram.

Audited events:

- CREATED;
- REOPENED;
- MARKED_STALE;
- DISMISSED;
- ARCHIVED.

Rules:

- событие добавляется только при реальном изменении состояния;
- idempotent-команда не создаёт новое событие;
- событие хранит источник, время, старый и новый статус;
- старым записям не создаётся вымышленная история;
- карточка показывает source metrics, но не рассчитывает новое решение;
- каждое событие и detail-result сохраняют executed=False.

Reason:

До дальнейшего развития автономности пользователь должен иметь возможность
проверить происхождение черновика и каждый переход его состояния.

Status:

Implemented

---

## Decision 027

Date:

2026-08-28

Topic:

Product Task Draft Readiness Checklist

Decision:

Готовность к ручной проверке и готовность к исполнению являются разными
состояниями. Полный factual checklist не разрешает выполнение действия.

Rules:

- factual checks зависят от типа proposal;
- нулевое значение считается доступным фактом, None — отсутствующим;
- STALE, DISMISSED и ARCHIVED не готовы к актуальной ручной проверке;
- missing facts отображаются без экстраполяции;
- execution_ready всегда False;
- execution blockers включают неподключённый workflow и отсутствующие
  бизнес-политики количества, срока поставки, цены или целевой маржи;
- checklist не меняет decision, draft lifecycle или review score.

Reason:

Даже качественные входные данные не заменяют утверждённые бизнес-правила и
явно спроектированный исполнительный контур.

Status:

Implemented


---

## Decision 028

Date:

2026-08-30

Topic:

Unknown Advertising Financial Evidence

Decision:

Отсутствие подтверждённого значения рекламных расходов не эквивалентно
нулевым расходам.

Rules:

- `advertising_cost=None` означает отсутствие evidence и сохраняется как unknown;
- только явно переданный `advertising_cost=0` означает подтверждённый ноль;
- при unknown advertising `business_profit` и `margin_percent` не рассчитываются;
- revenue и gross profit могут оставаться доступными как отдельные факты;
- presentation не превращает unknown financial values в `0`;
- отсутствие advertising evidence не является ошибкой внешнего API и не
  запускает автоматическое получение/классификацию данных;
- никакое seller/business execution из этого состояния не разрешается.

Reason:

Оптимистичная подстановка нулевой рекламы завышает финансовый результат и
смешивает отсутствие evidence с фактическим нулём. Финансовые выводы должны
быть fail-closed и evidence-bound.

Status:

Implemented


---

## Decision 029

Date:

2026-08-30

Topic:

Finance Context Evidence Scope

Decision:

Finance Intelligence context built from StorePeriodProfitService must preserve
the scope of its source evidence and must not promote missing facts to zero.

Rules:

- any explicit error row blocks finance-context aggregation;
- gross_sales and gross_profit are required for every accepted period-profit row;
- malformed, non-finite, boolean or missing required values fail closed;
- explicit numeric zero remains a valid fact;
- FinanceContextProvider preserves its existing output shape;
- Finance Intelligence may classify its own direct derived/caller-provided
  result internally without requiring a new provider context field;
- derived expenses remain revenue minus period gross profit and are described
  only as expenses by available evidence;
- Finance Intelligence must not call PERIOD_GROSS_PROFIT accounting net profit
  or claim that the whole business is profitable;
- no tax, advertising, storage or returns expense is inferred or subtracted
  again in this context layer.

Reason:

The finance recommendation pipeline consumes period gross-profit evidence.
Without explicit scope and fail-closed validation, incomplete payloads can look
like zero-cost facts and seller-facing wording can overstate what the evidence
proves.

Status:

Implemented


---

## Decision 030

Date:

2026-08-30

Topic:

Stock Evidence Availability

Decision:

Отсутствие или неполнота evidence по остаткам не эквивалентна доказанному
`low_stock=False`.

Rules:

- `low_stock=True` создаётся только из конкретных валидных stock + sales facts;
- подтверждённый low-stock action context сохраняет существующую форму;
- при отсутствии dependencies, товаров, периода, stock metrics или sales facts
  action не создаётся и `low_stock=False` сопровождается
  `stock_evidence_available=False`;
- только полностью проверенный no-risk ассортимент получает
  `stock_evidence_available=True`;
- malformed, boolean, non-finite, negative и cross-product evidence fail closed;
- explicit zero sales остаётся валидным фактом;
- общий fallback не утверждает отсутствие критичных проблем при unavailable
  stock evidence;
- availability metadata не разрешает replenishment execution;
- historical AssistantEntryService mode без data dependencies сохраняет
  прежний hardcoded fallback; availability semantics применяются к реально
  подключённому stock data path.

Reason:

Ранее несколько failure/missing-data веток возвращали только
`low_stock=False`, смешивая “риск не найден” с “риск невозможно проверить”.
Это могло создавать ложное clean-state впечатление.

Status:

Implemented


---

## Decision 031

Date:

2026-08-30

Topic:

Sales Evidence Availability

Decision:

Настроенный Sales Intelligence data path не должен превращать отсутствующее,
malformed или partial comparison evidence в подтверждённое
`sales_down=False` или искусственные нулевые метрики.

Rules:

- подтверждённый decline сохраняет существующий `sales_down=True` +
  `sales_context` action payload без нового availability field;
- complete non-decline comparison получает
  `sales_evidence_available=True`;
- unavailable/partial configured sales evidence получает
  `sales_down=False` + `sales_evidence_available=False` и не создаёт sales action;
- missing/malformed `change_percent` не считается 0%;
- malformed profits / period / analytics / comparison payloads fail closed;
- SalesIntelligenceService требует valid revenue и gross_profit;
- business_profit и margin могут оставаться `None`;
- explicit numeric zero остаётся валидным фактом;
- generic fallback не утверждает clean business state при unavailable sales evidence;
- historical AssistantEntryService mode без data dependencies сохраняет старый
  hardcoded fallback;
- availability metadata не является execution authorization.

Reason:

Ранее отсутствующий revenue comparison по default превращался в 0%, а missing
Sales Intelligence metrics могли превращаться в 0. Это смешивало
“нет доказательств” с “стабильно/нулевое значение” и могло подавлять sales action
или создавать ложное clean-state впечатление.

Status:

Implemented

---

## Decision 032

Date:

2026-08-30

Topic:

Marketing Evidence Integrity

Decision:

Marketing recommendation/executor boundaries must not claim analysis or channel
checks without explicit supplied evidence.

Rules:

- `marketing_problem=True` alone is not actionable;
- actionable marketing recommendation requires
  `marketing_evidence_available=True` and non-empty `marketing_context`;
- executor accepts only explicit non-empty string evidence items;
- executor formats provided evidence and does not invent findings;
- missing/malformed evidence returns an error;
- persisted router execution therefore uses the existing FAILED lifecycle;
- evidence availability is not mutation/execution authorization;
- no hidden marketing API fetch or campaign mutation is introduced.

Reason:

The previous executor had no marketing data source but returned completed-looking
claims such as checked channels and found opportunities. That overclaimed runtime
evidence.

Status:

Implemented

---

## Decision 033

Date:

2026-08-30

Topic:

Finance Evidence Availability Propagation

Decision:

Assistant report/recommendation semantics must distinguish unavailable finance
evidence from a verified clean finance state without changing
FinanceContextProvider's established payload.

Rules:

- successful derived finance context marks `finance_evidence_available=True`;
- derived finance failure with non-null period evidence marks
  `finance_evidence_available=False`;
- absent period evidence does not invent a finance availability conclusion;
- explicit incoming finance_context remains authoritative and available;
- `finance_evidence_available=False` suppresses finance recommendation and
  clean-business fallback;
- legacy direct callers with finance_context and no availability metadata remain
  backward compatible;
- availability does not authorize execution.

Reason:

A fail-closed provider result was previously discarded by AssistantEntryService,
allowing verified-safe Sales/Stock evidence plus unavailable Finance evidence to
produce an unsupported “no critical problems” conclusion.

Status:

Implemented

---

## Decision 034

Date:

2026-08-30

Topic:

Business Planner Result Integrity

Decision:

AssistantBusinessPlannerService must preserve downstream failure semantics and
must not convert malformed or failing recommendation/planning/execution/task
results into a successful seller-facing plan.

Rules:

- each consumed boundary result must be a dictionary with exact boolean error;
- explicit error=True is preserved unchanged;
- recommendation success requires a recommendations list;
- planning success requires a plan list;
- Action Plan execution success requires list actions plus a non-boolean,
  non-negative integer count matching len(actions);
- task creation errors are not hidden when the optional task-service path is used;
- malformed boundary payloads fail closed with deterministic non-secret codes;
- general recommendations remain presentation-only and do not enter planning;
- no new executor, mutation, action type or execution permission is introduced.

Reason:

The Business Planner previously could wrap an already fail-closed Action Plan
execution result in a new error=False response, suppressing failure semantics and
presenting an execution-adjacent planning operation as successful.

Status:

Implemented

---

## Decision 035

Date:

2026-08-30

Topic:

Business Flow Result Integrity

Decision:

AssistantBusinessFlowService must preserve downstream failure semantics and must
not present malformed or failing intent/planner/task/execution results as
successful seller-facing operations.

Rules:

- every consumed downstream result must be a dictionary with exact boolean error;
- successful intent requires a non-empty string command;
- explicit downstream error=True remains failure and is not paired with success wording;
- successful current-action execution requires a non-empty message, valid optional
  action fields, boolean completion flag, and valid non-negative progress;
- successful planner output requires list actions and a non-boolean, non-negative
  integer count matching len(actions);
- task lifecycle/read results are validated before success presentation;
- skip validates its target before mutation and validates its post-skip read;
- if skip is already committed and a later read fails, the result reports that
  partial committed state rather than pretending rollback;
- continue validates both next-action lookup and pending-action persistence;
- malformed results use deterministic non-secret fail-closed codes;
- no new executor, action type, mutation path, retry, rollback, or execution
  permission is introduced.

Reason:

The Business Flow previously used optimistic defaults such as error=False and
“Действие выполнено” and could therefore suppress lower-layer failures even after
Action Plan and Business Planner result integrity had been hardened.

Status:

Implemented

---

## Decision 036

Date:

2026-09-03

Topic:

Permanent Read-Only Ozon Analyst Product Boundary

Decision:

AI Business Assistant is a seller-facing analyst and advisor, not an autonomous
executor of Ozon business mutations.

Rules:

- production Ozon integration is read-only from the assistant's product boundary;
- the assistant may analyze seller/business evidence, compare periods, detect
  anomalies, rank priorities, explain reasons, recommend actions and prepare
  non-executable drafts/checklists;
- the assistant must not change prices;
- the assistant must not change advertising budgets, bids or campaign state;
- the assistant must not create replenishment/stock mutations;
- the assistant must not mutate product-card content or other seller state;
- Product Decision confirmation remains stored advisory intent, not execution permission;
- Product Task Draft remains a review artifact and never becomes executable;
- no future package may add Ozon mutation merely by adding authorization or a new
  execution workflow; changing this product boundary requires an explicit product
  decision that supersedes this Decision;
- fail-closed validation must reject execution-adjacent success claims on
  read-only analytical surfaces.

Reason:

The intended product role is an analytical assistant for the seller. Operational
actions on Ozon remain under human control outside the assistant.

Status:

Implemented

---

## Decision 037

Date:

2026-09-03

Topic:

Account-Level Ozon Monetary Authority for Period Profit

Decision:

Period Profit must use the complete account-level Ozon daily accrual result as the
authoritative monetary total for revenue, net accrual and Ozon fee components.
SKU-level finance remains a product-attribution source for unit counts, product
revenue reconciliation, product cost and drill-down, but must not be summed as
the authoritative account monetary total.

Rules:

- production Period Profit reads one account-level finance result per day with
  `sku=None`;
- account-level `gross_sales`, `net_accrual`, commission, logistics, acquiring,
  other fees and fee breakdown are authoritative for the period monetary summary;
- SKU-level finance remains required for product sales counts and COGS attribution;
- summed SKU revenue must reconcile to account-level Ozon revenue within 0.01 RUB;
- revenue mismatch fails closed with
  `PERIOD_PROFIT_PRODUCT_REVENUE_COVERAGE_INCOMPLETE`;
- period tax is calculated from reconciled account-level revenue using the
  configured tax fraction;
- period profit is
  `account_net_accrual - product_cost - tax`;
- the difference between account-level net accrual and summed SKU-attributed
  net accrual is exposed as `ozon_account_reconciliation`;
- that reconciliation may contain account-level operations without SKU and may
  also correct SKU-level duplication from multi-SKU postings;
- account-level Ozon accrual inclusion does not by itself prove complete
  accounting classification of returns, advertising or storage;
- known Ozon account-level monetary operations already included in net accrual
  must never be subtracted a second time;
- accounting net-profit claim remains prohibited until non-Ozon accounting
  adjustments and component completeness are separately established;
- Decision 036 read-only boundary remains unchanged.

Reason:

SKU-filtered daily finance can omit account-level charges without SKU and can
duplicate a posting-level total when one posting contains multiple SKUs. Summing
SKU-level net accruals therefore cannot be the authoritative seller-account
profit source. The account-level Ozon accrual is the safer monetary authority,
while SKU evidence is still needed to prove product revenue coverage and COGS.

Status:

Implemented

---

## Decision 038

Date:

2026-09-03

Topic:

External Operating Expense Evidence and Coverage

Decision:

Period Profit may derive a profit view after seller-recorded expenses outside the
Ozon accrual stream only from explicit local expense rows plus explicit period
coverage evidence.

Rules:

- existing local `expenses` rows remain the source of seller-entered external
  operating expenses;
- expense rows are evidence only when date, category and finite non-negative
  amount are valid;
- a missing expense row is never equivalent to a zero expense;
- explicit `expense_coverage` intervals record seller confirmation that expense
  accounting is complete for those dates;
- coverage for a requested Period Profit interval is complete only when the union
  of confirmed intervals covers every calendar day in the request;
- an empty covered period is an explicit zero-expense fact;
- an empty uncovered period remains unknown;
- partial expense rows may produce an observed profit-after-entered-expenses
  metric, but that metric must be labelled incomplete;
- only complete coverage may produce a complete
  `profit_after_external_expenses` derived value;
- external expenses are outside Ozon account net accrual and therefore may be
  subtracted from the account-level Period Profit exactly once;
- Ozon advertising/storage/return operations already present inside account
  net accrual remain excluded from this external-expense repository to avoid
  double subtraction;
- comparison semantics remain based on the existing Period Profit summary until
  external-expense coverage is proven for both compared periods;
- external expense coverage does not resolve return COGS recovery uncertainty,
  historical cost basis, compensation timing, or other accounting adjustments;
- accounting net-profit claim remains prohibited;
- local expense/coverage persistence is seller evidence input and does not
  authorize or perform any Ozon mutation;
- Decision 036 and Decision 037 remain unchanged.

Reason:

A local expense table without an explicit completeness marker cannot distinguish
"seller had no external expense" from "seller has not entered the expense yet".
Treating both as zero would overstate profit. Explicit coverage intervals make
zero/complete semantics evidence-bound while allowing known partial expenses to
be shown without overstating completeness.

Status:

Implemented

---

## Decision 039

Date:

2026-09-03

Topic:

Versioned Historical Product Cost Evidence

Decision:

Historical product cost used for return COGS evidence must come only from explicit,
effective-dated seller cost versions. The mutable current `product_costs` row is
not historical evidence and must never be backfilled into prior periods by
assumption.

Rules:

- existing `product_costs` remains the current product-cost configuration used
  by existing current calculations;
- a separate append-only `product_cost_history` evidence table stores explicit
  cost versions;
- every historical cost version requires `product_id`, at least one seller/Ozon
  product identifier (`sku` or `offer_id`), finite non-negative cost,
  currency, source and explicit `effective_from` date;
- no migration or automatic backfill from existing current cost rows is allowed;
- a current-cost update without explicit historical evidence does not create a
  historical cost version;
- duplicate versions for the same `product_id + effective_from` are rejected
  rather than silently overwritten;
- historical lookup for a sale date selects the latest explicit version whose
  `effective_from` is not later than that sale date;
- when product identity cannot be resolved uniquely, historical cost evidence is
  ambiguous and remains unconfirmed;
- missing historical cost remains unknown and is never replaced by current cost,
  zero or an inferred earlier value;
- deleting/changing the mutable current cost does not erase append-only historical
  evidence;
- confirmed historical cost may strengthen Return COGS evidence but does not by
  itself authorize COGS recovery or change Period Profit;
- return COGS recovery still requires independent sale-period lineage and
  saleable/restored inventory evidence, with compensation treatment kept
  separate;
- Decision 036 read-only Ozon boundary, Decision 037 monetary authority and
  Decision 038 external-expense contract remain unchanged.

Reason:

A single mutable current cost cannot prove the unit cost that applied when an
earlier sale occurred. Using today's cost for a historical return would create an
accounting claim from an assumption. Explicit effective-dated versions preserve
what the seller actually confirmed, allow future cost changes to be represented,
and keep unknown historical periods fail-closed.

Status:

Implemented

---

## Decision 040

Date:

2026-09-03

Topic:

Explicit Return Inventory Recovery Evidence

Decision:

Saleable/restored inventory recovery for Return COGS must be based on explicit
return-level evidence. Current stock snapshots, stock deltas, or the Returns API
visual placement status are not sufficient by themselves to prove that a returned
unit restored saleable inventory value.

Rules:

- a separate append-only `return_inventory_recovery_history` evidence table
  stores explicit return-level recovery confirmations;
- every evidence row requires exact return_id, posting_number, SKU, positive
  quantity, explicit recovery state, confirmation date and source;
- allowed recovery states are `SALEABLE_RESTORED` and `NON_SALEABLE`;
- absence of a recovery row remains unknown and is never treated as saleable,
  non-saleable or zero-value recovery;
- duplicate `return_id + confirmed_on` versions are rejected rather than
  overwritten;
- all versions for one return_id must preserve posting_number + SKU identity;
  identity drift makes the evidence conflicting and unconfirmed;
- the latest explicit confirmation may describe the current known recovery state,
  but its confirmation date does not by itself establish the accounting period in
  which COGS recovery should be recognized;
- recorded recovery quantity must exactly match the candidate return quantity
  before that candidate may be considered saleable-restored;
- compensated returns remain outside automatic saleable-recovery treatment;
- current Ozon stock observation or a positive stock delta must never be used as
  automatic proof of return recovery because other stock movements can produce the
  same change;
- confirmed saleable inventory recovery may strengthen Return COGS evidence but
  does not by itself authorize Period Profit adjustment;
- period attribution, originating sale quantity consistency and compensation
  accounting must remain independently proven before any COGS reversal;
- Decision 036, Decision 037, Decision 038 and Decision 039 remain unchanged.

Reason:

A stock snapshot shows only current quantity and cannot prove which movement
created it. A return being present at a return location likewise does not prove
that it became saleable inventory. Explicit return-level recovery evidence avoids
turning correlated stock movement into an accounting fact and preserves
fail-closed behavior.

Status:

Implemented


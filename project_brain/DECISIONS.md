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

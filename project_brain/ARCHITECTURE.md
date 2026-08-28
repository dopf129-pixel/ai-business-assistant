# AI Assistant Architecture


## Project


AI Business Assistant


Назначение:


Система автоматизированного бизнес-анализа,
планирования, выполнения действий
и накопления опыта для автономного поведения.



---


# Main Architecture Flow


User

↓

AssistantCoreService

↓

AssistantOrchestratorV2Service

↓

AssistantEntryService

↓

AssistantMainFlowService

↓

AssistantOrchestratorBusinessService

↓

AssistantBusinessFlowService

↓

AssistantBusinessPlannerService

↓

AssistantActionPlanExecutorService

↓

AssistantActionExecutionService

↓

AssistantActionRouterService

↓

Business Executors



---


# Autonomous Agent Flow


Execution

↓

Feedback

↓

Memory

↓

Planning Improvement

↓

Action Generation

↓

Execution



Назначение:


Агент использует результаты прошлых действий
для улучшения будущих решений.



---


# Core Components



## Intent Layer


Ответственность:


- определение намерения пользователя
- перевод текста в команду


Service:


AssistantIntentService



---


## Task Layer


Ответственность:


- создание задач
- управление состояниями
- выполнение шагов
- хранение состояния долгих процессов


Service:


AssistantTaskService


Статусы:


NEW

DONE

PAUSED

CANCELLED

SKIPPED

FAILED



---


## Planning Layer


Ответственность:


Создание и корректировка плана действий
с учётом зависимостей и прошлого опыта.



Components:


- RecommendationService
- PlanningService
- BusinessPlannerService
- ReplanningService



Поддерживает:


- multi-level dependencies
- dependency validation
- automatic replanning
- plan correction
- memory context



---


## Action Layer


Ответственность:


Управление действиями.



Pipeline:


Recommendation

↓

Action Generator

↓

Memory Context

↓

Priority Resolver

↓

Dependency Check

↓

Condition Check

↓

Execution

↓

Feedback

↓

History

↓

Memory



---


# Action Rules


Каждое действие содержит:


title

type

status

priority

depends_on

condition

result



Дополнительно может содержать:


memory_context



---


# Dependency System


Поддерживается:


Action B depends_on Action A


Action B может выполняться только после:


Action A = DONE



Поддерживается:


- multi-level dependencies
- dependency validation
- cycle detection



---


# Condition System


Поддерживается:


condition:


contains



Пример:


Если результат предыдущего действия содержит:


"падение"


тогда действие разрешено.



Если условие не выполнено:


status = SKIPPED


skip_reason сохраняется.



---


# Execution System


Router выбирает исполнителя:


sales

stock

marketing



Каждый executor отвечает
за свой тип действия.



Execution System поддерживает:


- FAILED state
- error storage
- retry execution
- retry policy
- retry limits
- retry blocked history



---


# Feedback System


Ответственность:


Получение результата выполнения
и формирование опыта.



Service:


AssistantFeedbackService



Процесс:


Execution Result

↓

Feedback

↓

Experience



---


# Memory System


Ответственность:


Хранение опыта агента
и использование его в будущих решениях.



Service:


AssistantMemoryService



Поддерживает:


- сохранение опыта
- поиск похожего опыта
- передачу контекста в планирование
- передачу опыта в генерацию действий



---


# History System


История хранит:


- действие
- статус
- результат
- причину пропуска
- ошибки выполнения
- retry события
- feedback события



---


# Project Brain Integration


Разработка управляется через:


- CURRENT_STATE.md
- ROADMAP.md
- TEST_MAP.md
- CHANGELOG.md
- DECISIONS.md



Каждый значимый этап:


1. получает тест

2. обновляет документацию

3. фиксируется в истории изменений



---


# Development Rules


Каждое новое изменение:


1. Новый тест

2. Изменение кода

3. Запуск pytest

4. Обновление документации

5. Архитектурное решение при изменении структуры



---


# Current Test Status


Last known:


49 passed



---


# Current Architecture Level


Task Orchestration Engine

+

Smart Planning

+

Autonomous Agent Foundation

+

AI Development Infrastructure


---


# Product Decision Memory

Flow:

ProductBusinessDecisionQueryService

↓

ProductDecisionHistoryService

↓

ProductDecisionHistoryStorageService

↓

data/product_decision_history.json

Responsibilities:

- persist the first successful decision baseline;
- persist only decision type or priority transitions;
- expose previous decision context to Telegram;
- retain a bounded history per seller article.

The history is observational. It does not modify decision rules and does not
trigger actions.

Feedback flow:

Telegram Decision Card

↓

AssistantButtonHandlerService

↓

ProductDecisionHistoryService.record_feedback

↓

Latest Decision Snapshot

Allowed signals:

- USEFUL
- NOT_RELEVANT

Feedback remains observational until a separate outcome-correlation stage is
implemented and validated.

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

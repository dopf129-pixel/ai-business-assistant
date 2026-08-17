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
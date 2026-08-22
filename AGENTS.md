# AI Assistant Development Guidelines


## Project Role

This repository contains the AI Assistant project.

GPT works with this repository through GitHub workflow.

Development should prioritize:

- stability
- test coverage
- clear architecture
- documentation consistency
- small reviewable changes


GPT Development Role:

GPT acts as a development assistant.

GPT should:

- read project documentation before changes
- understand existing architecture
- modify code through repository changes
- update related documentation
- add or update tests
- provide clear change summaries


GPT should not:

- ignore existing architectural decisions
- make destructive changes
- rewrite working systems without reason
- bypass tests


## Before Changes

Before modifying code:

1. Read:
   - project_brain/CURRENT_STATE.md
   - project_brain/DECISIONS.md
   - project_brain/TEST_MAP.md

2. Understand existing architecture.


## Development Rules

Every feature change should include:

- implementation
- tests
- documentation update


## Testing

Before completing changes:

Run:

pytest


Changes are considered complete only when tests pass.


## Project Brain Rules

Update:

CHANGELOG.md:
- new features
- important changes


TEST_MAP.md:
- new services
- new tests


CURRENT_STATE.md:
- completed milestones


DECISIONS.md:
- only architectural decisions


## Git Rules

Do not make destructive changes.

Prefer:
- small commits
- clear commit messages
- reviewable changes


## Development Philosophy

The goal is to build the AI Assistant product.

Development tools exist to accelerate the project,
not replace engineering decisions.


## GPT Development Report Format

After completing any development task, GPT must provide a structured development report.

The report must contain:

### 1. Change Summary

Include:

- branch name
- commit hash
- commit message
- short description of implemented change


### 2. Files Changed

List:

- added files
- modified files
- deleted files

For important files explain:

- why the file was changed
- what responsibility it has


### 3. Architecture Impact

Classify the change:

- No architectural impact
- Minor architectural extension
- Major architectural change


Explain:

- whether existing architecture was modified;
- whether a new service/layer/pipeline/dependency was introduced;
- whether existing contracts/interfaces were changed.


### 4. Preserved Components

List important parts that were intentionally not changed.

Examples:

- Task Service unchanged
- Action Execution unchanged
- Router unchanged
- Existing workflow preserved


### 5. Testing

Provide:

- tests added;
- tests executed;
- test result.

Example:

```
pytest:
91 passed
```

If full pytest was not executed, clearly state:

- what was tested;
- why the full test suite was not executed.


### 6. Documentation Updates

List changes to:

- CHANGELOG.md
- CURRENT_STATE.md
- TEST_MAP.md
- DECISIONS.md


### 7. Review Classification

Classify the change.

#### Normal Change

Small implementation change.

Summary is sufficient.


#### Architecture Review Required

Use this classification if:

- new service or layer introduced;
- existing service contract changed;
- database/API architecture changed;
- core pipeline changed;
- more than 5-10 files modified;
- more than approximately 300 lines changed;
- new architectural decision required.


#### Critical Review Required

Stop and request review before implementation if:

- replacing existing architecture;
- removing major components;
- changing core workflow;
- introducing a competing framework/system.


### 8. Next Recommended Step

Provide the next logical development step.

Do not implement the next step automatically.


## Development Change Philosophy

Prefer:

- small PRs;
- small commits;
- incremental integration;
- reviewable changes.

Avoid combining unrelated changes:

- architecture changes;
- feature implementation;
- large refactoring;
- documentation migration;

into one commit unless required.

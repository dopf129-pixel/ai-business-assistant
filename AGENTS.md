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
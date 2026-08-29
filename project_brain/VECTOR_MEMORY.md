# Vector Memory v1

## Goal

Add a safe similarity-search memory primitive for the Development Autopilot without introducing an external API dependency or changing business execution behavior.

## Service

`AssistantVectorMemoryService` stores text plus an optional payload and supports cosine-similarity lookup.

The default embedding path is deterministic and local:

- text is tokenized;
- tokens are mapped into a fixed-size vector with SHA-256 hashing;
- vectors are normalized;
- search uses cosine similarity.

This default is intentionally a lightweight local vectorizer, not a claim of semantic understanding.

## Extension contract

A richer embedding provider can be supplied through constructor injection. The provider only needs:

`embed(text) -> sequence of numbers`

This preserves the service API if a real embedding model is selected later.

## Safety and isolation

- no network request is required;
- no OpenAI or other paid embedding API is required;
- stored payloads and returned payloads are deep-copied to prevent caller mutation from changing memory state;
- search is read-only;
- the service does not execute tasks, commit code, change Product Decisions, or call Ozon;
- embedding dimension mismatches fail explicitly instead of silently producing invalid similarity scores.

## v1 scope

This stage provides the vector-memory primitive and its deterministic test contract. It does not automatically replace `AssistantMemoryService` or inject vector lookup into the business assistant's execution loop.

## Validation

`tests/test_vector_memory.py` covers ranking, injected embeddings, limits and thresholds, payload isolation, dimension mismatch, and clear behavior.

Targeted vector-memory tests passed.

The full repository suite was intentionally not rerun for this isolated feature under the reduced full-suite cadence. The previous full regression checkpoint remains `392 passed` from the preceding Self-improvement Cycle stage.

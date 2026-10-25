# Decision 059 — Serialize bot startup with backup snapshots

Bot startup and stopped-instance backup snapshots share a token-scoped operating-system guard in the existing lifecycle state root.

The backup acquires this guard before it checks lifecycle state and holds it until the verified archive is published or the attempt fails. The canonical `BotInstanceLease` acquires the same guard while it obtains the long-lived instance lock and publishes `STARTING`. Both paths fail closed when the other owns the guard; backup also requires lifecycle inspection to report `STOPPED` while holding the guard.

The guard is a transient lock only. It does not change lifecycle metadata, persist credentials, stop a running process, or add a new storage service. This prevents the canonical bot startup path from beginning while backup reads the application files and ensures a backup cannot pass its stopped check immediately before a concurrent start.

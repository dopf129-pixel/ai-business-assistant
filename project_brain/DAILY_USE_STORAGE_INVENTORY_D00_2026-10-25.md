# D00 — storage inventory and backup boundary — 25.10.2026

Status: **DONE / code-path inventory only**. No `.env`, SQLite/JSON seller data,
runtime process state, or API was read. Paths below come from constructors and
factory wiring; actual per-machine presence is intentionally unknown.

## Storage roots

`AI_ASSISTANT_STORAGE_ROOT` is resolved by `services.tenant_storage` for relative
files. When a tenant context is active, most repositories store files under
`<root>/data/tenants/<24-char-sha256-prefix>/`; without the variable, historical
relative paths are resolved from the process working directory. The supported
scripts run with the project directory as working directory. The root environment
value may itself be relative and then resolves from that directory.

The configured root is not a complete inventory of state. The existing application
also retains legacy paths beside or under the project directory, and some services
use only the basename of a path when tenant scope exists.

## Persistent business data included by contract v1

The backup manifest uses two roots: `project` and `storage`. Each entry stores a
root key, relative path, byte length, SHA-256, and storage type; it never stores an
absolute path or tenant owner/client value.

| Area | Project-root candidate | Configured storage-root candidate | Contents |
|---|---|---|---|
| Shared seller accounts | `ozon_assistant.db` | `ozon_assistant.db` | Seller/performance account tables; API credentials are ciphertext and require the separately-held `OZON_CREDENTIAL_MASTER_KEY` |
| Legacy product cost | `ozon_assistant.db` | — | `ProductCostService` opens this relative path directly and does not honor `AI_ASSISTANT_STORAGE_ROOT` |
| Tenant SQLite | `data/tenants/<24hex>/ozon_assistant.db` | `data/tenants/<24hex>/ozon_assistant.db` | Costs, external expenses, saved planning workspace and return-accounting repositories |
| Global legacy state | `data/users.json`, `data/tasks.json`, `data/profiles.json` | Same relative paths | User setup and legacy task/profile state; these constructors do not all use tenant storage |
| Root JSON state | Known app JSON basenames | Same relative paths | actions, assistant memory/session/user memory, conversation history, store reports |
| Tenant/legacy JSON | Known business JSON in `data/`, plus JSON under tenant directories | Same relative paths | tax settings, period-profit mappings, product-decision history, task drafts, action completions, and tenant-local histories |

Discovery is allowlisted and bounded. Under a tenant directory, only regular JSON
and SQLite files with supported names/types are included. Invalid tenant folder
names, path traversal, reparse points/symlinks, unsupported database types, invalid
JSON, and invalid SQLite integrity stop the operation; backup does not silently
skip an unsafe candidate. Temp/lock/quarantine files are not data snapshots.

## Explicitly excluded

- `.env`, API/Telegram/master keys, credentials in plaintext, source code, Git,
  virtualenvs, test fixtures, caches, logs, local reports, diagnostics, temporary
  files, lock files and process-control metadata.
- Runtime CPO/CPC diagnostic artifacts under `.runtime-data`; they are not durable
  business inputs and may contain source-derived details.
- External `PERIOD_PROFIT_MAPPING_REGISTRY_PATH` paths outside the project or
  configured storage root. An override that escapes these approved roots is an
  unsupported external state and must make backup fail before writing an archive.
- Unrecognized binary files. Contract v1 is for JSON and SQLite state only.

## Consistency and restore contract

- A backup is permitted only after the token-bound local bot lifecycle reports
  `STOPPED`; the command does not stop the process itself.
- SQLite uses the backup API and then `integrity_check`, which includes committed
  WAL state visible to SQLite. JSON is parsed and its root type is validated.
- A stopped bot provides a stable per-file snapshot. There is no cross-database
  transaction shared across seller accounts, tenant costs, expenses, and planning;
  the manifest does not claim cross-database transactional consistency.
- Manifest v1 is written last to a temporary archive. Archive checksums and
  database/JSON checks run before atomic publication of the completed `.zip`.
- Restore v1 maps `project/...` and `storage/...` into a new empty destination
  only. It never changes the current storage root, `.env`, running process, or
  original archive. Credential decryption remains a separate result requiring the
  original master key.

## Audit findings and limits

- `ProductCostService` is the main legacy bypass: it reads project-root
  `ozon_assistant.db`; tenant `CostService` uses tenant storage. Both locations
  must be represented separately.
- `OzonAccountRepository` uses a shared DB under the configured root, while tenant
  finance/expense repositories use hashed per-tenant DBs. The backups must include
  both.
- Global user/task/profile files and the mapping registry can stay in project
  `data/` even when `.env` sets `.runtime-data`; a backup of that folder alone is
  incomplete.
- The inventory does not assert which paths exist on the owner's machine. D01
  synthetic tests validate discovery/manifest/SQLite/JSON behavior without reading
  live seller data.

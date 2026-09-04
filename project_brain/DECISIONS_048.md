# Decision 048 — Committed Return COGS May Be Consumed by Read-Only Period Profit

Status: Accepted

Date: 2026-09-04

## Decision

Seller-facing Period Profit may consume a Return COGS recovery only when the exact accounting-recognition version remains application-eligible and has durable exact-once commit evidence.

Application is a read-only calculation, not a business mutation. Every query starts from the current account-level Ozon monetary summary and independently applies the same committed recovery, so repeated queries are idempotent rather than cumulative.

## Required invariants

- account-level Ozon `net_accrual` remains the monetary authority;
- exact recognition/application eligibility must still validate at read time;
- durable exact-once commit evidence is mandatory;
- committed identity, recognition version, accounting date, RUB amount and authorization lineage must reconcile;
- missing or uncommitted recovery is not applied and its adjustment remains `None`, never inferred zero;
- compensation and account-level monetary double counting remain prohibited;
- Ozon/business mutations and automatic recovery execution remain prohibited.

## Tax treatment

Period Profit tax is evaluated through the configured `TaxService` policy:

- `NONE`: tax is zero;
- `USN_INCOME`: tax base remains revenue, so Return COGS recovery does not change tax amount solely by changing profit;
- `USN_INCOME_MINUS_EXPENSES`: committed Return COGS recovery changes the pre-tax profit base and tax is recalculated, while minimum tax on revenue remains enforced.

## Seller-facing integration

After any committed Return COGS application, the final query rebuilds dependent Period Profit outputs, including comparison, external-expense observation, coverage and response text. The existing Telegram runtime therefore receives the final adjusted result rather than a pre-application summary.

## Rationale

Decisions 046 and 047 established explicit no-double-count eligibility and exact-once commitment before monetary application. With those gates in place, seller-facing consumption can now be deterministic, tax-aware, idempotent and read-only without weakening Ozon monetary authority or mutation restrictions.

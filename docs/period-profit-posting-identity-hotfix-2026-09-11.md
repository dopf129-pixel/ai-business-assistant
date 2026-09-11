# Period Profit legacy SKU posting-identity hotfix — 2026-09-11

## Live symptom

After the first legacy-SKU identity recovery was deployed, Telegram Period Profit still failed for finance SKU `3398133813` with:

`Не найдена подтвержденная себестоимость для SKU из финансов Ozon: 3398133813`

The current seller product is `hook-2` with current SKU `3921245627`.

## Root cause

The first recovery path assumed that a historical SKU preserved in Ozon finance would still be present as the SKU on a READ-ONLY FBO posting. That assumption is not reliable. Ozon finance may preserve the historical SKU while the current FBO posting representation already exposes the replacement SKU.

Therefore exact historical-SKU -> FBO `offer_id` lookup can legitimately return no match even though finance and FBO refer to the same posting and seller product.

## Production fix

The recovery remains fail-closed and uses two identity paths in order:

1. Preferred: exact historical finance SKU -> one FBO `offer_id`.
2. Fallback: finance POSTING `unit_number` -> matching FBO `posting_number` -> exactly one current catalog `offer_id` -> exactly one stable `product_id`.

The fallback is accepted only when the posting evidence identifies one current catalog offer. Missing, conflicting, or multi-offer evidence remains unresolved and Period Profit stops rather than guessing.

The exact live regression is covered for historical finance SKU `3398133813`, current `hook-2` SKU `3921245627`, and posting-number identity recovery.

## Cost authority

Posting identity recovery is identity-only. It does not provide a historical cost and does not copy the current `21 ₽` cost backwards into previous dates.

For every historical sale date, the existing effective-cost reconciliation remains authoritative. Historical seller-confirmed cost evidence or an applicable effective operational switch is still required by the downstream accounting path. If that dated evidence is genuinely absent, Period Profit must continue to fail closed.

## Ozon invariant

Ozon remains strictly READ-ONLY. The change only reads finance accruals and FBO posting evidence. No Ozon mutation capability is introduced.

Return COGS, accounting authorization/recognition, commit, and inventory-recovery gates are unchanged.

## Verification evidence

Feature head:

- SHA: `4558a2b364479f9148d76f906bdc8a49c4eb7b40`
- Verify run: `34597924460` — success
- Artifact: `verification-4558a2b364479f9148d76f906bdc8a49c4eb7b40`
- Digest: `sha256:28ba835c90fdffeb8a929acddc1c078aff0a58e1fc7c1fa832344b69173c2e24`

PR #531 synthetic merge:

- Synthetic SHA: `ac12dc51dcef439c40db022b61c70ba91f3f79f8`
- Verify run: `34598030821` — success
- Artifact: `verification-ac12dc51dcef439c40db022b61c70ba91f3f79f8`
- Digest: `sha256:adc919db2b11ac474dd4c1e0035696399672522f52cfe36e70146faeef66d4ef`

Production main after PR #531:

- SHA: `cae584197a44aafea508e8a114711bad9dfd0986`
- Verify run: `34598150629` — success
- Artifact: `verification-cae584197a44aafea508e8a114711bad9dfd0986`
- Digest: `sha256:2420389469bab991302eec1fbda39efef695d951de8c57133f946ab1a4636933`

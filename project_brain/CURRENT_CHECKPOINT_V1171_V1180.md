# CURRENT_CHECKPOINT_V1171_V1180

Date: 2026-09-03

## Telegram Custom Period Date Input

Production package:

`v1171-v1180: Telegram Custom Period Date Input`

Goal:

Allow sellers to request Period Profit for an exact calendar range using familiar `ДД.ММ.ГГГГ` input while preserving ISO compatibility and the permanent read-only Ozon analyst boundary.

## Verified behavior

- `прибыль 01.05.2026 - 03.09.2026` is accepted;
- `прибыль 1.5.2026 - 3.9.2026` is accepted;
- en dash and em dash between dates are accepted;
- existing ISO `YYYY-MM-DD` custom-period input remains supported;
- mixed supported date formats normalize consistently;
- localized dates normalize to ISO before the Period Profit query layer;
- invalid calendar dates fail closed without querying finance;
- incomplete custom-period input fails closed;
- missing-period guidance includes a localized date example;
- explicit custom-period queries bypass the general action/execution flow;
- successful Period Profit responses remain `read_only=True` and `executed=False`.

## Product boundary

Decision 036 remains active and unchanged.

AI Business Assistant is a read-only Ozon analyst and advisor.

No price, advertising, replenishment, product-card or other Ozon seller-state mutation is introduced by this package.

## SHA-bound verification evidence

- entering exact main `fa30bafeecfa9291175e7f1c4ac0ad2c078b4607`: Verify #881, 2071 passed / 0 failed, artifact 9884075851, digest `sha256:8bb0274a95fa48b01e315a2c4a7190fcae33c9a4eee11ebdb3c2db49a2303f72`;
- final feature `62b040e392514bc410b34d82eccb8e0385b9c548`: Verify #884, 2081 passed / 0 failed, artifact 9884220127, digest `sha256:18f9ac90e9a8d05bd01a76db6955afa578c951390018b504cae8374663e185be`;
- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61`: Verify #885, 2081 passed / 0 failed, artifact 9884251146, digest `sha256:04099f259682c0e84daa67dd74d3328081855cf86418b299336c16f38f2b0312`;
- squash main `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`: Verify #886, 2081 passed / 0 failed, artifact 9884281842, digest `sha256:a3f889420b898d65c8ef0f027b199ec6c23ebc8bb345933efe9d74c65b686344`;
- no failed production SHA occurred in this package.

## Next analytical priorities

- seller-facing daily attention summary;
- sales/profit period comparison;
- stock and out-of-stock risk;
- advertising-efficiency analysis from read-only evidence;
- returns/non-buyout impact;
- explainable SKU prioritization.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged by this package.

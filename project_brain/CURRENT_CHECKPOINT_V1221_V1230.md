# CURRENT_CHECKPOINT_V1221_V1230

Date: 2026-09-03

## Period Profit Revenue Share Presentation

Production package:

`v1221-v1230: Period Profit Revenue Share Presentation`

Goal:

Show the percentage of revenue in parentheses next to each main Period Profit monetary line without changing the underlying financial calculation.

## Verified seller-facing behavior

For the validated seller sample:

- Revenue: 1 348 371.10 ₽ (100.00%);
- Ozon net accrual: 752 971.82 ₽ (55.84%);
- Commission: 190 333.00 ₽ (14.12%);
- Logistics: 369 353.19 ₽ (27.39%);
- Acquiring: 15 778.95 ₽ (1.17%);
- Other fees: 19 934.14 ₽ (1.48%);
- Product cost: 361 368.00 ₽ (26.80%);
- Tax: 80 902.27 ₽ (6.00%);
- Profit: 310 701.55 ₽ (23.04%);
- Margin remains 23.04%.

Rules:

- fee lines use their existing absolute monetary presentation and positive deduction share;
- negative profit keeps a negative share of revenue;
- zero revenue suppresses derived shares;
- existing previous-period comparison percentages keep their previous-period meaning.

## Product boundary

Decision 036 remains active and unchanged.

This package changes presentation only.

No finance/tax formula, Ozon mutation, execution permission or return-cost inference is introduced.

## SHA-bound verification

- entering exact main `5cb69fed7bc44fcd5f66a8a004e625bee9993953`: Verify #967, 2121 passed / 0 failed, artifact 9887385716, digest `sha256:d48d11f3c4a478d585466db124b5f032776a76b4b591bac5eadb1fa1e31a7477`;
- final feature `77994ccb67c060f7c01694ac65eea5c8aec24e1d`: Verify #970, 2131 passed / 0 failed, artifact 9887454837, digest `sha256:1d0b3d4481b8c3b7db1574c937f204b5c9bf50b95faa6ad6302d8a3178c5392b`;
- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`: Verify #971, 2131 passed / 0 failed, artifact 9887485384, digest `sha256:a2fdc18398338989d9dffa1a782741d947f2eb0c2e94e623d2f9e121a656dddc`;
- squash main `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`: Verify #972, 2131 passed / 0 failed, artifact 9887518565, digest `sha256:ff0b6adc775f02a7454d785ad4b7815719ca11254e3f67836bf1fc29c17636b9`;
- no failed production SHA occurred in this package.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

# Return Financial Operation Authorization v1

Adds an explicit review decision over a return-operation review candidate.

Supported decisions:

- `AUTHORIZE` — permits only exact-name financial evidence mapping;
- `REJECT` — keeps the mapping blocked.

Even `AUTHORIZE` does not permit a return-profit adjustment and cannot activate itself automatically:

- `returns_profit_adjustment_allowed=False`;
- `automatic_activation_allowed=False`;
- `read_only=True`;
- `executed=False`.

This separates human review of Ozon operation semantics from any future change to the profit formula.

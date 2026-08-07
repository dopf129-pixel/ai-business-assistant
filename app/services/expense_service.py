class ExpenseService:

    def calculate(
        self,
        expenses=None
    ):

        expenses = expenses or []

        total_expenses = 0.0
        valid_expenses = []

        for expense in expenses:

            if not isinstance(
                expense,
                dict
            ):
                continue

            name = str(
                expense.get(
                    "name",
                    "Без названия"
                )
            )

            try:
                amount = float(
                    expense.get(
                        "amount",
                        0
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            if amount < 0:
                continue

            total_expenses += amount

            valid_expenses.append(
                {
                    "name": name,
                    "amount": round(
                        amount,
                        2
                    )
                }
            )

        return {
            "error": False,
            "expenses_count": len(
                valid_expenses
            ),
            "expenses": valid_expenses,
            "other_expenses": round(
                total_expenses,
                2
            )
        }

    def calculate_single(
        self,
        amount=0,
        name="Прочие расходы"
    ):

        try:
            amount = float(
                amount or 0
            )

        except (
            TypeError,
            ValueError
        ):

            return {
                "error": True,
                "message": (
                    "Некорректная сумма расхода"
                )
            }

        if amount < 0:

            return {
                "error": True,
                "message": (
                    "Расход не может быть "
                    "отрицательным"
                )
            }

        return {
            "error": False,
            "expenses_count": (
                1
                if amount > 0
                else 0
            ),
            "expenses": (
                [
                    {
                        "name": str(
                            name
                        ),
                        "amount": round(
                            amount,
                            2
                        )
                    }
                ]
                if amount > 0
                else []
            ),
            "other_expenses": round(
                amount,
                2
            )
        }
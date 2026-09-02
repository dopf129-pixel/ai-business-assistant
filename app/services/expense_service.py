import math


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

            raw_amount = expense.get(
                "amount",
                0
            )

            if isinstance(
                raw_amount,
                bool
            ):
                continue

            try:
                amount = float(
                    raw_amount
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            if (
                not math.isfinite(
                    amount
                )
                or amount < 0
            ):
                continue

            next_total = (
                total_expenses
                + amount
            )

            if not math.isfinite(
                next_total
            ):

                return {
                    "error": True,
                    "message": (
                        "Некорректный итог прочих расходов"
                    )
                }

            total_expenses = (
                next_total
            )

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

        if isinstance(
            amount,
            bool
        ):

            return self._invalid_amount()

        try:
            amount = float(
                amount or 0
            )

        except (
            TypeError,
            ValueError
        ):

            return self._invalid_amount()

        if not math.isfinite(
            amount
        ):

            return self._invalid_amount()

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

    @staticmethod
    def _invalid_amount():

        return {
            "error": True,
            "message": (
                "Некорректная сумма расхода"
            )
        }

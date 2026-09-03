import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.expense_repository import (
    ExpenseRepository,
)


def main():

    repository = ExpenseRepository()

    print("=========================")
    print("Подтверждение учёта расходов")
    print("=========================")
    print()
    print(
        "Подтверждайте период только после того, "
        "как внесли ВСЕ внешние расходы за эти даты."
    )
    print()

    date_from = input(
        "Период с (ГГГГ-ММ-ДД): "
    ).strip()

    date_to = input(
        "Период по (ГГГГ-ММ-ДД): "
    ).strip()

    note = input(
        "Комментарий (необязательно): "
    ).strip()

    result = repository.confirm_coverage(
        date_from=date_from,
        date_to=date_to,
        note=note,
    )

    print()

    if result.get("error"):

        print(
            "Ошибка:",
            result.get(
                "message",
                "Не удалось подтвердить период"
            )
        )

        return

    print("✅ Coverage расходов подтверждён")
    print(
        "Период:",
        result["date_from"],
        "—",
        result["date_to"],
    )

    if result.get("note"):

        print(
            "Комментарий:",
            result["note"],
        )


if __name__ == "__main__":
    main()

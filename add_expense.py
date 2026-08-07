import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.expense_repository import ExpenseRepository


def main():

    repository = ExpenseRepository()

    print("=========================")
    print("Добавление расхода")
    print("=========================")
    print()

    expense_date = input(
        "Дата расхода (ГГГГ-ММ-ДД): "
    ).strip()

    category = input(
        "Категория: "
    ).strip()

    amount = input(
        "Сумма, ₽: "
    ).strip()

    description = input(
        "Описание (необязательно): "
    ).strip()

    result = repository.add_expense(
        expense_date=expense_date,
        category=category,
        amount=amount,
        description=description
    )

    print()

    if result.get("error"):

        print(
            "Ошибка:",
            result.get(
                "message",
                "Не удалось сохранить расход"
            )
        )

        return

    print("✅ Расход сохранён")
    print(
        "ID:",
        result["id"]
    )
    print(
        "Дата:",
        result["expense_date"]
    )
    print(
        "Категория:",
        result["category"]
    )
    print(
        "Сумма:",
        f'{result["amount"]:.2f} ₽'
    )

    if result.get("description"):

        print(
            "Описание:",
            result["description"]
        )


if __name__ == "__main__":
    main()
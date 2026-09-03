import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.return_inventory_recovery_repository import (
    ReturnInventoryRecoveryRepository,
)


def main():

    repository = (
        ReturnInventoryRecoveryRepository()
    )

    return_id = input(
        "Return ID: "
    ).strip()

    posting_number = input(
        "Posting number: "
    ).strip()

    sku = input(
        "SKU: "
    ).strip()

    quantity = input(
        "Количество: "
    ).strip()

    recovery_state = input(
        "Состояние "
        "(SALEABLE_RESTORED/NON_SALEABLE): "
    ).strip()

    confirmed_on = input(
        "Дата подтверждения (YYYY-MM-DD): "
    ).strip()

    result = repository.record_recovery(
        return_id=return_id,
        posting_number=posting_number,
        sku=sku,
        quantity=quantity,
        recovery_state=recovery_state,
        confirmed_on=confirmed_on,
        source="SELLER_CONFIRMED",
    )

    print()

    if result.get("error"):
        print(
            "❌ Recovery evidence не сохранён"
        )
        print(
            result.get("code")
            or "UNKNOWN_ERROR"
        )
        return

    print(
        "✅ Recovery evidence сохранён"
    )
    print(
        "Состояние: "
        + str(
            result.get("recovery_state")
        )
    )
    print(
        "Подтверждено на дату: "
        + str(
            result.get("confirmed_on")
        )
    )


if __name__ == "__main__":
    main()

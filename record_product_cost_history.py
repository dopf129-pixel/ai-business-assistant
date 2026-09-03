import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)

from services.cost_service import ProductCostService


def main():

    service = ProductCostService()

    product_id = input(
        "Product ID: "
    ).strip()

    sku = input(
        "SKU: "
    ).strip()

    offer_id = input(
        "Offer ID: "
    ).strip()

    cost_price = input(
        "Историческая себестоимость, ₽: "
    ).strip()

    effective_from = input(
        "Действует с даты (YYYY-MM-DD): "
    ).strip()

    result = service.record_historical_cost(
        product_id=product_id,
        sku=sku,
        offer_id=offer_id,
        cost_price=cost_price,
        effective_from=effective_from,
        currency="RUB",
        source="SELLER_CONFIRMED",
    )

    print()

    if result.get("error"):
        print(
            "❌ Историческая себестоимость "
            "не сохранена"
        )
        print(
            result.get("code")
            or "UNKNOWN_ERROR"
        )
        return

    print(
        "✅ Историческая себестоимость сохранена"
    )
    print(
        "Действует с: "
        + str(
            result.get("effective_from")
        )
    )


if __name__ == "__main__":
    main()

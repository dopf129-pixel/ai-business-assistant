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
        "Себестоимость, ₽: "
    ).strip()

    service.set_cost(
        product_id=product_id,
        sku=sku,
        offer_id=offer_id,
        cost_price=float(cost_price),
        currency="RUB"
    )

    print()
    print("✅ Себестоимость сохранена")


if __name__ == "__main__":
    main()
import json
import sys
from pathlib import Path


APP_DIR = Path(__file__).parent / "app"

sys.path.insert(
    0,
    str(APP_DIR)
)


from api.ozon_client import OzonClient


PRODUCT_ID = "4108512640"


def main():

    client = OzonClient()

    response = client.get_products()

    if response.get("error"):

        print("Ошибка Ozon API:")
        print(response.get("message"))

        return

    items = (
        response
        .get("result", {})
        .get("items", [])
    )

    for product in items:

        current_id = (
            product.get("product_id")
            or product.get("id")
        )

        if str(current_id) == PRODUCT_ID:

            print(
                json.dumps(
                    product,
                    ensure_ascii=False,
                    indent=4
                )
            )

            return

    print("Товар не найден")


if __name__ == "__main__":
    main()
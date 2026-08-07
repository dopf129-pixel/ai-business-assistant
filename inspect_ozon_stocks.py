import json
import sys
from pathlib import Path

import requests


APP_DIR = Path(__file__).parent / "app"

sys.path.insert(
    0,
    str(APP_DIR)
)

from config import (
    OZON_CLIENT_ID,
    OZON_API_KEY
)


PRODUCT_ID = 4108512640
BASE_URL = "https://api-seller.ozon.ru"


def main():

    url = BASE_URL + "/v4/product/info/stocks"

    headers = {
        "Client-Id": OZON_CLIENT_ID,
        "Api-Key": OZON_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "filter": {
            "product_id": [
                str(PRODUCT_ID)
            ]
        },
        "limit": 100
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        print("HTTP статус:", response.status_code)
        print()

        try:

            data = response.json()

            print(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=4
                )
            )

        except ValueError:

            print(response.text)

    except requests.RequestException as error:

        print("Ошибка запроса:")
        print(error)


if __name__ == "__main__":
    main()
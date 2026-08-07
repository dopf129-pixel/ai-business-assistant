import json
import sys
from datetime import date
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


BASE_URL = "https://api-seller.ozon.ru"


def main():

    today = date.today()

    url = BASE_URL + "/v1/finance/accrual/by-day"

    headers = {
        "Client-Id": OZON_CLIENT_ID,
        "Api-Key": OZON_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "date": today.isoformat()
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(
            "Запрошенная дата:",
            today.isoformat()
        )

        print(
            "HTTP статус:",
            response.status_code
        )

        print()

        try:

            result = response.json()

            print(
                json.dumps(
                    result,
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
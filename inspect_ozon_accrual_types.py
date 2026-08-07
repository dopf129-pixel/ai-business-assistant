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


url = (
    "https://api-seller.ozon.ru"
    "/v1/finance/accrual/types"
)

headers = {
    "Client-Id": OZON_CLIENT_ID,
    "Api-Key": OZON_API_KEY,
    "Content-Type": "application/json"
}

try:

    response = requests.post(
        url,
        headers=headers,
        json={},
        timeout=30
    )

    print(
        "HTTP статус:",
        response.status_code
    )

    try:

        result = response.json()

        Path(
            "accrual_types.json"
        ).write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=4
            ),
            encoding="utf-8"
        )

        print(
            "Ответ сохранён в accrual_types.json"
        )

    except ValueError:

        print(response.text)

except requests.RequestException as error:

    print("Ошибка запроса:")
    print(error)
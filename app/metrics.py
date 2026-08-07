import requests

from config import (
    OZON_CLIENT_ID,
    OZON_API_KEY
)

def get_stocks():

    url = "https://api-seller.ozon.ru/v2/product/info/stocks"

    headers = {
        "Client-Id": OZON_CLIENT_ID,
        "Api-Key": OZON_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "filter": {},
        "limit": 100
    }

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    print()
    print("Ответ Ozon (остатки):")
    print("Код:", response.status_code)
    print(response.text)

    return response.text
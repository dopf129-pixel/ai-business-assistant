import time

import requests

from config import (
    OZON_CLIENT_ID,
    OZON_API_KEY
)


class OzonClient:

    def __init__(self):

        self.client_id = OZON_CLIENT_ID
        self.api_key = OZON_API_KEY

        self.base_url = "https://api-seller.ozon.ru"

    def get_headers(self):

        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def _post(
        self,
        endpoint,
        data,
        timeout=20,
        max_attempts=3
    ):

        if not self.client_id or not self.api_key:

            return {
                "error": True,
                "message": "Нет ключей Ozon API"
            }

        url = self.base_url + endpoint

        for attempt in range(
            1,
            max_attempts + 1
        ):

            try:

                response = requests.post(
                    url,
                    headers=self.get_headers(),
                    json=data,
                    timeout=timeout
                )

                if response.status_code == 429:

                    if attempt >= max_attempts:

                        return {
                            "error": True,
                            "status_code": 429,
                            "message": (
                                "Ozon API: превышен лимит запросов. "
                                "Все попытки исчерпаны."
                            )
                        }

                    retry_after = (
                        response.headers.get(
                            "Retry-After"
                        )
                    )

                    try:

                        wait_seconds = float(
                            retry_after
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        wait_seconds = (
                            2 ** attempt
                        )

                    print(
                        "Ozon API: достигнут лимит запросов."
                    )

                    print(
                        "Повтор через",
                        wait_seconds,
                        "сек."
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                response.raise_for_status()

                return response.json()

            except requests.exceptions.Timeout:

                if attempt >= max_attempts:

                    return {
                        "error": True,
                        "message": (
                            "Ozon API: превышено "
                            "время ожидания"
                        )
                    }

                wait_seconds = (
                    2 ** attempt
                )

                print(
                    "Ozon API: таймаут."
                )

                print(
                    "Повтор через",
                    wait_seconds,
                    "сек."
                )

                time.sleep(
                    wait_seconds
                )

            except requests.exceptions.HTTPError as error:

                message = str(
                    error
                )

                try:

                    response_data = (
                        response.json()
                    )

                    message = (
                        response_data.get(
                            "message",
                            message
                        )
                    )

                except ValueError:
                    pass

                return {
                    "error": True,
                    "status_code": (
                        response.status_code
                    ),
                    "message": message
                }

            except requests.exceptions.RequestException as error:

                if attempt >= max_attempts:

                    return {
                        "error": True,
                        "message": str(
                            error
                        )
                    }

                wait_seconds = (
                    2 ** attempt
                )

                print(
                    "Ozon API: ошибка соединения."
                )

                print(
                    "Повтор через",
                    wait_seconds,
                    "сек."
                )

                time.sleep(
                    wait_seconds
                )

        return {
            "error": True,
            "message": (
                "Ozon API: запрос не выполнен"
            )
        }

    def test_connection(self):

        if not self.client_id or not self.api_key:

            return {
                "status": "error",
                "message": "Нет ключей Ozon API"
            }

        return {
            "status": "ok",
            "message": "Ключи найдены"
        }

    def get_products(
        self,
        limit=100
    ):

        return self._post(
            "/v3/product/list",
            {
                "filter": {},
                "limit": int(
                    limit
                )
            }
        )

    def get_product_info(
        self,
        product_id
    ):

        return self._post(
            "/v3/product/info",
            {
                "product_id": int(
                    product_id
                )
            }
        )

    def get_product_stocks(
        self,
        product_id
    ):

        return self._post(
            "/v4/product/info/stocks",
            {
                "filter": {
                    "product_id": [
                        str(
                            product_id
                        )
                    ]
                },
                "limit": 100
            }
        )

    def get_accruals_by_day(
        self,
        accrual_date
    ):

        return self._post(
            "/v1/finance/accrual/by-day",
            {
                "date": str(
                    accrual_date
                )
            },
            timeout=30,
            max_attempts=3
        )

    def get_accrual_types(self):

        return self._post(
            "/v1/finance/accrual/types",
            {},
            timeout=30,
            max_attempts=3
        )
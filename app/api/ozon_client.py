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
        timeout=20
    ):

        if not self.client_id or not self.api_key:

            return {
                "error": True,
                "message": "Нет ключей Ozon API"
            }

        url = self.base_url + endpoint

        try:

            response = requests.post(
                url,
                headers=self.get_headers(),
                json=data,
                timeout=timeout
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.Timeout:

            return {
                "error": True,
                "message": (
                    "Ozon API: превышено время ожидания"
                )
            }

        except requests.exceptions.HTTPError as error:

            message = str(error)

            try:

                response_data = response.json()

                message = response_data.get(
                    "message",
                    message
                )

            except ValueError:
                pass

            return {
                "error": True,
                "status_code": response.status_code,
                "message": message
            }

        except requests.exceptions.RequestException as error:

            return {
                "error": True,
                "message": str(error)
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
                "limit": int(limit)
            }
        )

    def get_product_info(
        self,
        product_id
    ):

        return self._post(
            "/v3/product/info",
            {
                "product_id": int(product_id)
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
                        str(product_id)
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
                "date": str(accrual_date)
            },
            timeout=30
        )

    def get_accrual_types(self):

        return self._post(
            "/v1/finance/accrual/types",
            {},
            timeout=30
        )
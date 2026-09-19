from datetime import datetime

import time

import requests

from config import (
    OZON_CLIENT_ID,
    OZON_API_KEY
)
from services.period_profit_operation_diagnostics import current_period_profit_trace


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
        max_attempts=3,
        total_timeout=75,
    ):
        trace = current_period_profit_trace()
        started_at = time.monotonic()
        status = "exception"
        try:
            result = self._post_impl(
                endpoint,
                data,
                timeout=timeout,
                max_attempts=max_attempts,
                total_timeout=total_timeout,
            )
            status = (
                str(result.get("code") or result.get("status_code") or "error")
                if isinstance(result, dict) and result.get("error") is True
                else "ok"
            )
            return result
        finally:
            if trace is not None:
                trace.record_ozon_call(
                    endpoint,
                    time.monotonic() - started_at,
                    status,
                )

    def _post_impl(
        self,
        endpoint,
        data,
        timeout=20,
        max_attempts=3,
        total_timeout=75
    ):

        url = self.base_url + endpoint

        # Resolve tenant credentials once per HTTP request.  Tenant-aware
        # properties may read SQLite; calling get_headers() used to resolve
        # client_id and api_key independently on every retry, adding redundant
        # synchronous DB reads to Telegram callbacks.
        client_id = self.client_id
        api_key = self.api_key
        if not client_id or not api_key:
            return {
                "error": True,
                "message": "Нет ключей Ozon API"
            }
        headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json"
        }

        started_at = time.monotonic()

        for attempt in range(
            1,
            max_attempts + 1
        ):

            if (
                total_timeout is not None
                and time.monotonic() - started_at >= float(total_timeout)
            ):
                return {
                    "error": True,
                    "code": "OZON_API_TOTAL_TIMEOUT",
                    "message": "Ozon API: запрос превысил общий лимит ожидания"
                }

            try:

                request_timeout = float(timeout)
                if total_timeout is not None:
                    remaining = float(total_timeout) - (time.monotonic() - started_at)
                    if remaining <= 0:
                        return {
                            "error": True,
                            "code": "OZON_API_TOTAL_TIMEOUT",
                            "message": "Ozon API: запрос превысил общий лимит ожидания"
                        }
                    request_timeout = min(request_timeout, remaining)

                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=request_timeout
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

    def get_product_prices(
        self,
        product_id=None,
        offer_id=None
    ):

        filter_data = {}

        if product_id is not None:
            filter_data["product_id"] = [
                str(product_id)
            ]

        if offer_id is not None:
            filter_data["offer_id"] = [
                str(offer_id)
            ]

        return self._post(
            "/v5/product/info/prices",
            {
                "filter": filter_data,
                "limit": 100
            }
        )

    def get_fbo_postings(
        self,
        since,
        to,
        limit=1000,
        offset=0,
        direction="DESC",
        status=""
    ):

        return self._post(
            "/v2/posting/fbo/list",
            {
                "dir": str(direction),
                "filter": {
                    "since": str(since),
                    "status": str(status),
                    "to": str(to)
                },
                "limit": int(limit),
                "offset": int(offset),
                "translit": False,
                "with": {
                    "analytics_data": False,
                    "financial_data": False
                }
            }
        )

    def get_fbo_posting(self, posting_number):

        return self._post(
            "/v2/posting/fbo/get",
            {
                "posting_number": str(posting_number),
                "translit": False,
                "with": {
                    "analytics_data": False,
                    "financial_data": False
                }
            },
            timeout=30,
            max_attempts=3
        )

    def get_fbs_posting(self, posting_number):

        return self._post(
            "/v3/posting/fbs/get",
            {
                "posting_number": str(posting_number),
                "with": {
                    "analytics_data": False,
                    "barcodes": False,
                    "financial_data": False,
                    "translit": False
                }
            },
            timeout=30,
            max_attempts=3
        )

    def get_realization_posting(self, year, month):

        return self._post(
            "/v1/finance/realization/posting",
            {
                "year": int(year),
                "month": int(month)
            },
            timeout=30,
            max_attempts=3
        )

    def get_returns(
        self,
        offer_id=None,
        return_schema="FBO",
        since=None,
        to=None,
        limit=500,
        last_id=0
    ):

        filter_data = {
            "return_schema": str(return_schema)
        }

        if offer_id is not None:
            filter_data["offer_id"] = str(offer_id)

        if since is not None and to is not None:
            filter_data["visual_status_change_moment"] = {
                "time_from": self._returns_timestamp(
                    since,
                    end_of_day=False
                ),
                "time_to": self._returns_timestamp(
                    to,
                    end_of_day=True
                )
            }

        return self._post(
            "/v1/returns/list",
            {
                "filter": filter_data,
                "limit": int(limit),
                "last_id": int(last_id)
            },
            timeout=30,
            max_attempts=3
        )

    @staticmethod
    def _returns_timestamp(
        value,
        end_of_day=False
    ):

        text = str(value or "").strip()

        try:
            datetime.strptime(
                text,
                "%Y-%m-%d"
            )
        except ValueError:
            return text

        if end_of_day:
            return (
                text
                + "T23:59:59.999999999Z"
            )

        return (
            text
            + "T00:00:00Z"
        )


    def get_fbo_cancel_reasons(self):

        return self._post(
            "/v1/posting/fbo/cancel-reason/list",
            {},
            timeout=30,
            max_attempts=3
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
        accrual_date,
        max_pages=200
    ):

        all_accruals = []
        last_id = ""
        seen_last_ids = set()
        final_response = {}

        for page_number in range(
            1,
            int(max_pages) + 1
        ):
            response = self._post(
                "/v1/finance/accrual/by-day",
                {
                    "date": str(
                        accrual_date
                    ),
                    "last_id": str(
                        last_id
                    )
                },
                timeout=30,
                max_attempts=3
            )

            if not isinstance(
                response,
                dict
            ):
                return {
                    "error": True,
                    "code": (
                        "OZON_FINANCE_ACCRUAL_RESPONSE_INVALID"
                    ),
                    "message": (
                        "Некорректный ответ Ozon "
                        "по начислениям за день"
                    )
                }

            if response.get(
                "error"
            ):
                return response

            accruals = response.get(
                "accruals"
            )
            if not isinstance(
                accruals,
                list
            ):
                return {
                    "error": True,
                    "code": (
                        "OZON_FINANCE_ACCRUAL_RESPONSE_INVALID"
                    ),
                    "message": (
                        "Некорректный ответ Ozon "
                        "по начислениям за день"
                    )
                }

            all_accruals.extend(
                accruals
            )
            final_response = dict(
                response
            )

            next_last_id = str(
                response.get(
                    "last_id"
                )
                or ""
            )

            if not next_last_id:
                final_response[
                    "accruals"
                ] = all_accruals
                final_response[
                    "last_id"
                ] = ""
                final_response[
                    "pages_loaded"
                ] = page_number
                return final_response

            if (
                next_last_id == last_id
                or next_last_id
                in seen_last_ids
            ):
                return {
                    "error": True,
                    "code": (
                        "OZON_FINANCE_ACCRUAL_CURSOR_INVALID"
                    ),
                    "message": (
                        "Некорректная пагинация "
                        "начислений Ozon"
                    )
                }

            seen_last_ids.add(
                next_last_id
            )
            last_id = next_last_id

        return {
            "error": True,
            "code": (
                "OZON_FINANCE_ACCRUAL_PAGE_LIMIT_REACHED"
            ),
            "message": (
                "Не удалось дочитать "
                "начисления Ozon за день"
            )
        }

    def get_accrual_types(self):

        return self._post(
            "/v1/finance/accrual/types",
            {},
            timeout=30,
            max_attempts=3
        )

    def get_accruals_by_postings(self, posting_numbers):
        """Read finance accrual rows for exact posting numbers."""
        return self._post(
            "/v1/finance/accrual/postings",
            {
                "posting_numbers": [
                    str(value)
                    for value in posting_numbers or []
                ]
            },
            timeout=30,
            max_attempts=3
        )

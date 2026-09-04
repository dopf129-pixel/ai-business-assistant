class PeriodProfitReturnSaleQuantityEvidenceService:
    """Read-only FBO posting evidence for originating sale quantity."""

    SUPPORTED_RETURN_SCHEMA = "FBO"

    def __init__(self, ozon_client):
        self.ozon_client = ozon_client

    def analyze(
        self,
        candidate_records,
        return_schema="FBO",
    ):
        schema = str(
            return_schema or ""
        ).strip().upper()
        if schema != self.SUPPORTED_RETURN_SCHEMA:
            return self._unavailable(
                "RETURN_SALE_QUANTITY_SCHEMA_UNSUPPORTED"
            )

        if not isinstance(
            candidate_records,
            list,
        ):
            return self._unavailable(
                "RETURN_SALE_QUANTITY_CANDIDATES_INVALID"
            )

        records = []
        groups = {}
        malformed_candidate_count = 0

        for candidate in candidate_records:
            normalized = self._candidate(
                candidate
            )
            if normalized is None:
                malformed_candidate_count += 1
                continue

            records.append(
                normalized
            )
            key = (
                normalized["posting_number"],
                normalized["sku"],
            )
            group = groups.setdefault(
                key,
                {
                    "posting_number": key[0],
                    "sku": key[1],
                    "candidate_return_quantity": 0,
                    "records": [],
                },
            )
            group[
                "candidate_return_quantity"
            ] += normalized["quantity"]
            group["records"].append(
                normalized
            )

        posting_cache = {}
        confirmed_groups = 0
        exceeding_groups = 0
        missing_groups = 0
        ambiguous_groups = 0
        unavailable_groups = 0

        for key, group in groups.items():
            posting_number, sku = key
            if posting_number not in posting_cache:
                posting_cache[posting_number] = (
                    self._load_posting(
                        posting_number
                    )
                )

            posting = posting_cache[
                posting_number
            ]
            status = posting.get(
                "status"
            )
            sale_quantity = None
            evidence_source = posting.get(
                "source"
            )

            if status != "FBO_POSTING_READY":
                group_status = (
                    "ORIGINATING_SALE_POSTING_UNAVAILABLE"
                )
                unavailable_groups += 1
            else:
                products = posting.get(
                    "products"
                )
                matches = [
                    product
                    for product in products
                    if str(
                        product.get("sku")
                        or ""
                    ).strip()
                    == sku
                ]

                if not matches:
                    group_status = (
                        "ORIGINATING_SALE_PRODUCT_NOT_FOUND"
                    )
                    missing_groups += 1
                elif len(matches) != 1:
                    group_status = (
                        "ORIGINATING_SALE_PRODUCT_AMBIGUOUS"
                    )
                    ambiguous_groups += 1
                else:
                    sale_quantity = self._quantity(
                        matches[0].get(
                            "quantity"
                        )
                    )
                    if sale_quantity is None:
                        group_status = (
                            "ORIGINATING_SALE_QUANTITY_INVALID"
                        )
                        unavailable_groups += 1
                    elif (
                        group[
                            "candidate_return_quantity"
                        ]
                        > sale_quantity
                    ):
                        group_status = (
                            "RETURN_QUANTITY_EXCEEDS_ORIGINATING_SALE"
                        )
                        exceeding_groups += 1
                    else:
                        group_status = (
                            "ORIGINATING_SALE_QUANTITY_CONFIRMED"
                        )
                        confirmed_groups += 1

            for record in group[
                "records"
            ]:
                record[
                    "sale_quantity_evidence_status"
                ] = group_status
                record[
                    "originating_sale_quantity"
                ] = sale_quantity
                record[
                    "candidate_group_return_quantity"
                ] = group[
                    "candidate_return_quantity"
                ]
                record[
                    "sale_quantity_evidence_source"
                ] = evidence_source

        group_count = len(groups)
        quantity_consistency_confirmed = (
            bool(records)
            and malformed_candidate_count == 0
            and group_count > 0
            and confirmed_groups == group_count
        )
        complete = (
            malformed_candidate_count == 0
            and (
                group_count == 0
                or (
                    unavailable_groups == 0
                    and missing_groups == 0
                    and ambiguous_groups == 0
                )
            )
        )

        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_READY"
                if complete
                else "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_PARTIAL"
            ),
            "return_schema": schema,
            "candidate_record_count": len(records),
            "malformed_candidate_record_count": (
                malformed_candidate_count
            ),
            "candidate_group_count": group_count,
            "confirmed_group_count": confirmed_groups,
            "exceeding_group_count": exceeding_groups,
            "missing_group_count": missing_groups,
            "ambiguous_group_count": ambiguous_groups,
            "unavailable_group_count": unavailable_groups,
            "quantity_consistency_confirmed": (
                quantity_consistency_confirmed
            ),
            "records": records,
            "matching_basis": (
                "OZON_FBO_POSTING_NUMBER_AND_SKU_PRODUCT_QUANTITY"
            ),
            "source": "OZON_FBO_POSTING_DETAIL",
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }

    def _load_posting(
        self,
        posting_number,
    ):
        try:
            getter = getattr(
                self.ozon_client,
                "get_fbo_posting",
                None,
            )
            if callable(getter):
                response = getter(
                    posting_number
                )
            else:
                post = getattr(
                    self.ozon_client,
                    "_post",
                    None,
                )
                if not callable(post):
                    return self._posting_unavailable()
                response = post(
                    "/v2/posting/fbo/get",
                    {
                        "posting_number": (
                            posting_number
                        ),
                        "translit": False,
                        "with": {
                            "analytics_data": False,
                            "financial_data": False,
                        },
                    },
                    timeout=30,
                    max_attempts=3,
                )
        except Exception:
            return self._posting_unavailable()

        if (
            not isinstance(response, dict)
            or response.get("error") is True
        ):
            return self._posting_unavailable()

        result = response.get("result")
        if not isinstance(result, dict):
            result = response

        returned_number = str(
            result.get("posting_number")
            or ""
        ).strip()
        products = result.get("products")

        if (
            returned_number != posting_number
            or not isinstance(products, list)
        ):
            return self._posting_unavailable()

        normalized_products = []
        for product in products:
            if not isinstance(product, dict):
                continue
            normalized_products.append({
                "sku": str(
                    product.get("sku")
                    or ""
                ).strip(),
                "quantity": product.get(
                    "quantity"
                ),
                "offer_id": product.get(
                    "offer_id"
                ),
            })

        return {
            "status": "FBO_POSTING_READY",
            "posting_number": returned_number,
            "products": normalized_products,
            "source": "OZON_FBO_POSTING_DETAIL",
        }

    @classmethod
    def _candidate(cls, candidate):
        if not isinstance(candidate, dict):
            return None

        return_id = str(
            candidate.get("return_id")
            or ""
        ).strip()
        posting_number = str(
            candidate.get("posting_number")
            or ""
        ).strip()
        sku = str(
            candidate.get("sku")
            or ""
        ).strip()
        quantity = cls._quantity(
            candidate.get("quantity")
        )

        if (
            not return_id
            or not posting_number
            or not sku
            or quantity is None
        ):
            return None

        return {
            "return_id": return_id,
            "posting_number": posting_number,
            "sku": sku,
            "quantity": quantity,
        }

    @staticmethod
    def _quantity(value):
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        return number

    @staticmethod
    def _posting_unavailable():
        return {
            "status": "FBO_POSTING_UNAVAILABLE",
            "source": "OZON_FBO_POSTING_DETAIL",
        }

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_QUANTITY_EVIDENCE_UNAVAILABLE"
            ),
            "quantity_consistency_confirmed": False,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }

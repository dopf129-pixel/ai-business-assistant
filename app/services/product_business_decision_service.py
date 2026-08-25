class ProductBusinessDecisionService:

    DECISION_REPLENISH_HIGH_PRIORITY = "REPLENISH_HIGH_PRIORITY"
    DECISION_REPLENISH_NORMAL = "REPLENISH_NORMAL"
    DECISION_WATCH_LOW_MARGIN = "WATCH_LOW_MARGIN"
    DECISION_INVESTIGATE_LOW_PROFIT = "INVESTIGATE_LOW_PROFIT"
    DECISION_HOLD_STOCK = "HOLD_STOCK"
    DECISION_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    REASON_DAYS_OF_STOCK_CRITICAL = "DAYS_OF_STOCK_CRITICAL"
    REASON_DAYS_OF_STOCK_LOW = "DAYS_OF_STOCK_LOW"
    REASON_HIGH_SALES_VELOCITY = "HIGH_SALES_VELOCITY"
    REASON_SALES_DECLINING = "SALES_DECLINING"
    REASON_POSITIVE_UNIT_PROFIT = "POSITIVE_UNIT_PROFIT"
    REASON_LOW_UNIT_PROFIT = "LOW_UNIT_PROFIT"
    REASON_NEGATIVE_UNIT_PROFIT = "NEGATIVE_UNIT_PROFIT"
    REASON_LOW_MARGIN = "LOW_MARGIN"
    REASON_ECONOMICS_INCOMPLETE = "ECONOMICS_INCOMPLETE"
    REASON_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"

    PRIORITY_CRITICAL = "CRITICAL"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_NORMAL = "NORMAL"
    PRIORITY_LOW = "LOW"
    PRIORITY_NONE = "NONE"

    CONFIDENCE_HIGH = "HIGH"
    CONFIDENCE_MEDIUM = "MEDIUM"
    CONFIDENCE_LOW = "LOW"

    STOCK_CRITICAL = "CRITICAL"
    STOCK_HIGH = "HIGH"
    STOCK_MEDIUM = "MEDIUM"
    STOCK_LOW = "LOW"

    def __init__(self, low_margin_percent=10.0):
        self.low_margin_percent = float(low_margin_percent)

    def decide(self, product_metrics):
        metrics = dict(product_metrics or {})
        missing_data = self._normalize_missing_data(
            metrics.get("missing_data")
        )

        product_id = metrics.get("product_id")
        sku = metrics.get("sku")

        if self._has_identity_mismatch(missing_data):
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_INSUFFICIENT_DATA,
                priority=self.PRIORITY_NONE,
                reasons=[self.REASON_IDENTITY_MISMATCH],
                confidence=self.CONFIDENCE_LOW,
                missing_data=missing_data
            )

        required_missing = self._required_missing(metrics)

        if required_missing:
            combined_missing = self._merge_missing(
                missing_data,
                required_missing
            )

            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_INSUFFICIENT_DATA,
                priority=self.PRIORITY_NONE,
                reasons=[self.REASON_ECONOMICS_INCOMPLETE],
                confidence=self.CONFIDENCE_LOW,
                missing_data=combined_missing
            )

        profit_per_unit = float(metrics["profit_per_unit"])
        margin_percent = float(metrics["margin_percent"])
        stock_priority = str(metrics["stock_priority"]).upper()
        sales_velocity = float(metrics["sales_velocity"])
        sales_trend = str(metrics.get("sales_trend") or "").upper()

        # Economics safety guard wins over stock urgency.
        if profit_per_unit <= 0:
            profit_reason = (
                self.REASON_NEGATIVE_UNIT_PROFIT
                if profit_per_unit < 0
                else self.REASON_LOW_UNIT_PROFIT
            )
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_INVESTIGATE_LOW_PROFIT,
                priority=self.PRIORITY_HIGH,
                reasons=self._unique_values(
                    self._stock_reasons(stock_priority)
                    + [profit_reason]
                    + self._trend_reasons(sales_trend)
                ),
                confidence=self._confidence(missing_data),
                missing_data=missing_data
            )

        if stock_priority == self.STOCK_CRITICAL:
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_REPLENISH_HIGH_PRIORITY,
                priority=self.PRIORITY_CRITICAL,
                reasons=self._unique_values(
                    [
                        self.REASON_DAYS_OF_STOCK_CRITICAL,
                        self.REASON_POSITIVE_UNIT_PROFIT,
                    ]
                    + self._trend_reasons(sales_trend)
                ),
                confidence=self._confidence(missing_data),
                missing_data=missing_data
            )

        if stock_priority == self.STOCK_HIGH:
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_REPLENISH_NORMAL,
                priority=self.PRIORITY_HIGH,
                reasons=self._unique_values(
                    [
                        self.REASON_DAYS_OF_STOCK_LOW,
                        self.REASON_POSITIVE_UNIT_PROFIT,
                    ]
                    + self._trend_reasons(sales_trend)
                ),
                confidence=self._confidence(missing_data),
                missing_data=missing_data
            )

        if margin_percent < self.low_margin_percent:
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_WATCH_LOW_MARGIN,
                priority=self.PRIORITY_NORMAL,
                reasons=self._unique_values(
                    [
                        self.REASON_LOW_MARGIN,
                        self.REASON_LOW_UNIT_PROFIT,
                    ]
                    + self._trend_reasons(sales_trend)
                ),
                confidence=self._confidence(missing_data),
                missing_data=missing_data
            )

        if stock_priority == self.STOCK_LOW and sales_velocity <= 0:
            return self._result(
                product_id=product_id,
                sku=sku,
                decision_type=self.DECISION_HOLD_STOCK,
                priority=self.PRIORITY_LOW,
                reasons=self._unique_values(
                    [self.REASON_POSITIVE_UNIT_PROFIT]
                    + self._trend_reasons(sales_trend)
                ),
                confidence=self._confidence(missing_data),
                missing_data=missing_data
            )

        return self._result(
            product_id=product_id,
            sku=sku,
            decision_type=self.DECISION_HOLD_STOCK,
            priority=self.PRIORITY_LOW,
            reasons=self._unique_values(
                [self.REASON_POSITIVE_UNIT_PROFIT]
                + self._trend_reasons(sales_trend)
            ),
            confidence=self._confidence(missing_data),
            missing_data=missing_data
        )

    def _required_missing(self, metrics):
        required = (
            "product_id",
            "sku",
            "sales_velocity",
            "current_stock",
            "days_of_stock",
            "stock_priority",
            "profit_per_unit",
            "margin_percent"
        )
        return [
            field
            for field in required
            if metrics.get(field) is None
        ]

    def _stock_reasons(self, stock_priority):
        if stock_priority == self.STOCK_CRITICAL:
            return [self.REASON_DAYS_OF_STOCK_CRITICAL]
        if stock_priority == self.STOCK_HIGH:
            return [self.REASON_DAYS_OF_STOCK_LOW]
        return []

    def _trend_reasons(self, sales_trend):
        if sales_trend in {"DECLINING", "DOWN", "DECREASING"}:
            return [self.REASON_SALES_DECLINING]
        return []

    def _confidence(self, missing_data):
        if not missing_data:
            return self.CONFIDENCE_HIGH
        return self.CONFIDENCE_MEDIUM

    def _has_identity_mismatch(self, missing_data):
        return self.REASON_IDENTITY_MISMATCH in missing_data

    def _normalize_missing_data(self, missing_data):
        return self._unique_values(list(missing_data or []))

    def _merge_missing(self, existing, required):
        return self._unique_values(list(existing) + list(required))

    def _unique_values(self, values):
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def _result(
        self,
        product_id,
        sku,
        decision_type,
        priority,
        reasons,
        confidence,
        missing_data
    ):
        return {
            "product_id": product_id,
            "sku": sku,
            "decision_type": decision_type,
            "priority": priority,
            "reasons": reasons,
            "confidence": confidence,
            "missing_data": list(missing_data)
        }

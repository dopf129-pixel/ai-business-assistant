class StockIntelligenceService:

    def __init__(
        self,
        critical_days=3,
        high_days=7,
        medium_days=14
    ):

        self.critical_days = critical_days
        self.high_days = high_days
        self.medium_days = medium_days

    def analyze(
        self,
        stock_data,
        sales_data,
        period_days
    ):

        if not stock_data or not sales_data:
            return self._missing_data_result(
                stock_data,
                sales_data
            )

        product_id = (
            stock_data.get("product_id")
            or sales_data.get("product_id")
        )

        current_stock = stock_data.get(
            "current_stock"
        )

        sales_count = sales_data.get(
            "sales_count"
        )

        if (
            product_id is None
            or current_stock is None
            or sales_count is None
            or not period_days
            or period_days <= 0
        ):
            return self._missing_data_result(
                stock_data,
                sales_data
            )

        sales_velocity = (
            float(sales_count)
            /
            float(period_days)
        )

        if sales_velocity <= 0:
            return {
                "error": False,
                "product_id": str(product_id),
                "current_stock": current_stock,
                "sales_velocity": 0,
                "days_of_stock": None,
                "priority": "NO_SALES"
            }

        days_of_stock = (
            float(current_stock)
            /
            sales_velocity
        )

        return {
            "error": False,
            "product_id": str(product_id),
            "current_stock": current_stock,
            "sales_velocity": round(
                sales_velocity,
                2
            ),
            "days_of_stock": round(
                days_of_stock,
                2
            ),
            "priority": self._resolve_priority(
                days_of_stock
            )
        }

    def _resolve_priority(
        self,
        days_of_stock
    ):

        if days_of_stock <= self.critical_days:
            return "CRITICAL"

        if days_of_stock <= self.high_days:
            return "HIGH"

        if days_of_stock <= self.medium_days:
            return "MEDIUM"

        return "LOW"

    def _missing_data_result(
        self,
        stock_data,
        sales_data
    ):

        stock_data = stock_data or {}
        sales_data = sales_data or {}

        product_id = (
            stock_data.get("product_id")
            or sales_data.get("product_id")
        )

        return {
            "error": True,
            "product_id": (
                str(product_id)
                if product_id is not None
                else None
            ),
            "current_stock": stock_data.get(
                "current_stock"
            ),
            "sales_velocity": None,
            "days_of_stock": None,
            "priority": "UNKNOWN",
            "message": "Недостаточно данных для анализа остатков"
        }

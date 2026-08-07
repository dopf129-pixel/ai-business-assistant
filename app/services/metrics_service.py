from api.ozon_client import OzonClient


class MetricsService:

    def __init__(self):

        self.ozon = OzonClient()

    def get_product_metrics(
        self,
        product_id
    ):

        products = self.ozon.get_products()

        if products.get("error"):

            return products

        items = (
            products
            .get("result", {})
            .get("items", [])
        )

        for product in items:

            current_id = (
                product.get("product_id")
                or product.get("id")
            )

            if str(current_id) != str(product_id):
                continue

            metrics = dict(product)

            stocks_response = (
                self.ozon
                .get_product_stocks(product_id)
            )

            if stocks_response.get("error"):

                metrics["stocks_error"] = (
                    stocks_response.get(
                        "message",
                        "Не удалось получить остатки"
                    )
                )

                metrics["fbo_present"] = 0
                metrics["fbo_reserved"] = 0
                metrics["fbo_available"] = 0

                return {
                    "product_id": str(product_id),
                    "metrics": metrics
                }

            stock_items = stocks_response.get(
                "items",
                []
            )

            fbo_present = 0
            fbo_reserved = 0

            for stock_item in stock_items:

                stock_product_id = (
                    stock_item.get("product_id")
                )

                if (
                    str(stock_product_id)
                    != str(product_id)
                ):
                    continue

                for stock in stock_item.get(
                    "stocks",
                    []
                ):

                    if stock.get("type") != "fbo":
                        continue

                    fbo_present += int(
                        stock.get("present", 0)
                    )

                    fbo_reserved += int(
                        stock.get("reserved", 0)
                    )

            fbo_available = max(
                0,
                fbo_present - fbo_reserved
            )

            metrics["fbo_present"] = fbo_present
            metrics["fbo_reserved"] = fbo_reserved
            metrics["fbo_available"] = fbo_available

            metrics["has_fbo_stocks"] = (
                fbo_available > 0
            )

            return {
                "product_id": str(product_id),
                "metrics": metrics
            }

        return {
            "product_id": str(product_id),
            "message": "Товар не найден в Ozon",
            "found_items": len(items)
        }
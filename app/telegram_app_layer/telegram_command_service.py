from math import isfinite


class TelegramCommandService:


    def __init__(
        self,
        assistant_adapter,
        cost_service=None,
    ):

        self.assistant_adapter = (
            assistant_adapter
        )

        self.cost_service = cost_service



    def handle(
        self,
        user_id,
        text
    ):


        raw = str(text or "").strip()
        command = raw.lower()


        if command == "/start":

            return (
                self.assistant_adapter
                .get_start_response(
                    user_id
                )
            )



        if command == "/help":

            return {
                "error": False,

                "message": (
                    "Доступные команды:\n"
                    "/start - запуск\n"
                    "/memory - память\n"
                    "/costsku SKU СЕБЕСТОИМОСТЬ - сохранить локальную себестоимость исторического SKU"
                )
            }



        if command == "/memory":

            return (
                self.assistant_adapter
                .handle_button(
                    "memory",
                    user_id
                )
            )


        if command.startswith("/costsku"):
            return self._handle_costsku(raw)


        return None


    def _handle_costsku(self, raw):
        parts = raw.split()
        if len(parts) != 3:
            return self._costsku_usage()

        sku = str(parts[1] or "").strip()
        if not sku:
            return self._costsku_usage()

        try:
            cost = float(str(parts[2]).replace(",", "."))
        except (TypeError, ValueError, OverflowError):
            return self._costsku_usage()

        if not isfinite(cost) or cost < 0:
            return self._costsku_usage()

        if self.cost_service is None:
            return {
                "error": True,
                "message": "Локальное хранилище себестоимости недоступно",
            }

        setter = getattr(self.cost_service, "set_cost", None)
        if not callable(setter):
            return {
                "error": True,
                "message": "Локальное хранилище себестоимости недоступно",
            }

        product_id = "finance-sku:" + sku
        try:
            setter(
                product_id,
                sku,
                sku,
                cost,
                "RUB",
            )
        except Exception:
            return {
                "error": True,
                "message": "Не удалось сохранить локальную себестоимость",
            }

        return {
            "error": False,
            "message": (
                "Себестоимость для SKU "
                + sku
                + " сохранена локально: "
                + self._format_cost(cost)
                + " ₽. Повторите «Прибыль за период»."
            ),
            "sku": sku,
            "cost_price": round(cost, 2),
            "currency": "RUB",
            "seller_confirmed": True,
            "local_only": True,
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _costsku_usage():
        return {
            "error": False,
            "message": (
                "Укажите себестоимость так: /costsku SKU СЕБЕСТОИМОСТЬ. "
                "Например: /costsku 3398133813 450"
            ),
        }

    @staticmethod
    def _format_cost(value):
        rounded = round(float(value), 2)
        if rounded.is_integer():
            return str(int(rounded))
        return ("%.2f" % rounded).rstrip("0").rstrip(".")

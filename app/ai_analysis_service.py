class AIAnalysisService:


    def analyze(
        self,
        product,
        metrics,
        risk,
        health
    ):


        result = {

            "product": product.get(
                "name",
                "unknown"
            ),


            "main_problem": None,

            "reason": None,

            "recommendation": None,

            "forecast": None,

            "strategy": []

        }



        # анализ остатков

        if not metrics.get(
            "has_fbs_stocks",
            False
        ):


            result["main_problem"] = (
                "Нет FBS остатков"
            )


            result["reason"] = (
                "Ограничена скорость доставки "
                "и доступность товара"
            )


            result["recommendation"] = (
                "Подключить FBS"
            )


            result["forecast"] = (
                "При отсутствии изменений "
                "возможна потеря продаж"
            )


            result["strategy"].append(
                "Подключить FBS"
            )



        # анализ скидки

        if not metrics.get(
            "is_discounted",
            False
        ):


            result["strategy"].append(
                "Проверить ценовую стратегию"
            )


            result["strategy"].append(
                "Рассмотреть запуск акции"
            )



        # здоровье товара


        if health < 50:


            result["strategy"].append(
                "Провести глубокий анализ товара"
            )



        # если проблем нет


        if result["main_problem"] is None:


            result["main_problem"] = (
                "Критических проблем нет"
            )


            result["reason"] = (
                "Основные показатели стабильны"
            )


            result["recommendation"] = (
                "Продолжать мониторинг"
            )


            result["forecast"] = (
                "Стабильное состояние"
            )



        return result




    def print_report(
        self,
        analysis
    ):


        print()

        print("==============================")

        print(
            "AI Deep Analysis"
        )

        print("==============================")


        print()

        print(
            "Главная проблема:"
        )

        print(
            analysis["main_problem"]
        )


        print()

        print(
            "Причина:"
        )

        print(
            analysis["reason"]
        )


        print()

        print(
            "Рекомендация:"
        )

        print(
            analysis["recommendation"]
        )


        print()

        print(
            "Прогноз:"
        )

        print(
            analysis["forecast"]
        )


        print()

        print(
            "AI Стратегия:"
        )


        for item in analysis["strategy"]:

            print(
                "- " + item
            )


        print()
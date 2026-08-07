from typing import List, Dict

from config import SELLING_MODEL


class DecisionEngine:

    def __init__(self):
        pass

    def generate(
        self,
        metrics,
        health
    ) -> List[Dict]:

        decisions = []

        #
        # FBS
        #

        if SELLING_MODEL in ("HYBRID", "FBS"):

            if not metrics.get(
                "has_fbs_stocks"
            ):

                decisions.append(

                    {

                        "priority":
                            "Высокий",

                        "action":
                            "Подключить FBS",

                        "reason":
                            "Нет FBS остатков",

                        "impact":
                            "Высокий"

                    }

                )

        #
        # Нет FBO
        #

        if not metrics.get(
            "has_fbo_stocks"
        ):

            decisions.append(

                {

                    "priority":
                        "Высокий",

                    "action":
                        "Пополнить остатки FBO",

                    "reason":
                        "Нет FBO остатков",

                    "impact":
                        "Высокий"

                }

            )

        #
        # Нет скидки
        #

        if not metrics.get(
            "is_discounted"
        ):

            decisions.append(

                {

                    "priority":
                        "Средний",

                    "action":
                        "Рассмотреть запуск акции",

                    "reason":
                        "Нет активной скидки",

                    "impact":
                        "Средний"

                }

            )

        #
        # Плохое здоровье
        #

        if health.get(
            "score",
            100
        ) < 50:

            decisions.append(

                {

                    "priority":
                        "Высокий",

                    "action":
                        "Провести глубокий анализ товара",

                    "reason":
                        "Низкое здоровье товара",

                    "impact":
                        "Высокий"

                }

            )

        #
        # Всё хорошо
        #

        if not decisions:

            decisions.append(

                {

                    "priority":
                        "Низкий",

                    "action":
                        "Продолжать мониторинг",

                    "reason":
                        "Критических проблем нет",

                    "impact":
                        "Низкий"

                }

            )

        return decisions
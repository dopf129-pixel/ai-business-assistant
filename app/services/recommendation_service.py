class RecommendationService:

    def build(
        self,
        insights
    ):

        if not insights:

            return {
                "error": False,
                "recommendations": []
            }


        recommendations = []


        for item in insights:

            recommendations.append(
                {
                    "title": item,
                    "status": "NEW"
                }
            )


        return {
            "error": False,
            "recommendations": recommendations
        }
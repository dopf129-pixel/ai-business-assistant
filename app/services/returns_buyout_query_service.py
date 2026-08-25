class ReturnsBuyoutQueryService:
    """Orchestrate prepared returns/buyout facts into structured analytics."""

    def __init__(self, facts_source, analytics_service):
        self.facts_source = facts_source
        self.analytics_service = analytics_service

    def query(self, sku, since, to):
        facts = self.facts_source.get(
            sku=sku,
            since=since,
            to=to,
        )

        result = self.analytics_service.analyze(facts)

        if result.get("error"):
            return result

        return dict(result)

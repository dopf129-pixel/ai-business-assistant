class ReturnsFinanceAttributionQueryService:
    """Orchestrate returns finance facts into structured analytics."""

    def __init__(self, facts_source, analytics_service):
        self.facts_source = facts_source
        self.analytics_service = analytics_service

    def query(self, sku, finance_sku, since, to):
        facts = self.facts_source.get(
            sku=sku,
            finance_sku=finance_sku,
            since=since,
            to=to,
        )
        return self.analytics_service.analyze(facts)

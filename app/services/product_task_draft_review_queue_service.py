from copy import deepcopy


class ProductTaskDraftReviewQueueService:

    STATUS_SCORES = {
        "DRAFT": 100,
        "STALE": 20,
    }
    SOURCE_PRIORITY_SCORES = {
        "CRITICAL": 40,
        "HIGH": 30,
        "NORMAL": 20,
        "LOW": 10,
        "NONE": 0,
    }
    PROPOSAL_SCORES = {
        "REVIEW_REPLENISHMENT": 15,
        "REVIEW_UNIT_ECONOMICS": 10,
        "REVIEW_MARGIN": 5,
    }

    def prioritize(self, drafts, limit=10):
        items = []
        for source in drafts or []:
            if not isinstance(source, dict):
                continue
            status = str(source.get("status") or "").upper()
            if status not in self.STATUS_SCORES:
                continue
            item = deepcopy(source)
            score, reasons = self._score(item)
            item["review_score"] = score
            item["review_priority"] = self._priority(score)
            item["review_reasons"] = reasons
            item["execution_allowed"] = False
            item["executed"] = False
            items.append(item)

        items.sort(key=self._sort_key)
        limited = items[:max(0, int(limit))]
        priority_counts = {
            "URGENT": 0,
            "HIGH": 0,
            "NORMAL": 0,
            "LOW": 0,
        }
        for item in items:
            priority_counts[item["review_priority"]] += 1
        return {
            "error": False,
            "total_reviewable": len(items),
            "priority_counts": priority_counts,
            "items": limited,
            "executed_count": 0,
        }

    def _score(self, item):
        status = str(item.get("status") or "").upper()
        source_priority = str(item.get("priority") or "NONE").upper()
        proposal_type = str(item.get("proposal_type") or "").upper()
        reasons = [
            "CURRENT_DRAFT" if status == "DRAFT" else "STALE_DRAFT"
        ]
        if source_priority in self.SOURCE_PRIORITY_SCORES:
            reasons.append("SOURCE_PRIORITY_" + source_priority)
        proposal_reason = {
            "REVIEW_REPLENISHMENT": "REPLENISHMENT_REVIEW",
            "REVIEW_UNIT_ECONOMICS": "UNIT_ECONOMICS_REVIEW",
            "REVIEW_MARGIN": "MARGIN_REVIEW",
        }.get(proposal_type)
        if proposal_reason:
            reasons.append(proposal_reason)
        return (
            self.STATUS_SCORES.get(status, 0)
            + self.SOURCE_PRIORITY_SCORES.get(source_priority, 0)
            + self.PROPOSAL_SCORES.get(proposal_type, 0),
            reasons,
        )

    def _priority(self, score):
        if score >= 150:
            return "URGENT"
        if score >= 135:
            return "HIGH"
        if score >= 110:
            return "NORMAL"
        return "LOW"

    def _sort_key(self, item):
        return (
            -int(item.get("review_score") or 0),
            str(item.get("created_at") or ""),
            str(item.get("sku") or ""),
        )

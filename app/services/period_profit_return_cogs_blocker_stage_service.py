class PeriodProfitReturnCogsBlockerStageService:
    """Resolve the first fail-closed Return COGS presentation gate without writes."""

    NONE = "RETURN_COGS_BLOCKER_NONE"
    INVENTORY = "RETURN_COGS_BLOCKER_INVENTORY"
    ACCOUNTING_ATTRIBUTION = "RETURN_COGS_BLOCKER_ACCOUNTING_ATTRIBUTION"
    ACCOUNTING_RECOGNITION = "RETURN_COGS_BLOCKER_ACCOUNTING_RECOGNITION"
    APPLICATION_AUTHORIZATION = "RETURN_COGS_BLOCKER_APPLICATION_AUTHORIZATION"
    APPLICATION_COMMIT = "RETURN_COGS_BLOCKER_APPLICATION_COMMIT"
    FINAL_APPLICATION = "RETURN_COGS_BLOCKER_FINAL_APPLICATION"

    @classmethod
    def resolve(cls, evidence):
        if not isinstance(evidence, dict):
            return cls._result(cls.NONE, [], "RETURN_COGS_EVIDENCE_INVALID")

        candidates = evidence.get("candidate_records")
        if not isinstance(candidates, list) or not candidates:
            return cls._result(cls.NONE, [], None)

        pending_inventory = []
        for row in candidates:
            if not isinstance(row, dict):
                continue
            state = cls._text(row.get("inventory_recovery_state")).upper()
            status = cls._text(row.get("inventory_recovery_evidence_status")).upper()
            if status == "RETURN_INVENTORY_RECOVERY_READY" and state in {
                "NON_SALEABLE",
                "SALEABLE_RESTORED",
            }:
                continue
            pending_inventory.append(row)
        if pending_inventory:
            return cls._result(cls.INVENTORY, pending_inventory, None)

        if (
            "accounting_attribution_evidence_confirmed" in evidence
            and evidence.get("accounting_attribution_evidence_confirmed") is not True
        ):
            return cls._result(cls.ACCOUNTING_ATTRIBUTION, candidates, None)

        if (
            "return_cogs_accounting_recognition_evidence_confirmed" in evidence
            and evidence.get("return_cogs_accounting_recognition_evidence_confirmed") is not True
        ):
            return cls._result(cls.ACCOUNTING_RECOGNITION, candidates, None)

        if (
            "return_cogs_profit_application_eligibility_confirmed" in evidence
            and evidence.get("return_cogs_profit_application_eligibility_confirmed") is not True
        ):
            return cls._result(cls.APPLICATION_AUTHORIZATION, candidates, None)

        if (
            "return_cogs_profit_application_commit_confirmed" in evidence
            and evidence.get("return_cogs_profit_application_commit_confirmed") is not True
        ):
            return cls._result(cls.APPLICATION_COMMIT, candidates, None)

        if (
            "return_cogs_profit_applied" in evidence
            and evidence.get("return_cogs_profit_applied") is not True
        ):
            return cls._result(cls.FINAL_APPLICATION, candidates, None)

        return cls._result(cls.NONE, [], None)

    @staticmethod
    def _result(stage, records, code):
        return {
            "error": code is not None,
            "code": code,
            "stage": stage,
            "blocker_present": stage != "RETURN_COGS_BLOCKER_NONE",
            "records": list(records),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

class PeriodProfitReturnCogsBlockerStageService:
    """Resolve the first fail-closed Return COGS presentation gate without writes."""

    NONE = "RETURN_COGS_BLOCKER_NONE"
    INVENTORY = "RETURN_COGS_BLOCKER_INVENTORY"
    ACCOUNTING_ATTRIBUTION = "RETURN_COGS_BLOCKER_ACCOUNTING_ATTRIBUTION"
    ACCOUNTING_RECOGNITION = "RETURN_COGS_BLOCKER_ACCOUNTING_RECOGNITION"
    APPLICATION_AUTHORIZATION = "RETURN_COGS_BLOCKER_APPLICATION_AUTHORIZATION"
    APPLICATION_COMMIT = "RETURN_COGS_BLOCKER_APPLICATION_COMMIT"
    FINAL_APPLICATION = "RETURN_COGS_BLOCKER_FINAL_APPLICATION"

    ACCOUNTING_READY = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"
    RECOGNITION_READY = "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    APPLICATION_READY = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
    COMMIT_CONFIRMED = "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED"

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
                pending_inventory.append(row)
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

        accounting_status = cls._text(
            evidence.get("accounting_attribution_evidence_status")
        ).upper()
        if (
            accounting_status != cls.ACCOUNTING_READY
            or evidence.get("accounting_attribution_evidence_confirmed") is not True
        ):
            return cls._result(cls.ACCOUNTING_ATTRIBUTION, candidates, None)

        recognition_status = cls._text(
            evidence.get("return_cogs_accounting_recognition_status")
        ).upper()
        if (
            recognition_status != cls.RECOGNITION_READY
            or evidence.get("return_cogs_accounting_recognition_evidence_confirmed")
            is not True
        ):
            return cls._result(cls.ACCOUNTING_RECOGNITION, candidates, None)

        application_status = cls._text(
            evidence.get("return_cogs_profit_application_eligibility_status")
        ).upper()
        if (
            application_status != cls.APPLICATION_READY
            or evidence.get("return_cogs_profit_application_eligibility_confirmed")
            is not True
        ):
            return cls._result(cls.APPLICATION_AUTHORIZATION, candidates, None)

        commit_status = cls._text(
            evidence.get("return_cogs_profit_application_commit_status")
        ).upper()
        if (
            commit_status != cls.COMMIT_CONFIRMED
            or evidence.get("return_cogs_profit_application_commit_confirmed") is not True
        ):
            return cls._result(cls.APPLICATION_COMMIT, candidates, None)

        if evidence.get("return_cogs_profit_applied") is not True:
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

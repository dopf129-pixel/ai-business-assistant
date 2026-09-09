from math import isfinite


class ReturnCogsProfitApplicationCommitLedgerIntegrityService:
    """Read-only reconciliation of durable commits against current upstream evidence."""

    READY = "RETURN_COGS_PROFIT_APPLICATION_COMMIT_LEDGER_INTEGRITY_READY"
    BLOCKED = "RETURN_COGS_PROFIT_APPLICATION_COMMIT_LEDGER_INTEGRITY_BLOCKED"
    UNAVAILABLE = "RETURN_COGS_PROFIT_APPLICATION_COMMIT_LEDGER_INTEGRITY_UNAVAILABLE"
    RECOGNITION_READY = "RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
    AUTHORIZATION_READY = "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY"

    def __init__(self, commit_repository, recognition_repository, authorization_repository):
        self.commit_repository = commit_repository
        self.recognition_repository = recognition_repository
        self.authorization_repository = authorization_repository

    def audit(self):
        loader = getattr(self.commit_repository, "list_commits", None)
        if not callable(loader):
            return self._unavailable("RETURN_COGS_COMMIT_LEDGER_LIST_UNAVAILABLE")
        try:
            ledger = loader()
        except Exception:
            return self._unavailable("RETURN_COGS_COMMIT_LEDGER_LIST_EXCEPTION")
        if not isinstance(ledger, dict) or ledger.get("error") is not False:
            return self._unavailable("RETURN_COGS_COMMIT_LEDGER_LIST_INVALID")
        records = ledger.get("records")
        if not isinstance(records, list):
            return self._unavailable("RETURN_COGS_COMMIT_LEDGER_RECORDS_INVALID")

        issues = []
        checked = []
        seen_recognition = set()
        seen_authorization = set()
        for record in records:
            issue = self._audit_record(record, seen_recognition, seen_authorization)
            if issue:
                issues.append(issue)
            checked.append(self._identity(record))

        return {
            "error": False,
            "status": self.READY if not issues else self.BLOCKED,
            "integrity_confirmed": not issues,
            "commit_count": len(records),
            "checked_identities": checked,
            "issues": issues,
            "issue_count": len(issues),
            "read_only": True,
            "executed": False,
        }

    def _audit_record(self, record, seen_recognition, seen_authorization):
        if not isinstance(record, dict):
            return self._issue(None, "RETURN_COGS_COMMIT_LEDGER_ROW_INVALID")
        identity = self._identity(record)
        recognition_id = self._positive_int(record.get("recognition_history_id"))
        authorization_id = self._positive_int(record.get("authorization_history_id"))
        amount = self._money(record.get("committed_amount"))
        if identity is None or recognition_id is None or authorization_id is None or amount is None:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_ROW_INVALID")
        if recognition_id in seen_recognition:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_DUPLICATE_RECOGNITION")
        if authorization_id in seen_authorization:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_DUPLICATE_AUTHORIZATION")
        seen_recognition.add(recognition_id)
        seen_authorization.add(authorization_id)

        recognition_getter = getattr(self.recognition_repository, "get_latest_recognition", None)
        authorization_getter = getattr(self.authorization_repository, "get_application_authorization", None)
        if not callable(recognition_getter) or not callable(authorization_getter):
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_UPSTREAM_QUERY_UNAVAILABLE")
        try:
            recognition = recognition_getter(*identity)
            authorization = authorization_getter(recognition_id, *identity)
        except Exception:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_UPSTREAM_QUERY_EXCEPTION")
        if not isinstance(recognition, dict) or recognition.get("error") is not False:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_RECOGNITION_UNAVAILABLE")
        if not isinstance(authorization, dict) or authorization.get("error") is not False:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_AUTHORIZATION_UNAVAILABLE")
        if recognition.get("status") != self.RECOGNITION_READY or recognition.get("accounting_recognition_confirmed") is not True:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_RECOGNITION_NOT_CURRENT")
        if self._positive_int(recognition.get("history_id")) != recognition_id:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_RECOGNITION_VERSION_STALE")
        if authorization.get("status") != self.AUTHORIZATION_READY or authorization.get("application_authorization_confirmed") is not True:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_AUTHORIZATION_NOT_CURRENT")
        if self._positive_int(authorization.get("history_id")) != authorization_id:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_AUTHORIZATION_VERSION_STALE")
        if authorization.get("application_already_applied") is not False:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_ALREADY_APPLIED")
        if authorization.get("monetary_authority_non_overlap_confirmed") is not True:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_MONETARY_NON_OVERLAP_REQUIRED")
        if authorization.get("compensation_non_overlap_confirmed") is not True:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_COMPENSATION_NON_OVERLAP_REQUIRED")

        recognized = self._money(recognition.get("recognized_amount"))
        authorized = self._money(authorization.get("authorized_amount"))
        if recognized is None or authorized is None or abs(amount - recognized) > 0.01 or abs(amount - authorized) > 0.01:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_AMOUNT_MISMATCH")
        if str(record.get("currency") or "").upper() != "RUB" or str(recognition.get("currency") or "").upper() != "RUB" or str(authorization.get("currency") or "").upper() != "RUB":
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_CURRENCY_MISMATCH")
        dates = {
            str(record.get("recovery_accounting_date") or ""),
            str(recognition.get("recovery_accounting_date") or ""),
            str(authorization.get("recovery_accounting_date") or ""),
        }
        if "" in dates or len(dates) != 1:
            return self._issue(identity, "RETURN_COGS_COMMIT_LEDGER_ACCOUNTING_DATE_MISMATCH")
        return None

    @staticmethod
    def _issue(identity, code):
        return {
            "return_id": identity[0] if identity else None,
            "posting_number": identity[1] if identity else None,
            "sku": identity[2] if identity else None,
            "code": code,
        }

    @staticmethod
    def _identity(record):
        if not isinstance(record, dict):
            return None
        values = tuple(str(record.get(key) or "").strip() for key in ("return_id", "posting_number", "sku"))
        return values if all(values) else None

    @staticmethod
    def _positive_int(value):
        if isinstance(value, bool):
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _money(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return round(value, 2) if isfinite(value) and value >= 0.0 else None

    @classmethod
    def _unavailable(cls, code):
        return {
            "error": True,
            "code": code,
            "status": cls.UNAVAILABLE,
            "integrity_confirmed": False,
            "commit_count": None,
            "issues": [],
            "issue_count": None,
            "read_only": True,
            "executed": False,
        }

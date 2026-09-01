from copy import deepcopy


VALID_STATUSES = {
    "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED":
        ("CONFIRM_COMPLETED", True),
    "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED":
        ("NOT_COMPLETED", False),
}


class ProductDecisionUserActionCompletionPersistenceService:

    def __init__(self, storage_service):
        self.storage_service = storage_service

    def persist(self, evidence):
        if not isinstance(evidence, dict):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_INPUT_INVALID",
                {},
            )

        source = deepcopy(evidence)

        evidence_id = self._required_string(
            source.get("user_action_completion_evidence_id")
        )
        checklist_id = self._required_string(
            source.get("user_action_checklist_id")
        )
        guidance_id = self._required_string(
            source.get("user_action_guidance_id")
        )
        verification_id = self._required_string(
            source.get("decision_persistence_verification_id")
        )
        application_id = self._required_string(
            source.get("decision_persistence_application_id")
        )
        sku = self._required_string(source.get("sku"))
        item_id = self._required_string(source.get("item_id"))
        instruction = self._required_string(source.get("instruction"))
        verified_recorded_at = self._required_string(
            source.get("verified_recorded_at")
        )
        completion_decision = self._required_string(
            source.get("completion_decision")
        )

        if not all(
            (
                evidence_id,
                checklist_id,
                guidance_id,
                verification_id,
                application_id,
                sku,
                item_id,
                instruction,
                verified_recorded_at,
                completion_decision,
            )
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_CONTEXT_REQUIRED",
                source,
            )

        if (
            checklist_id
            != "product-decision-user-action-checklist:" + guidance_id
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_CHECKLIST_ID_MISMATCH",
                source,
            )

        if (
            guidance_id
            != "product-decision-user-action-guidance:" + verification_id
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_GUIDANCE_ID_MISMATCH",
                source,
            )

        if (
            verification_id
            != "product-decision-persistence-verification:" + application_id
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_VERIFICATION_ID_MISMATCH",
                source,
            )

        if source.get("error") is not False:
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_RESULT_INVALID",
                source,
            )

        expected_completion = VALID_STATUSES.get(source.get("status"))
        if expected_completion is None:
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_STATUS_INVALID",
                source,
            )

        expected_decision, expected_completed = expected_completion
        if (
            completion_decision != expected_decision
            or source.get("user_reported_completed") is not expected_completed
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_DECISION_MISMATCH",
                source,
            )

        if (
            source.get("decision_persistence_verified") is not True
            or source.get("completion_evidence_source") != "USER_REPORT"
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_SOURCE_INVALID",
                source,
            )

        if (
            source.get("externally_verified") is not False
            or source.get("persistent") is not False
            or source.get("checklist_mutated") is not False
            or source.get("ozon_mutation_called") is not False
            or source.get("execution_allowed") is not False
            or source.get("execution_ready") is not False
            or source.get("executed") is not False
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_SAFETY_BOUNDARY_VIOLATION",
                source,
            )

        root_id = (
            "product-decision-user-action-completion-evidence:%s:%s"
            % (checklist_id, item_id)
        )
        revision = source.get("completion_revision")

        if revision is None:
            if evidence_id != root_id:
                return self._blocked(
                    "USER_ACTION_COMPLETION_PERSISTENCE_EVIDENCE_ID_MISMATCH",
                    source,
                )
            supplied_root_id = source.get("completion_evidence_root_id")
            if (
                supplied_root_id is not None
                and self._required_string(supplied_root_id) != root_id
            ):
                return self._blocked(
                    "USER_ACTION_COMPLETION_PERSISTENCE_ROOT_ID_MISMATCH",
                    source,
                )
            normalized_revision = 1
            previous_evidence_id = None
        else:
            if type(revision) is not int or revision < 2:
                return self._blocked(
                    "USER_ACTION_COMPLETION_PERSISTENCE_REVISION_INVALID",
                    source,
                )
            normalized_revision = revision
            supplied_root_id = self._required_string(
                source.get("completion_evidence_root_id")
            )
            previous_evidence_id = self._required_string(
                source.get("previous_user_action_completion_evidence_id")
            )
            expected_evidence_id = "%s:revision:%d" % (
                root_id,
                normalized_revision,
            )
            expected_previous_id = (
                root_id
                if normalized_revision == 2
                else "%s:revision:%d" % (
                    root_id,
                    normalized_revision - 1,
                )
            )
            if (
                source.get("completion_revision_ready") is not True
                or supplied_root_id != root_id
                or evidence_id != expected_evidence_id
                or previous_evidence_id != expected_previous_id
            ):
                return self._blocked(
                    "USER_ACTION_COMPLETION_PERSISTENCE_REVISION_LINEAGE_INVALID",
                    source,
                )

        try:
            records = self.storage_service.load()
        except Exception:
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_READ_FAILED",
                source,
            )

        if not isinstance(records, list) or any(
            not isinstance(item, dict) for item in records
        ):
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_STORAGE_INVALID",
                source,
            )

        existing = next(
            (
                item for item in records
                if item.get("user_action_completion_evidence_id")
                == evidence_id
            ),
            None,
        )
        if existing is not None:
            if existing != source:
                return self._blocked(
                    "USER_ACTION_COMPLETION_PERSISTENCE_ID_CONFLICT",
                    source,
                )
            return self._success(
                source,
                saved=False,
                record_count=len(records),
                root_id=root_id,
                revision=normalized_revision,
                previous_evidence_id=previous_evidence_id,
            )

        records = [deepcopy(item) for item in records]
        records.append(deepcopy(source))
        try:
            saved = self.storage_service.save(records)
        except Exception:
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_WRITE_FAILED",
                source,
            )

        if saved is not True:
            return self._blocked(
                "USER_ACTION_COMPLETION_PERSISTENCE_WRITE_NOT_CONFIRMED",
                source,
            )

        return self._success(
            source,
            saved=True,
            record_count=len(records),
            root_id=root_id,
            revision=normalized_revision,
            previous_evidence_id=previous_evidence_id,
        )

    @staticmethod
    def _success(
        source,
        saved,
        record_count,
        root_id,
        revision,
        previous_evidence_id,
    ):
        return {
            "error": False,
            "status":
                "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED",
            "completion_evidence_root_id": root_id,
            "user_action_completion_evidence_id": source.get(
                "user_action_completion_evidence_id"
            ),
            "previous_user_action_completion_evidence_id":
                previous_evidence_id,
            "user_action_checklist_id": source.get(
                "user_action_checklist_id"
            ),
            "user_action_guidance_id": source.get(
                "user_action_guidance_id"
            ),
            "decision_persistence_verification_id": source.get(
                "decision_persistence_verification_id"
            ),
            "decision_persistence_application_id": source.get(
                "decision_persistence_application_id"
            ),
            "sku": source.get("sku"),
            "verified_recorded_at": source.get("verified_recorded_at"),
            "decision_persistence_verified": True,
            "item_id": source.get("item_id"),
            "instruction": source.get("instruction"),
            "completion_revision": revision,
            "completion_decision": source.get("completion_decision"),
            "user_reported_completed":
                source.get("user_reported_completed") is True,
            "completion_evidence_source": "USER_REPORT",
            "completion_persisted": True,
            "saved": saved,
            "record_count": record_count,
            "externally_verified": False,
            "persistent": True,
            "checklist_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @staticmethod
    def _required_string(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _blocked(code, source):
        safe_source = source if isinstance(source, dict) else {}
        return {
            "error": True,
            "code": code,
            "status":
                "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTENCE_BLOCKED",
            "user_action_completion_evidence_id": safe_source.get(
                "user_action_completion_evidence_id"
            ),
            "user_action_checklist_id": safe_source.get(
                "user_action_checklist_id"
            ),
            "user_action_guidance_id": safe_source.get(
                "user_action_guidance_id"
            ),
            "decision_persistence_verification_id": safe_source.get(
                "decision_persistence_verification_id"
            ),
            "decision_persistence_application_id": safe_source.get(
                "decision_persistence_application_id"
            ),
            "sku": safe_source.get("sku"),
            "verified_recorded_at": None,
            "decision_persistence_verified": False,
            "item_id": safe_source.get("item_id"),
            "completion_revision": None,
            "completion_persisted": False,
            "saved": False,
            "externally_verified": False,
            "persistent": False,
            "checklist_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

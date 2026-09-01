from copy import deepcopy


def build_product_decision_user_action_checklist_status(
    checklist,
    persisted_reports,
):
    if not isinstance(checklist, dict):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_INPUT_INVALID",
            {},
        )

    source = deepcopy(checklist)

    if not isinstance(persisted_reports, list):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_REPORTS_INPUT_INVALID",
            source,
        )

    checklist_id = _required_string(
        source.get("user_action_checklist_id")
    )
    guidance_id = _required_string(
        source.get("user_action_guidance_id")
    )
    verification_id = _required_string(
        source.get("decision_persistence_verification_id")
    )
    application_id = _required_string(
        source.get("decision_persistence_application_id")
    )
    sku = _required_string(source.get("sku"))
    verified_recorded_at = _required_string(
        source.get("verified_recorded_at")
    )

    if not all(
        (
            checklist_id,
            guidance_id,
            verification_id,
            application_id,
            sku,
            verified_recorded_at,
        )
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_CONTEXT_REQUIRED",
            source,
        )

    if (
        checklist_id
        != "product-decision-user-action-checklist:" + guidance_id
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_ID_MISMATCH",
            source,
        )

    if (
        guidance_id
        != "product-decision-user-action-guidance:" + verification_id
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_GUIDANCE_ID_MISMATCH",
            source,
        )

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_VERIFICATION_ID_MISMATCH",
            source,
        )

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY"
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_SOURCE_INVALID",
            source,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_VERIFICATION_REQUIRED",
            source,
        )

    if (
        source.get("externally_verified") is not False
        or source.get("persistent") is not True
        or source.get("completion_recording_allowed") is not False
        or source.get("user_execution_required") is not True
        or source.get("automatic_execution_prohibited") is not True
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_SAFETY_BOUNDARY_VIOLATION",
            source,
        )

    items = source.get("items")
    if not isinstance(items, list) or not items:
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_ITEMS_REQUIRED",
            source,
        )

    item_count = source.get("item_count")
    completed_count = source.get("completed_count")
    if (
        type(item_count) is not int
        or item_count != len(items)
        or type(completed_count) is not int
        or completed_count != 0
    ):
        return _blocked(
            "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID",
            source,
        )

    canonical_items = {}
    ordered_item_ids = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID",
                source,
            )

        item_id = _required_string(item.get("item_id"))
        instruction = _required_string(item.get("instruction"))
        position = item.get("position")

        if (
            item_id is None
            or instruction is None
            or type(position) is not int
            or position != index + 1
            or item.get("completion_source") != "USER"
            or item.get("completed") is not False
        ):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID",
                source,
            )

        if item_id in canonical_items:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_ITEMS_INVALID",
                source,
            )

        canonical_items[item_id] = {
            "instruction": instruction,
            "position": position,
        }
        ordered_item_ids.append(item_id)

    matching_reports = {}

    for raw_report in persisted_reports:
        if not isinstance(raw_report, dict):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_INVALID",
                source,
            )

        report = deepcopy(raw_report)
        report_checklist_id = _required_string(
            report.get("user_action_checklist_id")
        )

        if report_checklist_id is None:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_INVALID",
                source,
            )

        if report_checklist_id != checklist_id:
            continue

        report_error = report.get("error")
        if (
            report_error is not False
            or report.get("status")
            != "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED"
        ):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_RESULT_INVALID",
                source,
            )

        report_guidance_id = _required_string(
            report.get("user_action_guidance_id")
        )
        report_verification_id = _required_string(
            report.get("decision_persistence_verification_id")
        )
        report_application_id = _required_string(
            report.get("decision_persistence_application_id")
        )
        report_sku = _required_string(report.get("sku"))
        report_verified_recorded_at = _required_string(
            report.get("verified_recorded_at")
        )
        item_id = _required_string(report.get("item_id"))
        instruction = _required_string(report.get("instruction"))

        if (
            report_guidance_id != guidance_id
            or report_verification_id != verification_id
            or report_application_id != application_id
            or report_sku != sku
            or report_verified_recorded_at != verified_recorded_at
            or item_id not in canonical_items
            or instruction
            != canonical_items[item_id]["instruction"]
        ):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_LINEAGE_MISMATCH",
                source,
            )

        if (
            report.get("decision_persistence_verified") is not True
            or report.get("completion_evidence_source") != "USER_REPORT"
            or report.get("completion_persisted") is not True
            or report.get("persistent") is not True
            or report.get("externally_verified") is not False
            or report.get("checklist_mutated") is not False
            or report.get("ozon_mutation_called") is not False
            or report.get("execution_allowed") is not False
            or report.get("execution_ready") is not False
            or report.get("executed") is not False
        ):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_SAFETY_INVALID",
                source,
            )

        revision = report.get("completion_revision")
        if type(revision) is not int or revision < 1:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_REVISION_INVALID",
                source,
            )

        root_id = (
            "product-decision-user-action-completion-evidence:%s:%s"
            % (checklist_id, item_id)
        )
        evidence_root_id = _required_string(
            report.get("completion_evidence_root_id")
        )
        evidence_id = _required_string(
            report.get("user_action_completion_evidence_id")
        )
        previous_evidence_id = report.get(
            "previous_user_action_completion_evidence_id"
        )

        expected_evidence_id = (
            root_id
            if revision == 1
            else "%s:revision:%d" % (root_id, revision)
        )
        expected_previous_id = (
            None
            if revision == 1
            else (
                root_id
                if revision == 2
                else "%s:revision:%d" % (root_id, revision - 1)
            )
        )

        if (
            evidence_root_id != root_id
            or evidence_id != expected_evidence_id
            or (
                expected_previous_id is None
                and previous_evidence_id is not None
            )
            or (
                expected_previous_id is not None
                and _required_string(previous_evidence_id)
                != expected_previous_id
            )
        ):
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_REVISION_LINEAGE_INVALID",
                source,
            )

        completed = report.get("user_reported_completed")
        completion_decision = _required_string(
            report.get("completion_decision")
        )
        if type(completed) is not bool:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_DECISION_INVALID",
                source,
            )

        expected_decision = (
            "CONFIRM_COMPLETED"
            if completed
            else "NOT_COMPLETED"
        )
        if completion_decision != expected_decision:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_DECISION_INVALID",
                source,
            )

        key = (item_id, revision)
        if key in matching_reports:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_REVISION_AMBIGUOUS",
                source,
            )

        matching_reports[key] = report

    latest = {}

    for item_id in ordered_item_ids:
        revisions = sorted(
            revision
            for current_item_id, revision in matching_reports
            if current_item_id == item_id
        )

        if not revisions:
            continue

        expected_revisions = list(range(1, revisions[-1] + 1))
        if revisions != expected_revisions:
            return _blocked(
                "USER_ACTION_CHECKLIST_STATUS_REPORT_CHAIN_INCOMPLETE",
                source,
            )

        latest_revision = revisions[-1]
        latest[item_id] = matching_reports[
            (item_id, latest_revision)
        ]

    completed_item_ids = []
    reported_item_ids = []

    for item_id in ordered_item_ids:
        report = latest.get(item_id)
        if report is None:
            continue

        reported_item_ids.append(item_id)
        if report.get("user_reported_completed") is True:
            completed_item_ids.append(item_id)

    completed_count = len(completed_item_ids)
    reported_count = len(reported_item_ids)

    if completed_count == item_count:
        aggregate_status = "USER_REPORTED_COMPLETE"
    elif reported_count == 0:
        aggregate_status = "NO_USER_REPORTS"
    else:
        aggregate_status = "USER_REPORTED_PARTIAL"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_READY",
        "user_action_checklist_status_id":
            "product-decision-user-action-checklist-status:"
            + checklist_id,
        "user_action_checklist_id": checklist_id,
        "user_action_guidance_id": guidance_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "verified_recorded_at": verified_recorded_at,
        "decision_persistence_verified": True,
        "aggregate_status": aggregate_status,
        "item_count": item_count,
        "reported_count": reported_count,
        "completed_count": completed_count,
        "reported_item_ids": reported_item_ids,
        "completed_item_ids": completed_item_ids,
        "completion_evidence_source": "USER_REPORT",
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code, source):
    safe_source = source if isinstance(source, dict) else {}
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_STATUS_BLOCKED",
        "user_action_checklist_status_id": None,
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
        "aggregate_status": None,
        "item_count": 0,
        "reported_count": 0,
        "completed_count": 0,
        "reported_item_ids": [],
        "completed_item_ids": [],
        "completion_evidence_source": "USER_REPORT",
        "externally_verified": False,
        "persistent": False,
        "checklist_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }

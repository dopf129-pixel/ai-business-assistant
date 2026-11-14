"""Build a read-only FIFO supply manifest from deduplicated typed evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace

from services.fifo_cost_batch_rule_contracts import (
    AutomaticBatchManifest,
    BatchMembershipDecision,
    BatchRuleRevision,
    BatchTotalControl,
    BatchTotalControlKind,
    BatchTotalControlStatus,
    MAX_BATCH_TOTAL,
    ManifestFreshness,
    SupplyMembership,
    SupplyMembershipClassification,
    SupplyScanCoverage,
    SupplySkuObservation,
    SupplyTotalMode,
)
from services.fifo_cost_batch_supply_deduplicator import (
    CanonicalSupplySkuRecord,
    FifoCostBatchDeduplicationResult,
    FifoCostBatchSupplyDeduplicator,
    MAX_OBSERVATIONS,
    OwnerOrderControl,
    OwnerOrderControlStatus,
    SupplyLinkStatus,
)
from services.fifo_cost_transition_contracts import (
    NormalizedSupplyStatus,
    ScopeIdentity,
    TransitionCase,
    source_fingerprint,
)


_SHIPPED_STATUSES = frozenset({
    NormalizedSupplyStatus.IN_TRANSIT,
    NormalizedSupplyStatus.RECEIVING,
    NormalizedSupplyStatus.PARTIALLY_ACCEPTED,
    NormalizedSupplyStatus.ACCEPTED,
})
_CONTROL_METRICS = {
    BatchTotalControlKind.DECLARED_IN_FOUND_SUPPLIES: "declared_in_found_supplies",
    BatchTotalControlKind.DECLARED_IN_SHIPPED_SUPPLIES: "declared_in_shipped_supplies",
    BatchTotalControlKind.ACCEPTED_UNITS: "accepted_units",
    BatchTotalControlKind.PLANNED_UNITS: "planned_units",
}
_MAX_RECORDS = 20_000
_MAX_CONTROLS = 100


@dataclass(frozen=True, slots=True)
class BatchControlAssessment:
    """A dated control assessment; nonmatching windows are retained separately."""

    control_id: str
    revision: int
    total_units: int
    window_from: str
    window_through: str
    kind: str
    status: str
    calculated_units: int | None
    issue_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LegacyControlLabel:
    """An old owner total with no defensible date window."""

    label: str
    total_units: int


@dataclass(frozen=True, slots=True)
class FifoCostBatchManifestBuildResult:
    status: str
    code: str
    manifest: AutomaticBatchManifest | None
    control_assessments: tuple[BatchControlAssessment, ...] = ()
    legacy_control: LegacyControlLabel | None = None
    issue_codes: tuple[str, ...] = ()


class FifoCostBatchManifestBuilder:
    """Purely aggregate exact-SKU supply evidence; never persists or applies it."""

    @classmethod
    def build(
        cls,
        *,
        case: TransitionCase,
        rule,
        coverage: SupplyScanCoverage,
        deduplication: FifoCostBatchDeduplicationResult,
        classifications: tuple[SupplyMembershipClassification, ...],
        membership_decisions: tuple[BatchMembershipDecision, ...] = (),
        total_controls: tuple[BatchTotalControl, ...] = (),
    ) -> FifoCostBatchManifestBuildResult:
        """Build one manifest for an exact case/rule/scan and dated control set.

        ``declared_in_found_supplies`` is the complete shipped-composition
        total across API-found rows. ``declared_in_shipped_supplies`` is the
        complete shipped-composition total for included, dispatched supplies.
        ``accepted_units`` is emitted only when every included supply has a
        non-conflicting accepted quantity. ``known_subtotal`` is the sum of
        known accepted quantities, so an incomplete accepted total stays
        visibly partial with ``unknown_quantity_supply_count``.
        """
        if (
            isinstance(deduplication, FifoCostBatchDeduplicationResult)
            and deduplication.status == "CONFLICT"
        ):
            return cls._error(deduplication.code)
        invalid = cls._validate_inputs(
            case, rule, coverage, deduplication, classifications,
            membership_decisions, total_controls,
        )
        if invalid:
            return cls._error(invalid)

        scope = case.metadata.scope
        records = deduplication.records
        classification_by_key = {item.record_key: item for item in classifications}
        api_records = tuple(record for record in records if record.current_observation is not None)
        included: list[CanonicalSupplySkuRecord] = []
        undecided = 0
        issues = set(deduplication.issue_codes)
        issues.update(coverage.issue_codes)
        for record in records:
            classification = classification_by_key.get(record.record_key)
            if classification is not None:
                issues.update(classification.issue_codes)
            if record.status is SupplyLinkStatus.REVIEW_REQUIRED:
                issues.update(record.issues)
                undecided += 1
                continue
            if record.current_observation is None:
                # An owner-only reference is not an Ozon-discovered supply.
                undecided += 1
                issues.add("FIFO_BATCH_OWNER_SUPPLY_NOT_FOUND")
                continue
            if classification is None:
                undecided += 1
                issues.add("FIFO_BATCH_MEMBERSHIP_UNDECIDED")
                continue
            if classification.membership is SupplyMembership.ELIGIBLE:
                included.append(record)
            elif classification.membership in {
                SupplyMembership.NEEDS_CONFIRMATION,
                SupplyMembership.CONFLICT,
            }:
                undecided += 1
                issues.update(classification.issue_codes)

        found_composition = [
            item.current_observation.shipped_composition_quantity for item in api_records
        ]
        found_total, found_overflow = cls._complete_total(found_composition)
        if found_overflow:
            return cls._error("FIFO_BATCH_MANIFEST_AGGREGATE_OVERFLOW")

        dispatched = tuple(
            record for record in included
            if record.current_observation.normalized_status in _SHIPPED_STATUSES
            or (
                record.current_observation.normalized_status is NormalizedSupplyStatus.CANCELLED
                and record.current_observation.dispatch_local_date is not None
                and record.current_observation.dispatch_time_status.value == "CONFIRMED"
            )
        )
        shipped_values = [
            item.current_observation.shipped_composition_quantity for item in dispatched
        ]
        shipped_total, shipped_overflow = cls._complete_total(shipped_values)
        if shipped_overflow:
            return cls._error("FIFO_BATCH_MANIFEST_AGGREGATE_OVERFLOW")

        dispatched_keys = {item.record_key for item in dispatched}
        accepted_values = [item.effective_accepted_quantity for item in dispatched]
        accepted_known = [value for value in accepted_values if value is not None]
        accepted_complete = bool(dispatched) and len(accepted_known) == len(dispatched)
        accepted_total, accepted_overflow = (
            cls._bounded_sum(accepted_known) if accepted_complete else (None, False)
        )
        known_subtotal, subtotal_overflow = cls._bounded_sum(accepted_known)
        if accepted_overflow or subtotal_overflow:
            return cls._error("FIFO_BATCH_MANIFEST_AGGREGATE_OVERFLOW")

        unknown_quantity_keys = {
            record.record_key for record in included
            if (
                record.record_key in dispatched_keys
                and (
                    record.current_observation.shipped_composition_quantity is None
                    or record.current_observation.quantity_coverage.value != "COMPLETE"
                    or record.effective_accepted_quantity is None
                    or record.issues
                )
            )
            or (
                record.current_observation.normalized_status is NormalizedSupplyStatus.DECLARED
                and record.current_observation.planned_declared_quantity is None
            )
        }
        unknown_quantity_count = len(unknown_quantity_keys)

        pending_values = []
        pending_complete = bool(dispatched)
        for record in dispatched:
            shipped_units = record.current_observation.shipped_composition_quantity
            accepted_units = record.effective_accepted_quantity
            if (
                shipped_units is None or accepted_units is None
                or accepted_units > shipped_units or record.issues
            ):
                pending_complete = False
                if accepted_units is not None and shipped_units is not None and accepted_units > shipped_units:
                    issues.add("FIFO_BATCH_ACCEPTED_EXCEEDS_SHIPPED")
            else:
                pending_values.append(shipped_units - accepted_units)
        pending_total, pending_overflow = (
            cls._bounded_sum(pending_values)
            if pending_complete and len(pending_values) == len(dispatched)
            else (None, False)
        )
        if pending_overflow:
            return cls._error("FIFO_BATCH_MANIFEST_AGGREGATE_OVERFLOW")

        planned_values = [
            item.current_observation.planned_declared_quantity
            for item in included
            if item.current_observation.normalized_status is NormalizedSupplyStatus.DECLARED
        ]
        planned_total, planned_overflow = cls._complete_total(planned_values)
        if planned_overflow:
            return cls._error("FIFO_BATCH_MANIFEST_AGGREGATE_OVERFLOW")
        if planned_values and any(value is None for value in planned_values):
            unknown_quantity_keys.update(
                item.record_key for item in included
                if item.current_observation.normalized_status is NormalizedSupplyStatus.DECLARED
                and item.current_observation.planned_declared_quantity is None
            )
            unknown_quantity_count = len(unknown_quantity_keys)

        order_control_issues = cls._order_control_issues(deduplication.order_controls)
        issues.update(order_control_issues)
        assessments, exact_controls, control_issues = cls._assess_controls(
            total_controls, coverage, {
                "declared_in_found_supplies": found_total,
                "declared_in_shipped_supplies": shipped_total,
                "accepted_units": accepted_total,
                "planned_units": planned_total,
            },
        )
        issues.update(control_issues)
        legacy_control = (
            LegacyControlLabel("UNBOUNDED_LEGACY_CONTROL", case.declared_shipped_units)
            if case.declared_shipped_units is not None else None
        )

        membership_complete = (
            coverage.membership_complete
            and undecided == 0
            and all(
                classification_by_key.get(record.record_key) is not None
                and classification_by_key[record.record_key].membership
                in {SupplyMembership.ELIGIBLE, SupplyMembership.EXCLUDED, SupplyMembership.OUTSIDE_RULE}
                for record in api_records
            )
        )
        composition_complete = (
            coverage.quantity_complete
            and all(
                item.current_observation.shipped_composition_quantity is not None
                and item.current_observation.quantity_coverage.value == "COMPLETE"
                for item in api_records
            )
        )
        computed_coverage = replace(
            coverage,
            membership_complete=membership_complete,
            quantity_complete=composition_complete,
            unknown_quantity_supply_count=max(
                coverage.unknown_quantity_supply_count,
                sum(
                    item.current_observation.shipped_composition_quantity is None
                    or item.current_observation.quantity_coverage.value != "COMPLETE"
                    for item in api_records
                ),
            ),
        )
        if not api_records:
            issues.add("FIFO_BATCH_SOURCE_EMPTY_NOT_ZERO")
        if len({item.current_observation.source_profile_version for item in api_records}) > 1:
            issues.add("FIFO_BATCH_SOURCE_PROFILE_MISMATCH")

        decision_refs = set()
        for decision in membership_decisions:
            decision_refs.add(source_fingerprint({
                "decision_id": decision.decision_id,
                "revision": decision.revision,
            }))
        for classification in classifications:
            if classification.decision_ref is not None:
                decision_refs.add(classification.decision_ref)
        if len(decision_refs) > 20_000:
            return cls._error("FIFO_BATCH_MANIFEST_DECISION_REF_LIMIT_REACHED")

        if len(exact_controls) > 1:
            # The frozen manifest has one inline control slot. Preserve each
            # assessment in the result, but do not call the multi-control
            # manifest complete until its evidence contract can seal them all.
            issues.add("FIFO_BATCH_MULTIPLE_EXACT_WINDOW_CONTROLS")
        complete_for_current = cls._complete_current(
            computed_coverage, api_records, included, undecided,
            unknown_quantity_count, found_total, shipped_total, issues,
        )
        stale = any("STALE" in issue for issue in issues | set(computed_coverage.issue_codes))
        freshness = (
            ManifestFreshness.STALE if stale else
            ManifestFreshness.CURRENT if complete_for_current else
            ManifestFreshness.UNKNOWN
        )
        current_through = computed_coverage.source_as_of
        embedded_control = exact_controls[0] if len(exact_controls) == 1 else None
        if len(issues) > 128:
            return cls._error("FIFO_BATCH_MANIFEST_ISSUE_LIMIT_REACHED")
        manifest = AutomaticBatchManifest(
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            rule_fingerprint=rule.rule_fingerprint,
            scan_id=computed_coverage.scan_id,
            observation_record_keys=tuple(item.record_key for item in api_records),
            membership_decision_refs=tuple(sorted(decision_refs)),
            owner_control_total=None if embedded_control is None else embedded_control.total_units,
            owner_control_from=None if embedded_control is None else embedded_control.window_from,
            owner_control_through=None if embedded_control is None else embedded_control.window_through,
            owner_control_kind=None if embedded_control is None else embedded_control.control_kind.value,
            owner_control_status=None if embedded_control is None else cls._control_status_for_manifest(
                embedded_control, assessments,
            ),
            declared_in_found_supplies=found_total,
            declared_in_shipped_supplies=shipped_total,
            accepted_units=accepted_total,
            pending_units=pending_total,
            planned_units=planned_total,
            known_subtotal=known_subtotal,
            unknown_quantity_supply_count=unknown_quantity_count,
            found_supply_count=len(api_records),
            included_supply_count=len(included),
            undecided_supply_count=undecided,
            coverage=computed_coverage,
            current_through=current_through,
            freshness=freshness,
            issues=tuple(sorted(issues)),
        )
        if not api_records:
            status, code = "UNKNOWN", "FIFO_BATCH_MANIFEST_SOURCE_EMPTY"
        elif issues and any("CONFLICT" in item or "MISMATCH" in item for item in issues):
            status, code = "REVIEW_REQUIRED", "FIFO_BATCH_MANIFEST_REVIEW_REQUIRED"
        elif freshness is ManifestFreshness.CURRENT:
            status, code = "COMPLETE", "FIFO_BATCH_MANIFEST_COMPLETE"
        else:
            status, code = "PARTIAL", "FIFO_BATCH_MANIFEST_PARTIAL"
        return FifoCostBatchManifestBuildResult(
            status=status, code=code, manifest=manifest,
            control_assessments=assessments, legacy_control=legacy_control,
            issue_codes=tuple(sorted(issues)),
        )

    @classmethod
    def _validate_inputs(
        cls, case, rule, coverage, deduplication, classifications,
        decisions, controls,
    ):
        if not isinstance(case, TransitionCase) or not isinstance(rule, BatchRuleRevision):
            return "FIFO_BATCH_MANIFEST_INPUT_INVALID"
        if not isinstance(coverage, SupplyScanCoverage) or not isinstance(
            deduplication, FifoCostBatchDeduplicationResult,
        ) or deduplication.status not in {"UNKNOWN", "NORMALIZED", "REVIEW_REQUIRED"}:
            return "FIFO_BATCH_MANIFEST_INPUT_INVALID"
        if not isinstance(deduplication.issue_codes, tuple) or len(deduplication.issue_codes) > 128 or any(
            not isinstance(item, str) for item in deduplication.issue_codes
        ):
            return "FIFO_BATCH_MANIFEST_ISSUE_LIMIT_REACHED"
        scope = case.metadata.scope
        if (
            rule.scope != scope or rule.case_id != case.case_id
            or coverage.scope != scope or coverage.case_id != case.case_id
            or coverage.rule_revision != rule.rule_revision
            or case.supply_total_mode is not SupplyTotalMode.AUTO_FROM_SUPPLIES
        ):
            return "FIFO_BATCH_MANIFEST_SCOPE_OR_RULE_MISMATCH"
        if not isinstance(classifications, tuple) or len(classifications) > _MAX_RECORDS or any(
            not isinstance(item, SupplyMembershipClassification) for item in classifications
        ):
            return "FIFO_BATCH_MANIFEST_CLASSIFICATIONS_INVALID"
        if not isinstance(decisions, tuple) or len(decisions) > 20_000 or any(
            not isinstance(item, BatchMembershipDecision) for item in decisions
        ):
            return "FIFO_BATCH_MANIFEST_DECISIONS_INVALID"
        if not isinstance(controls, tuple) or len(controls) > _MAX_CONTROLS or any(
            not isinstance(item, BatchTotalControl) for item in controls
        ):
            return "FIFO_BATCH_MANIFEST_CONTROLS_INVALID"
        if not isinstance(deduplication.records, tuple):
            return "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
        if len(deduplication.records) > _MAX_RECORDS:
            return "FIFO_BATCH_MANIFEST_RECORD_LIMIT_REACHED"
        if len(deduplication.records) > 5_000:
            return "FIFO_BATCH_MANIFEST_SUPPLY_LIMIT_REACHED"
        if any(not isinstance(item, CanonicalSupplySkuRecord) for item in deduplication.records):
            return "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
        if any(
            not isinstance(item.record_key, str)
            or len(item.record_key) != 64
            or any(char not in "0123456789abcdef" for char in item.record_key)
            or not FifoCostBatchSupplyDeduplicator._is_digest(item.supply_ref_digest)
            for item in deduplication.records
        ):
            return "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
        keys = [item.record_key for item in deduplication.records]
        if len(keys) != len(set(keys)):
            return "FIFO_BATCH_MANIFEST_DUPLICATE_RECORD"
        if any(not isinstance(item.observations, tuple) for item in deduplication.records):
            return "FIFO_BATCH_MANIFEST_RECORDS_INVALID"
        if any(len(item.observations) > MAX_OBSERVATIONS for item in deduplication.records):
            return "FIFO_BATCH_MANIFEST_RECORD_LIMIT_REACHED"
        if sum(len(item.observations) for item in deduplication.records) > MAX_OBSERVATIONS:
            return "FIFO_BATCH_MANIFEST_RECORD_LIMIT_REACHED"
        if not isinstance(deduplication.order_controls, tuple) or len(deduplication.order_controls) > 2_000 or any(
            not isinstance(item, OwnerOrderControl)
            or not isinstance(item.child_record_keys, tuple)
            or len(item.child_record_keys) > _MAX_RECORDS
            or any(
                not isinstance(key, str)
                or len(key) != 64
                or any(char not in "0123456789abcdef" for char in key)
                for key in item.child_record_keys
            )
            or not isinstance(item.status, OwnerOrderControlStatus)
            for item in deduplication.order_controls
        ):
            return "FIFO_BATCH_MANIFEST_ORDER_CONTROLS_INVALID"
        if sum(len(item.child_record_keys) for item in deduplication.order_controls) > _MAX_RECORDS:
            return "FIFO_BATCH_MANIFEST_ORDER_CONTROLS_INVALID"
        record_keys = set(keys)
        if any(
            any(key not in record_keys for key in control.child_record_keys)
            for control in deduplication.order_controls
        ):
            return "FIFO_BATCH_MANIFEST_ORDER_LINK_MISMATCH"
        classification_keys = [item.record_key for item in classifications]
        if len(classification_keys) != len(set(classification_keys)):
            return "FIFO_BATCH_MANIFEST_DUPLICATE_MEMBERSHIP"
        if any(
            item.scope != scope
            or any(not isinstance(observation, SupplySkuObservation) for observation in item.observations)
            or (
                item.current_observation is not None
                and (
                    not isinstance(item.current_observation, SupplySkuObservation)
                    or item.current_observation not in item.observations
                )
            )
            or any(
                observation.scope != scope
                or observation.record_key != item.record_key
                or observation.supply_ref_digest != item.supply_ref_digest
                for observation in item.observations
            )
            or item.record_key != FifoCostBatchSupplyDeduplicator.canonical_record_key(
                scope, item.supply_ref_digest,
            )
            or any(observation.scope != scope for observation in item.observations)
            for item in deduplication.records
        ):
            return "FIFO_BATCH_MANIFEST_RECORD_SCOPE_MISMATCH"
        if sum(item.current_observation is not None for item in deduplication.records) > 5_000:
            return "FIFO_BATCH_MANIFEST_SUPPLY_LIMIT_REACHED"
        record_by_key = {item.record_key: item for item in deduplication.records}
        if any(item.record_key not in record_by_key for item in classifications):
            return "FIFO_BATCH_MANIFEST_MEMBERSHIP_RECORD_NOT_FOUND"
        if any(
            item.scope != scope or item.case_id != case.case_id
            or item.rule_id != rule.rule_id
            or item.rule_revision != rule.rule_revision
            or item.rule_fingerprint != rule.rule_fingerprint
            or record_by_key[item.record_key].current_observation is None
            or record_by_key[item.record_key].current_observation.source_fingerprint != item.source_fingerprint
            for item in classifications
        ):
            return "FIFO_BATCH_MANIFEST_MEMBERSHIP_SCOPE_MISMATCH"
        if any(
            item.scope != scope or item.case_id != case.case_id
            or item.rule_id != rule.rule_id or item.rule_revision != rule.rule_revision
            for item in decisions
        ):
            return "FIFO_BATCH_MANIFEST_DECISION_SCOPE_MISMATCH"
        if any(
            item.scope != scope or item.case_id != case.case_id
            for item in controls
        ):
            return "FIFO_BATCH_MANIFEST_CONTROL_SCOPE_MISMATCH"
        return None

    @staticmethod
    def _complete_total(values):
        if not values or any(value is None for value in values):
            return None, False
        return FifoCostBatchManifestBuilder._bounded_sum(values)

    @staticmethod
    def _bounded_sum(values):
        total = sum(values)
        return (None, True) if total > MAX_BATCH_TOTAL else (total, False)

    @classmethod
    def _assess_controls(cls, controls, coverage, metric_values):
        latest = {}
        issues = set()
        for control in controls:
            current = latest.get(control.control_id)
            if current is None or control.control_revision > current.control_revision:
                latest[control.control_id] = control
            elif control.control_revision == current.control_revision and control != current:
                issues.add("FIFO_BATCH_CONTROL_REVISION_CONFLICT")
        assessments = []
        exact_active = []
        for control in latest.values():
            if control.control_status is not BatchTotalControlStatus.OWNER_CONFIRMED:
                assessments.append(BatchControlAssessment(
                    control_id=control.control_id, revision=control.control_revision,
                    total_units=control.total_units, window_from=control.window_from,
                    window_through=control.window_through, kind=control.control_kind.value,
                    status=control.control_status.value, calculated_units=None,
                ))
                continue
            exact_window = (
                coverage.requested_from == control.window_from
                and coverage.requested_through == control.window_through
            )
            if not exact_window:
                assessments.append(BatchControlAssessment(
                    control_id=control.control_id, revision=control.control_revision,
                    total_units=control.total_units, window_from=control.window_from,
                    window_through=control.window_through, kind=control.control_kind.value,
                    status="WINDOW_NOT_COMPARABLE", calculated_units=None,
                ))
                continue
            exact_active.append(control)
            calculated = metric_values[_CONTROL_METRICS[control.control_kind]]
            if calculated is None:
                status = "UNVERIFIABLE"
                control_issue = "FIFO_BATCH_CONTROL_EXACT_WINDOW_UNVERIFIABLE"
                issues.add(control_issue)
                codes = (control_issue,)
            elif calculated != control.total_units:
                status = "MISMATCH"
                control_issue = "FIFO_BATCH_CONTROL_EXACT_WINDOW_MISMATCH"
                issues.add(control_issue)
                codes = (control_issue,)
            else:
                status, codes = "MATCH", ()
            assessments.append(BatchControlAssessment(
                control_id=control.control_id, revision=control.control_revision,
                total_units=control.total_units, window_from=control.window_from,
                window_through=control.window_through, kind=control.control_kind.value,
                status=status, calculated_units=calculated, issue_codes=codes,
            ))
        by_kind = {}
        for control in exact_active:
            by_kind.setdefault(control.control_kind, set()).add(control.total_units)
        if any(len(totals) > 1 for totals in by_kind.values()):
            issues.add("FIFO_BATCH_CONTROL_DUPLICATE_WINDOW_CONFLICT")
        return tuple(sorted(assessments, key=lambda item: (item.window_from, item.kind, item.control_id))), tuple(exact_active), issues

    @staticmethod
    def _control_status_for_manifest(control, assessments):
        assessment = next((item for item in assessments if item.control_id == control.control_id), None)
        return "UNKNOWN" if assessment is None else assessment.status

    @staticmethod
    def _order_control_issues(order_controls):
        issues = set()
        for control in order_controls:
            if control.status is OwnerOrderControlStatus.UNRESOLVED:
                issues.add("FIFO_BATCH_OWNER_ORDER_UNRESOLVED")
            elif control.status is OwnerOrderControlStatus.UNVERIFIABLE:
                issues.add("FIFO_BATCH_OWNER_ORDER_UNVERIFIABLE")
            elif control.status is OwnerOrderControlStatus.REVIEW_REQUIRED:
                issues.update(control.issues or ("FIFO_BATCH_OWNER_ORDER_CONFLICT",))
        return issues

    @staticmethod
    def _complete_current(
        coverage, api_records, included, undecided, unknown_quantity_count,
        found_total, shipped_total, issues,
    ):
        return bool(
            api_records and included and undecided == 0 and unknown_quantity_count == 0
            and found_total is not None and shipped_total is not None
            and coverage.list_pagination_complete and coverage.details_complete
            and coverage.sku_composition_complete and coverage.historical_window_proven
            and coverage.membership_complete and coverage.quantity_complete
            and coverage.source_as_of is not None
            and coverage.requested_from is not None and coverage.requested_through is not None
            and coverage.supported_state_profile and coverage.source_contract_version
            and coverage.unknown_order_count == 0 and coverage.unknown_supply_count == 0
            and coverage.unknown_quantity_supply_count == 0
            and not issues and not coverage.issue_codes
        )

    @staticmethod
    def _error(code):
        return FifoCostBatchManifestBuildResult(
            status="CONFLICT", code=code, manifest=None, issue_codes=(code,),
        )

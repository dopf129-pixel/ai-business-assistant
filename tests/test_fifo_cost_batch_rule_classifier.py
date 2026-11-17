from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_batch_rule_classifier import FifoCostBatchRuleClassifier
from services.fifo_cost_batch_rule_contracts import (
    BatchMembershipDecision,
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    MembershipDecisionKind,
    MembershipDecisionSource,
    SupplyMembership,
    SupplySkuObservation,
    canonical_membership_binding_fingerprint,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
)


SCOPE = ScopeIdentity(
    owner_id="owner-a", store_id="store-a", product_id="product-101",
    offer_id="hook-2", sku="3921245627",
)
NOW = "2026-11-13T12:00:00Z"


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rule(
    *, rule_id="rule_batch_001", revision=1, start="2026-11-05",
    cost="14.65", policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
    boundary=(), event=BatchRuleEventKind.CONFIRM, end=None,
    predecessor_id=None, predecessor_revision=None,
):
    return BatchRuleRevision(
        scope=SCOPE,
        case_id="case_batch_001",
        rule_id=rule_id,
        rule_revision=revision,
        policy_version=1,
        start_local_date=start,
        store_timezone="Europe/Moscow",
        start_day_policy=policy,
        new_unit_cost_rub=Decimal(cost),
        cost_input_fingerprint=_digest("cost-" + rule_id),
        old_home_confirmed_zero=True,
        old_transit_confirmed_zero=True,
        boundary_supply_digests=tuple(boundary),
        predecessor_rule_id=predecessor_id,
        predecessor_rule_revision=predecessor_revision,
        event_kind=event,
        end_local_date_exclusive=end,
        owner_confirmation_fingerprint=_digest("owner-" + str(revision)),
        confirmed_at_utc=NOW,
        rule_fingerprint=_digest("rule-" + rule_id + "-" + str(revision)),
    )


def _observation(
    *, date="2026-11-05", status=NormalizedSupplyStatus.IN_TRANSIT,
    dispatch_status=DispatchTimeStatus.CONFIRMED, supply="supply-001",
    source="source-001", issues=(), scope=SCOPE,
):
    key = _digest("record-" + supply)
    return SupplySkuObservation(
        scope=scope,
        record_key=key,
        order_ref_digest=_digest("order-" + supply),
        supply_ref_digest=_digest(supply),
        encrypted_lookup_payload=Fernet(Fernet.generate_key()).encrypt(
            b"synthetic opaque supply lookup",
        ).decode("ascii"),
        source_profile_version="synthetic-supply-v1",
        source_fingerprint=_digest(source),
        captured_at=NOW,
        source_as_of=NOW,
        source_status=status.value,
        normalized_status=status,
        is_crossdock=True,
        dispatch_local_date=date,
        dispatch_local_time=None,
        dispatch_time_status=dispatch_status,
        planned_declared_quantity=100,
        shipped_composition_quantity=100,
        accepted_quantity=None,
        quantity_source_kind=EvidenceSourceKind.OZON_API,
        quantity_coverage=EvidenceCompleteness.COMPLETE,
        acceptance_fingerprint=None,
        acceptance_version=None,
        explicit_zero_fields=(),
        membership=SupplyMembership.NEEDS_CONFIRMATION,
        issues=tuple(issues),
    )


def _decision(observation, rule, decision=MembershipDecisionKind.INCLUDED):
    binding = canonical_membership_binding_fingerprint(
        scope=observation.scope,
        supply_ref_digest=observation.supply_ref_digest,
        rule_id=rule.rule_id,
        rule_revision=rule.rule_revision,
        rule_fingerprint=rule.rule_fingerprint,
        dispatch_local_date=(
            observation.dispatch_local_date
            if observation.dispatch_time_status is DispatchTimeStatus.CONFIRMED
            and observation.normalized_status in {
                NormalizedSupplyStatus.IN_TRANSIT,
                NormalizedSupplyStatus.RECEIVING,
                NormalizedSupplyStatus.PARTIALLY_ACCEPTED,
                NormalizedSupplyStatus.ACCEPTED,
                NormalizedSupplyStatus.CANCELLED,
            }
            else None
        ),
        owner_selected=True,
    )
    return BatchMembershipDecision(
        decision_id="decision_batch_001",
        revision=1,
        scope=observation.scope,
        case_id="case_batch_001",
        rule_id=rule.rule_id,
        rule_revision=rule.rule_revision,
        decision=decision,
        source=MembershipDecisionSource.OWNER_SELECTED_SET,
        record_keys=(observation.record_key,),
        relevant_source_fingerprints=((observation.record_key, observation.source_fingerprint),),
        candidate_set_fingerprint=_digest("candidate-set"),
        membership_binding_fingerprint=binding,
        idempotency_key="decision-key-001",
        confirmed_at=NOW,
    )


def _successor_chain(*, new_start="2026-11-12", new_cost="16.00"):
    old = _rule()
    close = _rule(
        revision=2,
        event=BatchRuleEventKind.CLOSE,
        end=new_start,
        predecessor_id=old.rule_id,
        predecessor_revision=old.rule_revision,
    )
    new = _rule(
        rule_id="rule_batch_002",
        revision=3,
        start=new_start,
        cost=new_cost,
        policy=BatchStartDayPolicy.ALL_OWNER_CONFIRMED,
        event=BatchRuleEventKind.REPLACE,
        predecessor_id=old.rule_id,
        predecessor_revision=close.rule_revision,
    )
    new = replace(
        new, owner_confirmation_fingerprint=close.owner_confirmation_fingerprint,
    )
    return old, close, new


def test_all_owner_confirmed_start_day_and_later_dispatch_are_eligible():
    rule = _rule()
    start_day = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), _observation(date="2026-11-05"),
    )
    later = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), _observation(date="2026-11-06"),
    )
    assert start_day.membership is SupplyMembership.ELIGIBLE
    assert later.membership is SupplyMembership.ELIGIBLE
    assert start_day.rule_id == rule.rule_id
    assert later.membership_binding_fingerprint != start_day.membership_binding_fingerprint


def test_explicit_start_day_set_needs_exact_inclusion_but_later_date_is_automatic():
    included_observation = _observation(supply="selected-supply")
    unselected_observation = _observation(supply="unselected-supply")
    rule = _rule(
        policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET,
        boundary=(included_observation.supply_ref_digest,),
    )
    selected = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), included_observation,
    )
    unselected = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), unselected_observation,
    )
    later = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), replace(unselected_observation, dispatch_local_date="2026-11-06"),
    )
    assert selected.membership is SupplyMembership.ELIGIBLE
    assert selected.membership_binding_fingerprint
    assert unselected.membership is SupplyMembership.NEEDS_CONFIRMATION
    assert later.membership is SupplyMembership.ELIGIBLE


def test_owner_selected_exact_first_day_decision_resolves_boundary():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    observation = _observation(supply="manually-selected")
    decision = _decision(observation, rule)
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), observation, (decision,),
    )
    assert result.membership is SupplyMembership.ELIGIBLE
    assert result.decision_ref == "decision_batch_001-r1"


def test_unknown_or_unconfirmed_dispatch_date_is_not_inferred_from_other_timestamps():
    rule = _rule()
    observation = _observation(
        date="2026-11-05", dispatch_status=DispatchTimeStatus.UNKNOWN,
    )
    first = FifoCostBatchRuleClassifier.classify_supply((rule,), observation)
    second = FifoCostBatchRuleClassifier.classify_supply((rule,), observation)
    assert first.membership is SupplyMembership.NEEDS_CONFIRMATION
    assert first.dispatch_local_date is None
    assert first == second


def test_exact_scope_mismatch_is_conflict():
    rule = _rule()
    other_scope = ScopeIdentity(
        owner_id="owner-a", store_id="store-b", product_id="product-101",
        offer_id="hook-2", sku="3921245627",
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), _observation(scope=other_scope),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert "SCOPE_OR_CASE_MISMATCH" in result.issue_codes


def test_next_boundary_closes_old_interval_and_selects_new_cost_rule():
    chain = _successor_chain()
    old_result = FifoCostBatchRuleClassifier.classify_supply(
        chain, _observation(date="2026-11-11"),
    )
    new_result = FifoCostBatchRuleClassifier.classify_supply(
        chain, _observation(date="2026-11-12"),
    )
    assert old_result.membership is SupplyMembership.ELIGIBLE
    assert old_result.rule_id == chain[0].rule_id
    assert new_result.membership is SupplyMembership.ELIGIBLE
    assert new_result.rule_id == chain[2].rule_id
    assert new_result.rule_revision == chain[2].rule_revision


def test_timezone_change_across_rule_history_requires_review():
    old, close, new = _successor_chain()
    new = replace(new, store_timezone="Asia/Yekaterinburg")
    result = FifoCostBatchRuleClassifier.classify_supply(
        (old, close, new), _observation(date="2026-11-12"),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert result.issue_codes == ("RULE_CHAIN_TIMEZONE_CHANGE_NEEDS_REVIEW",)


def test_two_cost_boundaries_on_same_day_are_review_conflict():
    first = _rule()
    same_day = _rule(
        rule_id="rule_batch_002", revision=2,
        event=BatchRuleEventKind.REPLACE,
        predecessor_id=first.rule_id, predecessor_revision=1,
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (first, same_day), _observation(),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert "RULE_CHAIN_PREDECESSOR_OR_INTERVAL_GAP" in result.issue_codes or (
        "SAME_DAY_OR_REVERSED_RULE_BOUNDARY" in result.issue_codes
    )


def test_proven_date_cannot_be_overridden_by_conflicting_owner_inclusion():
    rule = _rule()
    observation = _observation(date="2026-11-04", source="confirmed-before-boundary")
    decision = _decision(observation, rule)
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), observation, (decision,),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert "OWNER_SELECTION_CONTRADICTS_DATE" in result.issue_codes


def test_membership_survives_transport_status_refresh_when_binding_is_unchanged():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    old_observation = _observation(
        source="source-before-refresh",
        status=NormalizedSupplyStatus.IN_TRANSIT,
    )
    decision = _decision(old_observation, rule)
    refreshed = replace(
        old_observation,
        source_fingerprint=_digest("source-after-refresh"),
        captured_at="2026-11-14T12:00:00Z",
        source_as_of="2026-11-14T11:59:00Z",
        source_status=NormalizedSupplyStatus.RECEIVING.value,
        normalized_status=NormalizedSupplyStatus.RECEIVING,
        planned_declared_quantity=120,
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), refreshed, (decision,),
    )
    assert result.membership is SupplyMembership.ELIGIBLE
    assert result.decision_ref == "decision_batch_001-r1"
    assert result.source_fingerprint == refreshed.source_fingerprint
    # The owner decision retains the exact source snapshot used at confirmation.
    assert dict(decision.relevant_source_fingerprints)[old_observation.record_key] == (
        old_observation.source_fingerprint
    )


def test_new_dispatch_date_outside_selected_rule_conflicts_instead_of_reusing_old_selection():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    old_observation = _observation(source="source-before-date-correction")
    decision = _decision(old_observation, rule)
    refreshed = replace(
        old_observation,
        source_fingerprint=_digest("source-after-date-correction"),
        dispatch_local_date="2026-11-04",
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), refreshed, (decision,),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert result.issue_codes == ("OWNER_SELECTION_CONTRADICTS_DATE",)


def test_cancellation_after_confirmed_dispatch_does_not_erase_batch_membership():
    rule = _rule()
    cancelled = _observation(
        date="2026-11-06", status=NormalizedSupplyStatus.CANCELLED,
    )
    result = FifoCostBatchRuleClassifier.classify_supply((rule,), cancelled)
    assert result.membership is SupplyMembership.ELIGIBLE
    assert "CANCELLED_AFTER_DISPATCH_PRESERVED" in result.issue_codes


def test_unknown_dispatch_cancel_requires_owner_confirmation():
    rule = _rule()
    cancelled = _observation(
        date=None,
        status=NormalizedSupplyStatus.CANCELLED,
        dispatch_status=DispatchTimeStatus.UNKNOWN,
    )
    result = FifoCostBatchRuleClassifier.classify_supply((rule,), cancelled)
    assert result.membership is SupplyMembership.NEEDS_CONFIRMATION


def test_cancelled_rule_history_fails_closed_without_reclassifying_history():
    base = _rule()
    cancelled_rule = replace(
        base,
        rule_revision=2,
        event_kind=BatchRuleEventKind.CANCEL,
        end_local_date_exclusive="2026-11-12",
        predecessor_rule_id=base.rule_id,
        predecessor_rule_revision=base.rule_revision,
        rule_fingerprint=_digest("cancelled-rule"),
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (base, cancelled_rule), _observation(date="2026-11-06"),
    )
    assert result.membership is SupplyMembership.CONFLICT
    assert result.issue_codes == ("CANCELLED_RULE_REQUIRES_REVIEW",)


def test_owner_exclusion_is_applied_only_to_exact_current_binding():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    observation = _observation(supply="owner-excluded")
    decision = _decision(observation, rule, MembershipDecisionKind.EXCLUDED)
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), observation, (decision,),
    )
    assert result.membership is SupplyMembership.EXCLUDED
    assert result.decision_ref == "decision_batch_001-r1"


def test_latest_append_only_decision_supersedes_prior_matching_revision():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    observation = _observation(supply="decision-revisioned")
    prior = _decision(observation, rule, MembershipDecisionKind.INCLUDED)
    latest = replace(
        prior,
        revision=2,
        decision=MembershipDecisionKind.EXCLUDED,
        idempotency_key="decision-key-002",
        previous_decision_ref="decision_batch_001-r1",
        confirmed_at="2026-11-13T12:30:00Z",
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), observation, (prior, latest),
    )
    assert result.membership is SupplyMembership.EXCLUDED
    assert result.decision_ref == "decision_batch_001-r2"


def test_stale_latest_decision_does_not_resurrect_superseded_membership():
    rule = _rule(policy=BatchStartDayPolicy.EXPLICIT_SUPPLY_SET)
    observation = _observation(supply="decision-revision-binding")
    prior = _decision(observation, rule, MembershipDecisionKind.INCLUDED)
    changed_date = replace(observation, dispatch_local_date="2026-11-06")
    stale_binding = canonical_membership_binding_fingerprint(
        scope=changed_date.scope,
        supply_ref_digest=changed_date.supply_ref_digest,
        rule_id=rule.rule_id,
        rule_revision=rule.rule_revision,
        rule_fingerprint=rule.rule_fingerprint,
        dispatch_local_date=changed_date.dispatch_local_date,
        owner_selected=True,
    )
    latest = replace(
        prior,
        revision=2,
        decision=MembershipDecisionKind.EXCLUDED,
        membership_binding_fingerprint=stale_binding,
        idempotency_key="decision-key-002",
        previous_decision_ref="decision_batch_001-r1",
        confirmed_at="2026-11-13T12:30:00Z",
    )
    result = FifoCostBatchRuleClassifier.classify_supply(
        (rule,), observation, (prior, latest),
    )
    assert result.membership is SupplyMembership.NEEDS_CONFIRMATION
    assert result.issue_codes == ("START_DAY_MEMBERSHIP_NEEDS_CONFIRMATION",)

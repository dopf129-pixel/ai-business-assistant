"""Deterministic, side-effect-free supply-to-batch rule classification."""

from __future__ import annotations

from collections import defaultdict

from services.fifo_cost_batch_rule_contracts import (
    BatchMembershipDecision,
    BatchRuleEventKind,
    BatchRuleRevision,
    BatchStartDayPolicy,
    DispatchTimeStatus,
    MembershipDecisionKind,
    MembershipDecisionSource,
    SupplyMembership,
    SupplyMembershipClassification,
    SupplySkuObservation,
    canonical_membership_binding_fingerprint,
)
from services.fifo_cost_transition_contracts import NormalizedSupplyStatus


_DISPATCHED_STATUSES = frozenset({
    NormalizedSupplyStatus.IN_TRANSIT,
    NormalizedSupplyStatus.RECEIVING,
    NormalizedSupplyStatus.PARTIALLY_ACCEPTED,
    NormalizedSupplyStatus.ACCEPTED,
    # A cancelled posting can still describe a supply that was dispatched.
    NormalizedSupplyStatus.CANCELLED,
})


class FifoCostBatchRuleClassifier:
    """Classify one SKU supply against a validated append-only rule chain."""

    @classmethod
    def classify_supply(
        cls,
        rule_chain: tuple[BatchRuleRevision, ...],
        observation: SupplySkuObservation,
        membership_decisions: tuple[BatchMembershipDecision, ...] = (),
    ) -> SupplyMembershipClassification:
        """Return membership without I/O, clocks, mutable state, or side effects.

        Only a confirmed dispatch date or an exact, current owner-selected
        membership decision can resolve a boundary. A cancelled status never
        erases a confirmed dispatch from the historical batch.
        """
        if not isinstance(observation, SupplySkuObservation):
            raise TypeError("FIFO_BATCH_OBSERVATION_INVALID")
        if not isinstance(rule_chain, tuple) or any(
            not isinstance(item, BatchRuleRevision) for item in rule_chain
        ):
            raise TypeError("FIFO_BATCH_RULE_CHAIN_INVALID")
        if not isinstance(membership_decisions, tuple) or any(
            not isinstance(item, BatchMembershipDecision)
            for item in membership_decisions
        ):
            raise TypeError("FIFO_BATCH_MEMBERSHIP_DECISIONS_INVALID")

        case_ids = {item.case_id for item in rule_chain}
        case_id = next(iter(case_ids)) if len(case_ids) == 1 else None
        if not rule_chain:
            return cls._result(
                observation, SupplyMembership.NEEDS_CONFIRMATION,
                case_id=None, issue="RULE_NOT_FOUND",
            )
        if len(case_ids) != 1 or any(
            item.scope != observation.scope for item in rule_chain
        ):
            return cls._result(
                observation, SupplyMembership.CONFLICT,
                case_id=case_id, issue="SCOPE_OR_CASE_MISMATCH",
            )

        intervals, issue = cls._build_intervals(rule_chain)
        if issue is not None:
            return cls._result(
                observation, SupplyMembership.CONFLICT,
                case_id=case_id, issue=issue,
            )

        confirmed_dispatch_date = (
            observation.dispatch_local_date
            if observation.dispatch_time_status is DispatchTimeStatus.CONFIRMED
            and observation.normalized_status in _DISPATCHED_STATUSES
            else None
        )
        target = None
        if confirmed_dispatch_date is not None:
            target_matches = [
                interval for interval in intervals
                if interval["start"] <= confirmed_dispatch_date
                and (
                    interval["end"] is None
                    or confirmed_dispatch_date < interval["end"]
                )
            ]
            if len(target_matches) > 1:
                return cls._result(
                    observation, SupplyMembership.CONFLICT,
                    case_id=case_id, issue="OVERLAPPING_RULE_INTERVALS",
                    dispatch_date=confirmed_dispatch_date,
                )
            target = target_matches[0] if target_matches else None

        owner_decision_candidates = cls._owner_decision_candidates(
            intervals, membership_decisions, observation, case_id,
        )
        owner_decision_candidates, decision_issue = cls._latest_decisions(
            owner_decision_candidates,
        )
        if decision_issue is not None:
            return cls._result(
                observation, SupplyMembership.CONFLICT,
                case_id=case_id, dispatch_date=confirmed_dispatch_date,
                issue=decision_issue,
            )
        exact_decisions = cls._matching_decisions(
            owner_decision_candidates, observation, confirmed_dispatch_date,
        )
        if confirmed_dispatch_date is not None and target is not None:
            target_key = (target["base"].rule_id, target["base"].rule_revision)
            contradictory_include = any(
                (item["decision"].rule_id, item["decision"].rule_revision) != target_key
                and item["decision"].decision is MembershipDecisionKind.INCLUDED
                for item in owner_decision_candidates
            )
            if contradictory_include:
                return cls._result(
                    observation, SupplyMembership.CONFLICT,
                    case_id=case_id, interval=target,
                    dispatch_date=confirmed_dispatch_date,
                    issue="OWNER_SELECTION_CONTRADICTS_PROVEN_RULE",
                )
            exact_decisions = [
                item for item in exact_decisions
                if (item["decision"].rule_id, item["decision"].rule_revision) == target_key
            ]
        if len(exact_decisions) > 1:
            unique_outcomes = {item["decision"].decision for item in exact_decisions}
            if len(unique_outcomes) > 1:
                return cls._result(
                    observation, SupplyMembership.CONFLICT,
                    case_id=case_id, issue="CONTRADICTORY_MEMBERSHIP_DECISIONS",
                    dispatch_date=confirmed_dispatch_date,
                )
            # The same supply cannot be independently confirmed by multiple
            # unrelated decision sets for the same exact rule binding.
            return cls._result(
                observation, SupplyMembership.CONFLICT,
                case_id=case_id, issue="DUPLICATE_MEMBERSHIP_DECISIONS",
                dispatch_date=confirmed_dispatch_date,
            )

        decision_match = exact_decisions[0] if exact_decisions else None
        if confirmed_dispatch_date is None:
            if target is None and decision_match is not None:
                target = decision_match["interval"]
            if target is None:
                active = [item for item in intervals if item["end"] is None]
                target = active[0] if len(active) == 1 else None
            if target is None:
                return cls._result(
                    observation, SupplyMembership.NEEDS_CONFIRMATION,
                    case_id=case_id, issue="DISPATCH_DATE_UNKNOWN",
                )

        if target is None:
            # A proven date before/after all rules is immutable evidence that
            # this supply cannot be assigned by an owner override.
            if any(
                item["decision"].decision is MembershipDecisionKind.INCLUDED
                for item in owner_decision_candidates
            ):
                return cls._result(
                    observation, SupplyMembership.CONFLICT,
                    case_id=case_id, issue="OWNER_SELECTION_CONTRADICTS_DATE",
                    dispatch_date=confirmed_dispatch_date,
                )
            return cls._result(
                observation, SupplyMembership.OUTSIDE_RULE,
                case_id=case_id, dispatch_date=confirmed_dispatch_date,
                issue="OUTSIDE_CONFIRMED_RULE_INTERVAL",
            )

        rule = target["base"]
        owner_selected = False
        if decision_match is not None:
            decision = decision_match["decision"]
            owner_selected = decision.source is MembershipDecisionSource.OWNER_SELECTED_SET
            if decision.decision is MembershipDecisionKind.EXCLUDED:
                if confirmed_dispatch_date is not None and cls._auto_included(rule, confirmed_dispatch_date):
                    return cls._result(
                        observation, SupplyMembership.CONFLICT,
                        case_id=case_id, interval=target,
                        dispatch_date=confirmed_dispatch_date,
                        issue="OWNER_EXCLUSION_CONTRADICTS_PROVEN_DISPATCH",
                    )
                return cls._result(
                    observation, SupplyMembership.EXCLUDED,
                    case_id=case_id, interval=target,
                    dispatch_date=confirmed_dispatch_date,
                    owner_selected=owner_selected,
                    decision_ref=f"{decision.decision_id}-r{decision.revision}",
                    issue="OWNER_EXCLUDED_EXACT_SUPPLY",
                )
            if decision.source is not MembershipDecisionSource.OWNER_SELECTED_SET:
                # A rule-derived decision is not a substitute for dispatch
                # proof; its bound date must still be available below.
                decision_match = None
            elif (
                confirmed_dispatch_date is None
                or cls._auto_included(rule, confirmed_dispatch_date)
                or (
                    confirmed_dispatch_date == rule.start_local_date
                    and rule.start_day_policy is BatchStartDayPolicy.EXPLICIT_SUPPLY_SET
                )
            ):
                return cls._result(
                    observation, SupplyMembership.ELIGIBLE,
                    case_id=case_id, interval=target,
                    dispatch_date=confirmed_dispatch_date,
                    owner_selected=True,
                    decision_ref=f"{decision.decision_id}-r{decision.revision}",
                    issue=("CANCELLED_AFTER_DISPATCH_PRESERVED"
                           if observation.normalized_status is NormalizedSupplyStatus.CANCELLED
                           else None),
                )
            else:
                return cls._result(
                    observation, SupplyMembership.CONFLICT,
                    case_id=case_id, interval=target,
                    dispatch_date=confirmed_dispatch_date,
                    issue="OWNER_SELECTION_CONTRADICTS_RULE_BOUNDARY",
                )

        if confirmed_dispatch_date is None:
            return cls._result(
                observation, SupplyMembership.NEEDS_CONFIRMATION,
                case_id=case_id, interval=target,
                issue="DISPATCH_DATE_REQUIRES_GROUP_CONFIRMATION",
            )
        if observation.issues:
            return cls._result(
                observation, SupplyMembership.NEEDS_CONFIRMATION,
                case_id=case_id, interval=target,
                dispatch_date=confirmed_dispatch_date,
                issue="OBSERVATION_HAS_UNRESOLVED_ISSUES",
            )
        if cls._auto_included(rule, confirmed_dispatch_date):
            return cls._result(
                observation, SupplyMembership.ELIGIBLE,
                case_id=case_id, interval=target,
                dispatch_date=confirmed_dispatch_date,
                issue=("CANCELLED_AFTER_DISPATCH_PRESERVED"
                       if observation.normalized_status is NormalizedSupplyStatus.CANCELLED
                       else None),
            )

        # The exact boundary day is never guessed. The rule itself may carry
        # an owner-confirmed set, or a separate current owner decision may
        # bind this exact supply and source revision.
        if (
            rule.start_day_policy is BatchStartDayPolicy.EXPLICIT_SUPPLY_SET
            and observation.supply_ref_digest in rule.boundary_supply_digests
        ):
            return cls._result(
                observation, SupplyMembership.ELIGIBLE,
                case_id=case_id, interval=target,
                dispatch_date=confirmed_dispatch_date,
                owner_selected=True,
            )
        return cls._result(
            observation, SupplyMembership.NEEDS_CONFIRMATION,
            case_id=case_id, interval=target,
            dispatch_date=confirmed_dispatch_date,
            issue="START_DAY_MEMBERSHIP_NEEDS_CONFIRMATION",
        )

    @classmethod
    def _build_intervals(cls, rule_chain):
        events_by_rule = defaultdict(list)
        seen_revisions = set()
        for event in rule_chain:
            if event.rule_revision in seen_revisions:
                return (), "DUPLICATE_RULE_REVISION"
            seen_revisions.add(event.rule_revision)
            events_by_rule[event.rule_id].append(event)

        intervals = []
        for rule_id, events in events_by_rule.items():
            events.sort(key=lambda item: item.rule_revision)
            bases = [
                item for item in events
                if item.event_kind in {BatchRuleEventKind.CONFIRM, BatchRuleEventKind.REPLACE}
            ]
            terminals = [
                item for item in events
                if item.event_kind in {BatchRuleEventKind.CLOSE, BatchRuleEventKind.CANCEL}
            ]
            if len(bases) != 1 or len(terminals) > 1:
                return (), "INVALID_RULE_EVENT_SEQUENCE"
            base = bases[0]
            if base.end_local_date_exclusive is not None:
                return (), "BASE_RULE_HAS_END_DATE"
            terminal = terminals[0] if terminals else None
            if terminal is not None:
                if terminal.event_kind is BatchRuleEventKind.CANCEL:
                    return (), "CANCELLED_RULE_REQUIRES_REVIEW"
                if not cls._same_rule_basis(base, terminal):
                    return (), "CLOSE_EVENT_BASIS_MISMATCH"
                if (
                    terminal.rule_revision <= base.rule_revision
                    or terminal.predecessor_rule_id != base.rule_id
                    or terminal.predecessor_rule_revision != base.rule_revision
                ):
                    return (), "CLOSE_EVENT_PREDECESSOR_MISMATCH"
            intervals.append({
                "base": base,
                "close": terminal,
                "start": base.start_local_date,
                "end": terminal.end_local_date_exclusive if terminal else None,
            })

        intervals.sort(key=lambda item: (item["start"], item["base"].rule_revision))
        if not intervals:
            return (), "RULE_NOT_FOUND"
        if intervals[0]["base"].event_kind is not BatchRuleEventKind.CONFIRM:
            return (), "RULE_CHAIN_MISSING_INITIAL_CONFIRM"
        if intervals[0]["base"].rule_revision != 1:
            return (), "RULE_CHAIN_INITIAL_REVISION_INVALID"
        if intervals[0]["base"].predecessor_rule_id is not None:
            return (), "INITIAL_RULE_HAS_PREDECESSOR"
        if len({item["base"].store_timezone for item in intervals}) != 1:
            return (), "RULE_CHAIN_TIMEZONE_CHANGE_NEEDS_REVIEW"
        for index, interval in enumerate(intervals):
            if index == 0:
                continue
            previous = intervals[index - 1]
            base = interval["base"]
            previous_close = previous["close"]
            if (
                base.event_kind is not BatchRuleEventKind.REPLACE
                or previous_close is None
                or previous["end"] != interval["start"]
                or previous_close.rule_revision >= base.rule_revision
                or previous_close.store_timezone != base.store_timezone
                or previous_close.owner_confirmation_fingerprint
                    != base.owner_confirmation_fingerprint
                or previous_close.confirmed_at_utc != base.confirmed_at_utc
                or base.predecessor_rule_id != previous_close.rule_id
                or base.predecessor_rule_revision != previous_close.rule_revision
            ):
                return (), "RULE_CHAIN_PREDECESSOR_OR_INTERVAL_GAP"
            if interval["start"] <= previous["start"]:
                return (), "SAME_DAY_OR_REVERSED_RULE_BOUNDARY"
        return tuple(intervals), None

    @staticmethod
    def _latest_decisions(matches):
        if len(matches) < 2:
            return matches, None
        by_id = defaultdict(list)
        for item in matches:
            by_id[item["decision"].decision_id].append(item)
        latest = []
        for decision_id, items in by_id.items():
            items.sort(key=lambda item: item["decision"].revision)
            revisions = [item["decision"].revision for item in items]
            if len(revisions) != len(set(revisions)):
                return (), "DUPLICATE_MEMBERSHIP_DECISION_REVISION"
            newest = items[-1]
            if (
                len(items) > 1
                and newest["decision"].previous_decision_ref
                != f"{decision_id}-r{items[-2]['decision'].revision}"
            ):
                return (), "MEMBERSHIP_DECISION_REVISION_GAP"
            latest.append(newest)
        superseded_refs = {
            item["decision"].previous_decision_ref
            for item in latest
            if item["decision"].previous_decision_ref is not None
        }
        active = [
            item for item in latest
            if f"{item['decision'].decision_id}-r{item['decision'].revision}"
            not in superseded_refs
        ]
        return active, None

    @staticmethod
    def _same_rule_basis(base, close):
        return (
            base.scope == close.scope
            and base.case_id == close.case_id
            and base.rule_id == close.rule_id
            and base.start_local_date == close.start_local_date
            and base.store_timezone == close.store_timezone
            and base.start_day_policy is close.start_day_policy
            and base.new_unit_cost_rub == close.new_unit_cost_rub
            and base.cost_input_fingerprint == close.cost_input_fingerprint
            and base.boundary_supply_digests == close.boundary_supply_digests
        )

    @staticmethod
    def _auto_included(rule, dispatch_date):
        if dispatch_date > rule.start_local_date:
            return True
        return (
            dispatch_date == rule.start_local_date
            and rule.start_day_policy is BatchStartDayPolicy.ALL_OWNER_CONFIRMED
        )

    @staticmethod
    def _matching_decisions(candidates, observation, confirmed_dispatch_date):
        matches = []
        for item in candidates:
            rule = item["interval"]["base"]
            binding = canonical_membership_binding_fingerprint(
                scope=observation.scope,
                supply_ref_digest=observation.supply_ref_digest,
                rule_id=rule.rule_id,
                rule_revision=rule.rule_revision,
                rule_fingerprint=rule.rule_fingerprint,
                dispatch_local_date=confirmed_dispatch_date,
                owner_selected=True,
            )
            if binding == item["decision"].membership_binding_fingerprint:
                matches.append(item)
        return matches

    @staticmethod
    def _owner_decision_candidates(intervals, decisions, observation, case_id):
        interval_by_key = {
            (interval["base"].rule_id, interval["base"].rule_revision): interval
            for interval in intervals
        }
        matches = []
        for decision in decisions:
            if (
                decision.scope != observation.scope
                or decision.case_id != case_id
                or decision.source is not MembershipDecisionSource.OWNER_SELECTED_SET
                or observation.record_key not in decision.record_keys
            ):
                continue
            interval = interval_by_key.get((decision.rule_id, decision.rule_revision))
            if interval is None:
                continue
            matches.append({
                "interval": interval,
                "decision": decision,
            })
        return matches

    @classmethod
    def _result(
        cls, observation, membership, *, case_id, interval=None,
        dispatch_date=None, owner_selected=False, decision_ref=None, issue=None,
    ):
        if interval is None:
            return SupplyMembershipClassification(
                scope=observation.scope,
                case_id=case_id,
                record_key=observation.record_key,
                source_fingerprint=observation.source_fingerprint,
                membership=membership,
                dispatch_local_date=dispatch_date,
                decision_ref=decision_ref,
                issue_codes=(issue,) if issue else (),
            )
        rule = interval["base"]
        binding = canonical_membership_binding_fingerprint(
            scope=observation.scope,
            supply_ref_digest=observation.supply_ref_digest,
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            rule_fingerprint=rule.rule_fingerprint,
            dispatch_local_date=dispatch_date,
            owner_selected=owner_selected,
        )
        return SupplyMembershipClassification(
            scope=observation.scope,
            case_id=case_id,
            record_key=observation.record_key,
            source_fingerprint=observation.source_fingerprint,
            membership=membership,
            rule_id=rule.rule_id,
            rule_revision=rule.rule_revision,
            rule_fingerprint=rule.rule_fingerprint,
            dispatch_local_date=dispatch_date,
            membership_binding_fingerprint=binding,
            decision_ref=decision_ref,
            issue_codes=(issue,) if issue else (),
        )

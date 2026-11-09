"""Prepare an exact FIFO transition preview from durable owner evidence."""

from __future__ import annotations

from datetime import date, timedelta

from services.fifo_cost_financial_period_summary_collection_service import (
    FifoCostFinancialPeriodSummaryCollectionService,
)
from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceBundle,
    FifoCostTransitionEvidenceService,
)
from services.fifo_cost_transition_review_service import (
    FifoCostTransitionReviewService,
)
from services.tax_configuration_service import TaxConfigurationService


class FifoCostTransitionApplyService:
    """Rebuild and seal a preview; never applies a FIFO cost transition.

    All evidence reads are local. The only business-state write is delegated
    to ``prepare_transition_preview`` after a complete before/after impact has
    been verified. FIFO history changes only in the later, separate apply step.
    """

    _MAX_PERIODS = 200

    def __init__(
        self, transition_service, history_service, *,
        tax_configuration_service=None, evidence_service=None,
        review_service=None, impact_service=None,
        cache_invalidator=None,
    ):
        self.transition_service = transition_service
        self.history_service = history_service
        self.repository = transition_service.repository
        self.tax_configuration_service = (
            tax_configuration_service or TaxConfigurationService()
        )
        self.evidence_service = evidence_service or FifoCostTransitionEvidenceService(
            transition_service,
        )
        self.review_service = review_service or FifoCostTransitionReviewService(
            transition_service, history_service,
            evidence_service=self.evidence_service,
        )
        self.impact_service = impact_service or FifoCostLateEntryImpactService()
        self.cache_invalidator = cache_invalidator

    def prepare(
        self, *, case_id, identity, expected_case_revision, idempotency_key,
    ):
        """Seal a verified read-only impact at revision N as READY revision N+1."""
        if (
            not isinstance(identity, dict)
            or set(identity) != {"store_id", "product_id", "offer_id", "sku"}
            or type(expected_case_revision) is not int
            or expected_case_revision < 1
            or not self.repository._valid_transition_case_id(case_id)
            or not self.repository._valid_transition_idempotency_key(idempotency_key)
        ):
            return self._error("FIFO_TRANSITION_PREPARE_INPUT_INVALID")
        normalized_identity = self.repository._normalize_transition_read_identity(
            identity.get("store_id"), product_id=identity.get("product_id"),
            offer_id=identity.get("offer_id"), sku=identity.get("sku"),
        )
        if normalized_identity.get("error"):
            return normalized_identity
        identity = {
            key: normalized_identity[key]
            for key in ("store_id", "product_id", "offer_id", "sku")
        }

        current = self.transition_service.get_case(case_id=case_id, **identity)
        if not isinstance(current, dict) or current.get("error") is not False:
            return current if isinstance(current, dict) else self._error(
                "FIFO_TRANSITION_CASE_UNAVAILABLE",
            )
        if current.get("case_revision") == expected_case_revision + 1 and (
            current.get("state") == "READY_TO_CONFIRM"
        ):
            replay = self._read_idempotent_preview(
                current, case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
        if (
            current.get("case_revision") != expected_case_revision
            or current.get("state") not in {"DRAFT", "AWAITING_EVIDENCE"}
        ):
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")

        review = self.review_service.assess(
            case_id=case_id, identity=identity,
            for_transition_prepare=True,
        )
        if not isinstance(review, dict) or review.get("error") is not False:
            return review if isinstance(review, dict) else self._error(
                "FIFO_TRANSITION_READINESS_UNAVAILABLE",
            )
        if review.get("case_revision") != expected_case_revision:
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        initialized = review.get("fifo_queue_initialized") is True
        if initialized and review.get("fifo_remaining_status") == "REPLAY_REQUIRED":
            return self._error("FIFO_HISTORY_INCOMPLETE")
        blockers = self._readiness_blockers(
            review.get("readiness"), allow_initialized=initialized,
        )
        if blockers:
            return self._blocked("FIFO_TRANSITION_NOT_READY", requirements=blockers)

        loaded = self.evidence_service.load(
            case_id=case_id, identity=identity,
            expected_case_revision=expected_case_revision,
            require_opening_composition=not initialized,
        )
        if not isinstance(loaded, dict) or loaded.get("error") is not False:
            return loaded if isinstance(loaded, dict) else self._error(
                "FIFO_TRANSITION_EVIDENCE_UNAVAILABLE",
            )
        bundle = loaded.get("bundle")
        missing = tuple(loaded.get("missing_requirements", ()))
        expected_scope = self.transition_service._case_from_payload(
            current["case"],
        ).metadata.scope
        if (
            loaded.get("case_revision") != expected_case_revision
            or not isinstance(bundle, FifoCostTransitionEvidenceBundle)
            or bundle.case.case_id != case_id
            or bundle.case.case_revision != expected_case_revision
            or bundle.case.metadata.scope != expected_scope
        ):
            return self._error("FIFO_TRANSITION_EVIDENCE_SCOPE_MISMATCH")
        allowed_missing = {"FINANCIAL_PERIOD_SUMMARY_SNAPSHOT_MISSING"}
        blockers = tuple(sorted(set(missing) - allowed_missing))
        if blockers:
            return self._blocked("FIFO_TRANSITION_EVIDENCE_INCOMPLETE", requirements=blockers)
        if bundle is None:
            return self._error("FIFO_TRANSITION_EVIDENCE_INVALID")

        proposal = review.get("proposal")
        bridge_result = self.evidence_service.build_cutoff_bridge(
            bundle=bundle, proposal=proposal,
        )
        if not isinstance(bridge_result, dict) or bridge_result.get("error") is not False:
            return bridge_result if isinstance(bridge_result, dict) else self._error(
                "FIFO_CUTOFF_BRIDGE_BUILD_FAILED",
            )
        cutoff_bridge = bridge_result.get("result")
        bridge_missing = tuple(bridge_result.get("missing_requirements", ()))
        from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult

        if not isinstance(cutoff_bridge, FifoCutoffBridgeResult) or (
            getattr(cutoff_bridge, "status", None) != "READY"
        ):
            return self._blocked(
                "FIFO_CUTOFF_BRIDGE_NOT_READY",
                requirements=bridge_missing or ("CUTOFF_BRIDGE_NOT_READY",),
            )
        if (
            cutoff_bridge.case_id != case_id
            or cutoff_bridge.case_revision != expected_case_revision
            or cutoff_bridge.scope.store_id != identity["store_id"]
            or cutoff_bridge.scope.product_id != identity["product_id"]
            or cutoff_bridge.scope.offer_id != identity["offer_id"]
            or cutoff_bridge.scope.sku != identity["sku"]
        ):
            return self._error("FIFO_CUTOFF_BRIDGE_SCOPE_MISMATCH")

        effective_date = self._successor_date(cutoff_bridge.cutoff_date)
        if isinstance(effective_date, str) and effective_date.startswith("FIFO_"):
            return self._error(effective_date)
        initial_opening_cutover = None
        if not initialized:
            opening = self.transition_service.read_confirmed_opening_composition(
                case_id=case_id, **identity,
            )
            if not isinstance(opening, dict) or opening.get("error") is not False:
                return opening if isinstance(opening, dict) else self._error(
                    "FIFO_OPENING_COMPOSITION_UNAVAILABLE",
                )
            if opening.get("case_revision") != expected_case_revision:
                return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
            layers = opening.get("layers")
            if not isinstance(layers, (list, tuple)) or not layers:
                return self._error("FIFO_INITIAL_CUTOVER_LAYERS_REQUIRED")
            initial_opening_cutover = {
                "schema_version": 1,
                "case_id": case_id,
                "case_revision": expected_case_revision,
                "cutoff_date": cutoff_bridge.cutoff_date,
                "stock_report_fingerprint": opening.get(
                    "stock_report_fingerprint",
                ),
                "layers": [dict(layer) for layer in layers],
                "ozon_units_include_reserved_confirmed": True,
                "transit_not_in_ozon_confirmed": True,
            }

        try:
            tax_policy_result = self.tax_configuration_service.get_policy()
        except Exception:
            return self._error("FIFO_TAX_POLICY_UNAVAILABLE")
        tax_policy_fingerprint = self._tax_policy_fingerprint(tax_policy_result)
        if not self.repository._valid_digest(tax_policy_fingerprint):
            return self._error("FIFO_TAX_POLICY_UNAVAILABLE")
        reconstruction = self.repository.reconstruct_transition_preview(
            case_id=case_id, store_id=identity["store_id"],
            product_id=identity["product_id"], offer_id=identity["offer_id"],
            sku=identity["sku"], expected_case_revision=expected_case_revision,
            effective_date=effective_date, cutoff_bridge=cutoff_bridge,
            tax_policy_fingerprint=tax_policy_fingerprint,
            idempotency_key=idempotency_key,
            initial_opening_cutover=initial_opening_cutover,
        )
        if not isinstance(reconstruction, dict) or reconstruction.get("error") is not False:
            return reconstruction if isinstance(reconstruction, dict) else self._error(
                "FIFO_TRANSITION_RECONSTRUCTION_UNAVAILABLE",
            )

        summaries = getattr(bundle, "period_summaries", ())
        if not isinstance(summaries, tuple) or len(summaries) > self._MAX_PERIODS:
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        if any(
            getattr(summary, "complete", False) is not True
            or not callable(getattr(summary, "as_impact_summary", None))
            for summary in summaries
        ):
            return self._error("FIFO_PERIOD_SUMMARY_SNAPSHOT_INVALID")
        impact = self.impact_service.preview(
            reconstruction=reconstruction,
            period_summaries=[summary.as_impact_summary() for summary in summaries],
            tax_policy_result=tax_policy_result,
        )
        if not isinstance(impact, dict) or impact.get("error") is not False:
            return impact if isinstance(impact, dict) else self._error(
                "FIFO_TRANSITION_IMPACT_UNAVAILABLE",
            )
        if impact.get("candidate_only") is True or impact.get("complete") is not True:
            return {
                "error": False,
                "code": "FIFO_TRANSITION_CANDIDATE_ONLY",
                "case_id": case_id,
                "case_revision": expected_case_revision,
                "candidate_total_cogs_rub": impact.get("candidate_total_cogs_rub"),
                "reason_code": impact.get("reason_code"),
                "impact_preview": impact,
                "read_only": True,
                "fifo_history_changed": False,
                "period_profit_changed": False,
                "case_state_changed": False,
            }

        impact_tax_fingerprint = impact.get("tax_policy_fingerprint")
        if not self.repository._valid_digest(impact_tax_fingerprint):
            return self._error("FIFO_TAX_POLICY_FINGERPRINT_INVALID")
        prepared = self.repository.prepare_transition_preview(
            case_id=case_id, store_id=identity["store_id"],
            product_id=identity["product_id"], offer_id=identity["offer_id"],
            sku=identity["sku"], expected_case_revision=expected_case_revision,
            effective_date=effective_date, cutoff_bridge=cutoff_bridge,
            impact_preview=impact,
            tax_policy_fingerprint=impact_tax_fingerprint,
            idempotency_key=idempotency_key,
            initial_opening_cutover=initial_opening_cutover,
        )
        if not isinstance(prepared, dict) or prepared.get("error") is not False:
            return prepared if isinstance(prepared, dict) else self._error(
                "FIFO_TRANSITION_PREVIEW_SEAL_FAILED",
            )
        return {
            "error": False,
            "code": "FIFO_TRANSITION_PREVIEW_READY",
            "case_id": case_id,
            "case_revision": prepared.get("case_revision"),
            "preview_id": prepared.get("preview_id"),
            "preview_fingerprint": prepared.get("preview_fingerprint"),
            "effective_date": effective_date,
            "candidate_cogs_rub": prepared.get("candidate_cogs_rub"),
            "complete_through": prepared.get("complete_through"),
            "impact_preview": impact,
            "case_state": "READY_TO_CONFIRM",
            "fifo_history_changed": False,
            "period_profit_changed": False,
            "case_state_changed": prepared.get("replayed") is not True,
            "replayed": prepared.get("replayed") is True,
        }

    def read_preview(self, *, case_id, identity, preview_id):
        if (
            not isinstance(identity, dict)
            or set(identity) != {"store_id", "product_id", "offer_id", "sku"}
            or not self.repository._valid_transition_case_id(case_id)
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_INPUT_INVALID")
        normalized_identity = self.repository._normalize_transition_read_identity(
            identity.get("store_id"), product_id=identity.get("product_id"),
            offer_id=identity.get("offer_id"), sku=identity.get("sku"),
        )
        if normalized_identity.get("error"):
            return normalized_identity
        identity = {
            key: normalized_identity[key]
            for key in ("store_id", "product_id", "offer_id", "sku")
        }
        result = self.repository.read_transition_preview(
            case_id=case_id, preview_id=preview_id, **identity,
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return result if isinstance(result, dict) else self._error(
                "FIFO_TRANSITION_PREVIEW_UNAVAILABLE",
            )
        preview = result.get("preview")
        sealed = result.get("sealed_preview")
        if not isinstance(preview, dict) or not isinstance(sealed, dict):
            return self._error("FIFO_TRANSITION_PREVIEW_CORRUPT")
        return {
            "error": False,
            "code": "FIFO_TRANSITION_PREVIEW_READ",
            "case_id": case_id,
            "case_revision": sealed.get("case_revision"),
            "basis_case_revision": preview.get("case_revision"),
            "preview_id": preview_id,
            "preview_fingerprint": sealed.get("preview_fingerprint"),
            "expires_at": sealed.get("expires_at"),
            "current_case_revision": result.get("current_case_revision"),
            "current_case_state": result.get("current_case_state"),
            "is_current": result.get("is_current") is True,
            "expired": result.get("expired") is True,
            "preview": preview,
            "read_only": True,
        }

    def read_commit(self, *, case_id, identity):
        """Read the exact durable receipt for an APPLIED case after restart."""
        if (
            not isinstance(identity, dict)
            or set(identity) != {"store_id", "product_id", "offer_id", "sku"}
            or not self.repository._valid_transition_case_id(case_id)
        ):
            return self._error("FIFO_TRANSITION_COMMIT_INPUT_INVALID")
        current = self.transition_service.get_case(case_id=case_id, **identity)
        if (
            not isinstance(current, dict) or current.get("error") is not False
            or current.get("state") != "APPLIED"
            or type(current.get("case_revision")) is not int
            or current["case_revision"] < 3
        ):
            return self._error("FIFO_TRANSITION_COMMIT_UNAVAILABLE")
        payload = current.get("case")
        last_commit = payload.get("last_commit") if isinstance(payload, dict) else None
        if not isinstance(last_commit, dict):
            return self._error("FIFO_TRANSITION_COMMIT_CORRUPT")
        preview_id = last_commit.get("preview_id")
        if not isinstance(preview_id, str):
            return self._error("FIFO_TRANSITION_COMMIT_CORRUPT")
        stored = self.read_preview(
            case_id=case_id, identity=identity, preview_id=preview_id,
        )
        if not isinstance(stored, dict) or stored.get("error") is not False:
            return stored if isinstance(stored, dict) else self._error(
                "FIFO_TRANSITION_PREVIEW_UNAVAILABLE",
            )
        preview = stored.get("preview")
        preview_fingerprint = stored.get("preview_fingerprint")
        idempotency_key = last_commit.get("idempotency_key")
        ready_revision = current["case_revision"] - 1
        if (
            stored.get("case_revision") != ready_revision
            or not isinstance(preview, dict)
            or preview.get("case_revision") != ready_revision - 1
            or not self.repository._valid_digest(preview_fingerprint)
            or not self.repository._valid_transition_idempotency_key(idempotency_key)
        ):
            return self._error("FIFO_TRANSITION_COMMIT_CORRUPT")
        result = self.repository.read_transition_commit(
            case_id=case_id, **identity,
            expected_case_revision=ready_revision,
            preview_id=preview_id,
            preview_fingerprint=preview_fingerprint,
            idempotency_key=idempotency_key,
        )
        if (
            not isinstance(result, dict) or result.get("error") is not False
            or result.get("found") is not True
            or not isinstance(result.get("result"), dict)
            or result["result"].get("case_revision") != current["case_revision"]
            or result["result"].get("preview_id") != preview_id
        ):
            return result if isinstance(result, dict) and result.get("error") is True else self._error(
                "FIFO_TRANSITION_COMMIT_UNAVAILABLE",
            )
        return {**result["result"], "read_only": True}

    def apply(
        self, *, case_id, identity, expected_case_revision, expected_preview_id,
        expected_preview_fingerprint, idempotency_key,
    ):
        """Recheck one exact READY seal, then atomically apply it once."""
        if (
            not isinstance(identity, dict)
            or set(identity) != {"store_id", "product_id", "offer_id", "sku"}
            or type(expected_case_revision) is not int
            or expected_case_revision < 2
            or not self.repository._valid_transition_case_id(case_id)
            or not isinstance(expected_preview_id, str)
            or not self.repository._valid_digest(expected_preview_fingerprint)
            or not self.repository._valid_transition_idempotency_key(idempotency_key)
        ):
            return self._error("FIFO_TRANSITION_APPLY_INPUT_INVALID")
        normalized_identity = self.repository._normalize_transition_read_identity(
            identity.get("store_id"), product_id=identity.get("product_id"),
            offer_id=identity.get("offer_id"), sku=identity.get("sku"),
        )
        if normalized_identity.get("error"):
            return normalized_identity
        identity = {
            key: normalized_identity[key]
            for key in ("store_id", "product_id", "offer_id", "sku")
        }

        # A committed exact retry is resolved before current tax/source/TTL
        # checks: mutable evidence must not turn a successful commit into a
        # second write or make a lost response impossible to recover.
        prior = self.repository.read_transition_commit(
            case_id=case_id, **identity,
            expected_case_revision=expected_case_revision,
            preview_id=expected_preview_id,
            preview_fingerprint=expected_preview_fingerprint,
            idempotency_key=idempotency_key,
        )
        if not isinstance(prior, dict) or prior.get("error") is not False:
            return prior if isinstance(prior, dict) else self._error(
                "FIFO_TRANSITION_COMMIT_UNAVAILABLE",
            )
        sealed_read = self.read_preview(
            case_id=case_id, identity=identity, preview_id=expected_preview_id,
        )
        if not isinstance(sealed_read, dict) or sealed_read.get("error") is not False:
            return sealed_read if isinstance(sealed_read, dict) else self._error(
                "FIFO_TRANSITION_PREVIEW_UNAVAILABLE",
            )
        preview = sealed_read.get("preview")
        if (
            not isinstance(preview, dict)
            or sealed_read.get("case_revision") != expected_case_revision
            or sealed_read.get("preview_fingerprint") != expected_preview_fingerprint
            or preview.get("case_revision") != expected_case_revision - 1
        ):
            recovered = self._recover_committed_retry(
                case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key,
                preview=preview if isinstance(preview, dict) else {},
            )
            if recovered is not None:
                return recovered
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        if prior.get("found") is True:
            result = prior.get("result")
            if not isinstance(result, dict) or result.get("error") is not False:
                return self._error("FIFO_TRANSITION_COMMIT_CORRUPT")
            return self._with_cache_invalidation(
                result, case_id=case_id, identity=identity, preview=preview,
            )
        if sealed_read.get("expired") is True:
            return self._error("FIFO_TRANSITION_PREVIEW_EXPIRED")
        if sealed_read.get("is_current") is not True or (
            sealed_read.get("current_case_revision") != expected_case_revision
            or sealed_read.get("current_case_state") != "READY_TO_CONFIRM"
        ):
            recovered = self._recover_committed_retry(
                case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key,
                preview=preview,
            )
            if recovered is not None:
                return recovered
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        current = self.transition_service.get_case(case_id=case_id, **identity)
        if (
            not isinstance(current, dict)
            or current.get("error") is not False
            or current.get("case_revision") != expected_case_revision
            or current.get("state") != "READY_TO_CONFIRM"
        ):
            recovered = self._recover_committed_retry(
                case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key,
                preview=preview,
            )
            if recovered is not None:
                return recovered
            return self._error("FIFO_TRANSITION_REVISION_CONFLICT")
        basis_revision = expected_case_revision - 1
        review = self.review_service.assess(
            case_id=case_id, identity=identity,
            for_transition_prepare=True,
            sealed_preview_id=expected_preview_id,
        )
        if not isinstance(review, dict) or review.get("error") is not False:
            failure = review if isinstance(review, dict) else self._error(
                "FIFO_TRANSITION_READINESS_UNAVAILABLE",
            )
            return self._failure_or_committed_retry(
                failure, case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key, preview=preview,
            )
        if (
            review.get("case_revision") != basis_revision
            or review.get("current_case_revision") != expected_case_revision
            or review.get("case_state") != "READY_TO_CONFIRM"
        ):
            return self._failure_or_committed_retry(
                self._error("FIFO_TRANSITION_PREVIEW_STALE"),
                case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key, preview=preview,
            )
        initialized = review.get("fifo_queue_initialized") is True
        if initialized and review.get("fifo_remaining_status") == "REPLAY_REQUIRED":
            return self._error("FIFO_HISTORY_INCOMPLETE")
        blockers = self._readiness_blockers(
            review.get("readiness"), allow_initialized=initialized,
        )
        if blockers:
            return self._blocked("FIFO_TRANSITION_NOT_READY", requirements=blockers)

        loaded = self.evidence_service.load(
            case_id=case_id, identity=identity,
            expected_case_revision=basis_revision,
            require_opening_composition=not initialized,
            sealed_preview_id=expected_preview_id,
        )
        if not isinstance(loaded, dict) or loaded.get("error") is not False:
            return loaded if isinstance(loaded, dict) else self._error(
                "FIFO_TRANSITION_EVIDENCE_UNAVAILABLE",
            )
        bundle = loaded.get("bundle")
        if (
            not isinstance(bundle, FifoCostTransitionEvidenceBundle)
            or bundle.case.case_id != case_id
            or bundle.case.case_revision != basis_revision
            or bundle.case.metadata.scope != self.transition_service._case_from_payload(
                current["case"],
            ).metadata.scope
            or loaded.get("case_revision") != basis_revision
            or loaded.get("missing_requirements")
        ):
            return self._blocked(
                "FIFO_TRANSITION_EVIDENCE_INCOMPLETE",
                requirements=tuple(loaded.get("missing_requirements", ())) or (
                    "SEALED_EVIDENCE_BASIS_MISMATCH",
                ),
            )
        bridge_result = self.evidence_service.build_cutoff_bridge(
            bundle=bundle, proposal=review.get("proposal"),
        )
        if not isinstance(bridge_result, dict) or bridge_result.get("error") is not False:
            return bridge_result if isinstance(bridge_result, dict) else self._error(
                "FIFO_CUTOFF_BRIDGE_BUILD_FAILED",
            )
        cutoff_bridge = bridge_result.get("result")
        from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult

        if (
            not isinstance(cutoff_bridge, FifoCutoffBridgeResult)
            or cutoff_bridge.status != "READY"
            or cutoff_bridge.case_id != case_id
            or cutoff_bridge.case_revision != basis_revision
            or cutoff_bridge.source_set_fingerprint != preview.get(
                "bridge_fingerprint",
            )
            or cutoff_bridge.scope != bundle.case.metadata.scope
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")

        try:
            tax_policy_result = self.tax_configuration_service.get_policy()
        except Exception:
            return self._error("FIFO_TAX_POLICY_UNAVAILABLE")
        current_tax_fingerprint = self._tax_policy_fingerprint(tax_policy_result)
        if (
            not self.repository._valid_digest(current_tax_fingerprint)
            or current_tax_fingerprint != preview.get("tax_policy_fingerprint")
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        reconstruction = self.repository.reconstruct_transition_preview(
            case_id=case_id, **identity,
            expected_case_revision=basis_revision,
            effective_date=preview.get("effective_date"),
            cutoff_bridge=cutoff_bridge,
            impact_preview=None,
            tax_policy_fingerprint=current_tax_fingerprint,
            idempotency_key=preview.get("idempotency_key"),
            initial_opening_cutover=preview.get("initial_opening_cutover"),
        )
        if (
            not isinstance(reconstruction, dict)
            or reconstruction.get("error") is not False
            or reconstruction.get("code") != "FIFO_TRANSITION_RECONSTRUCTION_READY"
        ):
            failure = reconstruction if isinstance(reconstruction, dict) else self._error(
                "FIFO_TRANSITION_RECONSTRUCTION_UNAVAILABLE",
            )
            return self._failure_or_committed_retry(
                failure, case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key, preview=preview,
            )
        summaries = getattr(bundle, "period_summaries", ())
        impact = self.impact_service.preview(
            reconstruction=reconstruction,
            period_summaries=[summary.as_impact_summary() for summary in summaries],
            tax_policy_result=tax_policy_result,
        )
        stored_impact = preview.get("impact_preview")
        if (
            not isinstance(impact, dict)
            or impact.get("error") is not False
            or impact.get("candidate_only") is True
            or impact.get("complete") is not True
            or not isinstance(stored_impact, dict)
            or impact.get("preview_fingerprint")
                != stored_impact.get("preview_fingerprint")
            or impact.get("reconstruction_fingerprint")
                != reconstruction.get("preview_fingerprint")
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        committed = self.repository.commit_transition_case(
            case_id=case_id, **identity,
            expected_case_revision=expected_case_revision,
            preview_id=expected_preview_id,
            idempotency_key=idempotency_key,
            cutoff_bridge=cutoff_bridge,
            impact_preview=impact,
            current_tax_policy_fingerprint=current_tax_fingerprint,
        )
        if not isinstance(committed, dict) or committed.get("error") is not False:
            failure = committed if isinstance(committed, dict) else self._error(
                "FIFO_TRANSITION_COMMIT_UNAVAILABLE",
            )
            return self._failure_or_committed_retry(
                failure, case_id=case_id, identity=identity,
                expected_case_revision=expected_case_revision,
                preview_id=expected_preview_id,
                preview_fingerprint=expected_preview_fingerprint,
                idempotency_key=idempotency_key, preview=preview,
            )
        return self._with_cache_invalidation(
            committed, case_id=case_id, identity=identity, preview=preview,
        )

    def _with_cache_invalidation(self, result, *, case_id, identity, preview):
        if not callable(self.cache_invalidator):
            return {**result, "cache_invalidation": "NOT_CONFIGURED"}
        if (
            not isinstance(preview, dict)
            or type(preview.get("base_fifo_revision")) is not int
            or preview["base_fifo_revision"] < 0
            or type(preview.get("base_allocation_revision")) is not int
            or preview["base_allocation_revision"] < 0
        ):
            return {**result, "cache_invalidation": "FAILED"}
        try:
            invalidated = self.cache_invalidator(
                identity=dict(identity),
                case_id=case_id,
                case_revision=result.get("case_revision"),
                fifo_revision=preview.get("base_fifo_revision", 0) + 1,
                allocation_revision=preview.get("base_allocation_revision", 0) + 1,
            )
            if isinstance(invalidated, dict) and invalidated.get("error") is True:
                return {**result, "cache_invalidation": "FAILED"}
            return {**result, "cache_invalidation": "COMPLETED"}
        except Exception:
            # The FIFO commit is already durable. Report invalidation separately
            # so callers can retry the idempotent invalidation without replaying
            # or duplicating business writes.
            return {**result, "cache_invalidation": "FAILED"}

    def _recover_committed_retry(
        self, *, case_id, identity, expected_case_revision,
        preview_id, preview_fingerprint, idempotency_key, preview,
    ):
        """Recover the exact commit if it won a concurrent same-key race."""
        prior = self.repository.read_transition_commit(
            case_id=case_id, **identity,
            expected_case_revision=expected_case_revision,
            preview_id=preview_id,
            preview_fingerprint=preview_fingerprint,
            idempotency_key=idempotency_key,
        )
        if not isinstance(prior, dict) or prior.get("error") is not False:
            return prior if isinstance(prior, dict) else self._error(
                "FIFO_TRANSITION_COMMIT_UNAVAILABLE",
            )
        if prior.get("found") is not True:
            return None
        result = prior.get("result")
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._error("FIFO_TRANSITION_COMMIT_CORRUPT")
        return self._with_cache_invalidation(
            result, case_id=case_id, identity=identity, preview=preview,
        )

    def _failure_or_committed_retry(self, failure, **retry_context):
        recovered = self._recover_committed_retry(**retry_context)
        return recovered if recovered is not None else failure

    def _read_idempotent_preview(
        self, current, *, case_id, identity, expected_case_revision,
        idempotency_key,
    ):
        case_payload = current.get("case")
        last_preview = (
            case_payload.get("last_preview")
            if isinstance(case_payload, dict) else None
        )
        if (
            not isinstance(last_preview, dict)
            or last_preview.get("idempotency_key") != idempotency_key
        ):
            return None
        preview_id = last_preview.get("preview_id")
        stored = self.repository.read_transition_preview(
            case_id=case_id, preview_id=preview_id, **identity,
        )
        if not isinstance(stored, dict) or stored.get("error") is not False:
            return stored if isinstance(stored, dict) else self._error(
                "FIFO_TRANSITION_PREVIEW_CORRUPT",
            )
        preview = stored.get("preview")
        if (
            not stored.get("is_current")
            or stored.get("expired")
            or not isinstance(preview, dict)
            or preview.get("case_revision") != expected_case_revision
            or preview.get("idempotency_key") != idempotency_key
        ):
            return self._error(
                "FIFO_TRANSITION_PREVIEW_EXPIRED" if stored.get("expired")
                else "FIFO_TRANSITION_PREVIEW_STALE",
            )
        try:
            current_policy_fingerprint = self._tax_policy_fingerprint(
                self.tax_configuration_service.get_policy(),
            )
        except Exception:
            return self._error("FIFO_TAX_POLICY_UNAVAILABLE")
        if current_policy_fingerprint != preview.get("tax_policy_fingerprint"):
            return self._error("FIFO_TRANSITION_PREVIEW_STALE")
        return {
            "error": False,
            "code": "FIFO_TRANSITION_PREVIEW_READY",
            "case_id": case_id,
            "case_revision": current["case_revision"],
            "preview_id": preview_id,
            "effective_date": preview.get("effective_date"),
            "candidate_cogs_rub": preview.get("allocation_preview", {}).get(
                "total_cogs_rub",
            ),
            "complete_through": preview.get("complete_through"),
            "case_state": "READY_TO_CONFIRM",
            "fifo_history_changed": False,
            "period_profit_changed": False,
            "case_state_changed": False,
            "replayed": True,
        }

    @classmethod
    def _readiness_blockers(cls, readiness, *, allow_initialized):
        requirements = getattr(readiness, "requirements", None)
        if not isinstance(requirements, tuple):
            return ("TRANSITION_READINESS_UNAVAILABLE",)
        result = []
        ignored_initialized = False
        for requirement in requirements:
            code = getattr(requirement, "code", None)
            blocks_apply = getattr(requirement, "blocks_apply", None)
            if not isinstance(code, str) or type(blocks_apply) is not bool:
                return ("TRANSITION_READINESS_INVALID",)
            if not blocks_apply:
                continue
            if allow_initialized and code == "FIFO_ALREADY_INITIALIZED":
                ignored_initialized = True
                continue
            result.append(code)
        status = getattr(readiness, "status", None)
        if status == "CONFLICT" and not result and not ignored_initialized:
            result.append("TRANSITION_READINESS_CONFLICT")
        elif status != "PREVIEW_READY" and not result:
            result.append("TRANSITION_READINESS_INCOMPLETE")
        return tuple(sorted(set(result)))

    @classmethod
    def _tax_policy_fingerprint(cls, tax_policy_result):
        normalized = FifoCostLateEntryImpactService._normalize_policy(
            tax_policy_result,
        )
        if isinstance(normalized, str):
            return None
        return normalized["fingerprint"]

    @staticmethod
    def _successor_date(value):
        try:
            normalized = date.fromisoformat(value)
            if normalized.isoformat() != value:
                raise ValueError
            return (normalized + timedelta(days=1)).isoformat()
        except (TypeError, ValueError, OverflowError):
            return "FIFO_CUTOFF_DATE_INVALID"

    @staticmethod
    def _blocked(code, *, requirements):
        return {
            "error": False,
            "code": code,
            "requirements": tuple(requirements),
            "read_only": True,
            "period_profit_changed": False,
            "case_state_changed": False,
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}

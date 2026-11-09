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
        ):
            return self._error("FIFO_TRANSITION_PREVIEW_INPUT_INVALID")
        return self.repository.read_transition_preview(
            case_id=case_id, preview_id=preview_id, **identity,
        )

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
        current_policy_fingerprint = self._tax_policy_fingerprint(
            self.tax_configuration_service.get_policy(),
        )
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

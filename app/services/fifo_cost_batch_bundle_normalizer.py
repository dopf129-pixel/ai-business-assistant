"""Fail-closed boundary for normalized per-SKU supply composition.

The raw Ozon bundle response schema is not verified. This module accepts only
the repository's typed observation contract; it never interprets raw JSON keys.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from services.fifo_cost_batch_rule_contracts import SupplySkuObservation
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
)


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_ROWS = 10_000


@dataclass(frozen=True, slots=True)
class FifoCostBatchSupplyCompositionResult:
    status: str
    source_status: str
    read_only: bool
    actual_http_attempts: int
    case_revision: int | None
    rule_revision: int | None
    planned_quantity: int | None
    shipped_quantity: int | None
    planned_explicit_zero: bool
    shipped_explicit_zero: bool
    issue_codes: tuple[str, ...]


class FifoCostBatchBundleNormalizer:
    """Map already-normalized typed rows to one exact owner/store/SKU scope."""

    @classmethod
    def normalize(
        cls,
        scope: ScopeIdentity,
        supply_ref_digest: str,
        observations: Sequence[SupplySkuObservation] | None,
        *,
        composition_complete: bool,
    ) -> FifoCostBatchSupplyCompositionResult:
        if (
            not isinstance(scope, ScopeIdentity)
            or not isinstance(supply_ref_digest, str)
            or not _DIGEST.fullmatch(supply_ref_digest)
            or type(composition_complete) is not bool
        ):
            return cls._unknown("FIFO_BATCH_BUNDLE_SCOPE_INVALID")
        if not isinstance(observations, (tuple, list)) or len(observations) > _MAX_ROWS:
            return cls._unknown("FIFO_BATCH_BUNDLE_NORMALIZED_ROWS_INVALID")
        if not observations:
            return cls._unknown("FIFO_BATCH_BUNDLE_COMPOSITION_EMPTY")

        matching: list[SupplySkuObservation] = []
        expected_order_ref = None
        seen_scope_keys: set[tuple[str, str, str]] = set()
        seen_record_keys: set[str] = set()
        profile_versions: set[str] = set()
        for observation in observations:
            if not isinstance(observation, SupplySkuObservation):
                return cls._unknown("FIFO_BATCH_BUNDLE_NORMALIZED_ROWS_INVALID")
            row_scope = observation.scope
            if (
                row_scope.owner_id != scope.owner_id
                or row_scope.store_id != scope.store_id
                or observation.supply_ref_digest != supply_ref_digest
                or observation.quantity_source_kind is not EvidenceSourceKind.OZON_API
            ):
                return cls._unknown("FIFO_BATCH_BUNDLE_SCOPE_MISMATCH")
            if expected_order_ref is None:
                expected_order_ref = observation.order_ref_digest
            elif observation.order_ref_digest != expected_order_ref:
                return cls._unknown("FIFO_BATCH_BUNDLE_ORDER_MAPPING_CONFLICT")
            if observation.record_key in seen_record_keys:
                return cls._unknown("FIFO_BATCH_BUNDLE_DUPLICATE_RECORD")
            seen_record_keys.add(observation.record_key)
            profile_versions.add(observation.source_profile_version)

            row_key = (row_scope.product_id, row_scope.offer_id, row_scope.sku)
            if row_key in seen_scope_keys:
                return cls._unknown("FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING")
            seen_scope_keys.add(row_key)

            if row_scope.sku == scope.sku:
                if row_scope != scope:
                    return cls._unknown("FIFO_BATCH_BUNDLE_SKU_MAPPING_CONFLICT")
                matching.append(observation)

        if len(profile_versions) != 1:
            return cls._unknown("FIFO_BATCH_BUNDLE_SOURCE_PROFILE_MISMATCH")
        if len(matching) != 1:
            return cls._unknown(
                "FIFO_BATCH_BUNDLE_SKU_MAPPING_CONFLICT"
                if matching else "FIFO_BATCH_BUNDLE_TARGET_SKU_NOT_FOUND"
            )

        observation = matching[0]
        planned_zero = "planned_declared_quantity" in observation.explicit_zero_fields
        shipped_zero = "shipped_composition_quantity" in observation.explicit_zero_fields
        if (
            observation.planned_declared_quantity == 0 and not planned_zero
        ) or (
            observation.shipped_composition_quantity == 0 and not shipped_zero
        ):
            return cls._unknown("FIFO_BATCH_BUNDLE_ZERO_WITHOUT_PROOF")

        complete = (
            composition_complete
            and observation.quantity_coverage is EvidenceCompleteness.COMPLETE
            and observation.planned_declared_quantity is not None
            and observation.shipped_composition_quantity is not None
        )
        return FifoCostBatchSupplyCompositionResult(
            status="COMPLETE" if complete else "PARTIAL",
            source_status="NORMALIZED",
            read_only=True,
            actual_http_attempts=0,
            case_revision=None,
            rule_revision=None,
            planned_quantity=observation.planned_declared_quantity,
            shipped_quantity=observation.shipped_composition_quantity,
            planned_explicit_zero=planned_zero,
            shipped_explicit_zero=shipped_zero,
            issue_codes=() if complete else ("FIFO_BATCH_BUNDLE_COMPOSITION_INCOMPLETE",),
        )

    @staticmethod
    def _unknown(issue_code: str) -> FifoCostBatchSupplyCompositionResult:
        return FifoCostBatchSupplyCompositionResult(
            status="UNKNOWN",
            source_status="NOT_VERIFIED",
            read_only=True,
            actual_http_attempts=0,
            case_revision=None,
            rule_revision=None,
            planned_quantity=None,
            shipped_quantity=None,
            planned_explicit_zero=False,
            shipped_explicit_zero=False,
            issue_codes=(issue_code,),
        )

    @classmethod
    def unknown(
        cls, issue_code: str, *, case_revision: int | None = None,
        rule_revision: int | None = None, status: str = "UNKNOWN",
        source_status: str = "NOT_VERIFIED",
    ) -> FifoCostBatchSupplyCompositionResult:
        result = cls._unknown(issue_code)
        return FifoCostBatchSupplyCompositionResult(
            status=status,
            source_status=source_status,
            read_only=result.read_only,
            actual_http_attempts=result.actual_http_attempts,
            case_revision=case_revision,
            rule_revision=rule_revision,
            planned_quantity=result.planned_quantity,
            shipped_quantity=result.shipped_quantity,
            planned_explicit_zero=result.planned_explicit_zero,
            shipped_explicit_zero=result.shipped_explicit_zero,
            issue_codes=result.issue_codes,
        )

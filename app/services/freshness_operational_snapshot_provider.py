from copy import deepcopy


ARTIFACTS = (
    ("preparation_audit", "get_preparation_audit"),
    ("executor_admission_audit", "get_executor_admission_audit"),
    ("write_protocol_audit", "get_write_protocol_audit"),
    ("adapter_boundary_audit", "get_adapter_boundary_audit"),
)


class FreshnessOperationalSnapshotProvider:
    """Read-only aggregation boundary for canonical freshness lifecycle audits."""

    def __init__(self, reader):
        self.reader = reader

    def get_snapshot(self):
        if self.reader is None:
            raise RuntimeError("FRESHNESS_OPERATIONAL_READER_REQUIRED")

        snapshot = {}
        for field, method_name in ARTIFACTS:
            method = getattr(self.reader, method_name, None)
            if method is None or not callable(method):
                raise RuntimeError("FRESHNESS_OPERATIONAL_READER_CAPABILITY_MISSING:{}".format(method_name))
            value = method()
            if value is not None and not isinstance(value, dict):
                raise RuntimeError("FRESHNESS_OPERATIONAL_ARTIFACT_MALFORMED:{}".format(field))
            snapshot[field] = deepcopy(value)

        return snapshot

"""Allowlisted control-condition events for price experiments."""

import re


class UnitEconomicsExperimentControlService:
    """Normalize owner-reported control conditions without claiming verification."""

    SCHEMA_VERSION = 1
    CONTROL_KEYS = (
        "advertising", "card", "cost", "inventory", "promotion", "tariff",
    )
    FLAG_VALUES = frozenset({
        "UNCHANGED", "CHANGED", "UNKNOWN", "NOT_APPLICABLE",
    })

    @classmethod
    def normalize_flags(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.CONTROL_KEYS):
            return None
        if any(not isinstance(flag, str) or flag not in cls.FLAG_VALUES
               for flag in value.values()):
            return None
        return {key: value[key] for key in cls.CONTROL_KEYS}

    @classmethod
    def normalize_event(cls, payload, *, expected_phase_id=None):
        fields = {
            "schema_version", "event_kind", "phase_id", "control_flags", "source",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.SCHEMA_VERSION
                or payload.get("event_kind") != "CONTROL_UPDATE"
                or payload.get("source") != "OWNER_REPORTED"):
            return None
        phase_id = payload.get("phase_id")
        if (not isinstance(phase_id, str)
                or re.fullmatch(r"[a-f0-9]{32}", phase_id) is None
                or (expected_phase_id is not None and phase_id != expected_phase_id)):
            return None
        flags = cls.normalize_flags(payload.get("control_flags"))
        if flags is None:
            return None
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "event_kind": "CONTROL_UPDATE",
            "phase_id": phase_id,
            "control_flags": flags,
            "source": "OWNER_REPORTED",
            "compatibility": cls.compatibility(flags),
        }

    @classmethod
    def compatibility(cls, *flag_snapshots):
        reasons = set()
        for snapshot in flag_snapshots:
            flags = cls.normalize_flags(snapshot)
            if flags is None:
                return {
                    "status": "UNKNOWN", "reason_codes": [
                        "EXPERIMENT_CONTROL_FLAGS_INVALID",
                    ],
                }
            for key, value in flags.items():
                if value == "CHANGED":
                    reasons.add(f"EXPERIMENT_CONTROL_CHANGED_{key.upper()}")
                elif value == "UNKNOWN":
                    reasons.add(f"EXPERIMENT_CONTROL_UNKNOWN_{key.upper()}")
        ordered = sorted(reasons)
        return {
            "status": "INCOMPATIBLE" if ordered else "COMPATIBLE",
            "reason_codes": ordered,
        }

    @classmethod
    def normalize_pause_event(cls, payload, *, expected_phase_id=None):
        fields = {
            "schema_version", "event_kind", "phase_id", "observation_id",
            "resume_target", "source",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.SCHEMA_VERSION
                or payload.get("event_kind") != "PAUSE"
                or payload.get("source") != "OWNER_ACTION"
                or payload.get("resume_target") not in {"READY", "CANDIDATE_READY"}):
            return None
        phase_id, observation_id = payload.get("phase_id"), payload.get("observation_id")
        if any(not isinstance(value, str)
               or re.fullmatch(r"[a-f0-9]{32}", value) is None
               for value in (phase_id, observation_id)):
            return None
        if expected_phase_id is not None and phase_id != expected_phase_id:
            return None
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "event_kind": "PAUSE", "phase_id": phase_id,
            "observation_id": observation_id,
            "resume_target": payload["resume_target"], "source": "OWNER_ACTION",
        }

    @classmethod
    def normalize_resume_event(cls, payload, *, expected_resume_target=None):
        fields = {
            "schema_version", "event_kind", "previous_phase_id", "phase_id",
            "resume_target", "source",
        }
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != cls.SCHEMA_VERSION
                or payload.get("event_kind") != "RESUME_SEGMENT_PREPARED"
                or payload.get("source") != "OWNER_ACTION"
                or payload.get("resume_target") not in {"READY", "CANDIDATE_READY"}
                or (expected_resume_target is not None
                    and payload.get("resume_target") != expected_resume_target)):
            return None
        previous_phase_id, phase_id = (
            payload.get("previous_phase_id"), payload.get("phase_id"),
        )
        if any(not isinstance(value, str)
               or re.fullmatch(r"[a-f0-9]{32}", value) is None
               for value in (previous_phase_id, phase_id)) or previous_phase_id == phase_id:
            return None
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "event_kind": "RESUME_SEGMENT_PREPARED",
            "previous_phase_id": previous_phase_id, "phase_id": phase_id,
            "resume_target": payload["resume_target"], "source": "OWNER_ACTION",
        }

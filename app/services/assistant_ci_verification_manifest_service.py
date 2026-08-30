import hashlib
import json
import re
import xml.etree.ElementTree as ET

from services.assistant_test_runner_service import AssistantTestRunnerService


class AssistantCiVerificationManifestService:
    """Build and validate deterministic SHA-bound verification manifests."""

    SCHEMA_VERSION = 1

    def __init__(self, test_runner_service=None):
        self.test_runner_service = (
            test_runner_service
            or AssistantTestRunnerService()
        )

    def build_from_junit(
        self,
        junit_path,
        commit_sha,
        workflow,
        event,
        run_id,
        run_number,
    ):
        sha = self._sha(commit_sha)
        metadata = self._metadata(
            workflow=workflow,
            event=event,
            run_id=run_id,
            run_number=run_number,
        )
        if sha is None:
            return self._error_manifest(
                "CI_VERIFICATION_COMMIT_SHA_INVALID",
                commit_sha=None,
                metadata=metadata,
            )
        if metadata is None:
            return self._error_manifest(
                "CI_VERIFICATION_METADATA_INVALID",
                commit_sha=sha,
                metadata=None,
            )

        counts = self._read_junit_counts(junit_path)
        if counts is None:
            return self._error_manifest(
                "CI_VERIFICATION_JUNIT_INVALID",
                commit_sha=sha,
                metadata=metadata,
            )

        report = self.test_runner_service.create_test_report(
            passed=counts["passed"],
            failed=counts["failed"],
            total=counts["total"],
            commit_sha=sha,
        )
        if report.get("error") is not False:
            return self._error_manifest(
                "CI_VERIFICATION_TEST_REPORT_INVALID",
                commit_sha=sha,
                metadata=metadata,
            )

        payload = {
            "schema_version": self.SCHEMA_VERSION,
            **report,
            "skipped": counts["skipped"],
            "junit_tests": counts["junit_tests"],
            "junit_failures": counts["junit_failures"],
            "junit_errors": counts["junit_errors"],
            "workflow": metadata["workflow"],
            "event": metadata["event"],
            "run_id": metadata["run_id"],
            "run_number": metadata["run_number"],
            "junit_source": "verification-artifacts/pytest-junit.xml",
            "read_only_evidence": True,
            "business_execution": False,
            "ozon_mutation": False,
        }
        payload["verification_manifest_id"] = self._manifest_id(payload)
        return payload

    def validate(self, manifest):
        source = dict(manifest) if isinstance(manifest, dict) else {}
        if source.get("schema_version") != self.SCHEMA_VERSION:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_SCHEMA_INVALID"
            )
        if source.get("error") is not False:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_NOT_SUCCESSFUL"
            )

        sha = self._sha(source.get("commit_sha"))
        if sha is None or source.get("sha_bound") is not True:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_SHA_INVALID"
            )

        metadata = self._metadata(
            workflow=source.get("workflow"),
            event=source.get("event"),
            run_id=source.get("run_id"),
            run_number=source.get("run_number"),
        )
        if metadata is None:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_METADATA_INVALID"
            )

        counts = self._manifest_counts(source)
        if counts is None:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_COUNTS_INVALID"
            )

        canonical_report = self.test_runner_service.create_test_report(
            passed=counts["passed"],
            failed=counts["failed"],
            total=counts["total"],
            commit_sha=sha,
        )
        if canonical_report.get("error") is not False:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_TEST_REPORT_INVALID"
            )

        for key, expected in canonical_report.items():
            if source.get(key) != expected:
                return self._validation_error(
                    "CI_VERIFICATION_MANIFEST_TEST_REPORT_MISMATCH"
                )

        expected_manifest_id = self._manifest_id(
            {
                key: value
                for key, value in source.items()
                if key != "verification_manifest_id"
            }
        )
        if source.get("verification_manifest_id") != expected_manifest_id:
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_ID_MISMATCH"
            )

        if (
            source.get("read_only_evidence") is not True
            or source.get("business_execution") is not False
            or source.get("ozon_mutation") is not False
        ):
            return self._validation_error(
                "CI_VERIFICATION_MANIFEST_SAFETY_INVALID"
            )

        return {
            "error": False,
            "status": "CI_VERIFICATION_MANIFEST_VALID",
            "commit_sha": sha,
            "test_report_id": source["test_report_id"],
            "verification_manifest_id": source[
                "verification_manifest_id"
            ],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "total": counts["total"],
            "skipped": counts["skipped"],
            "workflow": metadata["workflow"],
            "event": metadata["event"],
            "run_id": metadata["run_id"],
            "run_number": metadata["run_number"],
            "sha_bound": True,
            "read_only_evidence": True,
            "business_execution": False,
            "ozon_mutation": False,
        }

    def write_manifest(self, output_path, manifest):
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(
                manifest,
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            file.write("\n")

    def _read_junit_counts(self, junit_path):
        try:
            root = ET.parse(junit_path).getroot()
        except (OSError, ET.ParseError, TypeError, ValueError):
            return None

        if root.tag not in {"testsuite", "testsuites"}:
            return None

        raw = self._aggregate_junit_attributes(root)
        if raw is None:
            return None

        junit_tests = raw["tests"]
        failures = raw["failures"]
        errors = raw["errors"]
        skipped = raw["skipped"]

        if min(junit_tests, failures, errors, skipped) < 0:
            return None
        if failures + errors + skipped > junit_tests:
            return None

        failed = failures + errors
        total = junit_tests - skipped
        passed = total - failed

        if passed < 0 or passed + failed != total:
            return None

        return {
            "passed": passed,
            "failed": failed,
            "total": total,
            "skipped": skipped,
            "junit_tests": junit_tests,
            "junit_failures": failures,
            "junit_errors": errors,
        }

    def _aggregate_junit_attributes(self, root):
        if root.tag == "testsuite":
            return self._suite_attributes(root)

        direct = self._suite_attributes(root)
        if direct is not None and "tests" in root.attrib:
            return direct

        suites = [
            node
            for node in root
            if node.tag == "testsuite"
        ]
        if not suites:
            return None

        totals = {
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
        for suite in suites:
            counts = self._suite_attributes(suite)
            if counts is None:
                return None
            for key in totals:
                totals[key] += counts[key]
        return totals

    def _suite_attributes(self, node):
        try:
            return {
                "tests": int(node.attrib["tests"]),
                "failures": int(node.attrib.get("failures", 0)),
                "errors": int(node.attrib.get("errors", 0)),
                "skipped": int(node.attrib.get("skipped", 0)),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _manifest_counts(self, source):
        fields = (
            "passed",
            "failed",
            "total",
            "skipped",
            "junit_tests",
            "junit_failures",
            "junit_errors",
        )
        values = {}
        for field in fields:
            value = source.get(field)
            if isinstance(value, bool) or not isinstance(value, int):
                return None
            if value < 0:
                return None
            values[field] = value

        if values["passed"] + values["failed"] != values["total"]:
            return None
        if (
            values["failed"]
            != values["junit_failures"] + values["junit_errors"]
        ):
            return None
        if values["total"] + values["skipped"] != values["junit_tests"]:
            return None
        return values

    def _metadata(self, workflow, event, run_id, run_number):
        if workflow != "Verify":
            return None
        if event not in {"push", "pull_request", "workflow_dispatch"}:
            return None
        if isinstance(run_id, bool) or not isinstance(run_id, int):
            return None
        if isinstance(run_number, bool) or not isinstance(run_number, int):
            return None
        if run_id <= 0 or run_number <= 0:
            return None
        return {
            "workflow": workflow,
            "event": event,
            "run_id": run_id,
            "run_number": run_number,
        }

    def _error_manifest(self, code, commit_sha, metadata):
        result = {
            "schema_version": self.SCHEMA_VERSION,
            "error": True,
            "status": "invalid",
            "code": code,
            "commit_sha": commit_sha,
            "sha_bound": commit_sha is not None,
            "read_only_evidence": True,
            "business_execution": False,
            "ozon_mutation": False,
        }
        if metadata is not None:
            result.update(metadata)
        result["verification_manifest_id"] = self._manifest_id(result)
        return result

    @staticmethod
    def _validation_error(code):
        return {
            "error": True,
            "status": "CI_VERIFICATION_MANIFEST_INVALID",
            "code": code,
            "current_suite_verified": False,
            "business_execution": False,
            "ozon_mutation": False,
        }

    @staticmethod
    def _manifest_id(payload):
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return (
            "ci-verification:"
            + hashlib.sha256(canonical).hexdigest()
        )

    @staticmethod
    def _sha(value):
        text = str(value or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", text):
            return None
        return text

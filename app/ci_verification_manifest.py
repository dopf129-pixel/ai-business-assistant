import argparse
import sys

from services.assistant_ci_verification_manifest_service import (
    AssistantCiVerificationManifestService,
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-number", required=True, type=int)
    args = parser.parse_args(argv)

    service = AssistantCiVerificationManifestService()
    manifest = service.build_from_junit(
        junit_path=args.junit,
        commit_sha=args.commit_sha,
        workflow=args.workflow,
        event=args.event,
        run_id=args.run_id,
        run_number=args.run_number,
    )
    service.write_manifest(args.output, manifest)
    return 0 if manifest.get("error") is False else 1


if __name__ == "__main__":
    sys.exit(main())

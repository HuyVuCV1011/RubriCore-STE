import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.services.evaluation import evaluation_dataset_report, json_safe_evaluation_report  # noqa: E402
from app.db.services.pilot_io import validate_fixture_manifest  # noqa: E402


PUBLIC_EVALUATION_MANIFEST = Path("tests/fixtures/public/python_score_summary/evaluation_cases/manifest.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the public-safe synthetic Phase 3 evaluation fixture.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PUBLIC_EVALUATION_MANIFEST,
        help="Public-safe evaluation manifest path.",
    )
    parser.add_argument(
        "--actual-outcomes",
        type=Path,
        help="Optional JSON object keyed by case_id with actual outcome payloads.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Compare each case against its expected outcome for fixture validation.",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    errors = validate_fixture_manifest(manifest)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    actual_outcomes = load_json(args.actual_outcomes) if args.actual_outcomes else None
    report = evaluation_dataset_report(
        manifest=manifest,
        actual_outcomes_by_case_id=actual_outcomes,
        use_expected_as_actual=args.baseline,
    )
    print(json.dumps(json_safe_evaluation_report(report), indent=2, sort_keys=True))
    if report["missing_actuals"] or report["failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Suite count enforcement.

Verifies that the pytest suite count has not shrank below the required minimum
threshold (enforcing that deleting a test is caught).
"""

import argparse
import re
import subprocess
import sys

DEFAULT_MIN_COUNT = 652


def get_collected_test_count() -> int:
    """Run pytest --collect-only and return the number of tests collected."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    output = res.stdout + "\n" + res.stderr

    # Try matching "N tests collected" (pytest -q --collect-only standard)
    match = re.search(r"(\d+)\s+tests?\s+collected", output)
    if not match:
        # Fallback for full output: "collected N items"
        match = re.search(r"collected\s+(\d+)\s+items?", output)

    if not match:
        raise RuntimeError(
            f"Could not parse test count from pytest --collect-only output:\n{output}"
        )

    return int(match.group(1))


def check_suite_count(min_count: int = DEFAULT_MIN_COUNT) -> int:
    """Verify collected test count is at least min_count."""
    try:
        count = get_collected_test_count()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if count < min_count:
        print(
            f"Suite shrank! Collected {count} tests, which is less than "
            f"the required minimum of {min_count} tests.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Suite count check passed: {count} tests collected (minimum required: {min_count})."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check minimum pytest suite count.")
    parser.add_argument(
        "--min-count",
        type=int,
        default=DEFAULT_MIN_COUNT,
        help=f"Minimum required test count (default: {DEFAULT_MIN_COUNT})",
    )
    args = parser.parse_args()
    return check_suite_count(args.min_count)


if __name__ == "__main__":
    sys.exit(main())

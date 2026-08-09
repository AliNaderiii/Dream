"""Pin deprecation warnings configuration enforcement.

Evidence justifying this test:
- Rule 1 (warnings form): Every brief since M11 demanded the suite under
  deprecation-warnings-as-errors, but the build never ran it. Deprecations
  landing between milestones remained invisible.
This module verifies that pyproject.toml configures filterwarnings to treat
DeprecationWarning as an error by default.
"""

import tomllib


def test_pyproject_toml_enforces_deprecation_warnings_as_errors():
    """Verify pyproject.toml pytest ini_options contains error::DeprecationWarning."""
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    pytest_opts = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    filterwarnings = pytest_opts.get("filterwarnings", [])
    assert "error::DeprecationWarning" in filterwarnings

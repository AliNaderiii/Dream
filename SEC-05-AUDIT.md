# SEC-05 Audit Report: Tool Boundary Hardening

## Overview
SEC-05 hardens every Dream tool boundary against oversized, empty, malformed, and non-serializable input while preserving valid tool behavior and existing risk/approval semantics.

## Scope & Modified Files
- **Scope**: `dream/tools.py`, `dream/limits.py`, `tests/test_tool_validation.py`, `SEC-05-AUDIT.md`.
- **Unrelated files**: None modified (agent core, browser security, Rust, frontend, workflows, and unrelated tests untouched).

---

## Hardening Measures Implemented

### 1. Strict JSON Serialization Validation
- **Mechanism**: Validates tool arguments using `json.dumps(arguments)` before execution (without `default=str`).
- **Outcome**: Rejects non-serializable objects (such as `Path`, `datetime`, custom instances) immediately with a clean `ValueError`.

### 2. Active-Path Circular Reference Detection
- **Mechanism**: Replaced global/simple seen-sets with active-path cycle tracking in `_check_cycles` and `_validate_value`.
- **Outcome**: Tracks objects currently in the recursion stack, removing object IDs in a `finally` block when exiting containers. This correctly allows valid shared references (e.g., `[shared_obj, shared_obj]`) while catching true circular reference loops.

### 3. Strict Type & Boundary Validation
- **Integers**: Validates exact `int` type (rejecting booleans) and enforces `NUMERIC_RANGES` bounds.
- **Floats**:
  - Enforces strict numeric checks for general tools (rejecting string inputs and non-finite floats like `nan`, `inf`, `-inf`).
  - Preserves specialized tool contract coercion for `remember_fact.importance` (accepting numeric/sloppy strings for downstream normalization while rejecting non-finite floats).
- **Booleans**: Strict `bool` validation (rejecting integers like `0` or `1`).
- **Strings**: Enforces category-specific length limits (`MAX_TOOL_INPUT_CHARS`) and mandatory non-empty checks on critical identifiers/paths/queries.
- **Lists & Mappings**: Enforces `MAX_LIST_ITEMS` and `MAX_MAPPING_KEYS` limits, validates mapping keys are strings, and recursively validates items.

---

## Verification & CI Results

### CI Incident & Resolution
- **Failing CI Step & Error (Previous Push `2fb09a62`)**: **Lint** step failed across Python 3.10, 3.11, 3.12, and 3.13 due to Ruff E501 line length errors (`Line too long`) in `dream/tools.py`.
- **Root Cause**: Tool validation helper error messages and code blocks exceeded Ruff's 100-character line length limit.
- **Resolution**: Refactored `dream/tools.py` line wrapping and formatting to satisfy Ruff 100% and removed unauthorized `Co-authored-by` trailer from commit history.

### Commit Details
- **Old Remote SHA**: `2fb09a62bb6551e19d5d292b9353b0936a139411`
- **New Remote SHA**: `f3deb11a28273cd2386ae18e9c56897c13fc66bd`
- **Commit Author**: `Ali Naderi <alinaderi@users.noreply.github.com>`
- **Commit Message**: `fix(tools): validate and bound all tool inputs (SEC-05)`

### Verification Metrics
- **Python CI Results**:
  - Python 3.10: **PASS** (`https://github.com/AliNaderiii/Dream/actions/runs/33665782971/job/100367049069`)
  - Python 3.11: **PASS** (`https://github.com/AliNaderiii/Dream/actions/runs/33665782971/job/100367049064`)
  - Python 3.12: **PASS** (`https://github.com/AliNaderiii/Dream/actions/runs/33665782971/job/100367049040`)
  - Python 3.13: **PASS** (`https://github.com/AliNaderiii/Dream/actions/runs/33665782971/job/100367049079` / `100367048794`)
- **Full Pytest Count**: `3055 passed, 14 skipped` (0 errors, 0 failures).
- **Ruff Lint Result**: `All checks passed!` (0 errors).
- **Suite-Count Result**: Passed (`tests/test_m16_suite_count.py`).
- **Commit-Rule Check**: Passed (`tests/test_m16_commit_rules.py`, author verified, no `Co-authored-by` trailer, no AI-tooling references).
- **Scope Compliance**: Confirmed that only SEC-05 scope files changed (`dream/tools.py`, `dream/limits.py`, `tests/test_tool_validation.py`, `SEC-05-AUDIT.md`).

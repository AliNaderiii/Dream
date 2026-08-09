"""Pin conditional assertion detection in pytest test suites.

Evidence justifying this test:
- Rule 5 (conditional assertions): Nothing detected a test assertion sitting
  behind a condition the test does not control (the M11 defect trap).
- There are two 'if ... assert' shapes in the suite:
  1. The M11 offender in tests/test_skill_step_coercion.py:267, where an assert
     sits behind an 'if CLAIM_SAVED_TEXT in second.reply' condition in a test
     function. Repairing this test is explicitly deferred by the brief to its
     own milestone.
  2. A thread synchronisation guard in tests/test_telegram.py:505 inside the
     BlockingConversation helper class method 'run'. This is legitimate and must
     not be flagged.
This module verifies that check_conditional_assertions_in_file detects assert
statements inside if blocks within test functions, ignores helper classes/methods
like BlockingConversation, allowlists the single deferred M11 offender, and
rejects any newly introduced conditional assertions.
"""

import ast
import os

# Single deferred M11 offender: (relative_filename, test_function_name)
DEFERRED_M11_OFFENDER = (
    "test_skill_step_coercion.py",
    "test_two_message_sequence_saves_all_three_steps_and_never_claims_unsaved",
)


def check_conditional_assertions_in_file(
    filepath: str, rel_filename: str, ignore_deferred: bool = True
) -> list[str]:
    """Scan one test file for assert statements inside if blocks within test_* functions."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    tree = ast.parse(content, filename=filepath)

    violations = []
    for node in tree.body:
        # Only inspect top-level test functions (def test_*)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue

            if ignore_deferred and (rel_filename, node.name) == DEFERRED_M11_OFFENDER:
                continue

            # Search for If statements inside the function
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    # Check if any statement inside this If block is an Assert
                    for stmt in ast.walk(child):
                        if isinstance(stmt, ast.Assert):
                            violations.append(
                                f"Conditional assertion found in tests/{rel_filename} "
                                f"in function '{node.name}' at line {stmt.lineno}: "
                                f"assert inside 'if' block. Test assertions must not sit "
                                f"behind conditions the test does not control."
                            )
    return violations


def test_conditional_assertions_pass_clean_on_merged_trunk():
    """Verify all test files pass conditional assertion checks (with M11 deferred)."""
    tests_dir = "tests"
    all_violations = []
    for fname in sorted(os.listdir(tests_dir)):
        if fname.endswith(".py"):
            path = os.path.join(tests_dir, fname)
            all_violations.extend(
                check_conditional_assertions_in_file(path, fname, ignore_deferred=True)
            )
    assert all_violations == [], "\n".join(all_violations)


def test_conditional_assertions_detects_m11_offender():
    """Verify the M11 offender in test_skill_step_coercion.py is detected when not ignored."""
    violations = check_conditional_assertions_in_file(
        "tests/test_skill_step_coercion.py",
        "test_skill_step_coercion.py",
        ignore_deferred=False,
    )
    assert len(violations) == 1
    assert (
        "test_two_message_sequence_saves_all_three_steps_and_never_claims_unsaved"
        in violations[0]
    )
    assert "Conditional assertion found" in violations[0]


def test_conditional_assertions_ignores_helper_class_sync_guard():
    """Verify BlockingConversation.run in test_telegram.py is never flagged."""
    violations = check_conditional_assertions_in_file(
        "tests/test_telegram.py",
        "test_telegram.py",
        ignore_deferred=False,
    )
    assert violations == []


def test_conditional_assertions_rejects_new_conditional_assertion(tmp_path):
    """Verify check_conditional_assertions_in_file rejects a new conditional assertion."""
    dummy_file = tmp_path / "test_sample.py"
    dummy_file.write_text(
        "def test_example():\n"
        "    if True:\n"
        "        assert False\n",
        encoding="utf-8",
    )
    violations = check_conditional_assertions_in_file(
        str(dummy_file), "test_sample.py", ignore_deferred=True
    )
    assert len(violations) == 1
    assert (
        "Conditional assertion found in tests/test_sample.py in function 'test_example'"
        in violations[0]
    )
    assert "assert inside 'if' block" in violations[0]

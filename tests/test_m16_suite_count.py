"""Pin suite count enforcement rules.

Evidence justifying this test:
- Rule 6 (suite count): Nothing noticed the suite shrinking because test deletions
  were invisible and no automated check verified that the test count went up.
This module verifies that tools.check_suite_count correctly detects when the
number of collected pytest tests drops below the minimum threshold and passes
when the count is at or above the threshold.
"""


from tools.check_suite_count import check_suite_count, get_collected_test_count


def test_get_collected_test_count_returns_positive_int():
    """Verify get_collected_test_count collects the real suite count."""
    count = get_collected_test_count()
    assert isinstance(count, int)
    assert count >= 652


def test_check_suite_count_passes_on_valid_threshold(capsys):
    """Verify check_suite_count returns 0 when count >= min_count."""
    assert check_suite_count(min_count=652) == 0
    captured = capsys.readouterr()
    assert "Suite count check passed" in captured.out


def test_check_suite_count_fails_when_suite_shrinks(capsys):
    """Verify check_suite_count returns 1 and prints an error when count < min_count."""
    assert check_suite_count(min_count=999999) == 1
    captured = capsys.readouterr()
    assert "Suite shrank!" in captured.err

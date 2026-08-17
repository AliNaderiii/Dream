"""G4 — statistical analyses agree with scipy reference fixtures.

The t-test fixture pins the exact statistic computed independently with
``scipy.stats.ttest_ind`` on the host; the sandboxed script must agree to
1e-9. Other analyses check structural invariants plus published ground truth
where it exists (perfect correlation = 1.0, exact linear fit R² = 1.0, chi²
independence on a balanced table, PCA variance ordering).
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
scipy_stats = pytest.importorskip("scipy.stats")

from dream.skills.data_science import DataScienceError  # noqa: E402
from tests._data_science_helpers import make_runtime  # noqa: E402

GROUP_A = [12.1, 11.8, 12.5, 12.0, 11.9, 12.3, 12.2, 11.7]
GROUP_B = [10.9, 11.2, 10.8, 11.0, 11.3, 10.7, 11.1, 10.6]


@pytest.fixture()
def runtime(tmp_path):
    return make_runtime(tmp_path)


def load_csv(runtime, tmp_path, text, name="fixture.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return runtime.load_data(str(path))["dataset_id"]


def test_ttest_matches_scipy_reference(runtime, tmp_path):
    lines = ["value,group"]
    lines += [f"{v},a" for v in GROUP_A]
    lines += [f"{v},b" for v in GROUP_B]
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "ttest", "value_column": "value", "group_column": "group"}]
    )
    result = out["results"][0]
    assert result["status"] == "ok"
    expected_stat, expected_p = scipy_stats.ttest_ind(GROUP_A, GROUP_B)
    assert abs(result["statistic"] - float(expected_stat)) < 1e-9
    assert abs(result["p_value"] - float(expected_p)) < 1e-9
    assert result["n_a"] == 8 and result["n_b"] == 8


def test_ttest_refuses_more_than_two_levels(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "value,group\n1,a\n2,b\n3,c\n")
    out = runtime.analyze_data(
        ds, [{"kind": "ttest", "value_column": "value", "group_column": "group"}]
    )
    result = out["results"][0]
    assert result["status"] == "error"
    assert "2-level" in result["error"]


def test_correlation_perfect_positive(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "x,y\n1,2\n2,4\n3,6\n4,8\n")
    out = runtime.analyze_data(ds, [{"kind": "correlation", "columns": ["x", "y"]}])
    matrix = out["results"][0]["matrix"]
    assert abs(matrix[0][1] - 1.0) < 1e-9
    assert abs(matrix[1][0] - 1.0) < 1e-9


def test_anova_matches_scipy(runtime, tmp_path):
    groups = {"a": [1.0, 2.0, 3.0], "b": [2.0, 3.0, 4.0], "c": [8.0, 9.0, 10.0]}
    lines = ["v,g"] + [f"{v},{g}" for g, vs in groups.items() for v in vs]
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "anova", "value_column": "v", "group_column": "g"}]
    )
    result = out["results"][0]
    expected_stat, expected_p = scipy_stats.f_oneway(*groups.values())
    assert abs(result["statistic"] - float(expected_stat)) < 1e-9
    assert abs(result["p_value"] - float(expected_p)) < 1e-9


def test_chi_square_on_balanced_table(runtime, tmp_path):
    # Perfectly balanced 2x2 -> chi2 == 0, p == 1.
    rows = ["a,x", "a,y", "b,x", "b,y"] * 5
    ds = load_csv(runtime, tmp_path, "u,v\n" + "\n".join(rows) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "chi_square", "column_a": "u", "column_b": "v"}]
    )
    result = out["results"][0]
    assert result["status"] == "ok"
    assert abs(result["statistic"]) < 1e-9
    assert abs(result["p_value"] - 1.0) < 1e-9
    assert result["dof"] == 1


def test_linear_regression_exact_fit(runtime, tmp_path):
    # y = 3x + 2 exactly -> coefficient 3, intercept 2, R² = 1.
    lines = ["x,y"] + [f"{i},{3 * i + 2}" for i in range(10)]
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "linear_regression", "target": "y", "features": ["x"]}]
    )
    result = out["results"][0]
    assert abs(result["coefficients"]["x"] - 3.0) < 1e-9
    assert abs(result["intercept"] - 2.0) < 1e-9
    assert abs(result["r_squared"] - 1.0) < 1e-9


def test_logistic_regression_separable(runtime, tmp_path):
    lines = ["x,label"] + [f"{i},{'no' if i < 10 else 'yes'}" for i in range(20)]
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "logistic_regression", "target": "label", "features": ["x"]}]
    )
    result = out["results"][0]
    assert result["status"] == "ok"
    assert result["accuracy"] >= 0.95
    assert set(result["classes"]) == {"no", "yes"}


def test_kmeans_two_obvious_clusters(runtime, tmp_path):
    points = [(0.0 + i * 0.1, 0.0) for i in range(10)]
    points += [(100.0 + i * 0.1, 100.0) for i in range(10)]
    lines = ["x,y"] + [f"{x},{y}" for x, y in points]
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "kmeans", "columns": ["x", "y"], "k": 2}]
    )
    result = out["results"][0]
    assert sorted(result["cluster_sizes"]) == [10, 10]


def test_pca_explained_variance_is_ordered(runtime, tmp_path):
    lines = ["a,b,c"]
    for i in range(30):
        lines.append(f"{i},{2 * i + (i % 3)},{(i % 5)}")
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds, [{"kind": "pca", "columns": ["a", "b", "c"], "n_components": 2}]
    )
    result = out["results"][0]
    ratios = result["explained_variance_ratio"]
    assert len(ratios) == 2
    assert ratios[0] >= ratios[1]
    assert 0.0 < sum(ratios) <= 1.0 + 1e-9


def test_time_series_decompose(runtime, tmp_path):
    lines = ["day,v"]
    for i in range(28):
        lines.append(f"2024-01-{i + 1:02d},{10 + (i % 7)}")
    ds = load_csv(runtime, tmp_path, "\n".join(lines) + "\n")
    out = runtime.analyze_data(
        ds,
        [{
            "kind": "time_series_decompose",
            "datetime_column": "day",
            "value_column": "v",
            "period": 7,
        }],
    )
    result = out["results"][0]
    assert result["status"] == "ok"
    assert result["n"] == 28
    assert len(result["observed"]) == 28
    assert len(result["seasonal"]) == 28


def test_time_series_requires_parseable_datetime(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "day,v\nxxx,1\nyyy,2\nzzz,3\nqqq,4\n")
    out = runtime.analyze_data(
        ds,
        [{
            "kind": "time_series_decompose",
            "datetime_column": "day",
            "value_column": "v",
            "period": 2,
        }],
    )
    assert out["results"][0]["status"] == "error"
    assert "datetime" in out["results"][0]["error"]


def test_one_failed_analysis_does_not_kill_the_batch(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "x,y,g\n1,2,a\n2,4,b\n3,6,c\n")
    out = runtime.analyze_data(
        ds,
        [
            {"kind": "ttest", "value_column": "x", "group_column": "g"},  # 3 levels
            {"kind": "correlation", "columns": ["x", "y"]},
        ],
    )
    statuses = [r["status"] for r in out["results"]]
    assert statuses == ["error", "ok"]


def test_analyze_validates_before_sandbox(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "x\n1\n")
    with pytest.raises(DataScienceError, match="non-empty list"):
        runtime.analyze_data(ds, [])
    with pytest.raises(DataScienceError, match="unknown analysis"):
        runtime.analyze_data(ds, [{"kind": "melt_gpu"}])
    with pytest.raises(DataScienceError, match="not in the dataset schema"):
        runtime.analyze_data(ds, [{"kind": "correlation", "columns": ["ghost"]}])

"""Deterministic grounded planner for common English and Persian data questions.

No dataset values enter an instruction context. Plans reference only exact schema
columns and are the sole input accepted by the trusted worker.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from dream.dataqa.models import DatasetProfile, FilterSpec, QueryPlan
from dream.memory import normalize_fa

_AVG = ("average", "avg", "mean", "میانگین", "متوسط")
_SUM = ("sum", "total", "مجموع", "جمع", "کل")
_COUNT = ("count", "how many", "تعداد", "چند")
_MIN = ("minimum", "lowest", "min", "کمترین", "حداقل")
_MAX = ("maximum", "highest", "max", "بیشترین", "حداکثر")
_GROUP = (" by ", " per ", "for each", "به تفکیک", "بر اساس", "هر ")
_CHART = ("chart", "plot", "graph", "visual", "نمودار", "رسم")
_TREND = ("trend", "over time", "timeline", "روند", "در طول زمان")
_DISTRIBUTION = ("distribution", "histogram", "box plot", "توزیع", "هیستوگرام", "جعبه‌ای")
_BOX = ("box", "box plot", "جعبه‌ای")
_CORRELATION = ("correlation", "correlation matrix", "همبستگی", "ماتریس همبستگی")
_RELATIONSHIP = ("relationship", "versus", " vs ", "رابطه", "در برابر")
_RESET = ("reset", "start over", "از نو", "بازنشانی")
_ALIASES = (
    {"region", "province", "city", "area", "منطقه", "استان", "شهر", "ناحیه"},
    {"revenue", "sales", "amount", "فروش", "درآمد", "مبلغ", "جمع"},
    {"date", "time", "month", "year", "تاریخ", "زمان", "ماه", "سال"},
    {"product", "item", "category", "محصول", "کالا", "دسته"},
    {"customer", "client", "buyer", "مشتری", "خریدار"},
)


def _fold(text: str) -> str:
    return " " + normalize_fa(text).lower().replace("_", " ").strip() + " "


def _resolve(
    fragment: str,
    columns: list[str],
    *,
    roles: dict[str, str] | None = None,
    role: str | None = None,
) -> str | None:
    folded = _fold(fragment)
    direct = [name for name in columns if _fold(name).strip() in folded]
    if direct:
        return max(direct, key=len)
    words = set(re.findall(r"[\w\u0600-\u06ff]+", folded))
    for family in _ALIASES:
        # ``normalize_fa`` intentionally folds Arabic/Persian letter variants and
        # diacritics (for example درآمد -> درامد). Apply that same normalization
        # to aliases so bilingual matching cannot silently lose a grounded metric.
        normalized_family = {_fold(alias).strip() for alias in family}
        if not words.intersection(normalized_family):
            continue
        family_matches = [
            name for name in columns if set(_fold(name).split()).intersection(normalized_family)
        ]
        if family_matches:
            return family_matches[0]
    scored: list[tuple[float, str]] = []
    for name in columns:
        nfold = _fold(name).strip()
        ratio = SequenceMatcher(None, nfold, folded.strip()).ratio()
        if nfold in words:
            ratio += 1
        if role and roles and roles.get(name) == role:
            ratio += 0.05
        scored.append((ratio, name))
    if not scored:
        return None
    score, name = max(scored)
    return name if score >= 0.62 else None


def _audit_code(plan: QueryPlan) -> str:
    lines = [
        "# Auditable pandas equivalent; executed as a validated plan, not eval'd.",
        "result = df",
    ]
    for item in plan.filters:
        op = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(
            item.operator
        )
        if op:
            lines.append(f"result = result[result[{item.column!r}] {op} {item.value!r}]")
    if plan.action == "aggregate" and plan.aggregate:
        if plan.groups and plan.aggregate == "count":
            lines.append(
                f"result = result.groupby({plan.groups!r}, dropna=False).size()"
                ".reset_index(name='count_rows')"
            )
        elif plan.groups:
            lines.append(
                f"result = result.groupby({plan.groups!r}, dropna=False)[{plan.metric!r}]"
                f".{plan.aggregate}().reset_index()"
            )
        elif plan.aggregate == "count":
            lines.append("result = len(result)")
        else:
            lines.append(f"result = result[{plan.metric!r}].{plan.aggregate}()")
    elif plan.action == "distribution":
        lines.append(f"result = result[{plan.metric!r}].describe()")
    elif plan.action == "relationship":
        lines.append(f"result = result[[{plan.metric!r}, {plan.secondary_metric!r}]].dropna()")
    elif plan.action == "correlation":
        lines.append(f"result = result[{plan.groups!r}].corr(numeric_only=True)")
    else:
        lines.append(f"result = result.head({plan.limit})")
    return "\n".join(lines)


def plan_question(
    question: str, profile: DatasetProfile, *, previous: QueryPlan | None = None
) -> QueryPlan:
    if not isinstance(question, str) or not question.strip() or len(question) > 2_000:
        return QueryPlan(action="insufficient", intent="Question is empty or too long")
    text = _fold(question)
    language = "fa" if re.search(r"[\u0600-\u06ff]", text) else "en"
    if any(token in text for token in _RESET):
        return QueryPlan(action="reset", language=language, intent="reset session")
    columns = [column.name for column in profile.columns]
    roles = {column.name: column.role for column in profile.columns}
    numeric = [column.name for column in profile.columns if column.dtype == "number"]
    categories = [column.name for column in profile.columns if column.role == "category"]
    dates = [column.name for column in profile.columns if column.role == "time"]
    is_trend = any(term in text for term in _TREND)
    is_distribution = any(term in text for term in _DISTRIBUTION)
    is_correlation = any(term in text for term in _CORRELATION)
    is_relationship = any(term in text for term in _RELATIONSHIP)
    aggregate = None
    for name, terms in (
        ("mean", _AVG),
        ("sum", _SUM),
        ("count", _COUNT),
        ("min", _MIN),
        ("max", _MAX),
    ):
        if any(term in text for term in terms):
            aggregate = name
            break
    wants_chart = any(term in text for term in _CHART)
    group: str | None = None
    group_requested = False
    for marker in _GROUP:
        if marker in text:
            group_requested = True
            tail = text.split(marker, 1)[1]
            group = _resolve(tail, columns, roles=roles, role="category")
            break
    mentioned = [name for name in columns if _fold(name).strip() in text]
    metric = next((name for name in mentioned if name in numeric), None)
    if metric is None and numeric and aggregate != "count":
        metric = _resolve(question, numeric, roles=roles, role="measure")
    if group is None:
        group = next((name for name in mentioned if name in categories and name != metric), None)
    filters: list[FilterSpec] = []
    # Exact category mentions from profile summaries become grounded equality filters.
    for column in profile.columns:
        if column.role != "category" or column.name == group:
            continue
        for item in column.top_values:
            value = item.get("value")
            if value is not None and _fold(str(value)).strip() in text:
                filters.append(FilterSpec(column.name, "eq", value))
                break
    if aggregate and not (is_trend or is_distribution or is_correlation):
        if group_requested and group is None:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="The requested grouping is not present in the schema",
            )
        if aggregate != "count" and metric is None:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="No numeric measure is grounded in the schema",
            )
        plan = QueryPlan(
            action="aggregate",
            aggregate=aggregate,
            metric=metric,
            groups=[group] if group else [],
            filters=filters,
            date_column=group if group in dates else None,
            wants_chart=wants_chart or bool(group),
            chart_type="line" if group in dates else ("bar" if group else None),
            language=language,
            answer_shape="table" if group else "scalar",
            intent=f"{aggregate} {metric or 'rows'}" + (f" by {group}" if group else ""),
        )
    elif is_trend:
        date_column = next((name for name in mentioned if name in dates), None)
        date_column = date_column or _resolve(question, dates, roles=roles, role="time")
        if metric is None or date_column is None:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="A trend requires a grounded numeric measure and time column",
            )
        plan = QueryPlan(
            action="aggregate",
            aggregate="sum",
            metric=metric,
            groups=[date_column],
            filters=filters,
            date_column=date_column,
            wants_chart=True,
            chart_type="line",
            language=language,
            intent=f"trend of {metric} over {date_column}",
        )
    elif is_distribution:
        if metric is None:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="No numeric column is grounded for a distribution",
            )
        chart_type = "box" if any(term in text for term in _BOX) else "histogram"
        plan = QueryPlan(
            action="distribution",
            metric=metric,
            filters=filters,
            wants_chart=True,
            chart_type=chart_type,
            language=language,
            intent=f"distribution of {metric}",
        )
    elif is_correlation:
        correlation_columns = [name for name in mentioned if name in numeric] or numeric
        if len(correlation_columns) < 2:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="Correlation requires at least two grounded numeric columns",
            )
        plan = QueryPlan(
            action="correlation",
            groups=correlation_columns[:12],
            filters=filters,
            wants_chart=True,
            chart_type="heatmap",
            language=language,
            intent="correlation matrix for numeric columns",
        )
    elif len([name for name in mentioned if name in numeric]) >= 2 or is_relationship:
        pair = [name for name in mentioned if name in numeric][:2]
        if len(pair) < 2:
            return QueryPlan(
                action="insufficient",
                language=language,
                intent="A relationship requires two grounded numeric columns",
            )
        plan = QueryPlan(
            action="relationship",
            metric=pair[0],
            secondary_metric=pair[1],
            filters=filters,
            wants_chart=True,
            chart_type="scatter",
            language=language,
            intent="relationship between two numeric columns",
        )
    elif previous and filters:
        plan = QueryPlan.from_dict(previous.to_dict())
        plan.filters = [*previous.filters, *filters]
        plan.language = language
        plan.intent = f"follow-up to {previous.intent}"
    elif mentioned or any(word in text for word in ("show", "list", "نمایش", "نشان", "فهرست")):
        plan = QueryPlan(
            action="select",
            groups=mentioned,
            filters=filters,
            limit=50,
            language=language,
            answer_shape="table",
            intent="show matching rows",
        )
    else:
        return QueryPlan(
            action="insufficient",
            language=language,
            intent="The requested measure or grouping is ambiguous",
        )
    if previous and previous.filters:
        # The working dataframe is represented by its validated filters. Carry those
        # filters into every grounded follow-up until reset, not only terse category
        # follow-ups such as "What about North?".
        combined: list[FilterSpec] = []
        seen: set[tuple[str, str, str]] = set()
        for item in [*previous.filters, *plan.filters]:
            key = (
                item.column,
                item.operator,
                json.dumps(item.value, ensure_ascii=False, sort_keys=True),
            )
            if key not in seen:
                combined.append(item)
                seen.add(key)
        plan.filters = combined
    plan.code = _audit_code(plan)
    plan.sql = (
        "-- SQL is optional; validated Python plan selected\n-- "
        + json.dumps(plan.to_dict(), ensure_ascii=False)[:500]
    )
    return plan

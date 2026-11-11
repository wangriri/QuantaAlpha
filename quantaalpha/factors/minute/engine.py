from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from quantaalpha.backtest.expression_utils import replace_data_column_tokens
from quantaalpha.factors.coder.expr_parser import parse_expression, parse_symbol
from quantaalpha.factors.coder import function_lib

from . import operators
from .mongo_reader import MINUTE_COLUMNS, MinuteDataIssue, MongoMinuteProvider, is_sh_sz_a_share


MINUTE_FIELD_PATTERN = re.compile(r"\$m_(?:open|high|low|close|pre_close|volume|amount)\b")
FUNCTION_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
MINUTE_COMMON_FUNCTIONS = {
    "ABS", "SIGN", "LOG", "EXP", "SQRT", "POW", "INV", "FLOOR",
    "MAX", "MIN", "GT", "LT", "GE", "LE", "EQ", "NE", "AND", "OR",
    "WHERE", "FILTER", "SEQUENCE",
}


def contains_minute_expression(expression: str) -> bool:
    return bool(MINUTE_FIELD_PATTERN.search(expression or "") or re.search(r"\bM_[A-Z0-9_]+\s*\(", expression or ""))


def _matching_parenthesis(text: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"Unbalanced expression near: {text[opening:]}")


def _minute_reducer_calls(expression: str) -> list[str]:
    calls = []
    for match in FUNCTION_PATTERN.finditer(expression):
        if match.group(1) not in operators.DAILY_REDUCERS:
            continue
        opening = expression.find("(", match.start())
        end = _matching_parenthesis(expression, opening)
        calls.append(expression[match.start():end + 1])
    # Keep only outermost reducer strings. A reducer nested in another reducer is evaluated with it.
    return sorted({call for call in calls if not any(call != outer and call in outer for outer in calls)}, key=len, reverse=True)


def _globals() -> dict:
    values = {"np": np, "pd": pd}
    for module in (function_lib, operators):
        for name in dir(module):
            value = getattr(module, name)
            if not name.startswith("_") and callable(value):
                values[name] = value
    return values


def _evaluate(expression: str, frame: pd.DataFrame):
    parsed = parse_symbol(expression, frame.columns)
    parsed = parse_expression(parsed)
    parsed = replace_data_column_tokens(parsed, frame.columns)
    return eval(parsed, {**_globals(), "df": frame, "__builtins__": {}})


@dataclass
class MinuteExecutionReport:
    requested_stock_days: int = 0
    valid_stock_days: int = 0
    issues: list[MinuteDataIssue] | None = None

    @property
    def coverage(self) -> float:
        return self.valid_stock_days / self.requested_stock_days if self.requested_stock_days else 0.0

    def to_dict(self) -> dict:
        reasons = Counter(issue.reason.split(":", 1)[0] for issue in (self.issues or []))
        return {
            "requested_stock_days": self.requested_stock_days,
            "valid_stock_days": self.valid_stock_days,
            "coverage": self.coverage,
            "issue_counts": dict(sorted(reasons.items())),
        }


class MinuteFactorEngine:
    """Two-stage executor: minute subexpressions first, then the existing daily expression."""

    def __init__(self, provider=None):
        self.provider = provider
        self.last_report = MinuteExecutionReport(issues=[])

    def _provider(self):
        if self.provider is None:
            self.provider = MongoMinuteProvider()
        return self.provider

    @staticmethod
    def validate(expression: str, daily_columns: Iterable[str]) -> None:
        minute_fields = set(MINUTE_FIELD_PATTERN.findall(expression or ""))
        unknown_minute = minute_fields - set(MINUTE_COLUMNS)
        if unknown_minute:
            raise ValueError(f"Unknown minute fields: {sorted(unknown_minute)}")
        minute_functions = set(re.findall(r"\b(M_[A-Z0-9_]+)\s*\(", expression or ""))
        known_functions = {name for name in dir(operators) if name.startswith("M_") and callable(getattr(operators, name))}
        unknown_functions = minute_functions - known_functions
        if unknown_functions:
            raise ValueError(f"Unknown minute operators: {sorted(unknown_functions)}")
        reducers = _minute_reducer_calls(expression)
        if contains_minute_expression(expression) and not reducers:
            raise ValueError("Minute expression must end in M_TO_DAILY or an M_SESSION/M_FIRST/M_LAST reducer")
        for reducer in reducers:
            functions = set(FUNCTION_PATTERN.findall(reducer))
            daily_only = {name for name in functions if not name.startswith("M_") and name not in MINUTE_COMMON_FUNCTIONS}
            if daily_only:
                raise ValueError(f"Daily operators cannot run inside a minute branch: {sorted(daily_only)}")
        covered = expression
        for reducer in reducers:
            covered = covered.replace(reducer, "0")
        if MINUTE_FIELD_PATTERN.search(covered) or re.search(r"\bM_[A-Z0-9_]+\s*\(", covered):
            raise ValueError("Every minute branch must be reduced to one value per stock-day before daily operations")
        daily_fields = set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", covered))
        missing = daily_fields - set(map(str, daily_columns))
        if missing:
            raise KeyError(f"Missing daily fields: {sorted(missing)}")

    def calculate_many(self, expressions: Mapping[str, str], daily_frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(daily_frame.index, pd.MultiIndex) or not {"datetime", "instrument"}.issubset(daily_frame.index.names):
            raise ValueError("daily_frame must use a (datetime, instrument) MultiIndex")
        minute_expressions = {name: expr for name, expr in expressions.items() if contains_minute_expression(expr)}
        if not minute_expressions:
            return pd.DataFrame({name: _as_daily_series(_evaluate(expr, daily_frame), daily_frame.index, name) for name, expr in expressions.items()})
        for expression in minute_expressions.values():
            self.validate(expression, daily_frame.columns)

        reducers_by_expression = {name: _minute_reducer_calls(expr) for name, expr in minute_expressions.items()}
        unique_reducers = list(dict.fromkeys(call for calls in reducers_by_expression.values() for call in calls))
        required_fields = sorted({field for call in unique_reducers for field in MINUTE_FIELD_PATTERN.findall(call)})
        temp_names = {call: f"$minute_result_{index}" for index, call in enumerate(unique_reducers)}
        dates = pd.DatetimeIndex(daily_frame.index.get_level_values("datetime").unique()).sort_values()
        minute_values = {name: [] for name in temp_names.values()}
        issues: list[MinuteDataIssue] = []
        requested = valid = 0

        provider = self._provider()
        for date in dates:
            date_slice = daily_frame.xs(date, level="datetime", drop_level=False)
            instruments = [item for item in date_slice.index.get_level_values("instrument").unique() if is_sh_sz_a_share(item)]
            requested += len(instruments)
            day = provider.load_day(date, instruments, required_fields)
            issues.extend(day.issues)
            if day.frame.empty:
                continue
            valid += day.frame.index.droplevel("minute").unique().size
            for call, temp_name in temp_names.items():
                value = _evaluate(call, day.frame)
                value = _as_daily_series(value, day.frame.index.droplevel("minute").unique(), temp_name)
                minute_values[temp_name].append(value)

        enriched = daily_frame.copy()
        for temp_name, parts in minute_values.items():
            combined = pd.concat(parts).sort_index() if parts else pd.Series(dtype=float, name=temp_name)
            combined = combined[~combined.index.duplicated(keep="last")]
            enriched[temp_name] = combined.reindex(enriched.index)

        results = {}
        for name, expression in expressions.items():
            rewritten = expression
            for call, temp_name in temp_names.items():
                rewritten = rewritten.replace(call, temp_name)
            results[name] = _as_daily_series(_evaluate(rewritten, enriched), enriched.index, name)
        self.last_report = MinuteExecutionReport(requested, valid, issues)
        return pd.DataFrame(results, index=enriched.index)

    def calculate(self, name: str, expression: str, daily_frame: pd.DataFrame) -> pd.Series:
        return self.calculate_many({name: expression}, daily_frame)[name]


def _as_daily_series(value, index, name: str) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    if not isinstance(value, pd.Series):
        value = pd.Series(value, index=index)
    if "minute" in value.index.names:
        raise ValueError("Minute formula returned minute rows; add an explicit daily reducer")
    value = value.reindex(index)
    value.name = name
    return value.astype(np.float64)

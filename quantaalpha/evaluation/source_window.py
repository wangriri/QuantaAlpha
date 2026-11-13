"""Conservative input window for minute formulas during formal evaluation."""

import re

import pandas as pd

from quantaalpha.factors.minute.engine import contains_minute_expression


SAME_DAY_FUNCTIONS = {
    "RANK", "ZSCORE", "SCALE", "MEAN", "STD", "SKEW", "KURT", "MAX", "MIN", "MEDIAN",
    "ABS", "SIGN", "LOG", "EXP", "SQRT", "POW", "INV", "FLOOR",
    "GT", "LT", "GE", "LE", "EQ", "NE", "AND", "OR", "WHERE", "FILTER",
}


def is_same_day_minute_expression(expression: str) -> bool:
    if not contains_minute_expression(expression):
        return False
    functions = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression)
    return all(name.startswith("M_") or name.upper() in SAME_DAY_FUNCTIONS for name in functions)


def minute_source_start(expression: str, training_start: str) -> pd.Timestamp | None:
    if not is_same_day_minute_expression(expression):
        return None
    # Same-day expressions need only a short margin for trading alignment.
    # Expressions with daily history retain the original full source window.
    return pd.Timestamp(training_start) - pd.Timedelta(days=40)

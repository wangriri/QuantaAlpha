from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from quantaalpha.backtest.expression_utils import replace_data_column_tokens
from quantaalpha.factors.coder.expr_parser import parse_expression, parse_symbol
from quantaalpha.factors.coder import function_lib

from .engine import MinuteFactorEngine, contains_minute_expression


def _daily_expression(expression: str, daily_frame: pd.DataFrame, name: str) -> pd.Series:
    parsed = parse_expression(parse_symbol(expression, daily_frame.columns))
    parsed = replace_data_column_tokens(parsed, daily_frame.columns)
    namespace = {"df": daily_frame, "np": np, "pd": pd, "__builtins__": {}}
    for function_name in dir(function_lib):
        value = getattr(function_lib, function_name)
        if not function_name.startswith("_") and callable(value):
            namespace[function_name] = value
    result = eval(parsed, namespace)
    if isinstance(result, pd.DataFrame):
        result = result.iloc[:, 0]
    if not isinstance(result, pd.Series):
        result = pd.Series(result, index=daily_frame.index)
    result.name = name
    return result.astype(np.float64)


def calculate_factor_expressions(
    expressions: Mapping[str, str],
    daily_frame: pd.DataFrame,
    minute_engine: MinuteFactorEngine | None = None,
) -> pd.DataFrame:
    minute = {name: expr for name, expr in expressions.items() if contains_minute_expression(expr)}
    daily = {name: expr for name, expr in expressions.items() if name not in minute}
    results = {name: _daily_expression(expr, daily_frame, name) for name, expr in daily.items()}
    if minute:
        engine = minute_engine or MinuteFactorEngine()
        minute_result = engine.calculate_many(minute, daily_frame)
        results.update({name: minute_result[name] for name in minute})
    output = pd.DataFrame(results, index=daily_frame.index)
    if minute:
        output.attrs["minute_execution_report"] = engine.last_report.to_dict()
    return output


def calculate_factor_expression(
    expression: str,
    daily_frame: pd.DataFrame,
    name: str,
    minute_engine: MinuteFactorEngine | None = None,
) -> pd.Series:
    frame = calculate_factor_expressions({name: expression}, daily_frame, minute_engine)
    result = frame[name]
    result.attrs.update(frame.attrs)
    return result

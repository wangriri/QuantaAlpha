from __future__ import annotations

import numpy as np
import pandas as pd


GROUP_LEVELS = ["datetime", "instrument"]


def _groups(value: pd.Series):
    if not isinstance(value, pd.Series):
        raise TypeError("Minute operators require a pandas Series")
    missing = set(GROUP_LEVELS) - set(value.index.names)
    if missing:
        raise ValueError(f"Minute series is missing index levels: {sorted(missing)}")
    return value.groupby(level=GROUP_LEVELS, sort=False, group_keys=False)


def _rolling(value: pd.Series, window: int, method: str, **kwargs) -> pd.Series:
    window = int(window)
    if window <= 0:
        raise ValueError("Minute rolling window must be positive")
    return _groups(value).transform(
        lambda x: getattr(x.rolling(window, min_periods=1), method)(**kwargs)
    )


def _clock(index: pd.MultiIndex) -> pd.Series:
    minute = index.get_level_values("minute")
    values = minute.hour * 100 + minute.minute
    return pd.Series(values, index=index)


def M_SLICE(value: pd.Series, start_hhmm: int, end_hhmm: int) -> pd.Series:
    """Keep bars in an inclusive HHMM interval, e.g. M_SLICE(x, 1430, 1500)."""
    clock = _clock(value.index)
    return value.where(clock.between(int(start_hhmm), int(end_hhmm)))


def M_DELAY(value: pd.Series, periods: int = 1) -> pd.Series:
    if int(periods) < 0:
        raise ValueError("M_DELAY periods must be non-negative")
    return _groups(value).shift(int(periods))


def M_DELTA(value: pd.Series, periods: int = 1) -> pd.Series:
    return _groups(value).diff(int(periods))


def M_TS_PCTCHANGE(value: pd.Series, periods: int = 1) -> pd.Series:
    return _groups(value).pct_change(int(periods), fill_method=None)


def M_TS_MEAN(value, window=5): return _rolling(value, window, "mean")
def M_TS_SUM(value, window=5): return _rolling(value, window, "sum")
def M_TS_STD(value, window=5): return _rolling(value, window, "std")
def M_TS_VAR(value, window=5): return _rolling(value, window, "var")
def M_TS_MAX(value, window=5): return _rolling(value, window, "max")
def M_TS_MIN(value, window=5): return _rolling(value, window, "min")
def M_TS_MEDIAN(value, window=5): return _rolling(value, window, "median")
def M_TS_SKEW(value, window=5): return _rolling(value, window, "skew")
def M_TS_KURT(value, window=5): return _rolling(value, window, "kurt")
def M_TS_QUANTILE(value, window, q): return _rolling(value, window, "quantile", q=float(q))


def M_TS_RANK(value: pd.Series, window: int = 5) -> pd.Series:
    return _groups(value).transform(
        lambda x: x.rolling(int(window), min_periods=1).rank(pct=True)
    )


def M_TS_ZSCORE(value: pd.Series, window: int = 5) -> pd.Series:
    mean = M_TS_MEAN(value, window)
    std = M_TS_STD(value, window)
    return (value - mean) / std.replace(0, np.nan)


def M_TS_MAD(value: pd.Series, window: int = 5) -> pd.Series:
    def mad(x):
        median = np.nanmedian(x)
        return np.nanmedian(np.abs(x - median))
    return _groups(value).transform(
        lambda x: x.rolling(int(window), min_periods=1).apply(mad, raw=True)
    )


def M_TS_ARGMAX(value: pd.Series, window: int = 5) -> pd.Series:
    def bars_since(x):
        return np.nan if np.isnan(x).all() else len(x) - int(np.nanargmax(x)) - 1
    return _groups(value).transform(lambda x: x.rolling(int(window), min_periods=1).apply(bars_since, raw=True))


def M_TS_ARGMIN(value: pd.Series, window: int = 5) -> pd.Series:
    def bars_since(x):
        return np.nan if np.isnan(x).all() else len(x) - int(np.nanargmin(x)) - 1
    return _groups(value).transform(lambda x: x.rolling(int(window), min_periods=1).apply(bars_since, raw=True))


def _rolling_pair(left: pd.Series, right: pd.Series, window: int, method: str) -> pd.Series:
    aligned = pd.concat([left.rename("left"), right.rename("right")], axis=1)
    parts = []
    for _, group in aligned.groupby(level=GROUP_LEVELS, sort=False):
        result = getattr(group["left"].rolling(int(window), min_periods=2), method)(group["right"])
        parts.append(result)
    return pd.concat(parts).sort_index() if parts else pd.Series(dtype=float, index=left.index)


def M_TS_CORR(left, right, window=5): return _rolling_pair(left, right, window, "corr")
def M_TS_COVARIANCE(left, right, window=5): return _rolling_pair(left, right, window, "cov")


def M_SMA(value, window=5): return M_TS_MEAN(value, window)


def M_EMA(value: pd.Series, window: int = 5) -> pd.Series:
    return _groups(value).transform(lambda x: x.ewm(span=int(window), adjust=False, min_periods=1).mean())


def M_WMA(value: pd.Series, window: int = 5) -> pd.Series:
    def weighted(x):
        weights = np.arange(1, len(x) + 1, dtype=float)
        return np.dot(x, weights) / weights.sum()
    return _groups(value).transform(
        lambda x: x.rolling(int(window), min_periods=1).apply(weighted, raw=True)
    )


def M_COUNT(condition: pd.Series, window: int = 5) -> pd.Series:
    return M_TS_SUM(condition.astype(float), window)


def M_SUMIF(value: pd.Series, window: int, condition: pd.Series) -> pd.Series:
    return M_TS_SUM(value.where(condition, 0.0), window)


def M_PROD(value: pd.Series, window: int = 5) -> pd.Series:
    return _groups(value).transform(
        lambda x: x.rolling(int(window), min_periods=1).apply(np.prod, raw=True)
    )


def M_DECAYLINEAR(value: pd.Series, window: int = 5) -> pd.Series:
    return M_WMA(value, window)


def M_HIGHBAR(value: pd.Series, window: int = 5) -> pd.Series:
    return M_TS_ARGMAX(value, window)


def M_LOWBAR(value: pd.Series, window: int = 5) -> pd.Series:
    return M_TS_ARGMIN(value, window)


def _rolling_beta(y: pd.Series, x: pd.Series, window: int, residual: bool) -> pd.Series:
    paired = pd.concat([y.rename("y"), x.rename("x")], axis=1)
    output = pd.Series(np.nan, index=paired.index, dtype=float)
    for _, group in paired.groupby(level=GROUP_LEVELS, sort=False):
        yy, xx = group["y"], group["x"]
        for pos in range(len(group)):
            sample = pd.concat([yy.iloc[max(0, pos-window+1):pos+1], xx.iloc[max(0, pos-window+1):pos+1]], axis=1).dropna()
            if len(sample) < 2 or sample["x"].var() == 0:
                continue
            beta = sample["y"].cov(sample["x"]) / sample["x"].var()
            intercept = sample["y"].mean() - beta * sample["x"].mean()
            output.loc[group.index[pos]] = yy.iloc[pos] - (intercept + beta * xx.iloc[pos]) if residual else beta
    return output


def M_REGBETA(y, x, window=5): return _rolling_beta(y, x, int(window), False)
def M_REGRESI(y, x, window=5): return _rolling_beta(y, x, int(window), True)


def M_MACD(value: pd.Series, short: int = 12, long: int = 26) -> pd.Series:
    return M_EMA(value, short) - M_EMA(value, long)


def M_RSI(value: pd.Series, window: int = 14) -> pd.Series:
    delta = M_DELTA(value, 1)
    gain = M_TS_MEAN(delta.clip(lower=0), window)
    loss = M_TS_MEAN((-delta.clip(upper=0)), window)
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def M_BB_MIDDLE(value, window=20): return M_TS_MEAN(value, window)
def M_BB_UPPER(value, window=20, width=2): return M_TS_MEAN(value, window) + float(width) * M_TS_STD(value, window)
def M_BB_LOWER(value, window=20, width=2): return M_TS_MEAN(value, window) - float(width) * M_TS_STD(value, window)


def _reduce(value: pd.Series, method: str) -> pd.Series:
    grouped = _groups(value)
    if method == "first": return grouped.first()
    if method == "last": return grouped.last()
    if method == "count": return grouped.count().astype(float)
    return getattr(grouped, method)()


def M_FIRST(value): return _reduce(value, "first")
def M_LAST(value): return _reduce(value, "last")
def M_SESSION_SUM(value): return _reduce(value, "sum")
def M_SESSION_MEAN(value): return _reduce(value, "mean")
def M_SESSION_STD(value): return _reduce(value, "std")
def M_SESSION_MAX(value): return _reduce(value, "max")
def M_SESSION_MIN(value): return _reduce(value, "min")
def M_SESSION_MEDIAN(value): return _reduce(value, "median")
def M_SESSION_COUNT(value): return _reduce(value, "count")


def M_SESSION_RETURN(value: pd.Series) -> pd.Series:
    first, last = M_FIRST(value), M_LAST(value)
    return last / first.replace(0, np.nan) - 1


def _extreme_time(value: pd.Series, method: str) -> pd.Series:
    def one(group):
        clean = group.dropna()
        if clean.empty:
            return np.nan
        pos = clean.idxmax() if method == "max" else clean.idxmin()
        minute = pos[value.index.names.index("minute")]
        return float(minute.hour * 100 + minute.minute)
    return _groups(value).apply(one)


def M_MAX_TIME(value): return _extreme_time(value, "max")
def M_MIN_TIME(value): return _extreme_time(value, "min")


def M_TO_DAILY(value: pd.Series) -> pd.Series:
    """Reduce a minute expression to its last valid value for each stock-day."""
    return M_LAST(value)


DAILY_REDUCERS = {
    "M_FIRST", "M_LAST", "M_SESSION_SUM", "M_SESSION_MEAN", "M_SESSION_STD",
    "M_SESSION_MAX", "M_SESSION_MIN", "M_SESSION_MEDIAN", "M_SESSION_COUNT",
    "M_SESSION_RETURN", "M_MAX_TIME", "M_MIN_TIME", "M_TO_DAILY",
}

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from quantaalpha.factors.data_template.mongo_daily_pv import ts_code_to_instrument


PRICE_FIELDS = {"open", "high", "low", "close", "pre_close"}
SOURCE_FIELDS = PRICE_FIELDS | {"vol", "amount"}
MINUTE_COLUMNS = {
    "$m_open": "open", "$m_high": "high", "$m_low": "low",
    "$m_close": "close", "$m_pre_close": "pre_close",
    "$m_volume": "vol", "$m_amount": "amount",
}


@dataclass(frozen=True)
class MinuteDataIssue:
    trade_date: pd.Timestamp
    instrument: str
    reason: str


@dataclass
class MinuteDayResult:
    frame: pd.DataFrame
    issues: list[MinuteDataIssue] = field(default_factory=list)


def instrument_to_ts_code(instrument: str) -> str:
    text = str(instrument)
    if text.startswith(("sz", "sh")) and len(text) == 8:
        return f"{text[2:]}.{text[:2].upper()}"
    if "." in text:
        return text.upper()
    raise ValueError(f"Unsupported instrument format: {instrument}")


def is_sh_sz_a_share(instrument: str) -> bool:
    text = str(instrument).lower()
    if len(text) != 8 or not text[2:].isdigit():
        return False
    code = text[2:]
    if text.startswith("sh"):
        return code.startswith(("600", "601", "603", "605", "688", "689"))
    if text.startswith("sz"):
        return code.startswith(("000", "001", "002", "003", "300", "301"))
    return False


def _local_timestamp(value) -> pd.Timestamp:
    """Normalize the source's two equivalent local timestamp spellings.

    A trailing Z in this dataset is formatting noise rather than UTC semantics; stripping it
    is required to identify the known duplicate rows without shifting them by eight hours.
    """
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    stamp = pd.to_datetime(text, errors="coerce")
    return stamp.tz_localize(None) if isinstance(stamp, pd.Timestamp) and stamp.tzinfo else stamp


def normalize_minute_documents(
    rows: Iterable[dict],
    trade_date: str | pd.Timestamp,
    instrument: str,
    required_fields: Iterable[str],
    expected_bars: int = 241,
) -> MinuteDayResult:
    date = pd.Timestamp(trade_date).normalize()
    required = set(required_fields)
    records = list(rows)
    if not records:
        return MinuteDayResult(pd.DataFrame(), [MinuteDataIssue(date, instrument, "no_data")])

    frame = pd.DataFrame.from_records(records)
    time_source = frame.get("trade_time")
    if time_source is None:
        return MinuteDayResult(pd.DataFrame(), [MinuteDataIssue(date, instrument, "missing_trade_time")])
    frame["minute"] = time_source.map(_local_timestamp)
    frame = frame.dropna(subset=["minute"])
    frame = frame[frame["minute"].dt.normalize() == date]

    issues: list[MinuteDataIssue] = []
    conflicting_duplicates = 0
    clean_parts = []
    for minute, group in frame.groupby("minute", sort=True):
        if len(group) == 1:
            clean_parts.append(group.iloc[0])
            continue
        compare_fields = sorted((SOURCE_FIELDS & set(group.columns)) | required)
        first = group.iloc[0]
        equal = True
        for field_name in compare_fields:
            values = pd.to_numeric(group[field_name], errors="coerce")
            if values.isna().all():
                continue
            # The duplicated 2024-09-25 source batch mixes float32-like and
            # decimal representations (including a few yuan of amount rounding).
            # Treat economically identical rows as duplicates, while still
            # rejecting material disagreements.
            if not np.allclose(values, values.iloc[0], rtol=1e-6, atol=1e-6, equal_nan=True):
                equal = False
                break
        if not equal:
            conflicting_duplicates += 1
        else:
            clean_parts.append(first)

    if conflicting_duplicates:
        return MinuteDayResult(
            pd.DataFrame(),
            [MinuteDataIssue(date, instrument, f"conflicting_duplicates:{conflicting_duplicates}")],
        )
    clean = pd.DataFrame(clean_parts)
    if len(clean) != expected_bars:
        return MinuteDayResult(
            pd.DataFrame(), [MinuteDataIssue(date, instrument, f"bar_count:{len(clean)}")]
        )
    missing_columns = required - set(clean.columns)
    if missing_columns:
        return MinuteDayResult(
            pd.DataFrame(), [MinuteDataIssue(date, instrument, f"missing_fields:{','.join(sorted(missing_columns))}")]
        )
    for name in required:
        clean[name] = pd.to_numeric(clean[name], errors="coerce")
    strict_required = sorted(required - {"pre_close"})
    if strict_required and clean[strict_required].isna().any().any():
        return MinuteDayResult(
            pd.DataFrame(), [MinuteDataIssue(date, instrument, "null_required_value")]
        )
    clean["datetime"] = date
    clean["instrument"] = instrument
    clean = clean.sort_values("minute").set_index(["datetime", "instrument", "minute"])
    return MinuteDayResult(clean, [])


class MongoMinuteProvider:
    """Read one completed trading day at a time from MongoDB, without writes or disk cache."""

    def __init__(
        self,
        client=None,
        minute_db: str | None = None,
        daily_db: str | None = None,
        expected_bars: int = 241,
    ):
        if client is None:
            from pymongo import MongoClient
            uri = os.environ.get("MONGO_URI", "").strip()
            if not uri:
                raise RuntimeError("MONGO_URI must be configured for minute factors")
            client = MongoClient(uri, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
            client.admin.command("ping")
        self.client = client
        self.minute_db = client[minute_db or os.environ.get("MONGO_MINUTE_DB", "min_1")]
        resolved_daily_db = daily_db or os.environ.get("MONGO_DB", "").strip()
        self.daily_db = client[resolved_daily_db] if resolved_daily_db else None
        self.expected_bars = expected_bars

    @staticmethod
    def _collection(ts_code: str) -> str:
        return f"{ts_code}_1min"

    @staticmethod
    def _read_rows(collection, query: dict, projection: dict) -> list[dict]:
        from pymongo.errors import AutoReconnect

        for attempt in range(3):
            try:
                return list(collection.find(query, projection))
            except AutoReconnect:
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        raise AssertionError("unreachable")

    def _adjustment_factors(self, date: pd.Timestamp, ts_codes: list[str]) -> dict[str, float]:
        if self.daily_db is None:
            raise RuntimeError("MONGO_DB must be configured to apply point-in-time adjustment factors")
        collection = self.daily_db[f"Stock_Adj_{date.year}"]
        ymd = date.strftime("%Y%m%d")
        query = {"ts_code": {"$in": ts_codes}, "trade_date": {"$in": [ymd, date.strftime("%Y-%m-%d")]}}
        rows = self._read_rows(collection, query, {"_id": 0, "ts_code": 1, "adj_factor": 1})
        return {row["ts_code"]: float(row["adj_factor"]) for row in rows if row.get("adj_factor") is not None}

    def load_day(
        self,
        trade_date: str | pd.Timestamp,
        instruments: Iterable[str],
        minute_columns: Iterable[str],
    ) -> MinuteDayResult:
        date = pd.Timestamp(trade_date).normalize()
        instruments = [str(item) for item in instruments if is_sh_sz_a_share(str(item))]
        source_fields = {MINUTE_COLUMNS[column] for column in minute_columns}
        ts_codes = [instrument_to_ts_code(item) for item in instruments]
        factors = self._adjustment_factors(date, ts_codes) if source_fields & PRICE_FIELDS else {}
        output, issues = [], []
        date_values = [date.strftime("%Y%m%d"), date.strftime("%Y-%m-%d")]
        projection = {"_id": 0, "trade_time": 1, "trade_date": 1, **{name: 1 for name in source_fields}}
        for instrument, ts_code in zip(instruments, ts_codes):
            rows = self._read_rows(
                self.minute_db[self._collection(ts_code)],
                {"trade_date": {"$in": date_values}}, projection,
            )
            result = normalize_minute_documents(rows, date, instrument, source_fields, self.expected_bars)
            if result.frame.empty:
                issues.extend(result.issues)
                continue
            frame = result.frame.rename(columns={value: key for key, value in MINUTE_COLUMNS.items()})
            if source_fields & PRICE_FIELDS:
                factor = factors.get(ts_code)
                if factor is None:
                    issues.append(MinuteDataIssue(date, instrument, "missing_adj_factor"))
                    continue
                for column in set(frame.columns) & {f"$m_{name}" for name in PRICE_FIELDS}:
                    frame[column] = frame[column] * factor
            output.append(frame[list(minute_columns)])
        merged = pd.concat(output).sort_index() if output else pd.DataFrame(columns=list(minute_columns))
        return MinuteDayResult(merged, issues)

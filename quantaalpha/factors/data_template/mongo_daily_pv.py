from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BASE_FIELDS = {
    "open": "$open",
    "close": "$close",
    "high": "$high",
    "low": "$low",
    "vol": "$volume",
    "amount": "$amount",
}

DAILY_BASIC_FIELDS = {
    "volume_ratio": "$volume_ratio",
    "turnover_rate": "$turnover_rate",
    "turnover_rate_f": "$turnover_rate_f",
    "total_mv": "$total_mv",
    "pe": "$pe",
    "pe_ttm": "$pe_ttm",
    "pb": "$pb",
    "ps_ttm": "$ps_ttm",
}

BAK_DAILY_FIELDS = {
    "swing": "$swing",
    "float_mv": "$float_mv",
    "buying": "$buying",
    "selling": "$selling",
}

MONEYFLOW_FIELDS = {
    "buy_sm_vol": "$buy_sm_vol",
    "buy_sm_amount": "$buy_sm_amount",
    "sell_sm_vol": "$sell_sm_vol",
    "sell_sm_amount": "$sell_sm_amount",
    "buy_lg_vol": "$buy_lg_vol",
    "buy_lg_amount": "$buy_lg_amount",
    "sell_lg_vol": "$sell_lg_vol",
    "sell_lg_amount": "$sell_lg_amount",
    "net_mf_vol": "$net_mf_vol",
    "net_mf_amount": "$net_mf_amount",
}

FINAL_COLUMNS = [
    "$open",
    "$close",
    "$high",
    "$low",
    "$volume",
    "$amount",
    "$vwap",
    "$return",
    "$swing",
    "$volume_ratio",
    "$turnover_rate",
    "$turnover_rate_f",
    "$total_mv",
    "$float_mv",
    "$pe",
    "$pe_ttm",
    "$pb",
    "$ps_ttm",
    "$buy_sm_vol",
    "$buy_sm_amount",
    "$sell_sm_vol",
    "$sell_sm_amount",
    "$buy_lg_vol",
    "$buy_lg_amount",
    "$sell_lg_vol",
    "$sell_lg_amount",
    "$net_mf_vol",
    "$net_mf_amount",
    "$buying",
    "$selling",
]


@dataclass(frozen=True)
class MongoDailyPVConfig:
    start: str = "2018-01-01"
    end: str = "2025-12-31"
    full_output: Path = Path("daily_pv_all.h5")
    debug_output: Path = Path("daily_pv_debug.h5")
    debug_instruments: int = 100


def ts_code_to_instrument(ts_code: str) -> str:
    code, _, suffix = str(ts_code).partition(".")
    return f"{suffix.lower()}{code}" if suffix else code


def _to_ymd(value: str | pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _years(start: str, end: str) -> range:
    return range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)


def _collection_frame(db, collection: str, query: dict, projection: dict) -> pd.DataFrame:
    from pymongo.errors import PyMongoError

    if collection not in db.list_collection_names():
        return pd.DataFrame()
    last_error: Exception | None = None
    rows = []
    for _attempt in range(3):
        try:
            cursor = db[collection].find(query, projection, no_cursor_timeout=True).batch_size(20000)
            try:
                rows = list(cursor)
            finally:
                cursor.close()
            last_error = None
            break
        except PyMongoError as exc:
            last_error = exc
            rows = []
    if last_error is not None:
        raise last_error
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _prepare_common(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["datetime"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
    frame["instrument"] = frame["ts_code"].map(ts_code_to_instrument)
    frame = frame.drop(columns=[column for column in ["ts_code", "trade_date"] if column in frame])
    return frame.dropna(subset=["datetime", "instrument"]).drop_duplicates(
        ["datetime", "instrument"],
        keep="last",
    )


def _load_year(db, year: int, start_ymd: str, end_ymd: str) -> pd.DataFrame:
    query = {"trade_date": {"$gte": start_ymd, "$lte": end_ymd}}
    key_columns = ["datetime", "instrument"]

    base = _collection_frame(
        db,
        f"Stock_DayLine_{year}",
        query,
        {"_id": 0, "ts_code": 1, "trade_date": 1, **{field: 1 for field in BASE_FIELDS}},
    )
    if base.empty:
        return pd.DataFrame()
    base = _prepare_common(base).rename(columns=BASE_FIELDS)

    daily_basic = _collection_frame(
        db,
        f"Stock_DailyBasic_{year}",
        query,
        {"_id": 0, "ts_code": 1, "trade_date": 1, **{field: 1 for field in DAILY_BASIC_FIELDS}},
    )
    if not daily_basic.empty:
        daily_basic = _prepare_common(daily_basic).rename(columns=DAILY_BASIC_FIELDS)
        base = base.merge(daily_basic, on=key_columns, how="left", validate="one_to_one")

    bak_daily = _collection_frame(
        db,
        f"stock_bak_daily_{year}",
        query,
        {"_id": 0, "ts_code": 1, "trade_date": 1, **{field: 1 for field in BAK_DAILY_FIELDS}},
    )
    if not bak_daily.empty:
        bak_daily = _prepare_common(bak_daily).rename(columns=BAK_DAILY_FIELDS)
        base = base.merge(bak_daily, on=key_columns, how="left", validate="one_to_one")

    moneyflow = _collection_frame(
        db,
        f"StockMoneyflow_{year}",
        query,
        {"_id": 0, "ts_code": 1, "trade_date": 1, **{field: 1 for field in MONEYFLOW_FIELDS}},
    )
    if not moneyflow.empty:
        moneyflow = _prepare_common(moneyflow).rename(columns=MONEYFLOW_FIELDS)
        base = base.merge(moneyflow, on=key_columns, how="left", validate="one_to_one")

    return base


def normalize_daily_pv(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in FINAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    numeric_columns = [column for column in FINAL_COLUMNS if column not in {"$vwap", "$return"}]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["$pe"] = frame["$pe"].fillna(0.0)
    frame["$pe_ttm"] = frame["$pe_ttm"].fillna(0.0)
    frame["$vwap"] = frame["$amount"] / (frame["$volume"] + 1e-8)
    frame = frame.sort_values(["instrument", "datetime"])
    frame["$return"] = frame.groupby("instrument", sort=False)["$close"].pct_change().fillna(0.0)
    frame = frame.sort_values(["datetime", "instrument"]).set_index(["datetime", "instrument"])
    return frame[FINAL_COLUMNS]


def build_daily_pv(db, config: MongoDailyPVConfig) -> pd.DataFrame:
    start_ymd = _to_ymd(config.start)
    end_ymd = _to_ymd(config.end)
    frames = [
        _load_year(db, year, start_ymd, end_ymd)
        for year in _years(config.start, config.end)
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise RuntimeError("No Mongo daily stock data loaded")
    return normalize_daily_pv(pd.concat(frames, ignore_index=True))


def build_debug_frame(frame: pd.DataFrame, instrument_count: int) -> pd.DataFrame:
    instruments = frame.index.get_level_values("instrument").unique()[:instrument_count]
    return frame[frame.index.get_level_values("instrument").isin(instruments)].copy()


def write_hdf(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_hdf(path, key="data", mode="w", complevel=5, complib="blosc:zstd")


def _database():
    from pymongo import MongoClient

    uri = os.environ.get("MONGO_URI", "").strip()
    db_name = os.environ.get("MONGO_DB", "").strip()
    if not uri or not db_name:
        raise RuntimeError("MONGO_URI and MONGO_DB must be configured")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
    client.admin.command("ping")
    return client[db_name]


def main(argv: Iterable[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build enhanced daily_pv.h5 from Mongo daily features.")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--full-output", default="daily_pv_all.h5")
    parser.add_argument("--debug-output", default="daily_pv_debug.h5")
    parser.add_argument("--debug-instruments", type=int, default=100)
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = MongoDailyPVConfig(
        start=args.start,
        end=args.end,
        full_output=Path(args.full_output),
        debug_output=Path(args.debug_output),
        debug_instruments=args.debug_instruments,
    )
    frame = build_daily_pv(_database(), config)
    write_hdf(frame, config.full_output)
    write_hdf(build_debug_frame(frame, config.debug_instruments), config.debug_output)
    print(f"written {config.full_output} rows={len(frame)} columns={len(frame.columns)}")
    print(f"written {config.debug_output} rows={len(build_debug_frame(frame, config.debug_instruments))}")


if __name__ == "__main__":
    main()

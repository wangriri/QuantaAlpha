#!/usr/bin/env python3
"""Export local MongoDB market data into QuantaAlpha input files.

Outputs:
  - git_ignore_folder/factor_implementation_source_data/daily_pv.h5
  - git_ignore_folder/factor_implementation_source_data_debug/daily_pv.h5
  - data/mongo_exports/qlib_csv/*.csv

The HDF5 files are used by QuantaAlpha factor mining. The CSV files are shaped
for conversion to Qlib binary data with pyqlib's dump_bin utility.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
from pymongo import MongoClient


DEFAULT_MONGO_URI = "mongodb://hqy:hqy888@192.168.1.18:17629/admin?authSource=admin"
DEFAULT_DB = "StockBackSys"
PV_COLUMNS = ["$open", "$close", "$high", "$low", "$volume", "$amount", "$return"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI", DEFAULT_MONGO_URI))
    parser.add_argument("--db", default=os.environ.get("MONGO_DB", DEFAULT_DB))
    parser.add_argument("--start-year", type=int, default=int(os.environ.get("MONGO_START_YEAR", "2018")))
    parser.add_argument("--end-year", type=int, default=int(os.environ.get("MONGO_END_YEAR", "2025")))
    parser.add_argument("--market", default=os.environ.get("MONGO_MARKET", "csi300"))
    parser.add_argument("--debug-instruments", type=int, default=int(os.environ.get("DEBUG_INSTRUMENTS", "100")))
    parser.add_argument("--output-root", default=os.environ.get("DATA_EXPORT_ROOT", "."))
    parser.add_argument("--skip-csv", action="store_true", help="Only generate QuantaAlpha HDF5 files.")
    return parser.parse_args()


def iter_years(start_year: int, end_year: int) -> Iterable[int]:
    if end_year < start_year:
        raise ValueError("--end-year must be >= --start-year")
    return range(start_year, end_year + 1)


def stock_code_to_qlib(ts_code: str) -> str:
    code, exchange = ts_code.split(".")
    return f"{exchange.lower()}{code}"


def load_dayline(db, years: Iterable[int]) -> pd.DataFrame:
    fields = {
        "_id": 0,
        "ts_code": 1,
        "trade_date": 1,
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "vol": 1,
        "amount": 1,
    }
    frames: list[pd.DataFrame] = []
    for year in years:
        collection = f"Stock_DayLine_{year}"
        if collection not in db.list_collection_names():
            print(f"skip missing collection: {collection}")
            continue
        print(f"loading {collection} ...")
        docs = list(db[collection].find({}, fields))
        if docs:
            frames.append(pd.DataFrame.from_records(docs))

    if not frames:
        raise RuntimeError("No Stock_DayLine data was exported from MongoDB.")

    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    df["instrument"] = df["ts_code"].map(stock_code_to_qlib)
    df = df.rename(
        columns={
            "open": "$open",
            "high": "$high",
            "low": "$low",
            "close": "$close",
            "vol": "$volume",
            "amount": "$amount",
        }
    )
    for col in ["$open", "$high", "$low", "$close", "$volume", "$amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(["instrument", "datetime"])
    df["$return"] = df.groupby("instrument")["$close"].pct_change().fillna(0)
    df = df.set_index(["datetime", "instrument"]).sort_index()
    return df[PV_COLUMNS]


def load_calendar(db, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    docs = list(
        db.trade_calendar.find(
            {
                "is_open": 1,
                "cal_date": {
                    "$gte": start_date.strftime("%Y%m%d"),
                    "$lte": end_date.strftime("%Y%m%d"),
                },
            },
            {"_id": 0, "cal_date": 1},
        )
    )
    if not docs:
        raise RuntimeError("No open trading calendar rows found in MongoDB.")
    cal = pd.DataFrame.from_records(docs)
    cal["datetime"] = pd.to_datetime(cal["cal_date"], format="%Y%m%d")
    return cal.sort_values("datetime")


def load_instruments(db, instruments: list[str], start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    reverse = {stock_code_to_qlib(ts): ts for ts in db.Stock_Status.distinct("ts_code")}
    rows = []
    for instrument in instruments:
        ts_code = reverse.get(instrument)
        rows.append(
            {
                "instrument": instrument,
                "start_time": start_date.strftime("%Y-%m-%d"),
                "end_time": end_date.strftime("%Y-%m-%d"),
                "ts_code": ts_code or "",
            }
        )
    return pd.DataFrame(rows)


def write_h5(df: pd.DataFrame, output_root: Path, debug_instruments: int) -> None:
    full_dir = output_root / "git_ignore_folder" / "factor_implementation_source_data"
    debug_dir = output_root / "git_ignore_folder" / "factor_implementation_source_data_debug"
    full_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    full_path = full_dir / "daily_pv.h5"
    print(f"writing {full_path} ({len(df):,} rows) ...")
    df.to_hdf(full_path, key="data", mode="w")

    instruments = df.index.get_level_values("instrument").unique()[:debug_instruments]
    debug_df = df[df.index.get_level_values("instrument").isin(instruments)]
    debug_path = debug_dir / "daily_pv.h5"
    print(f"writing {debug_path} ({len(debug_df):,} rows) ...")
    debug_df.to_hdf(debug_path, key="data", mode="w")


def write_qlib_csv(df: pd.DataFrame, cal: pd.DataFrame, instruments_df: pd.DataFrame, output_root: Path, market: str) -> None:
    csv_root = output_root / "data" / "mongo_exports" / "qlib_csv"
    daily_dir = csv_root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    cal_path = csv_root / "calendars.csv"
    cal[["datetime"]].to_csv(cal_path, index=False, date_format="%Y-%m-%d")

    inst_dir = csv_root / "instruments"
    inst_dir.mkdir(exist_ok=True)
    all_inst = instruments_df[["instrument", "start_time", "end_time"]].sort_values("instrument")
    all_inst.to_csv(inst_dir / "all.txt", sep="\t", header=False, index=False)
    all_inst.to_csv(inst_dir / f"{market}.txt", sep="\t", header=False, index=False)

    csv_df = df.reset_index().rename(
        columns={
            "$open": "open",
            "$high": "high",
            "$low": "low",
            "$close": "close",
            "$volume": "volume",
            "$amount": "amount",
        }
    )
    csv_df["date"] = csv_df["datetime"].dt.strftime("%Y-%m-%d")
    for instrument, sub_df in csv_df.groupby("instrument", sort=True):
        out = daily_dir / f"{instrument}.csv"
        sub_df[["date", "open", "close", "high", "low", "volume", "amount"]].to_csv(out, index=False)

    print(f"wrote Qlib CSV staging files under {csv_root}")


def write_index_csv(db, start_date: pd.Timestamp, end_date: pd.Timestamp, output_root: Path) -> None:
    """Write benchmark index data, especially SH000300 used by default configs."""
    csv_root = output_root / "data" / "mongo_exports" / "qlib_csv"
    daily_dir = csv_root / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    fields = {
        "_id": 0,
        "ts_code": 1,
        "trade_date": 1,
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "vol": 1,
        "amount": 1,
    }
    cursor = db.Index_DayLine.find(
        {
            "trade_date": {
                "$gte": start_date.strftime("%Y%m%d"),
                "$lte": end_date.strftime("%Y%m%d"),
            },
        },
        fields,
    )
    index_df = pd.DataFrame.from_records(cursor)
    if index_df.empty:
        print("skip index csv: no Index_DayLine rows found")
        return
    index_df["instrument"] = index_df["ts_code"].map(stock_code_to_qlib)
    index_df["date"] = pd.to_datetime(index_df["trade_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    index_df = index_df.rename(columns={"vol": "volume"})
    for instrument, sub_df in index_df.groupby("instrument", sort=True):
        out = daily_dir / f"{instrument}.csv"
        sub_df[["date", "open", "close", "high", "low", "volume", "amount"]].to_csv(out, index=False)
    print(f"wrote index CSV files under {daily_dir}")


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root).resolve()

    client = MongoClient(args.mongo_uri, connectTimeoutMS=90000, serverSelectionTimeoutMS=90000)
    db = client[args.db]
    client.admin.command("ping")

    df = load_dayline(db, iter_years(args.start_year, args.end_year))
    start_date = df.index.get_level_values("datetime").min()
    end_date = df.index.get_level_values("datetime").max()
    instruments = sorted(df.index.get_level_values("instrument").unique())
    cal = load_calendar(db, start_date, end_date)
    instruments_df = load_instruments(db, instruments, start_date, end_date)

    print(f"exported date range: {start_date.date()} -> {end_date.date()}")
    print(f"exported instruments: {len(instruments):,}")
    write_h5(df, output_root, args.debug_instruments)
    if not args.skip_csv:
        write_qlib_csv(df, cal, instruments_df, output_root, args.market)
        write_index_csv(db, start_date, end_date, output_root)


if __name__ == "__main__":
    main()

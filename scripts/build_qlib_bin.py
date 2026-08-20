#!/usr/bin/env python3
"""Build a local Qlib binary dataset from the Mongo export staging files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


FIELD_MAP = {
    "$open": "open",
    "$close": "close",
    "$high": "high",
    "$low": "low",
    "$volume": "volume",
    "$amount": "amount",
    "$vwap": "vwap",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--h5", default="git_ignore_folder/factor_implementation_source_data/daily_pv.h5")
    parser.add_argument("--csv-root", default="data/mongo_exports/qlib_csv")
    parser.add_argument("--out", default="data/qlib/cn_data")
    parser.add_argument("--market", default="csi300")
    return parser.parse_args()


def write_feature(feature_dir: Path, field: str, values: pd.Series, calendar_index: dict[pd.Timestamp, int]) -> None:
    values = values.dropna()
    if values.empty:
        return

    idx = values.index.map(calendar_index.get)
    valid = pd.Series(idx, index=values.index).dropna().astype(int)
    if valid.empty:
        return

    start = int(valid.min())
    end = int(valid.max())
    arr = np.full(end - start + 1, np.nan, dtype=np.float32)
    for dt, pos in valid.items():
        arr[int(pos) - start] = np.float32(values.loc[dt])

    feature_dir.mkdir(parents=True, exist_ok=True)
    np.hstack([[start], arr]).astype("<f").tofile(feature_dir / f"{field}.day.bin")


def load_stock_data(h5_path: Path) -> pd.DataFrame:
    df = pd.read_hdf(h5_path, key="data").copy()
    if df.index.names != ["datetime", "instrument"]:
        df.index = df.index.set_names(["datetime", "instrument"])
    df["$vwap"] = np.where(df["$volume"].abs() > 0, df["$amount"] * 10.0 / df["$volume"], np.nan)
    return df


def load_index_data(csv_root: Path) -> pd.DataFrame:
    daily_dir = csv_root / "daily"
    frames = []
    for csv_path in daily_dir.glob("*.csv"):
        instrument = csv_path.stem.lower()
        if not (instrument.startswith("sh000") or instrument.startswith("sz399")):
            continue
        sub = pd.read_csv(csv_path)
        if sub.empty:
            continue
        sub["datetime"] = pd.to_datetime(sub["date"])
        sub["instrument"] = instrument
        sub["$open"] = sub["open"]
        sub["$close"] = sub["close"]
        sub["$high"] = sub["high"]
        sub["$low"] = sub["low"]
        sub["$volume"] = sub["volume"]
        sub["$amount"] = sub["amount"]
        sub["$vwap"] = np.where(sub["$volume"].abs() > 0, sub["$amount"] * 10.0 / sub["$volume"], np.nan)
        frames.append(sub.set_index(["datetime", "instrument"])[list(FIELD_MAP)])
    if not frames:
        return pd.DataFrame(columns=list(FIELD_MAP))
    return pd.concat(frames).sort_index()


def main() -> None:
    args = parse_args()
    root = Path(args.project_root).resolve()
    h5_path = (root / args.h5).resolve()
    csv_root = (root / args.csv_root).resolve()
    out = (root / args.out).resolve()

    stock_df = load_stock_data(h5_path)
    index_df = load_index_data(csv_root)
    all_df = pd.concat([stock_df, index_df]).sort_index()

    dates = pd.Index(sorted(all_df.index.get_level_values("datetime").unique()))
    calendar_index = {pd.Timestamp(dt): i for i, dt in enumerate(dates)}

    calendars_dir = out / "calendars"
    instruments_dir = out / "instruments"
    features_dir = out / "features"
    calendars_dir.mkdir(parents=True, exist_ok=True)
    instruments_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)

    pd.Series(dates.strftime("%Y-%m-%d")).to_csv(calendars_dir / "day.txt", index=False, header=False)

    stock_instruments = sorted(stock_df.index.get_level_values("instrument").unique())
    all_instruments = sorted(all_df.index.get_level_values("instrument").unique())
    start = dates.min().strftime("%Y-%m-%d")
    end = dates.max().strftime("%Y-%m-%d")
    for name, instruments in {"all": all_instruments, args.market: stock_instruments}.items():
        pd.DataFrame({"instrument": instruments, "start": start, "end": end}).to_csv(
            instruments_dir / f"{name}.txt",
            sep="\t",
            header=False,
            index=False,
        )

    for instrument, sub in all_df.groupby(level="instrument", sort=True):
        feature_dir = features_dir / instrument.lower()
        sub = sub.droplevel("instrument").sort_index()
        for qlib_field, file_field in FIELD_MAP.items():
            if qlib_field in sub:
                write_feature(feature_dir, file_field, pd.to_numeric(sub[qlib_field], errors="coerce"), calendar_index)

    print(f"Qlib data built at {out}")
    print(f"calendar days: {len(dates):,}")
    print(f"stock instruments in {args.market}: {len(stock_instruments):,}")
    print(f"all instruments including benchmarks: {len(all_instruments):,}")


if __name__ == "__main__":
    main()

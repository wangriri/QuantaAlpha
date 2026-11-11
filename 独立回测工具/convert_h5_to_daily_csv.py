#!/usr/bin/env python3
"""Convert a QuantaAlpha factor HDF5 Series into one CSV per trading day."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


QLIB_CODE_PATTERN = re.compile(r"^(?:sh|sz|bj)(\d{6})$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a MultiIndex factor Series in HDF5 to YYYYMMDD.csv files."
    )
    parser.add_argument("input_h5", type=Path, help="Input result.h5 path")
    parser.add_argument("output_dir", type=Path, help="Directory for daily CSV files")
    parser.add_argument("--key", default="data", help="HDF5 key (default: data)")
    parser.add_argument(
        "--factor-name",
        help="Output factor column name (default: use the Series name in HDF5)",
    )
    return parser.parse_args()


def normalize_instrument(instrument: object) -> str:
    """Convert a Qlib instrument such as sz000001 to a six-digit stock code."""
    text = str(instrument).strip()
    match = QLIB_CODE_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(f"Unsupported instrument code: {text!r}")
    return match.group(1)


def convert_h5_to_daily_csv(
    input_h5: Path,
    output_dir: Path,
    key: str = "data",
    factor_name: str | None = None,
) -> tuple[int, int, str, str, str]:
    """Convert the factor and return file/row/name/date summary values."""
    factor = pd.read_hdf(input_h5, key=key)
    if not isinstance(factor, pd.Series):
        raise TypeError(f"Expected a pandas Series, got {type(factor).__name__}")
    if factor.index.nlevels != 2:
        raise ValueError(f"Expected a 2-level index, got {factor.index.nlevels} levels")

    date_level = "datetime" if "datetime" in factor.index.names else factor.index.names[0]
    instrument_level = (
        "instrument" if "instrument" in factor.index.names else factor.index.names[1]
    )
    output_factor_name = factor_name or factor.name
    if not output_factor_name:
        raise ValueError("Factor has no name; pass --factor-name explicitly")

    dates = pd.to_datetime(factor.index.get_level_values(date_level), errors="raise")
    instruments = factor.index.get_level_values(instrument_level)
    codes = pd.Index(
        [normalize_instrument(value) for value in instruments],
        name="code",
    )

    frame = pd.DataFrame(
        {
            "date": dates,
            "code": codes,
            str(output_factor_name): factor.to_numpy(copy=False),
        }
    )
    duplicates = frame.duplicated(["date", "code"], keep=False)
    if duplicates.any():
        sample = frame.loc[duplicates, ["date", "code"]].head().to_dict("records")
        raise ValueError(f"Duplicate date/code pairs after normalization: {sample}")

    output_dir.mkdir(parents=True, exist_ok=True)
    file_count = 0
    row_count = 0
    for trade_date, daily in frame.groupby("date", sort=True):
        daily = daily.set_index("code")[[str(output_factor_name)]].sort_index()
        output_path = output_dir / f"{trade_date:%Y%m%d}.csv"
        temp_path = output_path.with_suffix(".csv.tmp")
        daily.to_csv(temp_path, index=True, index_label="code")
        temp_path.replace(output_path)
        file_count += 1
        row_count += len(daily)

    if file_count == 0:
        raise ValueError("No daily factor data was written")
    first_date = frame["date"].min().strftime("%Y%m%d")
    last_date = frame["date"].max().strftime("%Y%m%d")
    return file_count, row_count, str(output_factor_name), first_date, last_date


def main() -> None:
    args = parse_args()
    files, rows, name, first_date, last_date = convert_h5_to_daily_csv(
        input_h5=args.input_h5,
        output_dir=args.output_dir,
        key=args.key,
        factor_name=args.factor_name,
    )
    print(f"factor_name={name}")
    print(f"date_range={first_date}..{last_date}")
    print(f"files={files}")
    print(f"rows={rows}")
    print(f"output_dir={args.output_dir.resolve()}")


if __name__ == "__main__":
    main()

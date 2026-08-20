#!/usr/bin/env python3
"""Verify that the generated Qlib data can be read."""

from __future__ import annotations

import os

import qlib
from qlib.data import D


def main() -> None:
    provider = os.environ.get("QLIB_DATA_DIR", "/Users/wangjiayi/Downloads/QuantaAlpha/data/qlib/cn_data")
    qlib.init(provider_uri=provider, region="cn", expression_cache=None, dataset_cache=None)

    instruments = D.instruments("csi300")
    listed = D.list_instruments(instruments, start_time="2025-01-02", end_time="2025-01-10", as_list=True)
    print(f"csi300 instrument count: {len(listed)}")

    df = D.features(
        ["sz000001", "sh000300"],
        ["$open", "$close", "$volume", "$vwap"],
        start_time="2025-01-02",
        end_time="2025-01-10",
        freq="day",
        disk_cache=0,
    )
    print(df)


if __name__ == "__main__":
    main()

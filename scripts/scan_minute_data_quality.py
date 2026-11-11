#!/usr/bin/env python3
"""Read-only min_1 quality scan. Stores summary counts, never minute rows."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

from quantaalpha.factors.minute.mongo_reader import (
    MINUTE_COLUMNS,
    is_sh_sz_a_share,
    normalize_minute_documents,
    ts_code_to_instrument,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Scan min_1 without changing MongoDB")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--output", default="data/results/minute_quality_scan.json")
    parser.add_argument("--max-collections", type=int, default=0, help="0 scans every SH/SZ A-share collection")
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    uri = os.environ.get("MONGO_URI", "").strip()
    if not uri:
        raise RuntimeError("MONGO_URI is not configured")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
    db = client[os.environ.get("MONGO_MINUTE_DB", "min_1")]
    names = []
    for name in db.list_collection_names():
        if not name.endswith("_1min"):
            continue
        ts_code = name[:-5]
        try:
            if is_sh_sz_a_share(ts_code_to_instrument(ts_code)):
                names.append(name)
        except Exception:
            continue
    names.sort()
    if args.max_collections > 0:
        names = names[:args.max_collections]

    reasons, samples = Counter(), []
    stock_days = valid_stock_days = rows_read = 0
    projection = {"_id": 0, "trade_date": 1, "trade_time": 1, **{name: 1 for name in set(MINUTE_COLUMNS.values())}}
    for collection_name in names:
        ts_code = collection_name[:-5]
        instrument = ts_code_to_instrument(ts_code)
        cursor = db[collection_name].find(
            {"trade_date": {"$gte": args.start, "$lte": args.end}}, projection, no_cursor_timeout=True
        ).sort([("trade_date", 1), ("trade_time", 1)]).batch_size(20000)
        try:
            current_date, rows = None, []
            for row in cursor:
                rows_read += 1
                row_date = str(row.get("trade_date", ""))[:10].replace("-", "")
                if current_date is not None and row_date != current_date:
                    stock_days += 1
                    result = normalize_minute_documents(rows, current_date, instrument, MINUTE_COLUMNS.values())
                    if result.frame.empty:
                        for issue in result.issues:
                            reason = issue.reason.split(":", 1)[0]
                            reasons[reason] += 1
                            if len(samples) < 100:
                                samples.append({"date": str(issue.trade_date.date()), "instrument": instrument, "reason": issue.reason})
                    else:
                        valid_stock_days += 1
                    rows = []
                current_date = row_date
                rows.append(row)
            if rows and current_date:
                stock_days += 1
                result = normalize_minute_documents(rows, current_date, instrument, MINUTE_COLUMNS.values())
                if result.frame.empty:
                    for issue in result.issues:
                        reasons[issue.reason.split(":", 1)[0]] += 1
                else:
                    valid_stock_days += 1
        finally:
            cursor.close()

    report = {
        "database": db.name,
        "start": args.start,
        "end": args.end,
        "collections": len(names),
        "rows_read": rows_read,
        "stock_days": stock_days,
        "valid_stock_days": valid_stock_days,
        "coverage": valid_stock_days / stock_days if stock_days else 0.0,
        "issue_counts": dict(sorted(reasons.items())),
        "issue_samples": samples,
        "read_only": True,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "issue_samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

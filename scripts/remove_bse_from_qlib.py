#!/usr/bin/env python3
"""Remove Beijing Stock Exchange instruments from the local Qlib dataset.

This script only edits the Qlib binary dataset under --qlib-dir. It does not
connect to MongoDB or modify any source database.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qlib-dir", default="data/qlib/cn_data", help="Path to the active Qlib dataset.")
    parser.add_argument("--prefix", default="bj", help="Instrument prefix to remove. Defaults to BSE prefix bj.")
    parser.add_argument("--backup-dir", default=None, help="Optional backup directory. Defaults next to qlib-dir.")
    parser.add_argument("--apply", action="store_true", help="Actually update files. Without this, only preview.")
    return parser.parse_args()


def is_removed_instrument(line: str, prefix: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    return stripped.split()[0].lower().startswith(prefix.lower())


def filter_instrument_file(path: Path, qlib_dir: Path, backup_dir: Path, prefix: str, apply: bool) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = []
    removed = []
    for line in lines:
        if is_removed_instrument(line, prefix):
            removed.append(line.rstrip("\n"))
        else:
            kept.append(line)

    if apply and removed:
        backup_file = backup_dir / "instruments_original" / path.relative_to(qlib_dir)
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_file)
        path.write_text("".join(kept), encoding="utf-8")

    return {
        "file": str(path),
        "removed_count": len(removed),
        "kept_count": len(kept),
        "removed_preview": removed[:20],
    }


def move_feature_dirs(qlib_dir: Path, backup_dir: Path, prefix: str, apply: bool) -> dict:
    features_dir = qlib_dir / "features"
    if not features_dir.exists():
        return {"moved_count": 0, "moved_dirs": [], "note": "features directory does not exist"}

    removed_dirs = sorted(path for path in features_dir.iterdir() if path.is_dir() and path.name.lower().startswith(prefix.lower()))
    if apply and removed_dirs:
        target_root = backup_dir / "features"
        target_root.mkdir(parents=True, exist_ok=True)
        for source in removed_dirs:
            shutil.move(str(source), str(target_root / source.name))

    return {
        "moved_count": len(removed_dirs),
        "moved_dirs": [path.name for path in removed_dirs],
    }


def build_backup_dir(qlib_dir: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return qlib_dir.parent / f"{qlib_dir.name}_bse_backup_{timestamp}"


def main() -> None:
    args = parse_args()
    qlib_dir = Path(args.qlib_dir).expanduser().resolve()
    backup_dir = build_backup_dir(qlib_dir, args.backup_dir)

    if not qlib_dir.exists():
        raise SystemExit(f"Qlib directory does not exist: {qlib_dir}")
    if args.apply and backup_dir.exists():
        raise SystemExit(f"Backup directory already exists: {backup_dir}")
    if args.apply:
        backup_dir.mkdir(parents=True)

    instrument_reports = []
    instruments_dir = qlib_dir / "instruments"
    if instruments_dir.exists():
        for instrument_file in sorted(instruments_dir.glob("*.txt")):
            instrument_reports.append(filter_instrument_file(instrument_file, qlib_dir, backup_dir, args.prefix, args.apply))

    feature_report = move_feature_dirs(qlib_dir, backup_dir, args.prefix, args.apply)
    report = {
        "mode": "apply" if args.apply else "dry_run",
        "qlib_dir": str(qlib_dir),
        "backup_dir": str(backup_dir) if args.apply else None,
        "removed_prefix": args.prefix,
        "instrument_files": instrument_reports,
        "features": feature_report,
        "mongo_untouched": True,
    }

    if args.apply:
        (backup_dir / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

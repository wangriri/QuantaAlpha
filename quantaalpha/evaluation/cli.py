from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dedup import DeduplicationService
from .service import FactorLibraryEvaluationService


def _emit(data):
    print(json.dumps(data, ensure_ascii=False, default=str), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantaAlpha single-factor OTO evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate-library")
    evaluate.add_argument("--library", required=True)
    evaluate.add_argument("--mode", choices=["unevaluated", "all"], default="unevaluated")
    evaluate.add_argument("--factor-id", action="append", dest="factor_ids")
    evaluate.add_argument("--config")
    evaluate.add_argument("--refresh-market-cache", action="store_true")

    dedup = subparsers.add_parser("dedup-report")
    dedup.add_argument("--library", required=True)
    dedup.add_argument("--config")

    archive = subparsers.add_parser("archive-duplicates")
    archive.add_argument("--report", required=True)
    archive.add_argument("--factor-id", action="append", required=True, dest="factor_ids")
    archive.add_argument("--config")

    args = parser.parse_args()
    if args.command == "evaluate-library":
        from .config import load_evaluation_config

        service = FactorLibraryEvaluationService(load_evaluation_config(args.config))
        summary = service.evaluate_library(
            args.library,
            mode=args.mode,
            factor_ids=args.factor_ids,
            refresh_market_cache=args.refresh_market_cache,
            progress=lambda event: _emit({"type": "progress", **event}),
        )
        report = DeduplicationService(service.config).generate_report(args.library)
        _emit({"type": "result", "summary": summary, "dedup_report": report})
    elif args.command == "dedup-report":
        from .config import load_evaluation_config

        _emit({"type": "result", "dedup_report": DeduplicationService(load_evaluation_config(args.config)).generate_report(args.library)})
    else:
        from .config import load_evaluation_config

        service = DeduplicationService(load_evaluation_config(args.config))
        _emit({"type": "result", **service.archive_confirmed(args.report, args.factor_ids)})


if __name__ == "__main__":
    main()


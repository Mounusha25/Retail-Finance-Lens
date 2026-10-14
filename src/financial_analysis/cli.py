from __future__ import annotations

import argparse
import json
import logging
from datetime import date

from .config import COMPANIES, Settings
from .pipeline import ingest, load, refresh, transform, validate
from .report import generate_report


def _tickers(value: str) -> list[str]:
    if value.lower() == "all":
        return list(COMPANIES)
    return [item.strip().upper() for item in value.split(",")]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SEC retail financial analysis pipeline")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("ingest", "transform", "load", "validate", "refresh", "report"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--companies", default="all", help="Comma-separated WMT,TGT,COST or all")
        if command in {"transform", "refresh"}:
            sub.add_argument("--as-of", type=date.fromisoformat, help="Only use filings available by YYYY-MM-DD")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    tickers = _tickers(args.companies)
    if args.command == "ingest":
        result = {"downloaded": len(ingest(settings, tickers))}
    elif args.command == "transform":
        result = transform(settings, tickers, args.as_of)
    elif args.command == "load":
        result = {"run_id": str(load(settings, tickers))}
    elif args.command == "validate":
        result = validate(settings)
    elif args.command == "refresh":
        run_id, counts = refresh(settings, tickers, args.as_of)
        result = {"run_id": str(run_id), "validation": counts}
    else:
        result = {"report": str(generate_report(settings))}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

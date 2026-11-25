from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .engine import TickEngine, run_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate synthetic/normalized trade ticks into explainable observations.")
    parser.add_argument("input", type=Path, help="UTF-8 JSONL file of normalized trade ticks")
    parser.add_argument("--threshold-yuan", default="50000", help="absolute buy-sell net threshold in yuan")
    args = parser.parse_args()

    try:
        threshold = Decimal(args.threshold_yuan)
        with args.input.open(encoding="utf-8") as stream:
            for decision in run_jsonl(stream, TickEngine(threshold)):
                print(json.dumps(decision.as_dict(), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

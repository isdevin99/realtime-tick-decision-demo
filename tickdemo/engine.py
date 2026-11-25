from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TextIO


@dataclass(frozen=True)
class Tick:
    """Normalized trade tick. Price and turnover are yuan; volume is shares."""

    ts_code: str
    time: str
    price: Decimal
    volume: int
    turnover: Decimal
    bs_flag: str

    @property
    def epoch_millis_of_day(self) -> int:
        parsed = datetime.strptime(self.time, "%H:%M:%S.%f")
        return (((parsed.hour * 60 + parsed.minute) * 60 + parsed.second) * 1000
                + parsed.microsecond // 1000)


@dataclass(frozen=True)
class Decision:
    ts_code: str
    bucket_start: str
    bucket_end: str
    buy_yuan: Decimal
    sell_yuan: Decimal
    net_yuan: Decimal
    tick_count: int
    status: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("buy_yuan", "sell_yuan", "net_yuan"):
            result[key] = str(result[key])
        return result


def parse_tick(raw: dict[str, Any]) -> Tick:
    """Validate a normalized tick; never infer missing direction or size."""
    code = str(raw.get("ts_code", "")).strip().upper()
    if len(code) != 9 or code[6] != "." or code[:6].isdigit() is False:
        raise ValueError("ts_code must look like 000001.SZ")
    if code[-2:] not in {"SZ", "SH", "BJ"}:
        raise ValueError("ts_code suffix must be SZ, SH, or BJ")

    time_text = str(raw.get("time", ""))
    try:
        datetime.strptime(time_text, "%H:%M:%S.%f")
    except ValueError as exc:
        raise ValueError("time must use HH:MM:SS.mmm") from exc

    flag = str(raw.get("bs_flag", "")).strip().upper()
    if flag not in {"B", "S", "C", "N"}:
        raise ValueError("bs_flag must be B, S, C, or N")

    try:
        price = Decimal(str(raw["price"]))
        turnover = Decimal(str(raw["turnover"]))
        volume = int(raw["volume"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("price, volume, and turnover are required numeric fields") from exc
    if not price.is_finite() or price <= 0:
        raise ValueError("price must be finite and positive")
    if not turnover.is_finite() or turnover < 0:
        raise ValueError("turnover must be finite and nonnegative")
    if volume <= 0:
        raise ValueError("volume must be a positive share count")
    return Tick(code, time_text, price, volume, turnover, flag)


class TickEngine:
    """Aggregate B/S trade notional in fixed five-second buckets.

    C (cancel) and N (neutral/unknown aggressor) ticks do not contribute to
    directional net. A decision is emitted only when a later tick closes the
    bucket; flush() closes the final pending bucket explicitly.
    """

    def __init__(self, threshold_yuan: Decimal | int | str = Decimal("50000")) -> None:
        threshold = Decimal(str(threshold_yuan))
        if not threshold.is_finite() or threshold < 0:
            raise ValueError("threshold_yuan must be finite and nonnegative")
        self.threshold_yuan = threshold
        self._open: dict[tuple[str, int], dict[str, Any]] = {}
        self._last_slot: dict[str, int] = {}

    def push(self, tick: Tick) -> list[Decision]:
        slot = tick.epoch_millis_of_day // 5000
        previous = self._last_slot.get(tick.ts_code, -1)
        if slot < previous:
            raise ValueError(f"out-of-order tick for {tick.ts_code}: {tick.time}")
        if slot == previous:
            bucket = self._open.get((tick.ts_code, slot))
            if bucket is not None:
                self._add(bucket, tick)
            return []

        closed: list[Decision] = []
        for key in [key for key in self._open if key[0] == tick.ts_code and key[1] < slot]:
            bucket = self._open.pop(key)
            closed.append(self._decide(tick.ts_code, key[1], bucket))
        self._last_slot[tick.ts_code] = slot
        bucket = self._open.setdefault((tick.ts_code, slot), self._new_bucket())
        self._add(bucket, tick)
        return closed

    def flush(self) -> list[Decision]:
        closed = [self._decide(code, slot, bucket)
                  for (code, slot), bucket in sorted(self._open.items())]
        self._open.clear()
        return closed

    @staticmethod
    def _new_bucket() -> dict[str, Any]:
        return {"buy": Decimal(0), "sell": Decimal(0), "count": 0, "first": None, "last": None}

    @staticmethod
    def _add(bucket: dict[str, Any], tick: Tick) -> None:
        bucket["first"] = bucket["first"] or tick.time
        bucket["last"] = tick.time
        if tick.bs_flag == "B":
            bucket["buy"] += tick.turnover
            bucket["count"] += 1
        elif tick.bs_flag == "S":
            bucket["sell"] += tick.turnover
            bucket["count"] += 1

    def _decide(self, code: str, slot: int, bucket: dict[str, Any]) -> Decision:
        net = bucket["buy"] - bucket["sell"]
        start_ms = slot * 5000
        end_ms = start_ms + 4999

        def clock(ms: int) -> str:
            seconds, milli = divmod(ms, 1000)
            hours, rem = divmod(seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milli:03d}"

        if net >= self.threshold_yuan:
            status, reason = "observe_buy_pressure", f"buy-sell net {net} >= threshold {self.threshold_yuan} yuan"
        elif net <= -self.threshold_yuan:
            status, reason = "observe_sell_pressure", f"buy-sell net {net} <= -threshold {self.threshold_yuan} yuan"
        else:
            status, reason = "no_signal", f"absolute net {abs(net)} < threshold {self.threshold_yuan} yuan"
        return Decision(code, clock(start_ms), clock(end_ms), bucket["buy"], bucket["sell"],
                        net, bucket["count"], status, reason)


def run_jsonl(stream: TextIO, engine: TickEngine) -> Iterable[Decision]:
    """Read JSONL ticks, yielding completed bucket decisions."""
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("each JSONL row must be an object")
            tick = parse_tick(raw)
            yield from engine.push(tick)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"input line {line_number}: {exc}") from exc
    yield from engine.flush()

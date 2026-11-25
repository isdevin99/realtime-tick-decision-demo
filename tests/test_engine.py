from decimal import Decimal

import pytest

from tickdemo import Tick, TickEngine, parse_tick


def tick(time: str, flag: str, amount: str, *, code: str = "000001.SZ") -> Tick:
    return parse_tick({"ts_code": code, "time": time, "price": "10.00", "volume": 100,
                       "turnover": amount, "bs_flag": flag})


def test_buysell_net_emits_explainable_observation_when_next_slot_closes_bucket() -> None:
    engine = TickEngine("50000")
    assert engine.push(tick("09:30:01.000", "B", "60000")) == []
    decisions = engine.push(tick("09:30:06.000", "B", "100"))
    assert len(decisions) == 1
    assert decisions[0].status == "observe_buy_pressure"
    assert decisions[0].buy_yuan == Decimal("60000")
    assert decisions[0].net_yuan == Decimal("60000")
    assert "60000" in decisions[0].reason


def test_sell_pressure_and_cancel_neutral_are_not_directional_volume() -> None:
    engine = TickEngine("100")
    engine.push(tick("09:30:01.000", "C", "9000"))
    engine.push(tick("09:30:02.000", "N", "9000"))
    engine.push(tick("09:30:03.000", "S", "250"))
    decisions = engine.push(tick("09:30:06.000", "N", "9999"))
    assert decisions[0].status == "observe_sell_pressure"
    assert decisions[0].sell_yuan == Decimal("250")
    assert decisions[0].buy_yuan == Decimal("0")
    assert decisions[0].tick_count == 1


def test_flush_closes_last_open_bucket() -> None:
    engine = TickEngine("1")
    engine.push(tick("09:30:01.000", "B", "10"))
    decisions = engine.flush()
    assert len(decisions) == 1
    assert decisions[0].bucket_start == "09:30:00.000"
    assert decisions[0].bucket_end == "09:30:04.999"


def test_rejects_missing_or_invalid_trade_fields() -> None:
    with pytest.raises(ValueError, match="volume"):
        parse_tick({"ts_code": "000001.SZ", "time": "09:30:01.000", "price": 10, "bs_flag": "B"})
    with pytest.raises(ValueError, match="positive"):
        parse_tick({"ts_code": "000001.SZ", "time": "09:30:01.000", "price": 10,
                    "volume": 0, "turnover": 0, "bs_flag": "B"})
    with pytest.raises(ValueError, match="bs_flag"):
        tick("09:30:01.000", "?", "100")


def test_rejects_out_of_order_slots_per_symbol() -> None:
    engine = TickEngine("0")
    engine.push(tick("09:30:06.000", "B", "10"))
    with pytest.raises(ValueError, match="out-of-order"):
        engine.push(tick("09:30:01.000", "B", "10"))


def test_jsonl_example_contains_synthetic_data_and_emits_two_buckets(tmp_path) -> None:
    from tickdemo.engine import run_jsonl
    from pathlib import Path

    example = Path(__file__).parents[1] / "examples" / "synthetic_ticks.jsonl"
    with example.open(encoding="utf-8") as stream:
        decisions = list(run_jsonl(stream, TickEngine("20000")))
    assert len(decisions) == 3
    assert decisions[0].status == "observe_buy_pressure"
    assert decisions[0].buy_yuan == Decimal("60000")
    assert decisions[0].sell_yuan == Decimal("25025")
    assert decisions[-1].status == "no_signal"

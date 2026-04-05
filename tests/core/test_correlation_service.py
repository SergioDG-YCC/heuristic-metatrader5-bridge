from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from heuristic_mt5_bridge.core.correlation.models import (
    CorrelationMatrixSnapshot,
    CorrelationPairValue,
)
from heuristic_mt5_bridge.core.correlation.service import CorrelationService, _pearson


_BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_H = timedelta(hours=1)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_candles(n: int, *, start: float = 1.0, step: float = 0.001) -> list[dict]:
    return [
        {
            "timestamp": _ts(_BASE + i * _H),
            "open": start + i * step,
            "high": start + i * step + 0.0002,
            "low": start + i * step - 0.0001,
            "close": start + i * step,
            "volume": 100,
        }
        for i in range(n)
    ]


def _make_candles_with_timestamps(closes_by_ts: dict[str, float]) -> list[dict]:
    result = []
    for ts, close in closes_by_ts.items():
        result.append({"timestamp": ts, "close": close, "open": close, "high": close, "low": close})
    return result


class _MockMarketState:
    """Minimal stub for MarketStateService used in tests."""

    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {}
        self._updated_at: dict[str, str] = {}

    def set_candles(self, symbol: str, timeframe: str, candles: list[dict]) -> None:
        key = f"{symbol.upper()}::{timeframe.upper()}"
        self._data[key] = candles
        self._updated_at[key] = _ts(_BASE)

    def get_candles(self, symbol: str, timeframe: str, bars: int | None = None) -> list[dict]:
        key = f"{symbol.upper()}::{timeframe.upper()}"
        candles = self._data.get(key, [])
        if bars is not None:
            candles = candles[-bars:]
        return candles

    def query(self, symbol: str, timeframe: str, key: str) -> object:
        state_key = f"{symbol.upper()}::{timeframe.upper()}"
        if key == "updated_at":
            return self._updated_at.get(state_key)
        return None


class _MockSubscriptionManager:
    def __init__(self, symbols: list[str]) -> None:
        self._symbols = list(symbols)

    def subscribed_universe(self) -> list[str]:
        return list(self._symbols)

    def replace(self, symbols: list[str]) -> None:
        self._symbols = list(symbols)


def _make_service(
    symbols: list[str],
    *,
    window_bars: int = 50,
    min_coverage_bars: int = 5,
    timeframes: list[str] | None = None,
) -> tuple[CorrelationService, _MockMarketState, _MockSubscriptionManager]:
    ms = _MockMarketState()
    sm = _MockSubscriptionManager(symbols)
    svc = CorrelationService(
        ms,
        sm,
        window_bars=window_bars,
        min_coverage_bars=min_coverage_bars,
        timeframes=timeframes or ["M5"],
    )
    return svc, ms, sm


class TestCorrelationServiceGetPairBeforeRefresh(unittest.TestCase):
    def test_returns_none_before_first_refresh(self) -> None:
        svc, _, _ = _make_service(["EURUSD", "GBPUSD"])
        result = svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNone(result)

    def test_get_matrix_none_before_refresh(self) -> None:
        svc, _, _ = _make_service(["EURUSD"])
        self.assertIsNone(svc.get_matrix("M5"))


class TestCorrelationServiceAfterRefresh(unittest.TestCase):
    def setUp(self) -> None:
        self.svc, self.ms, self.sm = _make_service(
            ["EURUSD", "GBPUSD"],
            min_coverage_bars=5,
        )
        # Feed identical up-trending closes → perfect positive correlation
        candles_eur = _make_candles(20, start=1.1000, step=0.0005)
        candles_gbp = _make_candles(20, start=1.2700, step=0.0007)
        self.ms.set_candles("EURUSD", "M5", candles_eur)
        self.ms.set_candles("GBPUSD", "M5", candles_gbp)

    def _refresh(self) -> None:
        snapshot = self.svc._refresh_timeframe("M5")
        self.svc._snapshots["M5"] = snapshot

    def test_get_pair_after_refresh(self) -> None:
        self._refresh()
        pair = self.svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertIsInstance(pair, CorrelationPairValue)

    def test_get_pair_commutative(self) -> None:
        self._refresh()
        pair_ab = self.svc.get_pair("EURUSD", "GBPUSD", "M5")
        pair_ba = self.svc.get_pair("GBPUSD", "EURUSD", "M5")
        self.assertIsNotNone(pair_ab)
        self.assertIsNotNone(pair_ba)
        self.assertIs(pair_ab, pair_ba)

    def test_coefficient_not_none_with_sufficient_data(self) -> None:
        self._refresh()
        pair = self.svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertIsNotNone(pair.coefficient)

    def test_coverage_ok_with_sufficient_data(self) -> None:
        self._refresh()
        pair = self.svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertTrue(pair.coverage_ok)

    def test_get_matrix_returns_snapshot(self) -> None:
        self._refresh()
        matrix = self.svc.get_matrix("M5")
        self.assertIsNotNone(matrix)
        self.assertIsInstance(matrix, CorrelationMatrixSnapshot)
        self.assertEqual(matrix.timeframe, "M5")

    def test_get_matrix_case_insensitive(self) -> None:
        self._refresh()
        self.assertIs(self.svc.get_matrix("M5"), self.svc.get_matrix("m5"))

    def test_exposure_relations_returns_pair(self) -> None:
        self._refresh()
        relations = self.svc.get_exposure_relations("EURUSD", "M5")
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0].symbol_a, "EURUSD")
        self.assertEqual(relations[0].symbol_b, "GBPUSD")


class TestAtomicSnapshotSwap(unittest.TestCase):
    def test_second_refresh_replaces_snapshot(self) -> None:
        svc, ms, _ = _make_service(["EURUSD", "GBPUSD"], min_coverage_bars=5)
        candles = _make_candles(15, start=1.1000, step=0.0005)
        ms.set_candles("EURUSD", "M5", candles)
        ms.set_candles("GBPUSD", "M5", _make_candles(15, start=1.27, step=0.0007))

        snap1 = svc._refresh_timeframe("M5")
        svc._snapshots["M5"] = snap1

        snap2 = svc._refresh_timeframe("M5")
        svc._snapshots["M5"] = snap2

        self.assertIsNot(svc._snapshots["M5"], snap1)
        self.assertIs(svc._snapshots["M5"], snap2)


class TestCoverageOkFlag(unittest.TestCase):
    def test_coverage_not_ok_when_below_min_bars(self) -> None:
        svc, ms, _ = _make_service(
            ["EURUSD", "GBPUSD"],
            window_bars=50,
            min_coverage_bars=30,  # require 30 but only provide 10
        )
        candles = _make_candles(10, start=1.1000, step=0.0005)
        ms.set_candles("EURUSD", "M5", candles)
        ms.set_candles("GBPUSD", "M5", _make_candles(10, start=1.27, step=0.0007))

        snapshot = svc._refresh_timeframe("M5")
        svc._snapshots["M5"] = snapshot

        pair = svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertFalse(pair.coverage_ok)

    def test_coverage_ok_when_above_min_bars(self) -> None:
        svc, ms, _ = _make_service(
            ["EURUSD", "GBPUSD"],
            window_bars=50,
            min_coverage_bars=5,
        )
        candles = _make_candles(20, start=1.1000, step=0.0005)
        ms.set_candles("EURUSD", "M5", candles)
        ms.set_candles("GBPUSD", "M5", _make_candles(20, start=1.27, step=0.0007))

        snapshot = svc._refresh_timeframe("M5")
        svc._snapshots["M5"] = snapshot

        pair = svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertTrue(pair.coverage_ok)


class TestNullWhenNoData(unittest.TestCase):
    def test_coefficient_none_when_no_candles(self) -> None:
        svc, ms, _ = _make_service(["EURUSD", "GBPUSD"], min_coverage_bars=5)
        # Deliberately do NOT set any candles

        snapshot = svc._refresh_timeframe("M5")
        svc._snapshots["M5"] = snapshot

        pair = svc.get_pair("EURUSD", "GBPUSD", "M5")
        self.assertIsNotNone(pair)
        self.assertIsNone(pair.coefficient)
        self.assertFalse(pair.coverage_ok)


class TestElasticUniverse(unittest.TestCase):
    def test_new_symbol_picked_up_on_next_refresh(self) -> None:
        svc, ms, sm = _make_service(["EURUSD", "GBPUSD"], min_coverage_bars=5)
        for sym in ["EURUSD", "GBPUSD", "AUDUSD"]:
            ms.set_candles(sym, "M5", _make_candles(10, start=1.0, step=0.001))

        # First refresh — AUDUSD is not in universe yet
        snap1 = svc._refresh_timeframe("M5")
        self.assertNotIn(("EURUSD", "AUDUSD"), snap1.pairs)
        self.assertNotIn(("GBPUSD", "AUDUSD"), snap1.pairs)

        # Add AUDUSD to universe
        sm.replace(["EURUSD", "GBPUSD", "AUDUSD"])
        snap2 = svc._refresh_timeframe("M5")
        # Some pair with AUDUSD should now exist
        self.assertTrue(
            any("AUDUSD" in key for key in snap2.pairs.keys())
        )

    def test_active_symbols_reflects_universe(self) -> None:
        svc, _, sm = _make_service(["EURUSD", "GBPUSD"])
        self.assertEqual(set(svc.active_symbols()), {"EURUSD", "GBPUSD"})
        sm.replace(["EURUSD", "GBPUSD", "AUDUSD"])
        self.assertEqual(set(svc.active_symbols()), {"EURUSD", "GBPUSD", "AUDUSD"})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

from heuristic_mt5_bridge.core.correlation.aligner import (
    _iso_to_epoch,
    _log_returns,
    _simple_returns,
    align_and_returns,
)


def _ts(dt: datetime) -> str:
    """Format a UTC datetime as an ISO UTC string (Z suffix)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_candles(
    timestamps: list[str],
    closes: list[float],
) -> list[dict]:
    return [
        {"timestamp": ts, "open": c, "high": c, "low": c, "close": c, "volume": 100}
        for ts, c in zip(timestamps, closes)
    ]


_BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_H = timedelta(hours=1)


class TestIsoToEpoch(unittest.TestCase):
    def test_z_suffix(self) -> None:
        epoch = _iso_to_epoch("2026-01-01T00:00:00Z")
        self.assertIsNotNone(epoch)
        self.assertIsInstance(epoch, int)

    def test_plus_zero_suffix(self) -> None:
        a = _iso_to_epoch("2026-01-01T00:00:00Z")
        b = _iso_to_epoch("2026-01-01T00:00:00+00:00")
        self.assertEqual(a, b)

    def test_no_tz(self) -> None:
        # Treated as UTC when no timezone info is present
        a = _iso_to_epoch("2026-01-01T00:00:00Z")
        b = _iso_to_epoch("2026-01-01T00:00:00")
        self.assertEqual(a, b)

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_iso_to_epoch(""))

    def test_invalid_string_returns_none(self) -> None:
        self.assertIsNone(_iso_to_epoch("not-a-date"))

    def test_different_hours(self) -> None:
        e1 = _iso_to_epoch("2026-01-01T00:00:00Z")
        e2 = _iso_to_epoch("2026-01-01T01:00:00Z")
        self.assertIsNotNone(e1)
        self.assertIsNotNone(e2)
        self.assertEqual(e2 - e1, 3600)


class TestSimpleReturns(unittest.TestCase):
    def test_basic(self) -> None:
        closes = [100.0, 110.0, 99.0]
        returns = _simple_returns(closes)
        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(returns[0], 0.1)          # (110-100)/100
        self.assertAlmostEqual(returns[1], -11.0 / 110.0)

    def test_single_close_returns_empty(self) -> None:
        self.assertEqual(_simple_returns([1.0]), [])

    def test_zero_prev_does_not_crash(self) -> None:
        closes = [0.0, 1.0, 2.0]
        returns = _simple_returns(closes)
        self.assertEqual(len(returns), 2)
        self.assertEqual(returns[0], 0.0)  # prev=0 → safe fallback


class TestLogReturns(unittest.TestCase):
    def test_basic(self) -> None:
        closes = [100.0, 110.0, 99.0]
        returns = _log_returns(closes)
        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(returns[0], math.log(110.0 / 100.0))
        self.assertAlmostEqual(returns[1], math.log(99.0 / 110.0))

    def test_zero_close_does_not_crash(self) -> None:
        closes = [100.0, 0.0, 100.0]
        returns = _log_returns(closes)
        self.assertEqual(len(returns), 2)
        self.assertEqual(returns[0], 0.0)


class TestAlignAndReturns(unittest.TestCase):
    def _series(self, n: int, *, start_close: float = 1.0, step: float = 0.001) -> list[dict]:
        ts_list = [_ts(_BASE + i * _H) for i in range(n)]
        closes = [start_close + i * step for i in range(n)]
        return _make_candles(ts_list, closes)

    def test_perfect_alignment(self) -> None:
        candles_a = self._series(10)
        candles_b = self._series(10, start_close=2.0)
        result = align_and_returns(
            candles_a, candles_b, symbol_a="A", symbol_b="B", timeframe="M5"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.aligned_count, 10)
        self.assertAlmostEqual(result.coverage_ratio, 1.0)
        self.assertEqual(len(result.returns_a), 9)  # n-1 returns

    def test_gap_in_b_reduces_aligned_count(self) -> None:
        ts_all = [_ts(_BASE + i * _H) for i in range(6)]
        ts_gap = [_ts(_BASE + i * _H) for i in range(6) if i != 3]  # drop index 3
        candles_a = _make_candles(ts_all, [1.0 + i * 0.01 for i in range(6)])
        candles_b = _make_candles(ts_gap, [2.0 + i * 0.01 for i in range(5)])
        result = align_and_returns(
            candles_a, candles_b, symbol_a="A", symbol_b="B", timeframe="H1"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.aligned_count, 5)

    def test_no_overlap_returns_none(self) -> None:
        ts_a = [_ts(_BASE + i * _H) for i in range(5)]
        ts_b = [_ts(_BASE + timedelta(days=10) + i * _H) for i in range(5)]
        candles_a = _make_candles(ts_a, [1.0 + i * 0.001 for i in range(5)])
        candles_b = _make_candles(ts_b, [2.0 + i * 0.001 for i in range(5)])
        result = align_and_returns(candles_a, candles_b)
        self.assertIsNone(result)

    def test_empty_candles_returns_none(self) -> None:
        self.assertIsNone(align_and_returns([], []))

    def test_one_empty_side_returns_none(self) -> None:
        candles_a = self._series(5)
        self.assertIsNone(align_and_returns(candles_a, []))

    def test_fewer_than_three_common_returns_none(self) -> None:
        ts_a = [_ts(_BASE + i * _H) for i in range(5)]
        ts_b = [_ts(_BASE + i * _H) for i in [0, 1]]  # only 2 common with first 2 of a
        candles_a = _make_candles(ts_a, [1.0 + i * 0.001 for i in range(5)])
        candles_b = _make_candles(ts_b, [2.0, 2.001])
        result = align_and_returns(candles_a, candles_b)
        self.assertIsNone(result)

    def test_log_return_type(self) -> None:
        ts = [_ts(_BASE + i * _H) for i in range(4)]
        closes = [100.0, 110.0, 105.0, 108.0]
        candles = _make_candles(ts, closes)
        result = align_and_returns(
            candles,
            candles,
            symbol_a="X",
            symbol_b="X",
            timeframe="H1",
            return_type="log",
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.returns_a[0], math.log(110.0 / 100.0))

    def test_simple_return_formula(self) -> None:
        ts = [_ts(_BASE + i * _H) for i in range(4)]
        closes = [100.0, 110.0, 99.0, 108.0]
        candles = _make_candles(ts, closes)
        result = align_and_returns(
            candles,
            candles,
            return_type="simple",
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.returns_a[0], 0.1)
        self.assertAlmostEqual(result.returns_a[1], -11.0 / 110.0)

    def test_coverage_ratio_with_gap(self) -> None:
        # 10 bars in A, 8 in B (B is missing 2), 8 common
        ts_a = [_ts(_BASE + i * _H) for i in range(10)]
        ts_b = [_ts(_BASE + i * _H) for i in range(8)]
        candles_a = _make_candles(ts_a, [1.0 + i * 0.001 for i in range(10)])
        candles_b = _make_candles(ts_b, [2.0 + i * 0.001 for i in range(8)])
        result = align_and_returns(candles_a, candles_b)
        self.assertIsNotNone(result)
        self.assertEqual(result.aligned_count, 8)
        # min(10, 8) = 8; coverage = 8/8 = 1.0
        self.assertAlmostEqual(result.coverage_ratio, 1.0)

    def test_metadata_fields(self) -> None:
        candles_a = self._series(5)
        candles_b = self._series(5, start_close=2.0)
        result = align_and_returns(
            candles_a, candles_b, symbol_a="EURUSD", symbol_b="GBPUSD", timeframe="M15"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol_a, "EURUSD")
        self.assertEqual(result.symbol_b, "GBPUSD")
        self.assertEqual(result.timeframe, "M15")


if __name__ == "__main__":
    unittest.main()

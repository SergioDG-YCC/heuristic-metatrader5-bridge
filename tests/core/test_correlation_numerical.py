from __future__ import annotations

import unittest

from heuristic_mt5_bridge.core.correlation.service import _pearson


class TestPearsonPureFunction(unittest.TestCase):
    """Unit tests for the pure Python Pearson implementation.

    These tests verify mathematical correctness independently of any candle data
    or market connectivity.
    """

    def test_perfect_positive_correlation(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 1.0, places=10)

    def test_perfect_negative_correlation(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, -1.0, places=10)

    def test_zero_variance_x_returns_none(self) -> None:
        xs = [1.0, 1.0, 1.0, 1.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        self.assertIsNone(_pearson(xs, ys))

    def test_zero_variance_y_returns_none(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [5.0, 5.0, 5.0, 5.0]
        self.assertIsNone(_pearson(xs, ys))

    def test_both_zero_variance_returns_none(self) -> None:
        xs = [3.0, 3.0, 3.0]
        ys = [7.0, 7.0, 7.0]
        self.assertIsNone(_pearson(xs, ys))

    def test_single_element_returns_none(self) -> None:
        self.assertIsNone(_pearson([1.0], [1.0]))

    def test_empty_series_returns_none(self) -> None:
        self.assertIsNone(_pearson([], []))

    def test_mismatched_lengths_returns_none(self) -> None:
        self.assertIsNone(_pearson([1.0, 2.0, 3.0], [1.0, 2.0]))

    def test_known_value(self) -> None:
        # xs=[1,2,3,4,5], ys=[2,4,5,4,5]
        # mean_x=3, mean_y=4
        # dx=[-2,-1,0,1,2], dy=[-2,0,1,0,1]
        # cov = 4+0+0+0+2 = 6
        # var_x=10, var_y=6
        # r = 6 / sqrt(60) ≈ 0.7746
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 5.0, 4.0, 5.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 6.0 / (60.0 ** 0.5), places=10)

    def test_known_value_simple(self) -> None:
        # xs=[1,2,3], ys=[1,3,2]
        # mean_x=2, mean_y=2
        # cov = (-1)(-1)+(0)(1)+(1)(0) = 1
        # var_x=2, var_y=2, r=1/2=0.5
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 3.0, 2.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.5, places=10)

    def test_result_clamped_to_plus_one(self) -> None:
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 2.0, 3.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertLessEqual(result, 1.0)

    def test_result_clamped_to_minus_one(self) -> None:
        xs = [1.0, 2.0, 3.0]
        ys = [3.0, 2.0, 1.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, -1.0)

    def test_result_is_never_zero_for_nonzero_correlation(self) -> None:
        # r=0.5 was verified above; ensure it's not None and not 0.0
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 3.0, 2.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertNotEqual(result, 0.0)

    def test_minimum_two_elements(self) -> None:
        # 2 elements: well-defined as ±1.0 when non-constant
        xs = [1.0, 2.0]
        ys = [1.0, 2.0]
        result = _pearson(xs, ys)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 1.0, places=10)


if __name__ == "__main__":
    unittest.main()

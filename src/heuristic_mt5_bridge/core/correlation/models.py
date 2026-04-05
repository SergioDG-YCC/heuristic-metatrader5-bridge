from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlignmentResult:
    """Result of epoch-based inner join alignment between two candle series.

    ``returns_a`` and ``returns_b`` are the return series computed on the aligned
    close prices.  They have ``aligned_count - 1`` elements.  ``aligned_count``
    is the number of common epochs found (close prices).
    """

    symbol_a: str
    symbol_b: str
    timeframe: str
    returns_a: list[float]
    returns_b: list[float]
    aligned_count: int
    coverage_ratio: float  # aligned_count / min(len(candles_a), len(candles_b))


@dataclass
class CorrelationPairValue:
    """Pearson correlation result for a single (symbol_a, symbol_b, timeframe) triple.

    ``coefficient`` is ``None`` when there is insufficient data or when one series
    has zero variance.  It is *never* set to ``0.0`` as a sentinel value.
    """

    symbol_a: str
    symbol_b: str
    timeframe: str
    coefficient: float | None
    bars_used: int
    coverage_ratio: float
    coverage_ok: bool
    source_stale: bool
    computed_at: str  # ISO UTC string


@dataclass
class CorrelationMatrixSnapshot:
    """Atomic correlation matrix for a single timeframe.

    Instances are never mutated after assignment — always replaced atomically via::

        self._snapshots[tf] = new_snapshot
    """

    timeframe: str
    pairs: dict[tuple[str, str], CorrelationPairValue] = field(default_factory=dict)
    computed_at: str = ""
    min_pair_bars: int = 0
    all_pairs_coverage_ok: bool = False
    compute_stale: bool = False

    def get_pair(self, symbol_a: str, symbol_b: str) -> CorrelationPairValue | None:
        """Look up a pair regardless of key insertion order."""
        key_ab = (symbol_a.upper(), symbol_b.upper())
        key_ba = (symbol_b.upper(), symbol_a.upper())
        return self.pairs.get(key_ab) or self.pairs.get(key_ba)

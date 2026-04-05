from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from heuristic_mt5_bridge.core.correlation.service import CorrelationService


class FastCorrelationPolicy:
    """Interpret raw :class:`CorrelationPairValue` data for Fast Desk execution decisions.

    This is a **policy layer** — it consumes the pure-math output of
    :class:`CorrelationService` and applies thresholds relevant to intra-day
    execution risk.  No Pearson math lives here.

    Typical usage inside ``FastContextService.build_context``::

        policy = FastCorrelationPolicy(correlation_service)
        details["correlation"] = policy.build_details(symbol)
        conflict, reason = policy.check_entry_conflict(symbol, "buy", open_positions)
    """

    _CLASSIFICATIONS = ("high", "moderate", "low", "none", "unavailable")

    def __init__(
        self,
        correlation_service: CorrelationService,
        *,
        high_threshold: float = 0.80,
        moderate_threshold: float = 0.60,
        timeframe: str = "M5",
    ) -> None:
        self._service = correlation_service
        self._high_threshold = high_threshold
        self._moderate_threshold = moderate_threshold
        self._timeframe = timeframe.upper()

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, coefficient: float | None) -> str:
        """Map a raw Pearson coefficient to a human-readable classification.

        Returns one of: ``"high"``, ``"moderate"``, ``"low"``, ``"none"``,
        ``"unavailable"``.
        """
        if coefficient is None:
            return "unavailable"
        abs_r = abs(coefficient)
        if abs_r >= self._high_threshold:
            return "high"
        if abs_r >= self._moderate_threshold:
            return "moderate"
        if abs_r > 0.0:
            return "low"
        return "none"

    # ------------------------------------------------------------------
    # Entry conflict detection
    # ------------------------------------------------------------------

    def check_entry_conflict(
        self,
        symbol: str,
        side: str,
        open_positions: list[dict[str, Any]],
        *,
        timeframe: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether any open position creates a correlation conflict for a new entry.

        A conflict is flagged when:

        * **Implicit hedge**: strong positive correlation (r ≥ ``high_threshold``) and
          the new entry side is *opposite* to the open position's side — the two
          instruments tend to move together so opposing directions cancel out.
        * **Inverse concentration**: strong negative correlation (r ≤ ``-high_threshold``)
          and the new entry side is the *same* as the open position's side — instruments
          moving in opposite directions double the risk.

        Returns ``(conflict_bool, reason_str)``.  When no conflict, ``reason_str`` is
        an empty string.
        """
        tf = (timeframe or self._timeframe).upper()
        sym_upper = symbol.upper()
        side_lower = str(side or "").lower()

        for position in open_positions:
            pos_symbol = str(position.get("symbol", "") or "").upper()
            pos_side = str(
                position.get("side", position.get("direction", "")) or ""
            ).lower()

            if not pos_symbol or pos_symbol == sym_upper:
                continue

            pair_value = self._service.get_pair(sym_upper, pos_symbol, tf)
            if pair_value is None or pair_value.coefficient is None or not pair_value.coverage_ok:
                continue

            r = pair_value.coefficient

            # Strong positive correlation + opposite sides → implicit hedge
            if r >= self._high_threshold and side_lower != pos_side and pos_side:
                return True, (
                    f"implicit_hedge:{sym_upper}-{pos_symbol}"
                    f"(r={r:+.2f},new={side_lower},open={pos_side})"
                )

            # Strong negative correlation + same sides → inverse concentration
            if r <= -self._high_threshold and side_lower == pos_side and pos_side:
                return True, (
                    f"inverse_concentration:{sym_upper}-{pos_symbol}"
                    f"(r={r:+.2f},side={side_lower})"
                )

        return False, ""

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def build_details(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
    ) -> dict[str, Any]:
        """Build a ``details["correlation"]`` dict ready for ``FastContext``.

        Returns a structured snapshot of all exposure relations for *symbol*,
        sorted by absolute coefficient descending.
        """
        tf = (timeframe or self._timeframe).upper()
        sym_upper = symbol.upper()

        relations = self._service.get_exposure_relations(sym_upper, tf)
        snapshot = self._service.get_matrix(tf)

        pairs_out: list[dict[str, Any]] = []
        for pair in sorted(
            relations,
            key=lambda p: abs(p.coefficient) if p.coefficient is not None else 0.0,
            reverse=True,
        ):
            other = pair.symbol_b if pair.symbol_a == sym_upper else pair.symbol_a
            pairs_out.append(
                {
                    "symbol": other,
                    "coefficient": pair.coefficient,
                    "classification": self.classify(pair.coefficient),
                    "coverage_ok": pair.coverage_ok,
                    "coverage_ratio": pair.coverage_ratio,
                    "bars_used": pair.bars_used,
                    "source_stale": pair.source_stale,
                }
            )

        return {
            "timeframe": tf,
            "pairs": pairs_out,
            "matrix_computed_at": snapshot.computed_at if snapshot else None,
            "all_pairs_coverage_ok": snapshot.all_pairs_coverage_ok if snapshot else False,
        }

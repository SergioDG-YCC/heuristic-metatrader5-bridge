from __future__ import annotations

from typing import TYPE_CHECKING, Any

from heuristic_mt5_bridge.core.correlation.models import CorrelationPairValue

if TYPE_CHECKING:
    from heuristic_mt5_bridge.core.correlation.service import CorrelationService


class SmcCorrelationFormatter:
    """Format raw correlation data for SMC Desk consumption.

    This is a **policy/presentation layer** — it transforms :class:`CorrelationPairValue`
    objects from :class:`CorrelationService` into human-readable text snippets and
    structured dicts suitable for the LLM validator context window.

    Typical usage inside ``build_heuristic_output``::

        formatter = SmcCorrelationFormatter(correlation_service)
        analyst_input["correlation_context"] = formatter.build_context_dict(symbol)
    """

    def __init__(
        self,
        correlation_service: CorrelationService,
        *,
        timeframe: str = "H1",
        top_n: int = 5,
    ) -> None:
        self._service = correlation_service
        self._timeframe = timeframe.upper()
        self._top_n = max(1, top_n)

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    def top_correlations(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
    ) -> list[CorrelationPairValue]:
        """Return the ``top_n`` pairs for *symbol*, sorted by |coefficient| descending.

        Only pairs with ``coverage_ok=True`` are included.
        """
        tf = (timeframe or self._timeframe).upper()
        relations = self._service.get_exposure_relations(symbol.upper(), tf)
        eligible = [p for p in relations if p.coverage_ok and p.coefficient is not None]
        eligible.sort(key=lambda p: abs(p.coefficient), reverse=True)  # type: ignore[arg-type]
        return eligible[: self._top_n]

    # ------------------------------------------------------------------
    # Output builders
    # ------------------------------------------------------------------

    def build_context_snippet(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
    ) -> str:
        """Return a concise text block for inclusion in the LLM prompt context.

        Example output::

            CORRELATION (H1, window=50 bars):
              GBPUSD: r=+0.91 [high]   coverage=48/50
              USDJPY: r=-0.84 [high]   coverage=47/50
              AUDUSD: r=+0.71 [moderate]  coverage=43/50
            [matrix computed 2026-04-05T10:30:00Z]
        """
        tf = (timeframe or self._timeframe).upper()
        pairs = self.top_correlations(symbol, timeframe=tf)
        snapshot = self._service.get_matrix(tf)

        lines: list[str] = [f"CORRELATION ({tf}):"]
        if not pairs:
            lines.append("  (no coverage-ok pairs available)")
        else:
            for pair in pairs:
                other = (
                    pair.symbol_b
                    if pair.symbol_a.upper() == symbol.upper()
                    else pair.symbol_a
                )
                r = pair.coefficient
                sign = "+" if r >= 0.0 else ""  # type: ignore[operator]
                abs_r = abs(r)  # type: ignore[arg-type]
                tag = (
                    "high"
                    if abs_r >= 0.80
                    else "moderate"
                    if abs_r >= 0.60
                    else "low"
                )
                lines.append(
                    f"  {other}: r={sign}{r:.2f} [{tag}]"
                    f"  coverage={pair.bars_used} bars"
                    f"{'  [stale]' if pair.source_stale else ''}"
                )

        if snapshot:
            lines.append(f"[matrix computed {snapshot.computed_at}]")

        return "\n".join(lines)

    def build_context_dict(
        self,
        symbol: str,
        *,
        timeframe: str | None = None,
    ) -> dict[str, Any]:
        """Return a structured dict for ``analyst_input["correlation_context"]``.

        Schema::

            {
                "timeframe": "H1",
                "top_pairs": [
                    {"symbol": "GBPUSD", "coefficient": 0.91, "bars_used": 48,
                     "coverage_ratio": 0.96, "source_stale": false},
                    ...
                ],
                "snippet": "CORRELATION (H1):\n  ...",
                "matrix_computed_at": "2026-04-05T10:30:00Z",
                "symbols_in_universe": 8,
            }
        """
        tf = (timeframe or self._timeframe).upper()
        sym_upper = symbol.upper()
        pairs = self.top_correlations(symbol, timeframe=tf)
        snapshot = self._service.get_matrix(tf)

        top_pairs: list[dict[str, Any]] = []
        for pair in pairs:
            other = pair.symbol_b if pair.symbol_a == sym_upper else pair.symbol_a
            top_pairs.append(
                {
                    "symbol": other,
                    "coefficient": pair.coefficient,
                    "bars_used": pair.bars_used,
                    "coverage_ratio": pair.coverage_ratio,
                    "source_stale": pair.source_stale,
                }
            )

        return {
            "timeframe": tf,
            "top_pairs": top_pairs,
            "snippet": self.build_context_snippet(symbol, timeframe=tf),
            "matrix_computed_at": snapshot.computed_at if snapshot else None,
            "symbols_in_universe": len(self._service.active_symbols()),
        }

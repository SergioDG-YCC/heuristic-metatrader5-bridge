from __future__ import annotations

from typing import Any


class SymbolSpecRegistry:
    """
    In-memory registry of symbol specifications, indexed by symbol.

    Populated by CoreRuntimeService._refresh_symbol_specs() after each spec pull.
    Used by MarketStateService.build_chart_context() to resolve pip_size from
    the real spec `point` field instead of a hardcoded heuristic.

    Thread-safety: not required — all access runs within the asyncio event loop.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}  # symbol (upper) → spec dict

    def update(self, specs: list[dict[str, Any]]) -> None:
        """Replace specs for all symbols present in the list."""
        for spec in specs:
            symbol = str(spec.get("symbol", "")).upper()
            if symbol:
                self._data[symbol] = spec

    def pip_size(self, symbol: str) -> float | None:
        """Return the `point` value for *symbol*, or None if spec is unknown."""
        spec = self._data.get(str(symbol).upper())
        if spec is None:
            return None
        val = spec.get("point")
        return float(val) if isinstance(val, (int, float)) and float(val) > 0 else None

    def get(self, symbol: str) -> dict[str, Any] | None:
        """Return the full spec dict for *symbol*, or None."""
        return self._data.get(str(symbol).upper())

    def all_specs(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of all specs, keyed by symbol (upper-case)."""
        return dict(self._data)

    def __len__(self) -> int:
        return len(self._data)

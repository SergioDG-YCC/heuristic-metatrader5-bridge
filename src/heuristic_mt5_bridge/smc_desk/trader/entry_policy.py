"""SMC Trader entry policy — guards new order placement."""
from __future__ import annotations

from typing import Any

from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig


_QUALITY_RANK = {"high": 3, "medium": 2, "low": 1}


class SmcEntryPolicy:

    def __init__(self, config: SmcTraderConfig) -> None:
        self._config = config

    def can_open(
        self,
        symbol: str,
        side: str,
        smc_open_operations: list[dict[str, Any]],
        risk_limits: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        max_per_symbol = int(
            (risk_limits or {}).get("max_positions_per_symbol", self._config.max_positions_per_symbol)
            or self._config.max_positions_per_symbol
        )
        max_total = int(
            (risk_limits or {}).get("max_positions_total", self._config.max_positions_total)
            or self._config.max_positions_total
        )

        sym_upper = symbol.upper()
        symbol_count = sum(
            1 for op in smc_open_operations
            if str(op.get("symbol", "")).upper() == sym_upper
        )
        if symbol_count >= max_per_symbol:
            return False, f"max_per_symbol:{symbol_count}/{max_per_symbol}"

        if len(smc_open_operations) >= max_total:
            return False, f"max_total:{len(smc_open_operations)}/{max_total}"

        same_side = sum(
            1 for op in smc_open_operations
            if str(op.get("symbol", "")).upper() == sym_upper
            and str(op.get("side", "")).lower() == side.lower()
        )
        if same_side > 0:
            return False, f"duplicate_side:{side}/{sym_upper}"

        return True, "ok"

    def quality_allowed(self, quality: str) -> bool:
        min_rank = _QUALITY_RANK.get(self._config.min_quality, 2)
        candidate_rank = _QUALITY_RANK.get(str(quality).lower().strip(), 0)
        return candidate_rank >= min_rank

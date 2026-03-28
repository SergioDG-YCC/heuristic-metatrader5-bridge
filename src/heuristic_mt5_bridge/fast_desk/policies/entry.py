"""Fast Desk entry policy — gate before any new position is opened."""
from __future__ import annotations

from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig


class FastEntryPolicy:
    """Stateless entry policy checks."""

    def can_open(
        self,
        symbol: str,
        side: str,
        open_positions: list[dict],
        config: FastRiskConfig,
    ) -> tuple[bool, str]:
        """Return (allowed, reason).

        Rejects when:
        - Same symbol + same side already open.
        - Total open positions >= max_positions_total.
        """
        # Normalise side for comparison
        side_norm = str(side).lower()
        symbol_norm = str(symbol).upper()

        for pos in open_positions:
            pos_symbol = str(pos.get("symbol", "")).upper()
            # MT5 position type: 0 = buy, 1 = sell; also accept "buy"/"sell" strings
            raw_type = pos.get("type", pos.get("side", ""))
            if isinstance(raw_type, int):
                pos_side = "buy" if raw_type == 0 else "sell"
            else:
                pos_side = str(raw_type).lower()

            if pos_symbol == symbol_norm and pos_side == side_norm:
                return False, f"same symbol+side already open: {symbol_norm}/{side_norm}"

        # Per-symbol position cap (any side)
        symbol_count = sum(
            1 for pos in open_positions
            if str(pos.get("symbol", "")).upper() == symbol_norm
        )
        if symbol_count >= config.max_positions_per_symbol:
            return False, (
                f"max positions per symbol reached ({symbol_count} >= {config.max_positions_per_symbol})"
            )

        if len(open_positions) >= config.max_positions_total:
            return False, (
                f"max total positions reached ({len(open_positions)} >= {config.max_positions_total})"
            )

        # Directional concentration gate — block if >70% of open positions on same side
        max_concentration = 0.70
        if len(open_positions) >= 3:
            same_side_count = 0
            for pos in open_positions:
                raw_type = pos.get("type", pos.get("side", ""))
                if isinstance(raw_type, int):
                    ps = "buy" if raw_type == 0 else "sell"
                else:
                    ps = str(raw_type).lower()
                if ps == side_norm:
                    same_side_count += 1
            ratio = same_side_count / len(open_positions)
            if ratio >= max_concentration:
                return False, (
                    f"directional concentration too high: {same_side_count}/{len(open_positions)} "
                    f"({ratio:.0%}) positions already {side_norm}"
                )

        return True, "ok"

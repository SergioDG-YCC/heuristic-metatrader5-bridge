"""Fast Desk per-symbol in-memory state - never persisted."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SymbolDeskState:
    last_signal: Any | None = None
    last_signal_at: float = 0.0
    last_custody_at: float = 0.0
    positions_opened_today: int = 0
    positions_closed_today: int = 0
    scaled_out_position_ids: set[int] = field(default_factory=set)
    touched_pending_orders: set[int] = field(default_factory=set)
    adopted_protection_attempted: set[int] = field(default_factory=set)
    inherited_first_seen_at: dict[int, float] = field(default_factory=dict)


class FastDeskState:
    """In-memory per-symbol state dictionary. Not persisted across restarts."""

    def __init__(self) -> None:
        self._states: dict[str, SymbolDeskState] = {}

    def get(self, symbol: str) -> SymbolDeskState:
        key = str(symbol).upper()
        if key not in self._states:
            self._states[key] = SymbolDeskState()
        return self._states[key]

    def set(self, symbol: str, state: SymbolDeskState) -> None:
        self._states[str(symbol).upper()] = state

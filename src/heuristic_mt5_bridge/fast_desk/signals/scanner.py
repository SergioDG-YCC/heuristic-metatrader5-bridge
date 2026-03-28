"""Fast Desk signal scanner — momentum breakout detector."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ema(values: list[float], n: int) -> list[float]:
    """Return EMA series aligned with *values* (same length, NaN as 0.0 for first n-1)."""
    if not values or n <= 0:
        return []
    k = 2.0 / (n + 1)
    result: list[float] = []
    seed = sum(values[:n]) / n
    result.extend([0.0] * (n - 1))
    result.append(seed)
    for price in values[n:]:
        result.append(price * k + result[-1] * (1.0 - k))
    return result


def _atr(candles: list[dict], n: int) -> float:
    """ATR (simple) over last *n* bars."""
    trs: list[float] = []
    for i in range(1, len(candles)):
        high = float(candles[i].get("high", 0))
        low = float(candles[i].get("low", 0))
        prev_close = float(candles[i - 1].get("close", 0))
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    window = trs[-n:] if len(trs) >= n else trs
    return sum(window) / len(window)


@dataclass
class FastSignal:
    symbol: str
    side: Literal["buy", "sell"]
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_loss_pips: float
    confidence: float               # 0.0–1.0
    trigger: str                    # e.g. "momentum_breakout"
    evidence: dict[str, Any]
    generated_at: str               # UTC ISO


@dataclass
class FastScannerConfig:
    min_confidence: float = 0.65
    momentum_window: int = 14           # bars for EMA / momentum calc
    volume_multiplier: float = 1.5     # volume spike threshold
    atr_multiplier_sl: float = 1.5     # SL = ATR * multiplier
    rr_ratio: float = 3.0              # TP = entry ± SL_distance * rr_ratio




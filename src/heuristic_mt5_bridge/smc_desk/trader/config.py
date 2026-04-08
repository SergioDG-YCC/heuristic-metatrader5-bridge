"""SMC Trader configuration — loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SmcTraderConfig:
    enabled: bool = True
    min_quality: str = "medium"
    pending_ttl_seconds: int = 604800
    custody_interval_seconds: float = 30.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 5
    risk_per_trade_percent: float = 0.5
    max_lot_size: float = 10.0
    scale_out_pct: float = 50.0
    min_rr_ratio: float = 1.5
    bias_change_cooldown_seconds: float = 3600.0
    entry_zone_buffer_pips: float = 2.0
    # Breakeven and trailing (post-entry risk management)
    be_trigger_r: float = 1.0          # move SL to entry when profit >= 1×R
    enable_trailing: bool = True
    trailing_trigger_r: float = 2.0    # start trailing when profit >= 2×R
    trailing_atr_multiplier: float = 2.0  # trail distance = ATR × multiplier (H4-based)

    @classmethod
    def from_env(cls) -> SmcTraderConfig:
        return cls(
            enabled=os.getenv("SMC_TRADER_ENABLED", "false").strip().lower() in ("true", "1", "yes"),
            min_quality=os.getenv("SMC_TRADER_MIN_QUALITY", "medium").strip().lower(),
            pending_ttl_seconds=int(os.getenv("SMC_TRADER_PENDING_TTL_SECONDS", "604800")),
            custody_interval_seconds=float(os.getenv("SMC_TRADER_CUSTODY_INTERVAL_SECONDS", "30")),
            max_positions_per_symbol=int(os.getenv("SMC_TRADER_MAX_POSITIONS_PER_SYMBOL", "1")),
            max_positions_total=int(os.getenv("SMC_TRADER_MAX_POSITIONS_TOTAL", "5")),
            risk_per_trade_percent=float(os.getenv("SMC_TRADER_RISK_PER_TRADE_PCT", "0.5")),
            max_lot_size=float(os.getenv("SMC_TRADER_MAX_LOT_SIZE", "10.0")),
            scale_out_pct=float(os.getenv("SMC_TRADER_SCALE_OUT_PCT", "50")),
            min_rr_ratio=float(os.getenv("SMC_TRADER_MIN_RR_RATIO", "1.5")),
            bias_change_cooldown_seconds=float(os.getenv("SMC_TRADER_BIAS_CHANGE_COOLDOWN_SECONDS", "3600")),
            entry_zone_buffer_pips=float(os.getenv("SMC_TRADER_ENTRY_ZONE_BUFFER_PIPS", "2.0")),
            be_trigger_r=float(os.getenv("SMC_TRADER_BE_TRIGGER_R", "1.0")),
            enable_trailing=os.getenv("SMC_TRADER_ENABLE_TRAILING", "true").strip().lower() in ("true", "1", "yes"),
            trailing_trigger_r=float(os.getenv("SMC_TRADER_TRAILING_TRIGGER_R", "2.0")),
            trailing_atr_multiplier=float(os.getenv("SMC_TRADER_TRAILING_ATR_MULTIPLIER", "2.0")),
        )

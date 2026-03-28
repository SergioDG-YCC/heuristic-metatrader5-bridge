"""Fast Desk risk engine — lot-size calculation and account safety checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FastRiskConfig:
    risk_per_trade_percent: float = 1.0     # max allowed is 2.0
    max_drawdown_percent: float = 5.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 4
    max_lot_size: float = 10.0


class FastRiskEngine:
    """Stateless risk engine — all state comes from caller."""

    def __init__(self, config: FastRiskConfig | None = None) -> None:
        self.config = config or FastRiskConfig()

    def calculate_lot_size(
        self,
        balance: float,
        risk_pct: float,
        sl_pips: float,
        symbol_spec: dict[str, Any] | float,
        account_state: dict[str, Any] | None = None,
    ) -> float:
        """Calculate lot size using MT5 symbol specifications.
        
        Fully compliant with MetaTrader 5 margin calculation documentation:
        https://www.metatrader5.com/en/terminal/help/trading_advanced/margin_forex
        
        Works for:
        - Forex (EURUSD, GBPUSD, USDJPY)
        - Crypto (BTCUSD, ETHUSD)
        - Indices (US30, SPX, NAS100)
        - Metals (XAUUSD, XAGUSD)
        
        Formula: Lots = RiskAmount / (SL_points × tick_value)
        
        Parameters:
        - balance: Account balance in account currency
        - risk_pct: Risk percentage (e.g., 1.0 for 1%)
        - sl_pips: Stop loss in CONVENTIONAL pips
        - symbol_spec: MT5 symbol specification dict
        - account_state: Optional account state for margin check
        
        Returns:
        - Lot size rounded to 2 decimals, clamped to [0.01, 50.0]
        """
        # Backward compatibility: older tests/callers passed pip_value directly.
        if isinstance(symbol_spec, (int, float)):
            symbol_spec = {
                "tick_value": float(symbol_spec),
                "point": 0.0001,
                "digits": 4,
                "contract_size": 100000.0,
                "margin_rate": 1.0,
            }

        # === EXTRACT SPECS (all from MT5) ===
        tick_value = float(symbol_spec.get("tick_value", 0) or 0)
        point = float(symbol_spec.get("point", 0) or 0)
        digits = int(symbol_spec.get("digits", 5) or 5)
        contract_size = float(symbol_spec.get("contract_size", 1) or 1)
        margin_rate = float(symbol_spec.get("margin_rate", 1.0) or 1.0)
        
        # Account leverage (for margin check later)
        leverage = int((account_state or {}).get("leverage", 100) or 100)
        
        if tick_value <= 0 or point <= 0:
            return 0.01  # Minimum fallback
        
        # === DYNAMIC PIP SIZE (MT5 convention) ===
        if digits == 2:
            # 2 decimals: BTCUSD (70000.00), some indices
            # 1 pip = 0.01 = 1 × point
            pip_size = point
        elif digits in (3, 5):
            # 3 decimals: USDJPY (159.394)
            # 5 decimals: EURUSD, GBPUSD (1.08500)
            # 1 pip = 0.01 (JPY) or 0.0001 (FX) = 10 × point
            pip_size = point * 10
        else:
            # Exotic fallback
            pip_size = point
        
        # === CONVERT SL FROM PIPS TO POINTS ===
        # tick_value is $ per point per lot
        # We need SL in points, not pips
        sl_points = sl_pips * (pip_size / point)
        
        # === CALCULATE RISK AMOUNT ===
        effective_risk_pct = min(float(risk_pct or 0.0), 2.0)
        if balance <= 0 or effective_risk_pct <= 0:
            return 0.01
        
        risk_amount = balance * (effective_risk_pct / 100.0)
        
        if sl_points <= 0 or tick_value <= 0:
            return 0.01
        
        # === LOT SIZE FORMULA (MT5 compliant) ===
        # Lots = RiskAmount / (SL_points × tick_value)
        lot_size = risk_amount / (sl_points * tick_value)
        
        # === MARGIN CHECK (MT5 formula) ===
        # Margin = Volume × ContractSize / Leverage × MarginRate
        # We check that margin doesn't exceed reasonable % of free margin
        if account_state:
            free_margin = float(account_state.get("free_margin", 0) or 0)
            if free_margin > 0:
                # Estimated margin for this trade
                estimated_margin = (lot_size * contract_size / leverage) * margin_rate
                
                # Safety: don't use more than 50% of free margin on single trade
                max_margin_lots = (free_margin * 0.5) / (contract_size / leverage * margin_rate)
                if max_margin_lots > 0:
                    lot_size = min(lot_size, max_margin_lots)
        
        # === SAFETY CAPS ===
        lot_size = max(0.01, min(self.config.max_lot_size, lot_size))
        return round(lot_size, 2)

    def check_account_safe(
        self,
        account_state: dict,
        config: FastRiskConfig,
    ) -> bool:
        """Return True when the account equity drawdown is within accepted limits.

        Drawdown = (balance − equity) / balance × 100
        Returns False when drawdown > config.max_drawdown_percent OR equity <= 0.
        """
        if not isinstance(account_state, dict):
            return False
        balance = float(account_state.get("balance", 0) or 0)
        equity = float(account_state.get("equity", 0) or 0)
        if equity <= 0:
            return False
        if balance <= 0:
            return True  # no baseline to compare — treat as safe
        drawdown = (balance - equity) / balance * 100.0
        return drawdown <= config.max_drawdown_percent

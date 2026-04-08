"""SMC Trader Service — orchestrates thesis → pending order → custody."""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from heuristic_mt5_bridge.core.runtime.market_state import MarketStateService
from heuristic_mt5_bridge.core.runtime.spec_registry import SymbolSpecRegistry
from heuristic_mt5_bridge.fast_desk.execution.bridge import FastExecutionBridge
from heuristic_mt5_bridge.fast_desk.risk.engine import FastRiskConfig, FastRiskEngine
from heuristic_mt5_bridge.smc_desk.state.thesis_store import load_recent_smc_thesis
from heuristic_mt5_bridge.smc_desk.trader.config import SmcTraderConfig
from heuristic_mt5_bridge.smc_desk.trader.custody import SmcCustodyEngine
from heuristic_mt5_bridge.smc_desk.trader.entry_policy import SmcEntryPolicy
from heuristic_mt5_bridge.smc_desk.trader.pending import SmcPendingManager

logger = logging.getLogger("smc_desk.trader")


def _execution_slippage_from_spec(symbol_spec: dict[str, Any]) -> int:
    stops_level = int(symbol_spec.get("trade_stops_level", 0) or 0)
    if stops_level > 0:
        return max(5, min(stops_level, int(stops_level * 0.10)))
    spread = float(symbol_spec.get("spread", 0) or 0)
    if spread > 0:
        return max(5, int(spread * 3))
    return 30


class SmcTraderService:
    """Thesis-driven trader: places/modifies/cancels pending orders and manages custody."""

    def __init__(self, *, config: SmcTraderConfig) -> None:
        self.config = config
        self.entry_policy = SmcEntryPolicy(config)
        self.pending_manager = SmcPendingManager(config)
        self.custody_engine = SmcCustodyEngine(config)
        self.execution = FastExecutionBridge()
        self.risk_engine = FastRiskEngine(FastRiskConfig(
            risk_per_trade_percent=config.risk_per_trade_percent,
            max_lot_size=config.max_lot_size,
        ))
        self._scaled_out_ids: set[int] = set()
        self._last_bias: dict[str, tuple[str, float]] = {}

    def process_thesis(
        self,
        *,
        symbol: str,
        thesis: dict[str, Any],
        smc_owned_operations: list[dict[str, Any]],
        current_price: float,
        pip_size: float,
        symbol_spec: dict[str, Any],
        account_state: dict[str, Any],
        connector: Any,
        risk_gate_ref: Callable[[str], dict[str, Any]] | None = None,
        ownership_register_ref: Callable | None = None,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any] | None:
        candidates = thesis.get("operation_candidates", [])
        if not candidates:
            return None

        cand = candidates[0]
        quality = str(cand.get("quality", "")).lower()
        if not self.entry_policy.quality_allowed(quality):
            logger.info("[%s] quality gate: %s < min %s", symbol, quality, self.config.min_quality)
            return None

        side = str(cand.get("side", "")).lower()
        if side not in ("buy", "sell"):
            return None

        bias = str(thesis.get("bias", "")).lower()
        now_mono = time.monotonic()
        last_bias, last_time = self._last_bias.get(symbol, ("", 0.0))
        if last_bias and last_bias != bias and (now_mono - last_time) < self.config.bias_change_cooldown_seconds:
            logger.info("[%s] bias change cooldown: %s→%s, %.0fs remaining",
                        symbol, last_bias, bias,
                        self.config.bias_change_cooldown_seconds - (now_mono - last_time))
            return None
        self._last_bias[symbol] = (bias, now_mono)

        has_pending = any(
            str(op.get("operation_type", "")).lower() == "order"
            and str(op.get("lifecycle_status", "")).lower() == "active"
            and str(op.get("symbol", "")).upper() == symbol.upper()
            for op in smc_owned_operations
        )
        has_position = any(
            str(op.get("operation_type", "")).lower() == "position"
            and str(op.get("lifecycle_status", "")).lower() == "active"
            and str(op.get("symbol", "")).upper() == symbol.upper()
            for op in smc_owned_operations
        )

        if has_position:
            return None

        if has_pending:
            return None

        allowed, reason = self.entry_policy.can_open(symbol, side, smc_owned_operations)
        if not allowed:
            logger.info("[%s] entry policy blocked: %s", symbol, reason)
            return None

        if risk_gate_ref is not None:
            risk_decision = risk_gate_ref(symbol)
            if not bool(risk_decision.get("allowed", False)):
                logger.info("[%s] risk gate blocked: %s", symbol, risk_decision)
                return None
            # Use profile-based risk % when available (RiskKernel profiles)
            _gate_risk_pct = float(risk_decision.get("risk_per_trade_pct", 0) or 0)
        else:
            _gate_risk_pct = 0.0

        decision = self.pending_manager.evaluate_new_thesis(
            thesis=thesis,
            current_price=current_price,
            pip_size=pip_size,
        )

        if decision.action != "place":
            return None

        sl_pips = 0.0
        if decision.stop_loss and decision.entry_price and pip_size > 0:
            sl_pips = abs(decision.entry_price - decision.stop_loss) / pip_size

        if sl_pips <= 0:
            logger.warning("[%s] cannot calculate SL pips", symbol)
            return None

        if self.config.min_rr_ratio > 0 and decision.take_profit and decision.entry_price:
            tp_distance = abs(decision.take_profit - decision.entry_price)
            sl_distance = abs(decision.entry_price - decision.stop_loss) if decision.stop_loss else 0
            if sl_distance > 0 and (tp_distance / sl_distance) < self.config.min_rr_ratio:
                logger.info("[%s] RR ratio %.2f < min %.2f", symbol,
                            tp_distance / sl_distance, self.config.min_rr_ratio)
                return None

        # Always compute lot size from risk engine using account balance,
        # risk_per_trade_percent and SL distance.  Thesis volume_options are
        # LLM-generated hints that ignore the actual account size.
        # Prefer RiskKernel profile-based risk_pct when available.
        risk_pct = _gate_risk_pct if _gate_risk_pct > 0 else self.config.risk_per_trade_percent
        balance = float(account_state.get("balance", 0) or 0)
        volume = self.risk_engine.calculate_lot_size(
            balance,
            risk_pct,
            sl_pips,
            symbol_spec,
            account_state,
        )
        logger.info("[%s] risk-sized volume=%.2f (balance=%.0f, risk_pct=%.2f, sl_pips=%.1f)",
                    symbol, volume, balance, risk_pct, sl_pips)

        volume_max = float(symbol_spec.get("volume_max", 500.0) or 500.0)
        volume_min = float(symbol_spec.get("volume_min", 0.01) or 0.01)
        volume = max(volume_min, min(volume_max, volume))

        comment = f"smc:{thesis.get('thesis_id', '')[:20]}"

        # Normalize entry_type: pending manager returns "buy_limit"/"sell_stop"/etc.
        # but connector expects just "limit"/"stop"/"market" (side is separate).
        raw_entry_type = decision.entry_type or "limit"
        if "limit" in raw_entry_type:
            connector_entry_type = "limit"
        elif "stop" in raw_entry_type:
            connector_entry_type = "stop"
        else:
            connector_entry_type = "limit"

        try:
            result = self.execution.send_entry(
                connector,
                symbol=symbol,
                side=decision.side or side,
                entry_type=connector_entry_type,
                volume=volume,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                entry_price=decision.entry_price,
                comment=comment,
                max_slippage_points=_execution_slippage_from_spec(symbol_spec),
                mt5_execute_sync=mt5_execute_sync,
            )
            ok = bool(result.get("ok", False))
        except Exception as exc:
            logger.error("[%s] execution error: %s", symbol, exc)
            result = {"ok": False, "error": str(exc)}
            ok = False

        if ok and ownership_register_ref is not None:
            ownership_register_ref(result, symbol, side, None)

        logger.info(
            "[%s] %s entry=%s vol=%.2f sl=%.5f tp=%.5f ok=%s",
            symbol, decision.entry_type, decision.entry_price, volume,
            decision.stop_loss or 0, decision.take_profit or 0, ok,
        )

        return {
            "action": "placed",
            "symbol": symbol,
            "side": side,
            "entry_type": decision.entry_type,
            "volume": volume,
            "result": result,
            "thesis_id": thesis.get("thesis_id"),
        }

    def reconcile_pending_orders(
        self,
        *,
        symbol: str,
        orders: list[dict[str, Any]],
        thesis: dict[str, Any] | None,
        current_price: float,
        pip_size: float,
        connector: Any,
        mt5_execute_sync: Callable | None = None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for order in orders:
            decision = self.pending_manager.evaluate_existing_order(
                order=order,
                thesis=thesis,
                current_price=current_price,
                pip_size=pip_size,
            )

            if decision.action == "cancel":
                order_id = decision.order_id or int(order.get("order_id", order.get("mt5_order_id", 0)) or 0)
                if order_id > 0:
                    try:
                        result = self.execution.cancel_pending_order(
                            connector, order_id=order_id, mt5_execute_sync=mt5_execute_sync,
                        )
                        actions.append({"action": "cancelled", "order_id": order_id, "reason": decision.reason, "result": result})
                        logger.info("[%s] cancelled order %d: %s", symbol, order_id, decision.reason)
                    except Exception as exc:
                        logger.error("[%s] cancel order %d error: %s", symbol, order_id, exc)

            elif decision.action == "modify":
                order_id = decision.order_id or int(order.get("order_id", order.get("mt5_order_id", 0)) or 0)
                if order_id > 0 and decision.entry_price:
                    try:
                        result = self.execution.modify_pending_order(
                            connector,
                            symbol=symbol,
                            order_id=order_id,
                            price_open=decision.entry_price,
                            stop_loss=decision.stop_loss,
                            take_profit=decision.take_profit,
                            mt5_execute_sync=mt5_execute_sync,
                        )
                        actions.append({"action": "modified", "order_id": order_id, "reason": decision.reason, "result": result})
                        logger.info("[%s] modified order %d: %s → %.5f", symbol, order_id, decision.reason, decision.entry_price)
                    except Exception as exc:
                        logger.error("[%s] modify order %d error: %s", symbol, order_id, exc)

        return actions

    def run_custody(
        self,
        *,
        symbol: str,
        positions: list[dict[str, Any]],
        thesis: dict[str, Any] | None,
        pip_size: float,
        connector: Any,
        candles: list[dict[str, Any]] | None = None,
        mt5_execute_sync: Callable | None = None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for position in positions:
            decision = self.custody_engine.evaluate_position(
                position=position,
                thesis=thesis,
                pip_size=pip_size,
                scaled_out_ids=self._scaled_out_ids,
                candles=candles,
            )

            pos_id = decision.position_id
            if pos_id <= 0:
                continue

            if decision.action in ("close", "close_invalidated"):
                try:
                    side = str(position.get("side", "buy")).lower()
                    volume = float(position.get("volume", 0) or 0)
                    result = self.execution.close_position(
                        connector,
                        symbol=symbol,
                        position_id=pos_id,
                        side=side,
                        volume=volume,
                        mt5_execute_sync=mt5_execute_sync,
                    )
                    actions.append({"action": "closed", "position_id": pos_id, "reason": decision.reason, "result": result})
                    logger.info("[%s] closed position %d: %s", symbol, pos_id, decision.reason)
                except Exception as exc:
                    logger.error("[%s] close position %d error: %s", symbol, pos_id, exc)

            elif decision.action == "scale_out" and decision.partial_volume:
                try:
                    side = str(position.get("side", "buy")).lower()
                    result = self.execution.close_position(
                        connector,
                        symbol=symbol,
                        position_id=pos_id,
                        side=side,
                        volume=decision.partial_volume,
                        mt5_execute_sync=mt5_execute_sync,
                    )
                    if bool(result.get("ok", False)):
                        self._scaled_out_ids.add(pos_id)
                        if decision.new_sl is not None:
                            self.execution.modify_position_levels(
                                connector,
                                symbol=symbol,
                                position_id=pos_id,
                                stop_loss=decision.new_sl,
                                take_profit=None,
                                mt5_execute_sync=mt5_execute_sync,
                            )
                    actions.append({"action": "scaled_out", "position_id": pos_id, "reason": decision.reason, "result": result})
                    logger.info("[%s] scaled out position %d: %.2f lots", symbol, pos_id, decision.partial_volume)
                except Exception as exc:
                    logger.error("[%s] scale out position %d error: %s", symbol, pos_id, exc)

            elif decision.action == "move_sl_be" and decision.new_sl is not None:
                try:
                    result = self.execution.modify_position_levels(
                        connector,
                        symbol=symbol,
                        position_id=pos_id,
                        stop_loss=decision.new_sl,
                        take_profit=None,
                        mt5_execute_sync=mt5_execute_sync,
                    )
                    actions.append({"action": "moved_sl_be", "position_id": pos_id, "result": result})
                    logger.info("[%s] moved SL to BE for position %d", symbol, pos_id, decision.reason)
                except Exception as exc:
                    logger.error("[%s] move SL BE position %d error: %s", symbol, pos_id, exc)

            elif decision.action == "trail_sl" and decision.new_sl is not None:
                try:
                    result = self.execution.modify_position_levels(
                        connector,
                        symbol=symbol,
                        position_id=pos_id,
                        stop_loss=decision.new_sl,
                        take_profit=None,
                        mt5_execute_sync=mt5_execute_sync,
                    )
                    actions.append({"action": "trailed_sl", "position_id": pos_id, "reason": decision.reason, "result": result})
                    logger.info("[%s] trailed SL for position %d to %.5f: %s", symbol, pos_id, decision.new_sl, decision.reason)
                except Exception as exc:
                    logger.error("[%s] trail SL position %d error: %s", symbol, pos_id, exc)

        return actions

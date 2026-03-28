"""Fast Desk execution bridge - canonical MT5Connector wrapper for FastTraderService."""
from __future__ import annotations

from typing import Any, Callable


class FastExecutionBridge:
    """Submits orders and custody actions through MT5Connector canonical surface.

    All public methods accept an optional ``mt5_execute_sync`` callable.  When
    provided it must be a *synchronous* wrapper around
    ``CoreRuntimeService._mt5_call`` (e.g. built via
    ``asyncio.run_coroutine_threadsafe``).  This ensures every execution call
    serialises through the shared ``_mt5_lock`` even when the bridge runs
    inside an ``asyncio.to_thread`` worker.

    When ``mt5_execute_sync`` is ``None`` (unit-tests, legacy callers) the
    method falls back to calling the connector directly.
    """

    @staticmethod
    def _call(
        mt5_execute_sync: Callable | None,
        connector: Any,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        fn = getattr(connector, method_name)
        if mt5_execute_sync is not None:
            return mt5_execute_sync(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    def send_entry(
        self,
        connector: Any,
        *,
        symbol: str,
        side: str,
        entry_type: str,
        volume: float,
        stop_loss: float | None,
        take_profit: float | None,
        entry_price: float | None = None,
        comment: str = "",
        max_slippage_points: int = 20,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        instruction: dict[str, Any] = {
            "symbol": str(symbol).upper(),
            "side": str(side).lower(),
            "entry_type": str(entry_type).lower(),
            "volume": float(volume),
            "comment": str(comment)[:160],
            "execution_constraints": {"max_slippage_points": int(max_slippage_points)},
        }
        if isinstance(entry_price, (int, float)) and float(entry_price) > 0:
            instruction["entry_price"] = float(entry_price)
        if isinstance(stop_loss, (int, float)) and float(stop_loss) > 0:
            instruction["stop_loss"] = float(stop_loss)
        if isinstance(take_profit, (int, float)) and float(take_profit) > 0:
            instruction["take_profit"] = float(take_profit)
        return self._call(mt5_execute_sync, connector, "send_execution_instruction", instruction)

    def modify_position_levels(
        self,
        connector: Any,
        *,
        symbol: str,
        position_id: int,
        stop_loss: float | None,
        take_profit: float | None,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        return self._call(
            mt5_execute_sync,
            connector,
            "modify_position_levels",
            symbol=str(symbol).upper(),
            position_id=int(position_id),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def modify_pending_order(
        self,
        connector: Any,
        *,
        symbol: str,
        order_id: int,
        price_open: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        return self._call(
            mt5_execute_sync,
            connector,
            "modify_order_levels",
            symbol=str(symbol).upper(),
            order_id=int(order_id),
            price_open=price_open,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def cancel_pending_order(
        self,
        connector: Any,
        *,
        order_id: int,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        return self._call(mt5_execute_sync, connector, "remove_order", int(order_id))

    def close_position(
        self,
        connector: Any,
        *,
        symbol: str,
        position_id: int,
        side: str,
        volume: float,
        max_slippage_points: int = 20,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        return self._call(
            mt5_execute_sync,
            connector,
            "close_position",
            symbol=str(symbol).upper(),
            position_id=int(position_id),
            side=str(side).lower(),
            volume=float(volume),
            max_slippage_points=int(max_slippage_points),
        )

    def reduce_position(
        self,
        connector: Any,
        *,
        symbol: str,
        position_id: int,
        side: str,
        partial_volume: float,
        max_slippage_points: int = 20,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        return self._call(
            mt5_execute_sync,
            connector,
            "close_position",
            symbol=str(symbol).upper(),
            position_id=int(position_id),
            side=str(side).lower(),
            volume=float(partial_volume),
            max_slippage_points=int(max_slippage_points),
        )

    def apply_professional_custody(
        self,
        connector: Any,
        *,
        decision: Any,
        position: dict[str, Any],
        max_slippage_points: int = 20,
        mt5_execute_sync: Callable | None = None,
    ) -> dict[str, Any]:
        action = str(getattr(decision, "action", "hold"))
        symbol = str(position.get("symbol", "") or "")
        side = str(position.get("side", "") or "")
        position_id = int(position.get("position_id", 0) or 0)
        volume = float(position.get("volume", 0.0) or 0.0)

        if action == "close":
            return self.close_position(
                connector,
                symbol=symbol,
                position_id=position_id,
                side=side,
                volume=volume,
                max_slippage_points=max_slippage_points,
                mt5_execute_sync=mt5_execute_sync,
            )

        if action == "reduce":
            partial = float(getattr(decision, "partial_volume", 0.0) or 0.0)
            if partial <= 0:
                return {"ok": False, "action": action, "error": "missing_partial_volume"}
            return self.reduce_position(
                connector,
                symbol=symbol,
                position_id=position_id,
                side=side,
                partial_volume=partial,
                max_slippage_points=max_slippage_points,
                mt5_execute_sync=mt5_execute_sync,
            )

        if action in {"move_to_be", "trail_atr", "trail_structural"}:
            new_sl = getattr(decision, "new_sl", None)
            new_tp = getattr(decision, "new_tp", None)
            current_tp = position.get("take_profit", position.get("tp", None))
            effective_tp = new_tp if isinstance(new_tp, (int, float)) and float(new_tp) > 0 else current_tp
            return self.modify_position_levels(
                connector,
                symbol=symbol,
                position_id=position_id,
                stop_loss=float(new_sl) if isinstance(new_sl, (int, float)) and float(new_sl) > 0 else None,
                take_profit=float(effective_tp) if isinstance(effective_tp, (int, float)) and float(effective_tp) > 0 else None,
                mt5_execute_sync=mt5_execute_sync,
            )

        return {"ok": True, "action": action, "skipped": True}

    # ------------------------------------------------------------------
    # Legacy compatibility methods (existing tests still use these)
    # ------------------------------------------------------------------

    def open_position(self, connector: object, signal: FastSignal, volume: float) -> dict[str, Any]:
        return self.send_entry(
            connector,
            symbol=signal.symbol,
            side=signal.side,
            entry_type="market",
            volume=volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            comment="",
            max_slippage_points=20,
        )

    def apply_custody(
        self,
        connector: object,
        decision: CustodyDecision,
        position: dict | None = None,
    ) -> dict[str, Any]:
        position = position or {}
        symbol: str = str(position.get("symbol", "") or "")

        if decision.action == CustodyAction.CLOSE:
            side: str = str(position.get("side", "buy") or "buy")
            volume: float = float(position.get("volume", 0.0) or 0.0)
            return self.close_position(
                connector,
                symbol=symbol,
                position_id=decision.position_id,
                side=side,
                volume=volume,
                max_slippage_points=20,
            )

        if decision.action == CustodyAction.TRAIL_SL and decision.new_sl is not None:
            return self.modify_position_levels(
                connector,
                symbol=symbol,
                position_id=decision.position_id,
                stop_loss=decision.new_sl,
                take_profit=None,
            )

        return {"action": str(decision.action), "skipped": True, "ok": True}

from __future__ import annotations

import os
import statistics
import time
from datetime import datetime, timezone
from typing import Any


TIMEFRAME_MAP: dict[str, str] = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_epoch() -> float:
    return time.time()


def iso_to_datetime(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class MT5ConnectorError(RuntimeError):
    pass


class MT5Connector:
    def __init__(
        self,
        *,
        terminal_path: str = "",
        watch_symbols: list[str] | None = None,
        magic_number: int = 20260315,
        account_mode_guard: str | None = None,
        mt5_module: Any | None = None,
    ) -> None:
        self.terminal_path = str(terminal_path or "").strip()
        self.watch_symbols = [str(item).strip() for item in (watch_symbols or []) if str(item).strip()]
        self.magic_number = int(magic_number)
        self.account_mode_guard = str(account_mode_guard or "").strip().lower()
        self.server_time_offset_seconds = 0
        self._mt5: Any | None = mt5_module

    def connect(self) -> None:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise MT5ConnectorError(
                    "MetaTrader5 package is not installed in this Python environment."
                ) from exc
            self._mt5 = mt5
        mt5 = self._mt5
        if mt5 is None:
            raise MT5ConnectorError("MetaTrader5 module unavailable")

        ok = mt5.initialize(path=self.terminal_path) if self.terminal_path else mt5.initialize()
        if not ok:
            raise MT5ConnectorError(f"MetaTrader5.initialize() failed: {mt5.last_error()}")

        probe_symbols = self.watch_symbols
        if not probe_symbols:
            account = mt5.account_info()
            symbol_hint = str(getattr(account, "currency", "") or "").strip()
            probe_symbols = [symbol_hint] if symbol_hint else []
        self.server_time_offset_seconds = self.estimate_server_time_offset(probe_symbols)

    def shutdown(self) -> None:
        mt5 = self._mt5
        if mt5 is None:
            return
        try:
            mt5.shutdown()
        except Exception:
            return

    def _require_mt5(self) -> Any:
        if self._mt5 is None:
            raise MT5ConnectorError("MT5 connector is not connected")
        return self._mt5

    def broker_identity(self) -> dict[str, Any]:
        mt5 = self._require_mt5()
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        return {
            "broker_server": str(getattr(account, "server", "") or "") if account else "",
            "broker_company": str(getattr(terminal, "company", "") or "") if terminal else "",
            "account_login": int(getattr(account, "login", 0) or 0) if account else 0,
            "terminal_name": str(getattr(terminal, "name", "") or "") if terminal else "",
            "terminal_path": self.terminal_path,
        }

    def terminal_info(self) -> dict[str, Any]:
        """Get terminal information including trade_allowed status."""
        mt5 = self._require_mt5()
        terminal = mt5.terminal_info()
        if terminal is None:
            return {"trade_allowed": False}
        return {
            "terminal_name": str(getattr(terminal, "name", "") or ""),
            "terminal_path": str(getattr(terminal, "path", "") or ""),
            "trade_allowed": bool(getattr(terminal, "trade_allowed", False)),
            "connected": bool(getattr(terminal, "connected", False)),
        }

    def ensure_symbol(self, symbol: str) -> str:
        mt5 = self._require_mt5()
        requested = str(symbol or "").strip()
        if not requested:
            raise MT5ConnectorError("empty symbol")

        info = mt5.symbol_info(requested)
        resolved_symbol = requested
        if info is None:
            candidates = mt5.symbols_get() or ()
            requested_upper = requested.upper()
            for item in candidates:
                candidate_name = str(getattr(item, "name", "") or "").strip()
                if candidate_name and candidate_name.upper() == requested_upper:
                    info = mt5.symbol_info(candidate_name)
                    resolved_symbol = candidate_name
                    break
        if info is None:
            raise MT5ConnectorError(f"symbol_info failed for {requested}: {mt5.last_error()}")
        if not bool(getattr(info, "visible", False)):
            if not mt5.symbol_select(resolved_symbol, True):
                raise MT5ConnectorError(f"symbol_select failed for {resolved_symbol}: {mt5.last_error()}")
        return resolved_symbol

    def _tf_const(self, timeframe: str) -> Any:
        mt5 = self._require_mt5()
        tf_name = TIMEFRAME_MAP.get(str(timeframe).upper())
        if not tf_name or not hasattr(mt5, tf_name):
            raise MT5ConnectorError(f"unsupported timeframe for MT5 connector: {timeframe}")
        return getattr(mt5, tf_name)

    def _safe_iso_from_epoch(self, epoch: int | float | None, offset_seconds: int = 0) -> str:
        try:
            value = int(epoch or 0)
        except (TypeError, ValueError):
            value = 0
        try:
            value += int(offset_seconds or 0)
        except (TypeError, ValueError):
            pass
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value)) if value > 0 else ""

    def estimate_server_time_offset(self, symbols: list[str]) -> int:
        mt5 = self._require_mt5()
        now_epoch = int(time.time())
        offsets: list[int] = []
        for symbol in symbols:
            try:
                resolved_symbol = self.ensure_symbol(symbol)
            except MT5ConnectorError:
                continue
            tick = mt5.symbol_info_tick(resolved_symbol)
            if tick is None:
                continue
            tick_epoch = int(getattr(tick, "time", 0) or 0)
            if tick_epoch <= 0:
                continue
            offsets.append(tick_epoch - now_epoch)
        if not offsets:
            return 0
        median_offset = statistics.median(offsets)
        return int(round(median_offset / 1800.0) * 1800)

    def fetch_snapshot(self, symbol: str, timeframe: str, bars: int = 200) -> dict[str, Any]:
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        tf_const = self._tf_const(timeframe)
        tick = mt5.symbol_info_tick(resolved_symbol)
        if tick is None:
            raise MT5ConnectorError(f"symbol_info_tick failed for {resolved_symbol}: {mt5.last_error()}")

        rates = mt5.copy_rates_from_pos(resolved_symbol, tf_const, 0, int(bars))
        if rates is None:
            raise MT5ConnectorError(
                f"copy_rates_from_pos failed for {resolved_symbol}/{timeframe}: {mt5.last_error()}"
            )

        candles: list[dict[str, Any]] = []
        for row in rates:
            bar_epoch = int(row["time"] or 0)
            candles.append(
                {
                    "timestamp": self._safe_iso_from_epoch(bar_epoch, offset_seconds=-self.server_time_offset_seconds),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["tick_volume"]),
                }
            )

        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        spread = round(ask - bid, 10) if bid and ask else 0.0
        tick_epoch = int(getattr(tick, "time", 0) or 0)
        normalized_tick_epoch = tick_epoch - self.server_time_offset_seconds if tick_epoch else 0
        last_bar_epoch = int(rates[-1]["time"]) if len(rates) else 0
        normalized_bar_epoch = last_bar_epoch - self.server_time_offset_seconds if last_bar_epoch else 0

        return {
            "schema_version": "1.0.0",
            "snapshot_id": f"mt5_{resolved_symbol.lower()}_{str(timeframe).lower()}_{int(time.time())}",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "symbol": resolved_symbol.upper(),
            "timeframe": str(timeframe).upper(),
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "ohlc": candles,
            "indicators": {},
            "patterns": [],
            "structure": {},
            "market_context": {
                "source": "mt5_python_api",
                "terminal_connected": True,
                "broker_identity": self.broker_identity(),
                "server_time_offset_seconds": self.server_time_offset_seconds,
                "tick_time_raw": self._safe_iso_from_epoch(tick_epoch),
                "tick_time": self._safe_iso_from_epoch(normalized_tick_epoch),
                "bars_requested": int(bars),
                "bars_returned": len(candles),
                "last_bar_timestamp_raw": self._safe_iso_from_epoch(last_bar_epoch),
                "last_bar_timestamp": self._safe_iso_from_epoch(normalized_bar_epoch),
            },
        }

    def fetch_symbol_specification(self, symbol: str) -> dict[str, Any]:
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        info = mt5.symbol_info(resolved_symbol)
        if info is None:
            raise MT5ConnectorError(f"symbol_info failed for {resolved_symbol}: {mt5.last_error()}")
        account = mt5.account_info()
        broker = self.broker_identity()

        path = str(getattr(info, "path", "") or "")
        path_parts = [part.strip() for part in path.split("\\") if part.strip()]
        return {
            "schema_version": "1.0.0",
            "symbol": resolved_symbol.upper(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "broker_server": broker.get("broker_server", ""),
            "account_login": int(getattr(account, "login", 0) or 0),
            "account_currency": str(getattr(account, "currency", "") or ""),
            "description": str(getattr(info, "description", "") or ""),
            "path": path,
            "asset_class": path_parts[0] if len(path_parts) >= 1 else "",
            "path_group": path_parts[1] if len(path_parts) >= 2 else "",
            "path_subgroup": path_parts[2] if len(path_parts) >= 3 else "",
            "visible": bool(getattr(info, "visible", False)),
            "selected": bool(getattr(info, "select", False)),
            "custom": bool(getattr(info, "custom", False)),
            "digits": int(getattr(info, "digits", 0) or 0),
            "point": float(getattr(info, "point", 0.0) or 0.0),
            "tick_size": float(getattr(info, "trade_tick_size", 0.0) or 0.0),
            "tick_value": float(getattr(info, "trade_tick_value", 0.0) or 0.0),
            "contract_size": float(getattr(info, "trade_contract_size", 0.0) or 0.0),
            "spread_float": bool(getattr(info, "spread_float", False)),
            "spread_points": int(getattr(info, "spread", 0) or 0),
            "stops_level_points": int(getattr(info, "trade_stops_level", 0) or 0),
            "freeze_level_points": int(getattr(info, "trade_freeze_level", 0) or 0),
            "volume_min": float(getattr(info, "volume_min", 0.0) or 0.0),
            "volume_max": float(getattr(info, "volume_max", 0.0) or 0.0),
            "volume_step": float(getattr(info, "volume_step", 0.0) or 0.0),
            "volume_limit": float(getattr(info, "volume_limit", 0.0) or 0.0),
            "currency_base": str(getattr(info, "currency_base", "") or ""),
            "currency_profit": str(getattr(info, "currency_profit", "") or ""),
            "currency_margin": str(getattr(info, "currency_margin", "") or ""),
            "trade_mode": int(getattr(info, "trade_mode", 0) or 0),
            "filling_mode": int(getattr(info, "filling_mode", 0) or 0),
            "order_mode": int(getattr(info, "order_mode", 0) or 0),
            "expiration_mode": int(getattr(info, "expiration_mode", 0) or 0),
            "trade_calc_mode": int(getattr(info, "trade_calc_mode", 0) or 0),
            "margin_initial": float(getattr(info, "margin_initial", 0.0) or 0.0),
            "margin_maintenance": float(getattr(info, "margin_maintenance", 0.0) or 0.0),
            "margin_hedged": float(getattr(info, "margin_hedged", 0.0) or 0.0),
            "swap_long": float(getattr(info, "swap_long", 0.0) or 0.0),
            "swap_short": float(getattr(info, "swap_short", 0.0) or 0.0),
        }

    def fetch_available_symbol_catalog(self) -> list[dict[str, Any]]:
        mt5 = self._require_mt5()
        symbols = mt5.symbols_get() or ()
        account = mt5.account_info()
        broker = self.broker_identity()
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        items: list[dict[str, Any]] = []
        for info in symbols:
            name = str(getattr(info, "name", "") or "").strip()
            if not name:
                continue
            path = str(getattr(info, "path", "") or "")
            path_parts = [part.strip() for part in path.split("\\") if part.strip()]
            items.append(
                {
                    "schema_version": "1.0.0",
                    "broker_server": broker.get("broker_server", ""),
                    "broker_company": broker.get("broker_company", ""),
                    "account_login": int(getattr(account, "login", 0) or 0),
                    "account_currency": str(getattr(account, "currency", "") or ""),
                    "server_time_offset_seconds": self.server_time_offset_seconds,
                    "symbol": name.upper(),
                    "description": str(getattr(info, "description", "") or ""),
                    "path": path,
                    "asset_class": path_parts[0] if len(path_parts) >= 1 else "",
                    "path_group": path_parts[1] if len(path_parts) >= 2 else "",
                    "path_subgroup": path_parts[2] if len(path_parts) >= 3 else "",
                    "visible": bool(getattr(info, "visible", False)),
                    "selected": bool(getattr(info, "select", False)),
                    "custom": bool(getattr(info, "custom", False)),
                    "trade_mode": int(getattr(info, "trade_mode", 0) or 0),
                    "digits": int(getattr(info, "digits", 0) or 0),
                    "currency_base": str(getattr(info, "currency_base", "") or ""),
                    "currency_profit": str(getattr(info, "currency_profit", "") or ""),
                    "currency_margin": str(getattr(info, "currency_margin", "") or ""),
                    "updated_at": updated_at,
                }
            )
        return items

    def _extract_linked_ids(self, comment: str) -> dict[str, str]:
        text = str(comment or "").strip()
        linked_trader = ""
        linked_execution = ""
        if "ti:" in text:
            linked_trader = text.split("ti:", 1)[1].split("|", 1)[0].strip()[:120]
        if "ex:" in text:
            linked_execution = text.split("ex:", 1)[1].split("|", 1)[0].strip()[:120]
        return {
            "linked_trader_intent_id": linked_trader,
            "linked_execution_id": linked_execution,
        }

    def _order_type_name(self, order_type: Any) -> str:
        mt5 = self._require_mt5()
        mapping = {
            getattr(mt5, "ORDER_TYPE_BUY", -1): "buy_market",
            getattr(mt5, "ORDER_TYPE_SELL", -1): "sell_market",
            getattr(mt5, "ORDER_TYPE_BUY_LIMIT", -1): "buy_limit",
            getattr(mt5, "ORDER_TYPE_SELL_LIMIT", -1): "sell_limit",
            getattr(mt5, "ORDER_TYPE_BUY_STOP", -1): "buy_stop",
            getattr(mt5, "ORDER_TYPE_SELL_STOP", -1): "sell_stop",
        }
        return mapping.get(order_type, "other")

    def _account_mode_name(self, trade_mode: Any) -> str:
        mt5 = self._require_mt5()
        if trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", object()):
            return "demo"
        if trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", object()):
            return "real"
        if trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", object()):
            return "contest"
        return "unknown"

    def fetch_account_runtime(self, symbols: list[str]) -> dict[str, Any]:
        mt5 = self._require_mt5()
        account = mt5.account_info()
        if account is None:
            raise MT5ConnectorError(f"account_info failed: {mt5.last_error()}")
        terminal = mt5.terminal_info()

        positions_raw = mt5.positions_get() or ()
        orders_raw = mt5.orders_get() or ()
        now_utc = datetime.now(timezone.utc)
        date_from = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        deals_raw = mt5.history_deals_get(date_from, now_utc) or ()
        orders_history_raw = mt5.history_orders_get(date_from, now_utc) or ()

        buy_position_type = getattr(mt5, "POSITION_TYPE_BUY", 0)

        positions: list[dict[str, Any]] = []
        for item in positions_raw:
            comment = str(getattr(item, "comment", "") or "")
            linked = self._extract_linked_ids(comment)
            side = "buy" if int(getattr(item, "type", 0) or 0) == int(buy_position_type) else "sell"
            positions.append(
                {
                    "schema_version": "1.0.0",
                    "position_id": int(getattr(item, "ticket", 0) or 0),
                    "symbol": str(getattr(item, "symbol", "") or "").upper(),
                    "side": side,
                    "volume": float(getattr(item, "volume", 0.0) or 0.0),
                    "price_open": float(getattr(item, "price_open", 0.0) or 0.0),
                    "price_current": float(getattr(item, "price_current", 0.0) or 0.0),
                    "stop_loss": float(getattr(item, "sl", 0.0) or 0.0) or None,
                    "take_profit": float(getattr(item, "tp", 0.0) or 0.0) or None,
                    "profit": float(getattr(item, "profit", 0.0) or 0.0),
                    "swap": float(getattr(item, "swap", 0.0) or 0.0),
                    "commission": float(getattr(item, "commission", 0.0) or 0.0),
                    "magic": int(getattr(item, "magic", 0) or 0),
                    "comment": comment[:160],
                    **linked,
                    "opened_at": self._safe_iso_from_epoch(getattr(item, "time", 0)),
                    "updated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "status": "open",
                }
            )

        orders: list[dict[str, Any]] = []
        for item in orders_raw:
            comment = str(getattr(item, "comment", "") or "")
            linked = self._extract_linked_ids(comment)
            orders.append(
                {
                    "schema_version": "1.0.0",
                    "order_id": int(getattr(item, "ticket", 0) or 0),
                    "symbol": str(getattr(item, "symbol", "") or "").upper(),
                    "order_type": self._order_type_name(getattr(item, "type", None)),
                    "volume_initial": float(getattr(item, "volume_initial", 0.0) or 0.0),
                    "volume_current": float(getattr(item, "volume_current", 0.0) or 0.0),
                    "price_open": float(getattr(item, "price_open", 0.0) or 0.0) or None,
                    "stop_loss": float(getattr(item, "sl", 0.0) or 0.0) or None,
                    "take_profit": float(getattr(item, "tp", 0.0) or 0.0) or None,
                    "comment": comment[:160],
                    **linked,
                    "status": "working",
                    "created_at": self._safe_iso_from_epoch(
                        getattr(item, "time_setup", 0) or getattr(item, "time_setup_msc", 0)
                    ),
                    "updated_at": utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                }
            )

        gross_exposure = 0.0
        net_exposure = 0.0
        floating_profit = 0.0
        symbol_rows: dict[str, dict[str, Any]] = {}
        total_margin = float(getattr(account, "margin", 0.0) or 0.0)
        for position in positions:
            symbol = position["symbol"]
            signed_volume = float(position["volume"]) * (1 if position["side"] == "buy" else -1)
            gross_exposure += abs(float(position["volume"]))
            net_exposure += signed_volume
            floating_profit += float(position["profit"])
            row = symbol_rows.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "net_volume": 0.0,
                    "gross_volume": 0.0,
                    "floating_profit": 0.0,
                    "open_position_count": 0,
                    "used_margin_share": 0.0,
                    "risk_in_flight": 0.0,
                },
            )
            row["net_volume"] += signed_volume
            row["gross_volume"] += abs(float(position["volume"]))
            row["floating_profit"] += float(position["profit"])
            row["open_position_count"] += 1
            if position.get("stop_loss") and position.get("price_open"):
                row["risk_in_flight"] += abs(float(position["price_open"]) - float(position["stop_loss"])) * float(
                    position["volume"]
                )

        for symbol, row in symbol_rows.items():
            info = mt5.symbol_info(symbol)
            margin_initial = float(getattr(info, "margin_initial", 0.0) or 0.0) if info else 0.0
            if total_margin > 0 and margin_initial > 0:
                row["used_margin_share"] = round((row["gross_volume"] * margin_initial) / total_margin, 4)

        balance = float(getattr(account, "balance", 0.0) or 0.0)
        equity = float(getattr(account, "equity", 0.0) or 0.0)
        drawdown_amount = max(0.0, balance - equity)
        drawdown_percent = round((drawdown_amount / balance) * 100.0, 4) if balance > 0 else 0.0
        updated_at = utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        account_state = {
            "schema_version": "1.0.0",
            "account_state_id": f"account_{int(getattr(account, 'login', 0) or 0)}",
            "account_login": int(getattr(account, "login", 0) or 0),
            "broker_server": str(getattr(account, "server", "") or ""),
            "broker_company": str(getattr(terminal, "company", "") or "") if terminal else "",
            "account_mode": self._account_mode_name(getattr(account, "trade_mode", None)),
            "currency": str(getattr(account, "currency", "") or ""),
            "leverage": int(getattr(account, "leverage", 0) or 0),
            "balance": balance,
            "equity": equity,
            "margin": total_margin,
            "free_margin": float(getattr(account, "margin_free", 0.0) or 0.0),
            "margin_level": float(getattr(account, "margin_level", 0.0) or 0.0),
            "profit": float(getattr(account, "profit", 0.0) or 0.0),
            "drawdown_amount": drawdown_amount,
            "drawdown_percent": drawdown_percent,
            "open_position_count": len(positions),
            "pending_order_count": len(orders),
            "account_flags": [f"watch:{symbol}" for symbol in symbols[:20]],
            "heartbeat_at": updated_at,
            "updated_at": updated_at,
        }
        exposure_state = {
            "schema_version": "1.0.0",
            "exposure_state_id": f"exposure_{account_state['account_login']}",
            "updated_at": updated_at,
            "gross_exposure": round(gross_exposure, 8),
            "net_exposure": round(net_exposure, 8),
            "floating_profit": round(floating_profit, 2),
            "open_position_count": len(positions),
            "symbols": sorted(symbol_rows.values(), key=lambda row: row["symbol"]),
        }

        recent_deals = []
        for item in list(deals_raw)[-100:]:
            recent_deals.append(
                {
                    "deal_id": int(getattr(item, "ticket", 0) or 0),
                    "order_id": int(getattr(item, "order", 0) or 0),
                    "symbol": str(getattr(item, "symbol", "") or "").upper(),
                    "profit": float(getattr(item, "profit", 0.0) or 0.0),
                    "commission": float(getattr(item, "commission", 0.0) or 0.0),
                    "swap": float(getattr(item, "swap", 0.0) or 0.0),
                    "fee": float(getattr(item, "fee", 0.0) or 0.0),
                    "volume": float(getattr(item, "volume", 0.0) or 0.0),
                    "price": float(getattr(item, "price", 0.0) or 0.0),
                    "time": self._safe_iso_from_epoch(getattr(item, "time", 0)),
                    "entry": int(getattr(item, "entry", 0) or 0),
                    "comment": str(getattr(item, "comment", "") or "")[:160],
                }
            )

        recent_order_history = []
        for item in list(orders_history_raw)[-100:]:
            recent_order_history.append(
                {
                    "order_id": int(getattr(item, "ticket", 0) or 0),
                    "symbol": str(getattr(item, "symbol", "") or "").upper(),
                    "state": int(getattr(item, "state", 0) or 0),
                    "type": self._order_type_name(getattr(item, "type", None)),
                    "volume_initial": float(getattr(item, "volume_initial", 0.0) or 0.0),
                    "volume_current": float(getattr(item, "volume_current", 0.0) or 0.0),
                    "time_done": self._safe_iso_from_epoch(getattr(item, "time_done", 0)),
                    "comment": str(getattr(item, "comment", "") or "")[:160],
                }
            )

        return {
            "account_state": account_state,
            "positions": positions,
            "orders": orders,
            "exposure_state": exposure_state,
            "recent_deals": recent_deals,
            "recent_orders": recent_order_history,
        }

    def symbol_tick(self, symbol: str) -> dict[str, Any]:
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(resolved_symbol)
        if tick is None:
            raise MT5ConnectorError(f"symbol_info_tick failed for {resolved_symbol}: {mt5.last_error()}")
        return {
            "symbol": resolved_symbol.upper(),
            "bid": float(getattr(tick, "bid", 0.0) or 0.0),
            "ask": float(getattr(tick, "ask", 0.0) or 0.0),
            "last": float(getattr(tick, "last", 0.0) or 0.0),
            "time": self._safe_iso_from_epoch(getattr(tick, "time", 0)),
        }

    def login(self, account: int, *, password: str = "", server: str = "") -> dict[str, Any]:
        mt5 = self._require_mt5()
        kwargs: dict[str, Any] = {}
        if password:
            kwargs["password"] = password
        if server:
            kwargs["server"] = server
        ok = mt5.login(account, **kwargs)
        if not ok:
            error = mt5.last_error()
            return {"ok": False, "error_code": error[0], "error_message": error[1]}
        info = mt5.account_info()
        if info is None:
            return {"ok": True, "account_login": account}
        return {
            "ok": True,
            "account_login": int(getattr(info, "login", account)),
            "account_mode": self._account_mode_name(getattr(info, "trade_mode", None)),
            "broker_server": str(getattr(info, "server", "")),
            "broker_company": str(getattr(info, "company", "")),
            "balance": float(getattr(info, "balance", 0.0) or 0.0),
            "currency": str(getattr(info, "currency", "")),
            "leverage": int(getattr(info, "leverage", 0) or 0),
        }

    def probe_account(self, account: int, *, password: str = "", server: str = "") -> dict[str, Any]:
        mt5 = self._require_mt5()
        original_info = mt5.account_info()
        original_login = int(getattr(original_info, "login", 0)) if original_info else 0
        original_server = str(getattr(original_info, "server", "")) if original_info else ""
        probe = self.login(account, password=password, server=server)
        if original_login > 0:
            self.login(original_login, server=original_server)
        return probe

    def _resolve_filling_mode(self, symbol: str, entry_type: str) -> int:
        mt5 = self._require_mt5()
        fok = getattr(mt5, "ORDER_FILLING_FOK")
        ioc = getattr(mt5, "ORDER_FILLING_IOC")
        ret = getattr(mt5, "ORDER_FILLING_RETURN")
        if entry_type != "market":
            return ret
        info = mt5.symbol_info(symbol)
        if info is None:
            return fok
        filling = int(getattr(info, "filling_mode", 0) or 0)
        if filling & 1:
            return fok
        if filling & 2:
            return ioc
        return fok

    def send_execution_instruction(self, instruction: dict[str, Any]) -> dict[str, Any]:
        mt5 = self._require_mt5()
        account = mt5.account_info()
        if account is None:
            raise MT5ConnectorError(f"account_info failed before execution: {mt5.last_error()}")

        account_mode_guard = self.account_mode_guard or os.getenv("ACCOUNT_MODE", "demo").strip().lower()
        if account_mode_guard == "demo":
            actual_mode = self._account_mode_name(getattr(account, "trade_mode", None))
            if actual_mode != "demo":
                raise MT5ConnectorError(
                    f"ACCOUNT_MODE=demo but connected account mode is '{actual_mode}'. "
                    "Set ACCOUNT_MODE=live only when running a real account."
                )

        symbol = str(instruction.get("symbol", "")).upper()
        resolved_symbol = self.ensure_symbol(symbol)
        side = str(instruction.get("side", "")).lower()
        entry_type = str(instruction.get("entry_type", "")).lower()
        tick = self.symbol_tick(resolved_symbol)
        constraints = instruction.get("execution_constraints")
        if not isinstance(constraints, dict):
            constraints = {}
        deviation = int(constraints.get("max_slippage_points", 20) or 20)
        if side not in {"buy", "sell"} or entry_type not in {"market", "limit", "stop"}:
            raise MT5ConnectorError("unsupported execution instruction side/entry_type")

        if side == "buy":
            deal_type = getattr(mt5, "ORDER_TYPE_BUY")
            pending_type = getattr(mt5, "ORDER_TYPE_BUY_LIMIT" if entry_type == "limit" else "ORDER_TYPE_BUY_STOP")
            market_price = tick["ask"] or tick["last"]
        else:
            deal_type = getattr(mt5, "ORDER_TYPE_SELL")
            pending_type = getattr(mt5, "ORDER_TYPE_SELL_LIMIT" if entry_type == "limit" else "ORDER_TYPE_SELL_STOP")
            market_price = tick["bid"] or tick["last"]

        request: dict[str, Any] = {
            "action": getattr(mt5, "TRADE_ACTION_DEAL" if entry_type == "market" else "TRADE_ACTION_PENDING"),
            "symbol": resolved_symbol,
            "volume": float(instruction.get("volume", 0.0) or 0.0),
            "type": deal_type if entry_type == "market" else pending_type,
            "price": float(instruction.get("entry_price", market_price) or market_price),
            "deviation": deviation,
            "magic": self.magic_number,
            "comment": str(instruction.get("comment", ""))[:160],
            "type_time": getattr(mt5, "ORDER_TIME_GTC"),
            "type_filling": self._resolve_filling_mode(resolved_symbol, entry_type),
        }
        if instruction.get("stop_loss"):
            request["sl"] = float(instruction["stop_loss"])
        if instruction.get("take_profit"):
            request["tp"] = float(instruction["take_profit"])

        result = mt5.order_send(request)
        if result is None:
            raise MT5ConnectorError(f"order_send returned None: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ok_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1),
            getattr(mt5, "TRADE_RETCODE_PLACED", -2),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -3),
        }
        return {
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "") or ""),
            "order": int(getattr(result, "order", 0) or 0),
            "deal": int(getattr(result, "deal", 0) or 0),
            "position": int(getattr(result, "position", 0) or 0),
            "volume": float(getattr(result, "volume", request["volume"]) or request["volume"]),
            "price": float(getattr(result, "price", request["price"]) or request["price"]),
            "request": request,
            "ok": retcode in ok_codes,
        }

    # ------------------------------------------------------------------
    # Preflight safety helper
    # ------------------------------------------------------------------

    def _ensure_trading_available(self) -> None:
        """Verify terminal and account state before any write action.

        Raises MT5ConnectorError with actionable text when trading cannot proceed.

        NOTE: probe_account() is intentionally NOT called here. Certification
        confirmed that probe_account() can degrade the terminal session by
        switching accounts and leaving MT5 in a broken operational state.
        """
        mt5 = self._require_mt5()

        account = mt5.account_info()
        if account is None:
            raise MT5ConnectorError(
                f"MT5 account/session unavailable — account_info() returned None: {mt5.last_error()}"
            )

        terminal = mt5.terminal_info()
        if terminal is None:
            raise MT5ConnectorError(
                f"MT5 session unavailable — terminal_info() returned None: {mt5.last_error()}"
            )

        if not bool(getattr(terminal, "trade_allowed", False)):
            raise MT5ConnectorError(
                "Terminal trading is disabled — trade_allowed=False. "
                "Enable algo trading in the MT5 terminal before sending orders."
            )

        # Preserve ACCOUNT_MODE guard semantics from send_execution_instruction
        account_mode_guard = self.account_mode_guard or os.getenv("ACCOUNT_MODE", "demo").strip().lower()
        if account_mode_guard == "demo":
            actual_mode = self._account_mode_name(getattr(account, "trade_mode", None))
            if actual_mode != "demo":
                raise MT5ConnectorError(
                    f"ACCOUNT_MODE=demo but connected account mode is '{actual_mode}'. "
                    "Set ACCOUNT_MODE=live only when running a real account."
                )

    # ------------------------------------------------------------------
    # Execution surface — position and order mutation
    # ------------------------------------------------------------------

    def modify_position_levels(
        self,
        symbol: str,
        position_id: int,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> dict[str, Any]:
        """Modify SL/TP of an open position using TRADE_ACTION_SLTP."""
        self._ensure_trading_available()
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        request: dict[str, Any] = {
            "action": getattr(mt5, "TRADE_ACTION_SLTP"),
            "symbol": resolved_symbol.upper(),
            "position": int(position_id),
        }
        if isinstance(stop_loss, (int, float)) and stop_loss > 0:
            request["sl"] = float(stop_loss)
        if isinstance(take_profit, (int, float)) and take_profit > 0:
            request["tp"] = float(take_profit)
        result = mt5.order_send(request)
        if result is None:
            raise MT5ConnectorError(f"order_send SLTP returned None: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ok_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1),
            getattr(mt5, "TRADE_RETCODE_PLACED", -2),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -3),
        }
        return {
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "") or ""),
            "order": int(getattr(result, "order", 0) or 0),
            "deal": int(getattr(result, "deal", 0) or 0),
            "position": int(getattr(result, "position", position_id) or position_id),
            "request": request,
            "ok": retcode in ok_codes,
        }

    def modify_order_levels(
        self,
        symbol: str,
        order_id: int,
        price_open: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Modify price/SL/TP of a pending order using TRADE_ACTION_MODIFY."""
        self._ensure_trading_available()
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        request: dict[str, Any] = {
            "action": getattr(mt5, "TRADE_ACTION_MODIFY"),
            "symbol": resolved_symbol.upper(),
            "order": int(order_id),
        }
        if isinstance(price_open, (int, float)) and price_open > 0:
            request["price"] = float(price_open)
        if isinstance(stop_loss, (int, float)) and stop_loss > 0:
            request["sl"] = float(stop_loss)
        if isinstance(take_profit, (int, float)) and take_profit > 0:
            request["tp"] = float(take_profit)
        result = mt5.order_send(request)
        if result is None:
            raise MT5ConnectorError(f"order_send MODIFY returned None: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ok_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1),
            getattr(mt5, "TRADE_RETCODE_PLACED", -2),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -3),
        }
        return {
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "") or ""),
            "order": int(getattr(result, "order", 0) or order_id),
            "deal": int(getattr(result, "deal", 0) or 0),
            "request": request,
            "ok": retcode in ok_codes,
        }

    def remove_order(self, order_id: int) -> dict[str, Any]:
        """Cancel a pending order using TRADE_ACTION_REMOVE."""
        self._ensure_trading_available()
        mt5 = self._require_mt5()
        request: dict[str, Any] = {
            "action": getattr(mt5, "TRADE_ACTION_REMOVE"),
            "order": int(order_id),
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5ConnectorError(f"order_send REMOVE returned None: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ok_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1),
            getattr(mt5, "TRADE_RETCODE_PLACED", -2),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -3),
        }
        return {
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "") or ""),
            "order": int(getattr(result, "order", 0) or order_id),
            "deal": int(getattr(result, "deal", 0) or 0),
            "request": request,
            "ok": retcode in ok_codes,
        }

    def close_position(
        self,
        symbol: str,
        position_id: int,
        side: str,
        volume: float,
        max_slippage_points: int = 20,
    ) -> dict[str, Any]:
        """Close an open position by opposite market deal.

        Supports both full and partial close.
        Comment is intentionally empty to avoid broker comment-rejection bugs
        confirmed during certification.
        """
        self._ensure_trading_available()
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        tick = self.symbol_tick(resolved_symbol)
        normalized_side = str(side or "").strip().lower()
        if normalized_side == "buy":
            order_type = getattr(mt5, "ORDER_TYPE_SELL")
            price = tick["bid"] or tick["last"]
        elif normalized_side == "sell":
            order_type = getattr(mt5, "ORDER_TYPE_BUY")
            price = tick["ask"] or tick["last"]
        else:
            raise MT5ConnectorError(f"Unsupported close_position side: '{side}'")
        request: dict[str, Any] = {
            "action": getattr(mt5, "TRADE_ACTION_DEAL"),
            "symbol": resolved_symbol,
            "position": int(position_id),
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "deviation": int(max_slippage_points),
            "magic": self.magic_number,
            "comment": "",
            "type_time": getattr(mt5, "ORDER_TIME_GTC"),
            "type_filling": self._resolve_filling_mode(resolved_symbol, "market"),
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5ConnectorError(f"order_send CLOSE returned None: {mt5.last_error()}")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ok_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -1),
            getattr(mt5, "TRADE_RETCODE_PLACED", -2),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -3),
        }
        return {
            "retcode": retcode,
            "comment": str(getattr(result, "comment", "") or ""),
            "order": int(getattr(result, "order", 0) or 0),
            "deal": int(getattr(result, "deal", 0) or 0),
            "position": int(getattr(result, "position", position_id) or position_id),
            "request": request,
            "ok": retcode in ok_codes,
        }

    def find_open_position_id(self, symbol: str, comment: str) -> int | None:
        """Return ticket of the first open position on *symbol* whose comment
        exactly matches *comment*.

        Returns None when no match is found or when *comment* is empty.
        Never raises on comment-not-found.
        """
        mt5 = self._require_mt5()
        resolved_symbol = self.ensure_symbol(symbol)
        wanted = str(comment or "").strip()
        if not wanted:
            return None
        positions = mt5.positions_get(symbol=resolved_symbol.upper()) or ()
        for item in positions:
            if str(getattr(item, "comment", "") or "").strip() == wanted:
                position_id = int(getattr(item, "ticket", 0) or 0)
                if position_id > 0:
                    return position_id
        return None


def timeframe_seconds(timeframe: str) -> int:
    mapping = {
        "M1": 60,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H4": 14400,
        "D1": 86400,
    }
    return mapping.get(str(timeframe).upper(), 300)


def determine_feed_status(snapshot: dict[str, Any], poll_seconds: float) -> dict[str, Any]:
    now = utc_now()
    market_context = snapshot.get("market_context") if isinstance(snapshot.get("market_context"), dict) else {}
    tick_dt = iso_to_datetime(str(market_context.get("tick_time", "")))
    bar_dt = iso_to_datetime(str(market_context.get("last_bar_timestamp", "")))
    timeframe = str(snapshot.get("timeframe", "M5")).upper()
    tf_seconds = timeframe_seconds(timeframe)
    tick_age = (now - tick_dt).total_seconds() if tick_dt else None
    bar_age = (now - bar_dt).total_seconds() if bar_dt else None

    feed_status = "unknown"
    if tick_age is not None and tick_age <= max(float(poll_seconds) * 3, 15):
        feed_status = "live"
    elif tick_age is not None and tick_age > tf_seconds * 3:
        feed_status = "market_closed"
    elif tick_age is not None:
        feed_status = "idle"

    if bar_age is not None and bar_age > tf_seconds * 4 and feed_status == "idle":
        feed_status = "stale_feed"

    return {
        "feed_status": feed_status,
        "tick_age_seconds": None if tick_age is None else round(tick_age, 1),
        "bar_age_seconds": None if bar_age is None else round(bar_age, 1),
        "timeframe_seconds": tf_seconds,
        "server_time_offset_seconds": market_context.get("server_time_offset_seconds", 0),
    }


def estimate_local_clock_drift_ms(server_time_offset_seconds: int, tick_time_raw: str) -> float | None:
    tick_dt = iso_to_datetime(tick_time_raw)
    if not tick_dt:
        return None
    expected_utc = tick_dt.timestamp() - float(server_time_offset_seconds)
    return round((expected_utc - utc_now_epoch()) * 1000.0, 1)

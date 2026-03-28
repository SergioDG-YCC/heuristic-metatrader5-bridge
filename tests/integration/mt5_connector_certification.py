from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = next((p for p in [CURRENT_FILE.parent, *CURRENT_FILE.parents] if (p / "pyproject.toml").exists()), CURRENT_FILE.parent)
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from heuristic_mt5_bridge.core.config.env import load_env_file  # noqa: E402
from heuristic_mt5_bridge.infra.mt5.connector import MT5Connector  # noqa: E402

DOCS = {
    "initialize": "https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py",
    "login": "https://www.mql5.com/en/docs/python_metatrader5/mt5login_py",
    "shutdown": "https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py",
    "symbol_info": "https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py",
    "symbol_info_tick": "https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py",
    "copy_rates_from_pos": "https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py",
    "positions_get": "https://www.mql5.com/en/docs/python_metatrader5/mt5positionsget_py",
    "orders_get": "https://www.mql5.com/en/docs/python_metatrader5/mt5ordersget_py",
    "history_orders_get": "https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py",
    "history_deals_get": "https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py",
    "order_calc_margin": "https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py",
    "order_check": "https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py",
    "order_send": "https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py",
}

SURFACE_METHODS = (
    "connect",
    "shutdown",
    "broker_identity",
    "ensure_symbol",
    "fetch_snapshot",
    "fetch_symbol_specification",
    "fetch_available_symbol_catalog",
    "fetch_account_runtime",
    "symbol_tick",
    "login",
    "probe_account",
    "send_execution_instruction",
    "modify_position_levels",
    "modify_order_levels",
    "remove_order",
    "close_position",
    "find_open_position_id",
)


class SkipCase(RuntimeError):
    pass


class GapCase(RuntimeError):
    pass


@dataclass(frozen=True)
class Case:
    case_id: str
    kind: str
    summary: str
    docs: tuple[str, ...]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def truthy(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "_asdict"):
        return to_jsonable(value._asdict())  # type: ignore[attr-defined]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return repr(value)


def filter_matches(case_id: str, filters: list[str]) -> bool:
    if not filters:
        return True
    target = case_id.lower()
    for item in filters:
        token = item.lower().strip()
        if target == token or target.startswith(f"{token}."):
            return True
    return False


class CertificationRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        env_values = load_env_file(REPO_ROOT / ".env")
        self.include = split_csv(args.include or os.getenv("MT5_TEST_INCLUDE", env_values.get("MT5_TEST_INCLUDE", "")))
        self.exclude = split_csv(args.exclude or os.getenv("MT5_TEST_EXCLUDE", env_values.get("MT5_TEST_EXCLUDE", "")))
        self.watch_symbols = split_csv(os.getenv("MT5_WATCH_SYMBOLS", env_values.get("MT5_WATCH_SYMBOLS", "EURUSD")))
        self.watch_timeframes = split_csv(os.getenv("MT5_WATCH_TIMEFRAMES", env_values.get("MT5_WATCH_TIMEFRAMES", "M5")))
        preferred_symbol = args.symbol or os.getenv("MT5_TEST_SYMBOL", env_values.get("MT5_TEST_SYMBOL", ""))
        self.symbol = preferred_symbol or ("EURUSD" if "EURUSD" in self.watch_symbols else (self.watch_symbols[0] if self.watch_symbols else "EURUSD"))
        self.timeframe = (args.timeframe or os.getenv("MT5_TEST_TIMEFRAME", env_values.get("MT5_TEST_TIMEFRAME", "")) or (self.watch_timeframes[0] if self.watch_timeframes else "M5")).upper()
        self.terminal_path = os.getenv("MT5_TERMINAL_PATH", env_values.get("MT5_TERMINAL_PATH", "")).strip()
        self.account_mode_guard = os.getenv("ACCOUNT_MODE", env_values.get("ACCOUNT_MODE", "demo")).strip().lower()
        self.magic_number = int(os.getenv("MT5_MAGIC_NUMBER", env_values.get("MT5_MAGIC_NUMBER", "20260315")) or 20260315)
        self.volume = float(args.volume or os.getenv("MT5_TEST_VOLUME", env_values.get("MT5_TEST_VOLUME", "0.01")) or 0.01)
        self.partial_volume = float(os.getenv("MT5_TEST_PARTIAL_VOLUME", env_values.get("MT5_TEST_PARTIAL_VOLUME", str(max(self.volume * 2.0, 0.02)))) or max(self.volume * 2.0, 0.02))
        self.sl_points = int(os.getenv("MT5_TEST_SL_POINTS", env_values.get("MT5_TEST_SL_POINTS", "150")) or 150)
        self.tp_points = int(os.getenv("MT5_TEST_TP_POINTS", env_values.get("MT5_TEST_TP_POINTS", "300")) or 300)
        self.pending_distance_points = int(os.getenv("MT5_TEST_PENDING_DISTANCE_POINTS", env_values.get("MT5_TEST_PENDING_DISTANCE_POINTS", "250")) or 250)
        self.trailing_step_points = int(os.getenv("MT5_TEST_TRAILING_STEP_POINTS", env_values.get("MT5_TEST_TRAILING_STEP_POINTS", "50")) or 50)
        self.history_hours = int(os.getenv("MT5_TEST_HISTORY_HOURS", env_values.get("MT5_TEST_HISTORY_HOURS", "24")) or 24)
        self.allow_live_writes = bool(args.allow_live_writes or truthy(os.getenv("MT5_TEST_ALLOW_LIVE_WRITES", env_values.get("MT5_TEST_ALLOW_LIVE_WRITES", "false"))))
        self.allow_destructive = bool(args.allow_destructive or truthy(os.getenv("MT5_TEST_ALLOW_DESTRUCTIVE", env_values.get("MT5_TEST_ALLOW_DESTRUCTIVE", "false"))))
        self.allow_dirty_symbol = bool(args.allow_dirty_symbol or truthy(os.getenv("MT5_TEST_ALLOW_DIRTY_SYMBOL", env_values.get("MT5_TEST_ALLOW_DIRTY_SYMBOL", "false"))))
        self.comment_mode = (args.comment_mode or os.getenv("MT5_TEST_COMMENT_MODE", env_values.get("MT5_TEST_COMMENT_MODE", "tagged")) or "tagged").strip().lower()
        report_root = Path(args.report_dir or os.getenv("MT5_TEST_REPORT_DIR", env_values.get("MT5_TEST_REPORT_DIR", "")) or (REPO_ROOT / "storage" / "certification"))
        report_root.mkdir(parents=True, exist_ok=True)
        self.report_path = report_root / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
        self.connector: MT5Connector | None = None
        self.mt5: Any | None = None
        self.spec_cache: dict[str, Any] | None = None
        self.account_login = 0
        self.account_server = ""
        self.run_id = self.report_path.stem
        self.results: list[dict[str, Any]] = []

    def cases(self) -> list[Case]:
        items = [Case(f"surface.{name}", "introspection", f"Connector exposes `{name}()`", ()) for name in SURFACE_METHODS]
        items += [
            Case("official.symbol_info", "read", "Raw MT5 symbol_info()", (DOCS["symbol_info"],)),
            Case("official.symbol_info_tick", "read", "Raw MT5 symbol_info_tick()", (DOCS["symbol_info_tick"],)),
            Case("official.copy_rates_from_pos", "read", "Raw MT5 copy_rates_from_pos()", (DOCS["copy_rates_from_pos"],)),
            Case("official.positions_get", "read", "Raw MT5 positions_get()", (DOCS["positions_get"],)),
            Case("official.orders_get", "read", "Raw MT5 orders_get()", (DOCS["orders_get"],)),
            Case("official.history_orders_get", "read", "Raw MT5 history_orders_get()", (DOCS["history_orders_get"],)),
            Case("official.history_deals_get", "read", "Raw MT5 history_deals_get()", (DOCS["history_deals_get"],)),
            Case("official.order_calc_margin.buy", "read", "Raw MT5 order_calc_margin() buy", (DOCS["order_calc_margin"],)),
            Case("official.order_calc_margin.sell", "read", "Raw MT5 order_calc_margin() sell", (DOCS["order_calc_margin"],)),
            Case("official.order_check.market_buy", "read", "Raw MT5 order_check() valid market buy", (DOCS["order_check"],)),
            Case("official.order_check.invalid_buy_limit", "read", "Raw MT5 order_check() invalid buy limit", (DOCS["order_check"],)),
            Case("official.live.position_sltp", "write", "Raw MT5 TRADE_ACTION_SLTP", (DOCS["order_send"],)),
            Case("official.live.order_modify", "write", "Raw MT5 TRADE_ACTION_MODIFY", (DOCS["order_send"],)),
            Case("official.live.order_remove", "destructive", "Raw MT5 TRADE_ACTION_REMOVE", (DOCS["order_send"],)),
            Case("official.live.position_close_full", "destructive", "Raw MT5 full close by opposite deal", (DOCS["order_send"],)),
            Case("official.live.position_close_partial", "destructive", "Raw MT5 partial close by opposite deal", (DOCS["order_send"],)),
            Case("official.pattern.trailing_sltp", "write", "Raw MT5 trailing pattern via repeated SLTP", (DOCS["order_send"],)),
            Case("connector.read.broker_identity", "read", "Bridge broker_identity()", (DOCS["initialize"], DOCS["login"])),
            Case("connector.read.fetch_snapshot", "read", "Bridge fetch_snapshot()", (DOCS["copy_rates_from_pos"],)),
            Case("connector.read.fetch_account_runtime", "read", "Bridge fetch_account_runtime()", (DOCS["positions_get"], DOCS["orders_get"], DOCS["history_orders_get"], DOCS["history_deals_get"])),
            Case("connector.read.fetch_available_symbol_catalog", "read", "Bridge fetch_available_symbol_catalog()", (DOCS["symbol_info"],)),
            Case("connector.read.login_current", "read", "Bridge login() current account", (DOCS["login"],)),
            Case("connector.read.probe_current", "read", "Bridge probe_account() current account", (DOCS["login"],)),
            Case("connector.read.probe_invalid_account", "read", "Bridge probe_account() invalid account/password", (DOCS["login"],)),
            Case("connector.write.market_buy", "write", "Bridge market buy", (DOCS["order_send"],)),
            Case("connector.write.market_sell", "write", "Bridge market sell", (DOCS["order_send"],)),
            Case("connector.write.buy_limit", "write", "Bridge buy limit", (DOCS["order_send"],)),
            Case("connector.write.sell_limit", "write", "Bridge sell limit", (DOCS["order_send"],)),
            Case("connector.write.buy_stop", "write", "Bridge buy stop", (DOCS["order_send"],)),
            Case("connector.write.sell_stop", "write", "Bridge sell stop", (DOCS["order_send"],)),
            Case("connector.manage.find_open_position_id", "write", "Bridge find_open_position_id()", (DOCS["positions_get"],)),
            Case("connector.manage.modify_position_levels", "write", "Bridge modify_position_levels()", (DOCS["order_send"],)),
            Case("connector.manage.modify_order_levels", "write", "Bridge modify_order_levels()", (DOCS["order_send"],)),
            Case("connector.manage.remove_order", "destructive", "Bridge remove_order()", (DOCS["order_send"],)),
            Case("connector.manage.close_position_full", "destructive", "Bridge close_position() full", (DOCS["order_send"],)),
            Case("connector.manage.close_position_partial", "destructive", "Bridge close_position() partial", (DOCS["order_send"],)),
            Case("connector.pattern.trailing_stop", "write", "Bridge trailing pattern via repeated SLTP", (DOCS["order_send"],)),
        ]
        return items

    def should_run(self, case_id: str) -> bool:
        return filter_matches(case_id, self.include) and not (self.exclude and filter_matches(case_id, self.exclude))

    def require_runtime(self) -> None:
        if self.connector is not None and self.mt5 is not None:
            return
        self.connector = MT5Connector(
            terminal_path=self.terminal_path,
            watch_symbols=self.watch_symbols,
            magic_number=self.magic_number,
            account_mode_guard=self.account_mode_guard,
        )
        self.connector.connect()
        self.mt5 = self.connector._require_mt5()
        info = self.mt5.account_info()
        self.account_login = int(getattr(info, "login", 0) or 0) if info else 0
        self.account_server = str(getattr(info, "server", "") or "") if info else ""
        self.symbol = self.connector.ensure_symbol(self.symbol)

    def shutdown(self) -> None:
        if self.connector is None:
            return
        try:
            self.connector.shutdown()
        except Exception:
            pass

    def spec(self) -> dict[str, Any]:
        self.require_runtime()
        if self.spec_cache is None:
            assert self.connector is not None
            self.spec_cache = self.connector.fetch_symbol_specification(self.symbol)
        return self.spec_cache

    def tick(self) -> dict[str, Any]:
        self.require_runtime()
        assert self.connector is not None
        return self.connector.symbol_tick(self.symbol)

    def point(self) -> float:
        value = float(self.spec().get("point", 0.0) or 0.0)
        return value if value > 0 else 0.0001

    def digits(self) -> int:
        return int(self.spec().get("digits", 5) or 5)

    def norm_price(self, value: float) -> float:
        return round(float(value), self.digits())

    def norm_volume(self, requested: float) -> float:
        spec = self.spec()
        vmin = float(spec.get("volume_min", 0.01) or 0.01)
        vmax = float(spec.get("volume_max", requested) or requested)
        step = float(spec.get("volume_step", vmin) or vmin or 0.01)
        clamped = max(vmin, min(float(requested), vmax))
        steps = max(0, math.floor(((clamped - vmin) / step) + 1e-9))
        value = max(vmin, min(vmin + (steps * step), vmax))
        decimals = max(0, len(str(step).split(".", 1)[1].rstrip("0")) if "." in str(step) else 0)
        return round(value, decimals)

    def safe_points(self, requested: int) -> int:
        spec = self.spec()
        return max(int(requested), int(spec.get("stops_level_points", 0) or 0) + int(spec.get("freeze_level_points", 0) or 0) + 10, 10)

    def ok_codes(self) -> set[int]:
        self.require_runtime()
        assert self.mt5 is not None
        return {
            int(getattr(self.mt5, "TRADE_RETCODE_DONE", -1)),
            int(getattr(self.mt5, "TRADE_RETCODE_PLACED", -2)),
            int(getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", -3)),
            0,
        }

    def require_clean_symbol(self) -> None:
        self.require_runtime()
        if self.allow_dirty_symbol:
            return
        assert self.mt5 is not None
        positions = self.mt5.positions_get(symbol=self.symbol) or ()
        orders = self.mt5.orders_get(symbol=self.symbol) or ()
        if positions or orders:
            raise SkipCase(f"test symbol {self.symbol} is not clean ({len(positions)} positions, {len(orders)} orders)")

    def require_live(self) -> None:
        if not self.allow_live_writes:
            raise SkipCase("live writes disabled; pass --allow-live-writes")
        self.require_runtime()

    def require_destructive_mode(self) -> None:
        if not self.allow_live_writes:
            raise SkipCase("live writes disabled; pass --allow-live-writes")
        if not self.allow_destructive:
            raise SkipCase("destructive cases disabled; pass --allow-destructive")
        self.require_runtime()

    def require_method(self, method_name: str) -> Any:
        self.require_runtime()
        assert self.connector is not None
        if not hasattr(self.connector, method_name):
            raise GapCase(f"connector missing public method `{method_name}()`")
        return getattr(self.connector, method_name)

    def comment(self, case_id: str) -> str:
        if self.comment_mode == "empty":
            return ""
        safe = case_id.replace(".", "_").replace(":", "_").replace("-", "_")
        return f"cert_{safe}_{uuid.uuid4().hex[:8]}"[:31]

    def current_tf_const(self) -> Any:
        self.require_runtime()
        assert self.mt5 is not None
        name = f"TIMEFRAME_{self.timeframe.upper()}"
        if not hasattr(self.mt5, name):
            raise RuntimeError(f"unsupported timeframe {self.timeframe}")
        return getattr(self.mt5, name)

    def assert_ok(self, response: dict[str, Any], context: str) -> None:
        if not response.get("ok"):
            raise AssertionError(f"{context} failed retcode={response.get('retcode')} comment={response.get('comment')}")

    def order_send(self, request: dict[str, Any]) -> dict[str, Any]:
        self.require_runtime()
        assert self.mt5 is not None
        result = self.mt5.order_send(request)
        if result is None:
            raise AssertionError(f"mt5.order_send returned None: {self.mt5.last_error()}")
        payload = result._asdict() if hasattr(result, "_asdict") else to_jsonable(result)
        if not isinstance(payload, dict):
            payload = {"value": to_jsonable(payload)}
        payload = to_jsonable(payload)
        payload["ok"] = int(payload.get("retcode", 0) or 0) in self.ok_codes()
        return payload

    def order_check(self, request: dict[str, Any]) -> dict[str, Any]:
        self.require_runtime()
        assert self.mt5 is not None
        result = self.mt5.order_check(request)
        if result is None:
            raise AssertionError(f"mt5.order_check returned None: {self.mt5.last_error()}")
        payload = result._asdict() if hasattr(result, "_asdict") else to_jsonable(result)
        if not isinstance(payload, dict):
            payload = {"value": to_jsonable(payload)}
        payload = to_jsonable(payload)
        payload["ok"] = int(payload.get("retcode", 0) or 0) in self.ok_codes()
        return payload

    def wait_for_position(self, *, ticket: int = 0, comment: str = "", timeout: float = 5.0) -> dict[str, Any] | None:
        self.require_runtime()
        assert self.mt5 is not None
        deadline = time.time() + timeout
        while time.time() <= deadline:
            for item in self.mt5.positions_get(symbol=self.symbol) or ():
                row = to_jsonable(item)
                if ticket and int(row.get("ticket", 0) or 0) == ticket:
                    return row
                if comment and str(row.get("comment", "")).strip() == comment:
                    return row
            time.sleep(0.2)
        return None

    def wait_for_order(self, *, ticket: int = 0, comment: str = "", timeout: float = 5.0) -> dict[str, Any] | None:
        self.require_runtime()
        assert self.mt5 is not None
        deadline = time.time() + timeout
        while time.time() <= deadline:
            for item in self.mt5.orders_get(symbol=self.symbol) or ():
                row = to_jsonable(item)
                if ticket and int(row.get("ticket", 0) or 0) == ticket:
                    return row
                if comment and str(row.get("comment", "")).strip() == comment:
                    return row
            time.sleep(0.2)
        return None

    def get_position(self, ticket: int) -> dict[str, Any] | None:
        return self.wait_for_position(ticket=ticket, timeout=0.2)

    def get_order(self, ticket: int) -> dict[str, Any] | None:
        return self.wait_for_order(ticket=ticket, timeout=0.2)

    def position_side(self, position: dict[str, Any]) -> str:
        self.require_runtime()
        assert self.mt5 is not None
        buy_type = int(getattr(self.mt5, "POSITION_TYPE_BUY", 0) or 0)
        return "buy" if int(position.get("type", 0) or 0) == buy_type else "sell"

    def market_request(self, side: str, comment: str, *, include_levels: bool, volume: float | None = None) -> dict[str, Any]:
        self.require_runtime()
        assert self.mt5 is not None
        tick = self.tick()
        price = tick["ask"] if side == "buy" else tick["bid"]
        request = {
            "action": getattr(self.mt5, "TRADE_ACTION_DEAL"),
            "symbol": self.symbol,
            "volume": self.norm_volume(volume if volume is not None else self.volume),
            "type": getattr(self.mt5, "ORDER_TYPE_BUY" if side == "buy" else "ORDER_TYPE_SELL"),
            "price": self.norm_price(price),
            "deviation": 20,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": getattr(self.mt5, "ORDER_TIME_GTC"),
            "type_filling": self.connector._resolve_filling_mode(self.symbol, "market") if self.connector else getattr(self.mt5, "ORDER_FILLING_FOK"),
        }
        if include_levels:
            slp = self.safe_points(self.sl_points) * self.point()
            tpp = self.safe_points(self.tp_points) * self.point()
            request["sl"] = self.norm_price(price - slp if side == "buy" else price + slp)
            request["tp"] = self.norm_price(price + tpp if side == "buy" else price - tpp)
        return request

    def pending_request(self, side: str, entry_type: str, comment: str) -> dict[str, Any]:
        self.require_runtime()
        assert self.mt5 is not None
        tick = self.tick()
        dist = self.safe_points(self.pending_distance_points) * self.point()
        slp = self.safe_points(self.sl_points) * self.point()
        tpp = self.safe_points(self.tp_points) * self.point()
        if side == "buy" and entry_type == "limit":
            price = tick["bid"] - dist
            order_type = getattr(self.mt5, "ORDER_TYPE_BUY_LIMIT")
        elif side == "sell" and entry_type == "limit":
            price = tick["ask"] + dist
            order_type = getattr(self.mt5, "ORDER_TYPE_SELL_LIMIT")
        elif side == "buy" and entry_type == "stop":
            price = tick["ask"] + dist
            order_type = getattr(self.mt5, "ORDER_TYPE_BUY_STOP")
        else:
            price = tick["bid"] - dist
            order_type = getattr(self.mt5, "ORDER_TYPE_SELL_STOP")
        request = {
            "action": getattr(self.mt5, "TRADE_ACTION_PENDING"),
            "symbol": self.symbol,
            "volume": self.norm_volume(self.volume),
            "type": order_type,
            "price": self.norm_price(price),
            "deviation": 20,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": getattr(self.mt5, "ORDER_TIME_GTC"),
            "type_filling": self.connector._resolve_filling_mode(self.symbol, entry_type) if self.connector else getattr(self.mt5, "ORDER_FILLING_RETURN"),
        }
        request["sl"] = self.norm_price(price - slp if side == "buy" else price + slp)
        request["tp"] = self.norm_price(price + tpp if side == "buy" else price - tpp)
        return request

    def create_position(self, case_id: str, side: str = "buy", include_levels: bool = False, volume: float | None = None) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
        comment = self.comment(case_id)
        request = self.market_request(side, comment, include_levels=include_levels, volume=volume)
        response = self.order_send(request)
        self.assert_ok(response, case_id)
        ticket = int(response.get("position", 0) or response.get("order", 0) or 0)
        position = self.wait_for_position(ticket=ticket, comment=comment)
        if position is None:
            raise AssertionError(f"{case_id} could not find created position")
        return position, comment, request, response

    def create_order(self, case_id: str, side: str, entry_type: str) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
        comment = self.comment(case_id)
        request = self.pending_request(side, entry_type, comment)
        response = self.order_send(request)
        self.assert_ok(response, case_id)
        order = self.wait_for_order(ticket=int(response.get("order", 0) or 0), comment=comment)
        if order is None:
            raise AssertionError(f"{case_id} could not find created order")
        return order, comment, request, response

    def cleanup_position(self, position: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self.close_position_raw(position)
        except Exception:
            return None

    def cleanup_order(self, order: dict[str, Any]) -> dict[str, Any] | None:
        try:
            self.require_runtime()
            assert self.mt5 is not None
            request = {"action": getattr(self.mt5, "TRADE_ACTION_REMOVE"), "order": int(order.get("ticket", 0) or 0)}
            return self.order_send(request)
        except Exception:
            return None

    def close_position_raw(self, position: dict[str, Any], volume: float | None = None) -> dict[str, Any]:
        self.require_runtime()
        assert self.mt5 is not None
        side = self.position_side(position)
        tick = self.tick()
        request = {
            "action": getattr(self.mt5, "TRADE_ACTION_DEAL"),
            "symbol": self.symbol,
            "position": int(position.get("ticket", 0) or 0),
            "volume": self.norm_volume(volume if volume is not None else float(position.get("volume", 0.0) or 0.0)),
            "type": getattr(self.mt5, "ORDER_TYPE_SELL" if side == "buy" else "ORDER_TYPE_BUY"),
            "price": self.norm_price(tick["bid"] if side == "buy" else tick["ask"]),
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "",
            "type_time": getattr(self.mt5, "ORDER_TIME_GTC"),
            "type_filling": self.connector._resolve_filling_mode(self.symbol, "market") if self.connector else getattr(self.mt5, "ORDER_FILLING_FOK"),
        }
        return self.order_send(request)

    def run(self) -> int:
        print(f"MT5 certification run_id={self.run_id}")
        print(f"symbol={self.symbol} timeframe={self.timeframe} live_writes={self.allow_live_writes} destructive={self.allow_destructive}")
        for case in self.cases():
            if self.should_run(case.case_id):
                self.run_case(case)
        self.report_path.write_text(json.dumps({"run_id": self.run_id, "created_at": iso_now(), "results": self.results}, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"report={self.report_path}")
        failed = len([r for r in self.results if r["status"] in {"failed", "gap"}])
        passed = len([r for r in self.results if r["status"] == "passed"])
        skipped = len([r for r in self.results if r["status"] == "skipped"])
        print(f"summary passed={passed} failed={failed} skipped={skipped}")
        self.shutdown()
        return 1 if failed else 0

    def run_case(self, case: Case) -> None:
        print(f"[RUN ] {case.case_id}")
        row = {"case_id": case.case_id, "kind": case.kind, "summary": case.summary, "docs": list(case.docs), "status": "passed", "started_at": iso_now(), "finished_at": "", "request": None, "response": None, "notes": "", "error_text": ""}
        try:
            if case.case_id.startswith("surface."):
                name = case.case_id.split(".", 1)[1]
                if not hasattr(MT5Connector, name):
                    raise GapCase(f"MT5Connector class does not expose `{name}()`")
                row["response"] = {"method": name, "present": True}
            elif case.case_id == "official.symbol_info":
                self.require_runtime(); assert self.mt5 is not None
                info = self.mt5.symbol_info(self.symbol)
                if info is None: raise AssertionError(self.mt5.last_error())
                row["response"] = to_jsonable(info)
            elif case.case_id == "official.symbol_info_tick":
                self.require_runtime(); assert self.mt5 is not None
                tick = self.mt5.symbol_info_tick(self.symbol)
                if tick is None: raise AssertionError(self.mt5.last_error())
                row["response"] = to_jsonable(tick)
            elif case.case_id == "official.copy_rates_from_pos":
                self.require_runtime(); assert self.mt5 is not None
                rates = self.mt5.copy_rates_from_pos(self.symbol, self.current_tf_const(), 0, 10)
                if rates is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"bars": len(rates), "sample": to_jsonable(list(rates[:2]))}
            elif case.case_id == "official.positions_get":
                self.require_runtime(); assert self.mt5 is not None
                items = self.mt5.positions_get(symbol=self.symbol)
                if items is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"count": len(items), "sample": to_jsonable(list(items[:2]))}
            elif case.case_id == "official.orders_get":
                self.require_runtime(); assert self.mt5 is not None
                items = self.mt5.orders_get(symbol=self.symbol)
                if items is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"count": len(items), "sample": to_jsonable(list(items[:2]))}
            elif case.case_id == "official.history_orders_get":
                self.require_runtime(); assert self.mt5 is not None
                now = datetime.now(timezone.utc); items = self.mt5.history_orders_get(now - timedelta(hours=self.history_hours), now)
                if items is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"count": len(items), "sample": to_jsonable(list(items[:2]))}
            elif case.case_id == "official.history_deals_get":
                self.require_runtime(); assert self.mt5 is not None
                now = datetime.now(timezone.utc); items = self.mt5.history_deals_get(now - timedelta(hours=self.history_hours), now)
                if items is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"count": len(items), "sample": to_jsonable(list(items[:2]))}
            elif case.case_id.startswith("official.order_calc_margin."):
                self.require_runtime(); assert self.mt5 is not None
                side = "buy" if case.case_id.endswith(".buy") else "sell"; tick = self.tick()
                action = getattr(self.mt5, "ORDER_TYPE_BUY" if side == "buy" else "ORDER_TYPE_SELL")
                price = tick["ask"] if side == "buy" else tick["bid"]
                value = self.mt5.order_calc_margin(action, self.symbol, self.norm_volume(self.volume), price)
                if value is None: raise AssertionError(self.mt5.last_error())
                row["response"] = {"side": side, "margin": float(value), "price": price}
            elif case.case_id == "official.order_check.market_buy":
                req = self.market_request("buy", self.comment(case.case_id), include_levels=True); req.pop("comment", None); res = self.order_check(req); self.assert_ok(res, case.case_id); row["request"] = req; row["response"] = res
            elif case.case_id == "official.order_check.invalid_buy_limit":
                req = self.pending_request("buy", "limit", self.comment(case.case_id)); req["price"] = self.norm_price(self.tick()["ask"] + (self.safe_points(5) * self.point())); req.pop("comment", None); res = self.order_check(req); row["request"] = req; row["response"] = res; 
                if res.get("ok"): raise AssertionError("invalid buy limit unexpectedly passed order_check")
            elif case.case_id == "connector.read.broker_identity":
                self.require_runtime(); assert self.connector is not None; row["response"] = self.connector.broker_identity()
            elif case.case_id == "connector.read.fetch_snapshot":
                self.require_runtime(); assert self.connector is not None; snap = self.connector.fetch_snapshot(self.symbol, self.timeframe, bars=25); row["response"] = {"symbol": snap["symbol"], "timeframe": snap["timeframe"], "bars": len(snap["ohlc"])}
            elif case.case_id == "connector.read.fetch_account_runtime":
                self.require_runtime(); assert self.connector is not None; data = self.connector.fetch_account_runtime(self.watch_symbols or [self.symbol]); row["response"] = {"account_login": data["account_state"]["account_login"], "positions": data["account_state"]["open_position_count"], "orders": data["account_state"]["pending_order_count"]}
            elif case.case_id == "connector.read.fetch_available_symbol_catalog":
                self.require_runtime(); assert self.connector is not None; catalog = self.connector.fetch_available_symbol_catalog(); row["response"] = {"count": len(catalog), "sample": catalog[:2]}
            elif case.case_id == "connector.read.login_current":
                self.require_runtime(); assert self.connector is not None; res = self.connector.login(self.account_login, server=self.account_server); row["response"] = res; 
                if not res.get("ok"): raise AssertionError(res)
            elif case.case_id == "connector.read.probe_current":
                self.require_runtime(); assert self.connector is not None; res = self.connector.probe_account(self.account_login, server=self.account_server); row["response"] = res; 
                if not res.get("ok"): raise AssertionError(res)
            elif case.case_id == "connector.read.probe_invalid_account":
                self.require_runtime(); assert self.connector is not None
                bogus_login = int(os.getenv("MT5_TEST_INVALID_ACCOUNT_LOGIN", "999999999") or 999999999)
                res = self.connector.probe_account(bogus_login, password=os.getenv("MT5_TEST_INVALID_ACCOUNT_PASSWORD", "invalid-password"), server=self.account_server)
                row["request"] = {"account_login": bogus_login, "server": self.account_server}
                row["response"] = res
                if res.get("ok"):
                    raise AssertionError("invalid account probe unexpectedly succeeded")
            else:
                self.run_live_case(case, row)
        except SkipCase as exc:
            row["status"] = "skipped"; row["notes"] = str(exc); print(f"[SKIP] {case.case_id} | {exc}")
        except GapCase as exc:
            row["status"] = "gap"; row["notes"] = str(exc); print(f"[GAP ] {case.case_id} | {exc}")
        except Exception as exc:  # noqa: BLE001
            row["status"] = "failed"; row["notes"] = str(exc); row["error_text"] = traceback.format_exc(limit=8); print(f"[FAIL] {case.case_id} | {exc}")
        else:
            print(f"[PASS] {case.case_id}")
        row["finished_at"] = iso_now()
        self.results.append(row)

    def run_live_case(self, case: Case, row: dict[str, Any]) -> None:
        if case.kind == "destructive":
            self.require_destructive_mode()
        else:
            self.require_live()
        self.require_clean_symbol()
        if case.case_id == "official.live.position_sltp":
            pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False)
            try:
                open_price = float(pos.get("price_open", 0.0) or 0.0)
                sl = self.norm_price(open_price - (self.safe_points(self.sl_points) * self.point()))
                tp = self.norm_price(open_price + (self.safe_points(self.tp_points) * self.point()))
                out = self.order_send({"action": getattr(self.mt5, "TRADE_ACTION_SLTP"), "symbol": self.symbol, "position": int(pos["ticket"]), "sl": sl, "tp": tp})
                self.assert_ok(out, case.case_id)
                row["request"] = {"position_id": pos["ticket"], "sl": sl, "tp": tp}; row["response"] = {"modify": out, "position": self.wait_for_position(ticket=int(pos["ticket"]))}
            finally:
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            return
        if case.case_id == "official.live.order_modify":
            order, comment, req, res = self.create_order(case.case_id, side="buy", entry_type="limit")
            try:
                point = self.point()
                price = self.norm_price(float(order.get("price_open", 0.0) or 0.0) - (self.safe_points(5) * point))
                sl = self.norm_price(float(order.get("sl", 0.0) or 0.0) - (self.safe_points(5) * point))
                tp = self.norm_price(float(order.get("tp", 0.0) or 0.0) + (self.safe_points(5) * point))
                out = self.order_send({"action": getattr(self.mt5, "TRADE_ACTION_MODIFY"), "symbol": self.symbol, "order": int(order["ticket"]), "price": price, "sl": sl, "tp": tp})
                self.assert_ok(out, case.case_id)
                row["request"] = {"order_id": order["ticket"], "price": price, "sl": sl, "tp": tp}; row["response"] = {"modify": out, "order": self.wait_for_order(ticket=int(order["ticket"]))}
            finally:
                self.cleanup_order(self.get_order(int(order["ticket"])) or order)
            return
        if case.case_id == "official.live.order_remove":
            order, comment, req, res = self.create_order(case.case_id, side="buy", entry_type="limit")
            out = self.order_send({"action": getattr(self.mt5, "TRADE_ACTION_REMOVE"), "order": int(order["ticket"])})
            self.assert_ok(out, case.case_id)
            row["request"] = {"order_id": order["ticket"]}; row["response"] = out
            if self.wait_for_order(ticket=int(order["ticket"]), timeout=2.0) is not None:
                raise AssertionError("order still present after raw remove")
            return
        if case.case_id in {"official.live.position_close_full", "official.live.position_close_partial"}:
            pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False, volume=self.partial_volume if case.case_id.endswith("partial") else None)
            try:
                original = float(pos.get("volume", 0.0) or 0.0)
                close_volume = self.norm_volume(max(float(self.spec().get("volume_min", 0.01) or 0.01), original / 2.0)) if case.case_id.endswith("partial") else original
                out = self.close_position_raw(pos, volume=close_volume)
                self.assert_ok(out, case.case_id)
                latest = self.wait_for_position(ticket=int(pos["ticket"]), timeout=3.0)
                row["request"] = {"position_id": pos["ticket"], "close_volume": close_volume}; row["response"] = {"close": out, "position": latest}
                if case.case_id.endswith("full") and latest is not None:
                    raise AssertionError("position still present after raw full close")
                if case.case_id.endswith("partial") and (latest is None or float(latest.get("volume", 0.0) or 0.0) >= original):
                    raise AssertionError("position did not shrink after raw partial close")
            finally:
                latest = self.get_position(int(pos["ticket"]))
                if latest is not None:
                    self.cleanup_position(latest)
            return
        if case.case_id == "official.pattern.trailing_sltp":
            pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False)
            try:
                open_price = float(pos.get("price_open", 0.0) or 0.0)
                first_sl = self.norm_price(open_price - (self.safe_points(self.sl_points) * self.point()))
                second_sl = self.norm_price(first_sl + (self.safe_points(self.trailing_step_points) * self.point()))
                a = self.order_send({"action": getattr(self.mt5, "TRADE_ACTION_SLTP"), "symbol": self.symbol, "position": int(pos["ticket"]), "sl": first_sl})
                self.assert_ok(a, case.case_id + ":first")
                b = self.order_send({"action": getattr(self.mt5, "TRADE_ACTION_SLTP"), "symbol": self.symbol, "position": int(pos["ticket"]), "sl": second_sl})
                self.assert_ok(b, case.case_id + ":second")
                latest = self.wait_for_position(ticket=int(pos["ticket"]))
                if latest is None or float(latest.get("sl", 0.0) or 0.0) + 1e-12 < second_sl:
                    raise AssertionError("raw trailing SL not updated as expected")
                row["request"] = {"position_id": pos["ticket"], "first_sl": first_sl, "second_sl": second_sl}; row["response"] = {"first": a, "second": b, "position": latest}
            finally:
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            return
        if case.case_id.startswith("connector.write."):
            side, entry = {
                "connector.write.market_buy": ("buy", "market"),
                "connector.write.market_sell": ("sell", "market"),
                "connector.write.buy_limit": ("buy", "limit"),
                "connector.write.sell_limit": ("sell", "limit"),
                "connector.write.buy_stop": ("buy", "stop"),
                "connector.write.sell_stop": ("sell", "stop"),
            }[case.case_id]
            self.require_method("send_execution_instruction"); assert self.connector is not None
            if entry == "market":
                req = {"symbol": self.symbol, "side": side, "entry_type": "market", "volume": self.norm_volume(self.volume), "comment": self.comment(case.case_id)}
                res = self.connector.send_execution_instruction(req); self.assert_ok(res, case.case_id)
                pos = self.wait_for_position(ticket=int(res.get("position", 0) or res.get("order", 0) or 0), comment=str(req["comment"]))
                if pos is None: raise AssertionError("position not found")
                row["request"] = req; row["response"] = {"execution": res, "position": pos}
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            else:
                raw = self.pending_request(side, entry, self.comment(case.case_id))
                req = {"symbol": self.symbol, "side": side, "entry_type": entry, "volume": raw["volume"], "entry_price": raw["price"], "stop_loss": raw["sl"], "take_profit": raw["tp"], "comment": raw["comment"]}
                res = self.connector.send_execution_instruction(req); self.assert_ok(res, case.case_id)
                order = self.wait_for_order(ticket=int(res.get("order", 0) or 0), comment=str(req["comment"]))
                if order is None: raise AssertionError("order not found")
                row["request"] = req; row["response"] = {"execution": res, "order": order}
                self.cleanup_order(self.get_order(int(order["ticket"])) or order)
            return
        if case.case_id == "connector.manage.find_open_position_id":
            if self.comment_mode == "empty":
                raise SkipCase("find_open_position_id requires tagged comments; run with --comment-mode tagged")
            method = self.require_method("find_open_position_id"); pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False)
            try:
                found = method(self.symbol, comment)
                if int(found or 0) != int(pos["ticket"]): raise AssertionError(f"returned {found}, expected {pos['ticket']}")
                row["request"] = {"symbol": self.symbol, "comment": comment}; row["response"] = {"position_id": found}
            finally:
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            return
        if case.case_id == "connector.manage.modify_position_levels":
            method = self.require_method("modify_position_levels"); pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False)
            try:
                open_price = float(pos.get("price_open", 0.0) or 0.0); sl = self.norm_price(open_price - (self.safe_points(self.sl_points) * self.point())); tp = self.norm_price(open_price + (self.safe_points(self.tp_points) * self.point()))
                out = method(symbol=self.symbol, position_id=int(pos["ticket"]), stop_loss=sl, take_profit=tp); self.assert_ok(out, case.case_id)
                row["request"] = {"position_id": pos["ticket"], "sl": sl, "tp": tp}; row["response"] = {"modify": out, "position": self.wait_for_position(ticket=int(pos["ticket"]))}
            finally:
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            return
        if case.case_id == "connector.manage.modify_order_levels":
            method = self.require_method("modify_order_levels"); order, comment, req, res = self.create_order(case.case_id, side="buy", entry_type="limit")
            try:
                point = self.point(); price = self.norm_price(float(order.get("price_open", 0.0) or 0.0) - (self.safe_points(5) * point)); sl = self.norm_price(float(order.get("sl", 0.0) or 0.0) - (self.safe_points(5) * point)); tp = self.norm_price(float(order.get("tp", 0.0) or 0.0) + (self.safe_points(5) * point))
                out = method(symbol=self.symbol, order_id=int(order["ticket"]), price_open=price, stop_loss=sl, take_profit=tp); self.assert_ok(out, case.case_id)
                row["request"] = {"order_id": order["ticket"], "price": price, "sl": sl, "tp": tp}; row["response"] = {"modify": out, "order": self.wait_for_order(ticket=int(order["ticket"]))}
            finally:
                self.cleanup_order(self.get_order(int(order["ticket"])) or order)
            return
        if case.case_id == "connector.manage.remove_order":
            method = self.require_method("remove_order"); order, comment, req, res = self.create_order(case.case_id, side="buy", entry_type="limit"); out = method(int(order["ticket"])); self.assert_ok(out, case.case_id)
            row["request"] = {"order_id": order["ticket"]}; row["response"] = out
            if self.wait_for_order(ticket=int(order["ticket"]), timeout=2.0) is not None: raise AssertionError("order still present after remove")
            return
        if case.case_id in {"connector.manage.close_position_full", "connector.manage.close_position_partial"}:
            method = self.require_method("close_position"); vol = self.partial_volume if case.case_id.endswith("partial") else None; pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False, volume=vol)
            try:
                original = float(pos.get("volume", 0.0) or 0.0); close_volume = self.norm_volume(max(float(self.spec().get("volume_min", 0.01) or 0.01), original / 2.0)) if case.case_id.endswith("partial") else original
                out = method(symbol=self.symbol, position_id=int(pos["ticket"]), side="buy", volume=close_volume); self.assert_ok(out, case.case_id)
                latest = self.wait_for_position(ticket=int(pos["ticket"]), timeout=3.0)
                row["request"] = {"position_id": pos["ticket"], "close_volume": close_volume}; row["response"] = {"close": out, "position": latest}
                if case.case_id.endswith("full") and latest is not None: raise AssertionError("position still present after full close")
                if case.case_id.endswith("partial") and (latest is None or float(latest.get("volume", 0.0) or 0.0) >= original): raise AssertionError("position did not shrink after partial close")
            finally:
                latest = self.get_position(int(pos["ticket"]))
                if latest is not None: self.cleanup_position(latest)
            return
        if case.case_id == "connector.pattern.trailing_stop":
            method = self.require_method("modify_position_levels"); pos, comment, req, res = self.create_position(case.case_id, side="buy", include_levels=False)
            try:
                open_price = float(pos.get("price_open", 0.0) or 0.0); first_sl = self.norm_price(open_price - (self.safe_points(self.sl_points) * self.point())); second_sl = self.norm_price(first_sl + (self.safe_points(self.trailing_step_points) * self.point()))
                a = method(symbol=self.symbol, position_id=int(pos["ticket"]), stop_loss=first_sl, take_profit=None); self.assert_ok(a, case.case_id + ":first")
                b = method(symbol=self.symbol, position_id=int(pos["ticket"]), stop_loss=second_sl, take_profit=None); self.assert_ok(b, case.case_id + ":second")
                latest = self.wait_for_position(ticket=int(pos["ticket"]))
                if latest is None or float(latest.get("sl", 0.0) or 0.0) + 1e-12 < second_sl: raise AssertionError("trailing SL not updated as expected")
                row["request"] = {"position_id": pos["ticket"], "first_sl": first_sl, "second_sl": second_sl}; row["response"] = {"first": a, "second": b, "position": latest}
            finally:
                self.cleanup_position(self.get_position(int(pos["ticket"])) or pos)
            return
        raise RuntimeError(f"unhandled live case {case.case_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MT5 connector certification runner")
    parser.add_argument("--list", action="store_true", help="List case ids and exit")
    parser.add_argument("--include", default="", help="Comma-separated case ids or prefixes")
    parser.add_argument("--exclude", default="", help="Comma-separated case ids or prefixes")
    parser.add_argument("--allow-live-writes", action="store_true", help="Allow order placement/modification")
    parser.add_argument("--allow-destructive", action="store_true", help="Allow remove/close/partial-close cases")
    parser.add_argument("--allow-dirty-symbol", action="store_true", help="Allow live tests on symbol with existing positions/orders")
    parser.add_argument("--comment-mode", default="", help="`tagged` or `empty` for trade comments")
    parser.add_argument("--symbol", default="", help="Symbol for certification")
    parser.add_argument("--timeframe", default="", help="Timeframe for rates/snapshot tests")
    parser.add_argument("--volume", type=float, default=0.0, help="Base volume for live tests")
    parser.add_argument("--report-dir", default="", help="Directory for JSON evidence")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner = CertificationRunner(args)
    if args.list:
        for case in runner.cases():
            print(f"{case.case_id} | {case.kind} | {case.summary}")
        return 0
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())

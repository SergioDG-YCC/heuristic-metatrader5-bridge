from __future__ import annotations

import time
import unittest

from heuristic_mt5_bridge.infra.mt5.connector import MT5Connector, MT5ConnectorError, determine_feed_status


class _Obj:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeMT5:
    TIMEFRAME_M5 = 5
    ACCOUNT_TRADE_MODE_DEMO = 0

    # MT5 trade action / retcode constants used by the new methods
    TRADE_ACTION_SLTP = 6
    TRADE_ACTION_MODIFY = 7
    TRADE_ACTION_REMOVE = 8
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    ORDER_TIME_GTC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010

    def __init__(self) -> None:
        self._visible = False
        self._tick_epoch = int(time.time()) + 7200
        self._rates = [
            {"time": self._tick_epoch - 600, "open": 1.1, "high": 1.1005, "low": 1.0998, "close": 1.1002, "tick_volume": 10},
            {"time": self._tick_epoch - 300, "open": 1.1002, "high": 1.101, "low": 1.1001, "close": 1.1008, "tick_volume": 12},
        ]
        self._order_send_calls: list[dict] = []
        self._positions: list[_Obj] = []
        # Default terminal_info: trade allowed
        self._trade_allowed = True

    def initialize(self, path: str | None = None) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def last_error(self) -> tuple[int, str]:
        return (0, "ok")

    def account_info(self) -> _Obj:
        return _Obj(login=123456, server="Broker-1", currency="USD", trade_mode=0)

    def terminal_info(self) -> _Obj:
        return _Obj(company="Broker Co", name="MT5", trade_allowed=self._trade_allowed)

    def symbol_info(self, symbol: str) -> _Obj | None:
        if symbol.upper() == "EURUSD":
            return _Obj(
                visible=self._visible,
                select=self._visible,
                custom=False,
                description="EURUSD",
                path="Forex\\Majors",
                digits=5,
                point=0.00001,
                trade_tick_size=0.00001,
                trade_tick_value=1.0,
                trade_contract_size=100000.0,
                spread_float=True,
                spread=15,
                trade_stops_level=10,
                trade_freeze_level=0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                volume_limit=0.0,
                currency_base="EUR",
                currency_profit="USD",
                currency_margin="USD",
                trade_mode=0,
                filling_mode=3,
                order_mode=127,
                expiration_mode=15,
                trade_calc_mode=0,
                margin_initial=0.0,
                margin_maintenance=0.0,
                margin_hedged=0.0,
                swap_long=0.0,
                swap_short=0.0,
            )
        return None

    def symbols_get(self) -> tuple[_Obj, ...]:
        return (_Obj(name="EURUSD"),)

    def symbol_select(self, symbol: str, flag: bool) -> bool:
        self._visible = bool(flag)
        return True

    def symbol_info_tick(self, symbol: str) -> _Obj:
        return _Obj(time=self._tick_epoch, bid=1.1007, ask=1.1009, last=1.1008)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, offset: int, bars: int) -> list[dict[str, float]]:
        return self._rates[:bars]

    def order_send(self, request: dict) -> _Obj:
        self._order_send_calls.append(dict(request))
        return _Obj(retcode=10009, comment="done", order=999, deal=888, position=777, volume=0.1, price=1.1009)

    def positions_get(self, symbol: str | None = None) -> list[_Obj]:
        return list(self._positions)


class MT5ConnectorTest(unittest.TestCase):
    def _make_connected_connector(self, trade_allowed: bool = True) -> tuple[MT5Connector, FakeMT5]:
        fake = FakeMT5()
        fake._trade_allowed = trade_allowed
        fake._visible = True  # symbol already visible so ensure_symbol skips select
        connector = MT5Connector(mt5_module=fake, watch_symbols=["EURUSD"])
        connector.connect()
        return connector, fake

    def test_fetch_snapshot_keeps_utc_normalization_and_market_context(self) -> None:
        fake = FakeMT5()
        connector = MT5Connector(mt5_module=fake, watch_symbols=["EURUSD"])
        connector.connect()
        snapshot = connector.fetch_snapshot("eurusd", "m5", bars=2)

        self.assertEqual(snapshot["symbol"], "EURUSD")
        self.assertEqual(snapshot["timeframe"], "M5")
        self.assertEqual(len(snapshot["ohlc"]), 2)
        self.assertTrue(snapshot["ohlc"][0]["timestamp"].endswith("Z"))
        self.assertEqual(
            snapshot["market_context"]["server_time_offset_seconds"],
            connector.server_time_offset_seconds,
        )

    def test_determine_feed_status_live(self) -> None:
        now_epoch = int(time.time())
        snapshot = {
            "timeframe": "M5",
            "market_context": {
                "tick_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch)),
                "last_bar_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch - 60)),
                "server_time_offset_seconds": 7200,
            },
        }
        status = determine_feed_status(snapshot, poll_seconds=5)
        self.assertEqual(status["feed_status"], "live")
        self.assertLessEqual(status["tick_age_seconds"], 15.0)

    # ------------------------------------------------------------------
    # New execution surface methods
    # ------------------------------------------------------------------

    def test_modify_position_levels_builds_sltp_request(self) -> None:
        connector, fake = self._make_connected_connector()
        result = connector.modify_position_levels("EURUSD", 12345, stop_loss=1.09, take_profit=1.12)

        self.assertEqual(len(fake._order_send_calls), 1)
        req = fake._order_send_calls[0]
        self.assertEqual(req["action"], FakeMT5.TRADE_ACTION_SLTP)
        self.assertEqual(req["position"], 12345)
        self.assertAlmostEqual(req["sl"], 1.09)
        self.assertAlmostEqual(req["tp"], 1.12)
        self.assertTrue(result["ok"])

    def test_modify_position_levels_omits_zero_sl_tp(self) -> None:
        connector, fake = self._make_connected_connector()
        connector.modify_position_levels("EURUSD", 12345, stop_loss=0.0, take_profit=None)

        req = fake._order_send_calls[0]
        self.assertNotIn("sl", req)
        self.assertNotIn("tp", req)

    def test_modify_order_levels_builds_modify_request(self) -> None:
        connector, fake = self._make_connected_connector()
        result = connector.modify_order_levels("EURUSD", 55555, price_open=1.095, stop_loss=1.08, take_profit=1.11)

        self.assertEqual(len(fake._order_send_calls), 1)
        req = fake._order_send_calls[0]
        self.assertEqual(req["action"], FakeMT5.TRADE_ACTION_MODIFY)
        self.assertEqual(req["order"], 55555)
        self.assertAlmostEqual(req["price"], 1.095)
        self.assertAlmostEqual(req["sl"], 1.08)
        self.assertAlmostEqual(req["tp"], 1.11)
        self.assertTrue(result["ok"])

    def test_remove_order_builds_remove_request(self) -> None:
        connector, fake = self._make_connected_connector()
        result = connector.remove_order(77777)

        self.assertEqual(len(fake._order_send_calls), 1)
        req = fake._order_send_calls[0]
        self.assertEqual(req["action"], FakeMT5.TRADE_ACTION_REMOVE)
        self.assertEqual(req["order"], 77777)
        self.assertTrue(result["ok"])

    def test_close_position_builds_opposite_side_sell(self) -> None:
        """Buy position closed with a sell deal."""
        connector, fake = self._make_connected_connector()
        result = connector.close_position("EURUSD", 9999, side="buy", volume=0.1)

        self.assertEqual(len(fake._order_send_calls), 1)
        req = fake._order_send_calls[0]
        self.assertEqual(req["action"], FakeMT5.TRADE_ACTION_DEAL)
        self.assertEqual(req["type"], FakeMT5.ORDER_TYPE_SELL)
        self.assertEqual(req["position"], 9999)
        self.assertAlmostEqual(req["volume"], 0.1)
        # close uses bid price when closing buy
        self.assertAlmostEqual(req["price"], 1.1007)
        self.assertTrue(result["ok"])

    def test_close_position_builds_opposite_side_buy(self) -> None:
        """Sell position closed with a buy deal."""
        connector, fake = self._make_connected_connector()
        connector.close_position("EURUSD", 9998, side="sell", volume=0.05)

        req = fake._order_send_calls[0]
        self.assertEqual(req["type"], FakeMT5.ORDER_TYPE_BUY)
        # close uses ask price when closing sell
        self.assertAlmostEqual(req["price"], 1.1009)

    def test_close_position_invalid_side_raises(self) -> None:
        connector, fake = self._make_connected_connector()
        with self.assertRaises(MT5ConnectorError):
            connector.close_position("EURUSD", 9997, side="long", volume=0.1)

    def test_find_open_position_id_exact_comment_match(self) -> None:
        connector, fake = self._make_connected_connector()
        fake._positions = [
            _Obj(ticket=11111, comment="fast_desk:A", symbol="EURUSD"),
            _Obj(ticket=22222, comment="fast_desk:B", symbol="EURUSD"),
        ]
        result = connector.find_open_position_id("EURUSD", "fast_desk:B")
        self.assertEqual(result, 22222)

    def test_find_open_position_id_not_found_returns_none(self) -> None:
        connector, fake = self._make_connected_connector()
        fake._positions = [_Obj(ticket=11111, comment="fast_desk:A", symbol="EURUSD")]
        result = connector.find_open_position_id("EURUSD", "fast_desk:Z")
        self.assertIsNone(result)

    def test_find_open_position_id_empty_comment_returns_none(self) -> None:
        connector, fake = self._make_connected_connector()
        fake._positions = [_Obj(ticket=11111, comment="fast_desk:A", symbol="EURUSD")]
        result = connector.find_open_position_id("EURUSD", "")
        self.assertIsNone(result)

    def test_preflight_fails_when_terminal_trading_disabled(self) -> None:
        connector, fake = self._make_connected_connector(trade_allowed=False)
        with self.assertRaises(MT5ConnectorError) as ctx:
            connector.modify_position_levels("EURUSD", 12345, stop_loss=1.09, take_profit=None)
        self.assertIn("trade_allowed", str(ctx.exception).lower())

    def test_preflight_blocks_remove_order_when_trading_disabled(self) -> None:
        connector, fake = self._make_connected_connector(trade_allowed=False)
        with self.assertRaises(MT5ConnectorError):
            connector.remove_order(77777)

    def test_preflight_blocks_close_position_when_trading_disabled(self) -> None:
        connector, fake = self._make_connected_connector(trade_allowed=False)
        with self.assertRaises(MT5ConnectorError):
            connector.close_position("EURUSD", 9999, side="buy", volume=0.1)


if __name__ == "__main__":
    unittest.main()

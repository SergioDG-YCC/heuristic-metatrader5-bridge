from __future__ import annotations

import unittest
from datetime import datetime, timezone

from heuristic_mt5_bridge.infra.sessions.gate import evaluate_symbol_session_gate, is_trade_open_from_registry


class SessionGateTest(unittest.TestCase):
    def test_is_trade_open_from_registry_respects_server_offset(self) -> None:
        now_utc = datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc)
        session_groups = {
            "sig_1": {
                "trade_sessions": {
                    "1": [{"from": 43000, "to": 45000}],
                }
            }
        }
        symbol_to_group = {"EURUSD": "sig_1"}

        self.assertTrue(
            is_trade_open_from_registry(
                session_groups,
                symbol_to_group,
                "EURUSD",
                server_time_offset_seconds=7200,
                now_utc=now_utc,
            )
        )

    def test_evaluate_symbol_session_gate_requires_sessions_and_required_feeds(self) -> None:
        payload = {
            "server_time_offset_seconds": 7200,
            "feed_status": [
                {"symbol": "EURUSD", "timeframe": "M5", "feed_status": "live"},
                {"symbol": "EURUSD", "timeframe": "H1", "feed_status": "idle"},
            ],
            "broker_session_registry": {
                "symbol_to_session_group": {"EURUSD": "sig_1"},
                "session_groups": {"sig_1": {"trade_sessions": {"1": [{"from": 0, "to": 86399}]}}},
            },
        }

        gate = evaluate_symbol_session_gate(
            "EURUSD",
            payload,
            now_utc=datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc),  # Monday
        )

        self.assertEqual(gate["gate_state"], "normal")
        self.assertTrue(gate["allow_new_entry"])
        self.assertEqual(gate["reason"], "session_open")


if __name__ == "__main__":
    unittest.main()

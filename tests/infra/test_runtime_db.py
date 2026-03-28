from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from heuristic_mt5_bridge.infra.storage.runtime_db import (
    append_fast_trade_log,
    append_operation_ownership_event,
    append_risk_event,
    decode_json_text,
    ensure_runtime_db,
    list_operation_ownership,
    list_recent_risk_events,
    load_risk_budget_state,
    load_risk_profile_state,
    purge_stale_broker_data,
    replace_position_cache,
    runtime_db_path,
    runtime_db_connection,
    upsert_fast_signal,
    upsert_operation_ownership,
    upsert_account_state_cache,
    upsert_execution_event_cache,
    upsert_market_state_cache,
    upsert_risk_budget_state,
    upsert_risk_profile_state,
    upsert_symbol_spec_cache,
)


class RuntimeDbTest(unittest.TestCase):
    def test_runtime_db_supports_core_operational_caches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_root = Path(tmp) / "storage"
            db_path = runtime_db_path(storage_root)
            ensure_runtime_db(db_path)
            upsert_market_state_cache(
                db_path,
                broker_server="Broker-1",
                account_login=123456,
                symbol="eurusd",
                timeframe="m5",
                updated_at="2026-03-23T10:00:00Z",
                state_summary={"market_phase": "impulse_up"},
                chart_context={"window_bars": 50},
                indicator_summary={"ema_20": 1.1},
                source="unit_test",
            )
            upsert_account_state_cache(
                db_path,
                {
                    "account_state_id": "acct_1",
                    "account_login": 123456,
                    "broker_server": "Broker-1",
                    "broker_company": "Example",
                    "account_mode": "demo",
                    "currency": "USD",
                    "balance": 10000.0,
                    "equity": 10025.0,
                    "margin": 50.0,
                    "free_margin": 9975.0,
                    "margin_level": 200.0,
                    "profit": 25.0,
                    "drawdown_amount": 0.0,
                    "drawdown_percent": 0.0,
                    "leverage": 100,
                    "open_position_count": 1,
                    "pending_order_count": 0,
                    "heartbeat_at": "2026-03-23T10:00:00Z",
                    "updated_at": "2026-03-23T10:00:00Z",
                    "account_flags": ["connected"],
                },
            )
            replace_position_cache(
                db_path,
                [
                    {
                        "position_id": 1,
                        "symbol": "EURUSD",
                        "side": "buy",
                        "volume": 0.1,
                        "price_open": 1.1,
                        "price_current": 1.1012,
                        "stop_loss": 1.098,
                        "take_profit": 1.105,
                        "profit": 12.0,
                        "swap": 0.0,
                        "commission": 0.0,
                        "magic": 42,
                        "comment": "test",
                        "linked_execution_id": "exec_1",
                        "opened_at": "2026-03-23T09:55:00Z",
                        "updated_at": "2026-03-23T10:00:00Z",
                        "status": "open",
                    }
                ],
            )
            upsert_execution_event_cache(
                db_path,
                {
                    "execution_event_id": "evt_1",
                    "execution_id": "exec_1",
                    "symbol": "EURUSD",
                    "event_type": "order_filled",
                    "status": "filled",
                    "mt5_order_id": 10,
                    "mt5_deal_id": 20,
                    "mt5_position_id": 1,
                    "price": 1.1,
                    "volume": 0.1,
                    "reason": "unit test",
                    "created_at": "2026-03-23T10:00:01Z",
                },
            )

            with runtime_db_connection(db_path) as conn:
                market_row = conn.execute(
                    "SELECT symbol, timeframe, state_summary_json, source FROM market_state_cache"
                ).fetchone()
                account_row = conn.execute(
                    "SELECT account_login, balance, account_flags_json FROM account_state_cache"
                ).fetchone()
                position_row = conn.execute(
                    "SELECT symbol, status, linked_execution_id FROM position_cache"
                ).fetchone()
                event_row = conn.execute(
                    "SELECT execution_id, event_type, status FROM execution_event_cache"
                ).fetchone()

            self.assertEqual(market_row[0], "EURUSD")
            self.assertEqual(market_row[1], "M5")
            self.assertEqual(decode_json_text(market_row[2], {})["market_phase"], "impulse_up")
            self.assertEqual(market_row[3], "unit_test")
            self.assertEqual(account_row[0], 123456)
            self.assertEqual(account_row[1], 10000.0)
            self.assertEqual(decode_json_text(account_row[2], [])[0], "connected")
            self.assertEqual(position_row, ("EURUSD", "open", "exec_1"))
            self.assertEqual(event_row, ("exec_1", "order_filled", "filled"))

    def test_purge_stale_broker_data_removes_other_broker_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = runtime_db_path(Path(tmp) / "storage")
            ensure_runtime_db(db_path)

            # Insert rows for two different broker identities
            for broker, login in [("Broker-A", 111), ("Broker-B", 222)]:
                upsert_market_state_cache(
                    db_path,
                    broker_server=broker,
                    account_login=login,
                    symbol="EURUSD",
                    timeframe="M5",
                    updated_at="2026-03-23T10:00:00Z",
                    state_summary={},
                    chart_context=None,
                    indicator_summary=None,
                    source="test",
                )

            # Purge keeping only Broker-A / 111
            purge_stale_broker_data(db_path, "Broker-A", 111)

            with runtime_db_connection(db_path) as conn:
                rows = conn.execute(
                    "SELECT broker_server, account_login FROM market_state_cache"
                ).fetchall()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "Broker-A")
            self.assertEqual(rows[0][1], 111)

    def test_runtime_db_path_defaults_inside_storage(self) -> None:
        storage_root = Path("E:/tmp/storage")
        self.assertEqual(runtime_db_path(storage_root), storage_root / "runtime.db")

    def test_runtime_db_supports_fast_desk_signal_and_trade_log_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = runtime_db_path(Path(tmp) / "storage")
            ensure_runtime_db(db_path)

            upsert_fast_signal(
                db_path,
                "Broker-1",
                123456,
                {
                    "signal_id": "sig_1",
                    "symbol": "EURUSD",
                    "side": "buy",
                    "trigger": "breakout",
                    "confidence": 0.8,
                    "entry_price": 1.1,
                    "stop_loss": 1.09,
                    "take_profit": 1.12,
                    "stop_loss_pips": 10.0,
                    "evidence_json": {"ema": 1.099},
                    "generated_at": "2026-03-24T10:00:00Z",
                },
            )
            append_fast_trade_log(
                db_path,
                "Broker-1",
                123456,
                {
                    "log_id": "log_1",
                    "symbol": "EURUSD",
                    "action": "open_position",
                    "position_id": 9001,
                    "signal_id": "sig_1",
                    "details_json": {"ok": True},
                    "logged_at": "2026-03-24T10:00:01Z",
                },
            )

            with runtime_db_connection(db_path) as conn:
                signal_row = conn.execute(
                    "SELECT symbol, side, evidence_json FROM fast_desk_signals WHERE signal_id='sig_1'"
                ).fetchone()
                log_row = conn.execute(
                    "SELECT symbol, action, position_id FROM fast_desk_trade_log WHERE log_id='log_1'"
                ).fetchone()

            self.assertEqual(signal_row[0], "EURUSD")
            self.assertEqual(signal_row[1], "buy")
            self.assertEqual(decode_json_text(signal_row[2], {})["ema"], 1.099)
            self.assertEqual(log_row, ("EURUSD", "open_position", 9001))

    def test_runtime_db_supports_ownership_and_risk_state_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = runtime_db_path(Path(tmp) / "storage")
            ensure_runtime_db(db_path)

            upsert_operation_ownership(
                db_path,
                {
                    "operation_uid": "Broker-1:123456:position:101",
                    "broker_server": "Broker-1",
                    "account_login": 123456,
                    "operation_type": "position",
                    "mt5_position_id": 101,
                    "mt5_order_id": None,
                    "desk_owner": "fast",
                    "ownership_status": "inherited_fast",
                    "lifecycle_status": "active",
                    "origin_type": "adopted_inherited",
                    "reevaluation_required": False,
                    "reason": "unit_test",
                    "adopted_at": "2026-03-24T10:00:00Z",
                    "reassigned_at": None,
                    "opened_at": "2026-03-24T09:59:00Z",
                    "closed_at": None,
                    "cancelled_at": None,
                    "last_seen_open_at": "2026-03-24T10:00:00Z",
                    "metadata": {"symbol": "EURUSD"},
                    "created_at": "2026-03-24T10:00:00Z",
                    "updated_at": "2026-03-24T10:00:00Z",
                },
            )
            append_operation_ownership_event(
                db_path,
                {
                    "broker_server": "Broker-1",
                    "account_login": 123456,
                    "operation_uid": "Broker-1:123456:position:101",
                    "event_type": "adopted_inherited",
                    "from_owner": None,
                    "to_owner": "fast",
                    "from_status": None,
                    "to_status": "inherited_fast",
                    "reevaluation_required": 0,
                    "reason": "unit_test",
                    "payload": {"position_id": 101},
                    "created_at": "2026-03-24T10:00:01Z",
                },
            )

            rows = list_operation_ownership(
                db_path,
                broker_server="Broker-1",
                account_login=123456,
                lifecycle_statuses=("active",),
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["ownership_status"], "inherited_fast")

            upsert_risk_profile_state(
                db_path,
                {
                    "broker_server": "Broker-1",
                    "account_login": 123456,
                    "profile_global": 2,
                    "profile_fast": 3,
                    "profile_smc": 1,
                    "overrides": {"max_positions_total": 8},
                    "fast_budget_weight": 1.2,
                    "smc_budget_weight": 0.8,
                    "kill_switch_enabled": True,
                    "updated_at": "2026-03-24T10:00:02Z",
                },
            )
            upsert_risk_budget_state(
                db_path,
                {
                    "broker_server": "Broker-1",
                    "account_login": 123456,
                    "limits": {"global": {"max_positions_total": 8}},
                    "allocator": {"share_fast": 0.6, "share_smc": 0.4},
                    "usage": {"open_positions_total": 1},
                    "kill_switch_state": {"state": "armed"},
                    "updated_at": "2026-03-24T10:00:02Z",
                },
            )
            append_risk_event(
                db_path,
                {
                    "broker_server": "Broker-1",
                    "account_login": 123456,
                    "event_type": "profile_updated",
                    "reason": "unit_test",
                    "payload": {"global": 2},
                    "created_at": "2026-03-24T10:00:03Z",
                },
            )

            profile_state = load_risk_profile_state(db_path, broker_server="Broker-1", account_login=123456)
            budget_state = load_risk_budget_state(db_path, broker_server="Broker-1", account_login=123456)
            events = list_recent_risk_events(db_path, broker_server="Broker-1", account_login=123456, limit=5)

            self.assertIsNotNone(profile_state)
            self.assertEqual(profile_state["profile_fast"], 3)
            self.assertEqual(profile_state["overrides"]["max_positions_total"], 8)
            self.assertIsNotNone(budget_state)
            self.assertEqual(budget_state["kill_switch_state"]["state"], "armed")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "profile_updated")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from typing import Any

from fastapi import HTTPException

import apps.control_plane as control_plane


class _FakeService:
    def __init__(self) -> None:
        self.reassign_calls: list[dict[str, Any]] = []
        self.profile_updates: list[dict[str, Any]] = []
        self.trip_calls: list[dict[str, Any]] = []
        self.reset_calls: list[dict[str, Any]] = []

    def ownership_all(self) -> dict[str, Any]:
        return {"items": [{"operation_uid": "a"}], "summary": {"total": 1, "open": 1, "history": 0}}

    def ownership_open(self) -> dict[str, Any]:
        return {"items": [{"operation_uid": "a"}], "summary": {"open": 1}}

    def ownership_history(self) -> dict[str, Any]:
        return {"items": [{"operation_uid": "b"}], "summary": {"history": 1}}

    def ownership_reassign(self, **kwargs: Any) -> dict[str, Any]:
        self.reassign_calls.append(kwargs)
        return {"item": {"operation_uid": "a", "desk_owner": kwargs["target_owner"]}, "summary": {"open": 1}}

    def risk_status_payload(self) -> dict[str, Any]:
        return {"status": "up", "kill_switch": {"state": "armed"}}

    def risk_limits_payload(self) -> dict[str, Any]:
        return {"global": {"max_positions_total": 5}, "desks": {"fast": {}, "smc": {}}}

    def risk_profile_payload(self) -> dict[str, Any]:
        return {"global": 2, "fast": 2, "smc": 2, "overrides": {}}

    def update_risk_profile(self, **kwargs: Any) -> dict[str, Any]:
        self.profile_updates.append(kwargs)
        return {"global": kwargs.get("profile_global", 2), "fast": kwargs.get("profile_fast", 2), "smc": kwargs.get("profile_smc", 2)}

    def trip_risk_kill_switch(self, **kwargs: Any) -> dict[str, Any]:
        self.trip_calls.append(kwargs)
        return {"state": "tripped", "reason": kwargs.get("reason")}

    def reset_risk_kill_switch(self, **kwargs: Any) -> dict[str, Any]:
        self.reset_calls.append(kwargs)
        return {"state": "armed", "reason": kwargs.get("reason")}


class ControlPlaneOwnershipRiskApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._previous_service = control_plane._service
        self.fake = _FakeService()
        control_plane._service = self.fake

    def tearDown(self) -> None:
        control_plane._service = self._previous_service

    async def test_ownership_read_endpoints(self) -> None:
        all_payload = await control_plane.ownership_all()
        open_payload = await control_plane.ownership_open()
        history_payload = await control_plane.ownership_history()

        self.assertEqual(all_payload["summary"]["total"], 1)
        self.assertEqual(open_payload["summary"]["open"], 1)
        self.assertEqual(history_payload["summary"]["history"], 1)

    async def test_ownership_reassign_endpoint(self) -> None:
        payload = control_plane.OwnershipReassignRequest(
            position_id=5001,
            target_owner="smc",
            reevaluation_required=True,
            reason="manual handoff",
        )
        response = await control_plane.ownership_reassign(payload)

        self.assertEqual(response["item"]["desk_owner"], "smc")
        self.assertEqual(len(self.fake.reassign_calls), 1)
        self.assertTrue(self.fake.reassign_calls[0]["reevaluation_required"])

    async def test_ownership_reassign_requires_ticket(self) -> None:
        payload = control_plane.OwnershipReassignRequest(
            target_owner="fast",
            reevaluation_required=False,
            reason="test",
        )
        with self.assertRaises(HTTPException) as ctx:
            await control_plane.ownership_reassign(payload)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_risk_read_and_profile_update_endpoints(self) -> None:
        status_payload = await control_plane.risk_status()
        limits_payload = await control_plane.risk_limits()
        profile_payload = await control_plane.risk_profile()

        self.assertEqual(status_payload["status"], "up")
        self.assertEqual(limits_payload["global"]["max_positions_total"], 5)
        self.assertEqual(profile_payload["global"], 2)

        updated = await control_plane.risk_profile_update(
            control_plane.RiskProfileUpdateRequest(
                profile_global=3,
                profile_fast=4,
                profile_smc=1,
                overrides={"max_positions_total": 8},
                reason="operator_update",
            )
        )
        self.assertEqual(updated["global"], 3)
        self.assertEqual(len(self.fake.profile_updates), 1)
        self.assertEqual(self.fake.profile_updates[0]["reason"], "operator_update")

    async def test_kill_switch_trip_and_reset_endpoints(self) -> None:
        tripped = await control_plane.risk_kill_switch_trip(
            control_plane.KillSwitchRequest(reason="panic", manual_override=True)
        )
        reset = await control_plane.risk_kill_switch_reset(
            control_plane.KillSwitchRequest(reason="recovered", manual_override=False)
        )

        self.assertEqual(tripped["state"], "tripped")
        self.assertEqual(reset["state"], "armed")
        self.assertEqual(len(self.fake.trip_calls), 1)
        self.assertEqual(len(self.fake.reset_calls), 1)

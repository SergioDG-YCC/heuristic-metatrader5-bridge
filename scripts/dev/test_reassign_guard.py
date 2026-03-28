"""Quick validation of the smc->fast reassign guard (R1)."""
from pathlib import Path
import tempfile

from heuristic_mt5_bridge.core.ownership.registry import OwnershipRegistry

db = Path(tempfile.mkdtemp()) / "test.db"
reg = OwnershipRegistry(
    db_path=db, broker_server="test", account_login=1, auto_adopt_foreign=True
)

# Register an SMC position
reg.register_owned_operation(
    owner="smc", operation_type="position", position_id=12345, reason="test"
)

# smc -> fast must be blocked
try:
    reg.reassign(target_owner="fast", position_id=12345, reason="test")
    print("FAIL: smc->fast was allowed!")
except ValueError as e:
    print(f"PASS: smc->fast blocked — {e}")

# Register a fast position
reg.register_owned_operation(
    owner="fast", operation_type="position", position_id=99999, reason="test"
)

# fast -> smc must succeed
try:
    row = reg.reassign(target_owner="smc", position_id=99999, reason="promotion")
    print(f"PASS: fast->smc ok — new owner={row['desk_owner']}, status={row['ownership_status']}")
except ValueError as e:
    print(f"FAIL: fast->smc blocked — {e}")

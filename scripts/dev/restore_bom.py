"""Restore BOM to files where git HEAD has BOM (confirmed from diff)."""
from pathlib import Path

REPO = Path(__file__).parent.parent.parent

files_to_restore_bom = [
    "src/heuristic_mt5_bridge/fast_desk/setup/engine.py",
    "src/heuristic_mt5_bridge/fast_desk/runtime.py",
    "src/heuristic_mt5_bridge/fast_desk/trader/service.py",
    "src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py",
]

BOM = b"\xef\xbb\xbf"

for rel in files_to_restore_bom:
    path = REPO / rel
    raw = path.read_bytes()
    if raw[:3] != BOM:
        path.write_bytes(BOM + raw)
        print(f"Restored BOM: {rel}")
    else:
        print(f"BOM already present: {rel}")

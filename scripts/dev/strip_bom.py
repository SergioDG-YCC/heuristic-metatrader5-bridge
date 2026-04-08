"""Strip BOM from files where git HEAD does not have BOM (based on manual verification)."""
from pathlib import Path

REPO = Path(__file__).parent.parent.parent

# These files have BOM in working copy but NOT in git HEAD (confirmed via git show)
files_to_strip = [
    "src/heuristic_mt5_bridge/fast_desk/setup/engine.py",
    "src/heuristic_mt5_bridge/fast_desk/runtime.py",
    "src/heuristic_mt5_bridge/fast_desk/trader/service.py",
    "src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py",
]

for rel in files_to_strip:
    path = REPO / rel
    raw = path.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        content = raw[3:].decode("utf-8")
        path.write_bytes(content.encode("utf-8"))
        print(f"Stripped BOM: {rel}")
    else:
        print(f"No BOM (skip): {rel}")

"""Fix: rewrite files that my utf-8-sig script accidentally added BOM to.
These files in git have no BOM (plain UTF-8).
"""
from pathlib import Path
import subprocess

REPO = Path(__file__).parent.parent.parent

files = [
    "src/heuristic_mt5_bridge/fast_desk/setup/engine.py",
    "src/heuristic_mt5_bridge/fast_desk/runtime.py",
    "src/heuristic_mt5_bridge/fast_desk/trader/service.py",
    "src/heuristic_mt5_bridge/fast_desk/workers/symbol_worker.py",
]

for rel in files:
    path = REPO / rel
    data_ws = path.read_bytes()[:3]
    result = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=str(REPO))
    data_git = result.stdout[:3]
    ws_bom = data_ws == b"\xef\xbb\xbf"
    git_bom = data_git == b"\xef\xbb\xbf"
    print(f"{rel}: working={'BOM' if ws_bom else 'no-BOM'}, git={'BOM' if git_bom else 'no-BOM'}")
    if ws_bom and not git_bom:
        # Remove BOM: read with utf-8-sig (strips BOM), write back as plain utf-8
        content = path.read_text(encoding="utf-8-sig")
        # Detect line ending from working copy
        raw = path.read_bytes()
        newline = "\r\n" if b"\r\n" in raw[:200] else "\n"
        path.write_text(content, encoding="utf-8", newline=newline)
        print(f"  -> Stripped BOM from {rel}")

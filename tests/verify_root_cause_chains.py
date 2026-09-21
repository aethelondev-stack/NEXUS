"""
Empirical 6-Chain Verification Suite
Tests all 6 chains under test_empty_workspace_5 without mocks.
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time

# Add ORCHESTRATOR root to sys.path
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from orchestrator.mcp_server import create_mcp_server

test_ws = pathlib.Path(r"C:\Users\Korhan\Desktop\AG Korhan\test_empty_workspace_5")
app_py = test_ws / "sample_app.py"
db_py = test_ws / "sample_db.py"

print("=" * 60)
print("ORCHESTRATOR V3: 6-CHAIN EMPIRICAL VERIFICATION MATRIX")
print("Target Workspace:", test_ws)
print("=" * 60)

results = {}

# TEST A: CLI -> BUBU (Dry Run in empty workspace)
t0 = time.time()
cmd_a = [
    "python",
    r"C:\Users\Korhan\Desktop\AG Korhan\aistudio\BUBU\.agents\skills\ai-studio-worker\scripts\ai_worker.py",
    "--type", "AUDIT",
    "--prompt", "Check sample_app.py architecture",
    "--files", "sample_app.py",
    "--dry-run"
]
res_a = subprocess.run(cmd_a, cwd=str(test_ws), capture_output=True, text=True, timeout=10)
dur_a = round(time.time() - t0, 3)
status_a = "PASS" if res_a.returncode == 0 and "dry_run_success" in res_a.stdout else "FAIL"
results["Test A (CLI -> BUBU)"] = (status_a, f"{dur_a}s")
print(f"[1/6] Test A (CLI -> BUBU): {status_a} ({dur_a}s)")
if status_a != "PASS":
    print("      Err:", res_a.stderr[:200])

# Server setup for MCP tests
server = create_mcp_server()
tool_dispatch = server._tool_manager.get_tool("orchestrator_dispatch")

# TEST B: MCP -> Orchestrator -> BUBU (Multi-file Dry Run)
t0 = time.time()
res_b = tool_dispatch.fn(
    prompt="Audit workspace architecture",
    files=[str(app_py), str(db_py)],
    task_type="AUDIT",
    dry_run=True
)
dur_b = round(time.time() - t0, 3)
ev_count_b = len(res_b.get("evidence", []))
status_b = "PASS" if res_b.get("status") == "success" and ev_count_b >= 2 else "FAIL"
results["Test B (MCP -> Orchestrator -> BUBU Dry Run)"] = (status_b, f"{dur_b}s, evidence={ev_count_b}")
print(f"[2/6] Test B (MCP -> Orchestrator -> BUBU Dry Run): {status_b} ({dur_b}s, evidence={ev_count_b})")

# TEST C: Real Cloud API BUBU Execution (gemini-3.5-flash-lite)
t0 = time.time()
res_c = tool_dispatch.fn(
    prompt="Audit sample_app.py logic and safety",
    files=[str(app_py)],
    task_type="AUDIT",
    dry_run=False
)
dur_c = round(time.time() - t0, 3)
findings_c = len(res_c.get("findings", []))
status_c = "PASS" if res_c.get("status") == "success" and findings_c > 0 else "FAIL"
results["Test C (MCP -> Orchestrator -> BUBU Real API)"] = (status_c, f"{dur_c}s, findings={findings_c}")
print(f"[3/6] Test C (MCP -> Orchestrator -> BUBU Real API): {status_c} ({dur_c}s, findings={findings_c})")
print("      Summary:", res_c.get("summary", "")[:120])

# TEST D: Direct FastMCP -> ARGUS (smart_ui_desktop_items)
t0 = time.time()
async def direct_argus():
    server_params = StdioServerParameters(command="python", args=[r"C:\Users\Korhan\.gemini\antigravity\mcp\argus\server.py"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool("smart_ui_desktop_items", {})

res_d = asyncio.run(direct_argus())
dur_d = round(time.time() - t0, 3)
content_d = json.loads(res_d.content[0].text)
items_d = content_d.get("desktop_items_count", 0)
status_d = "PASS" if items_d > 0 else "FAIL"
results["Test D (Direct FastMCP -> ARGUS)"] = (status_d, f"{dur_d}s, items={items_d}")
print(f"[4/6] Test D (Direct FastMCP -> ARGUS): {status_d} ({dur_d}s, items={items_d})")

# TEST E: MCP -> Orchestrator -> ARGUS (via FastMCP Client Transport)
t0 = time.time()
res_e = tool_dispatch.fn(
    prompt="Check desktop items with argus",
    files=[],
    action="desktop_items"
)
dur_e = round(time.time() - t0, 3)
findings_e = len(res_e.get("findings", []))
status_e = "PASS" if res_e.get("status") == "success" and findings_e > 0 else "FAIL"
results["Test E (MCP -> Orchestrator -> ARGUS Transport)"] = (status_e, f"{dur_e}s, items={findings_e}")
print(f"[5/6] Test E (MCP -> Orchestrator -> ARGUS Transport): {status_e} ({dur_e}s, items={findings_e})")

# TEST F: Orchestrator Infinite-Loop & Freeze Detector
t0 = time.time()
_ = tool_dispatch.fn(prompt="Check desktop items with argus", files=[], action="desktop_items")
_ = tool_dispatch.fn(prompt="Check desktop items with argus", files=[], action="desktop_items")
res_f = tool_dispatch.fn(prompt="Check desktop items with argus", files=[], action="desktop_items")
dur_f = round(time.time() - t0, 3)
status_f = "PASS" if res_f.get("status") == "loop_detected" else "FAIL"
results["Test F (Orchestrator Loop Detector)"] = (status_f, f"{dur_f}s")
print(f"[6/6] Test F (Orchestrator Loop Detector): {status_f} ({dur_f}s)")
print("      Breaker Message:", res_f.get("summary"))

print("=" * 60)
all_pass = all(s == "PASS" for s, _ in results.values())
print(f"OVERALL RESULT: {'100% PASS' if all_pass else 'FAILURES ENCOUNTERED'}")
print("=" * 60)

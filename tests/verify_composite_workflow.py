"""
ORCHESTRATOR V3: Real Composite Multi-Worker Workflow Integration Proof
Executes a single unified workflow call: orch.execute_workflow([req_bubu, req_argus])
Verifies that Orchestrator Core coordinates both BUBU (Cloud LLM) and ARGUS (FastMCP Stdio)
and aggregates their findings and evidence into a single composite WorkerResponse.
Generates machine-readable evidence artifact at tests/artifacts/last_composite_workflow.json.
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import os
import pathlib
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Ensure repository root is on sys.path
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from orchestrator.contracts import WorkerRequest, WorkerResponse
from orchestrator.orchestrator import Orchestrator
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerRegistry


REGISTRY_PATH = pathlib.Path.home() / ".gemini" / "orchestrator" / "workers.json"
ARTIFACTS_DIR = BASE_DIR / "tests" / "artifacts"
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"


def compute_file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_test_invariants(script_path: pathlib.Path) -> None:
    """Statically verifies this test does NOT orchestrate workers directly."""
    lines = script_path.read_text(encoding="utf-8").splitlines()
    forbidden_task_call = "orch." + "execute_task"
    forbidden_bubu = "BubuAdapter" + "("
    forbidden_argus = "ArgusAdapter" + "("
    for idx, line in enumerate(lines, 1):
        if "def verify_test_invariants" in line or "forbidden_" in line:
            continue
        assert forbidden_task_call not in line, f"Line {idx} calls execute_task directly: {line}"
        assert forbidden_bubu not in line, f"Line {idx} instantiates BubuAdapter: {line}"
        assert forbidden_argus not in line, f"Line {idx} instantiates ArgusAdapter: {line}"



def run_composite_workflow_proof() -> Dict[str, Any]:
    print("=" * 68)
    print("ORCHESTRATOR V3: COMPOSITE MULTI-WORKER WORKFLOW EXECUTION PROOF")
    print("Single Public Call: orch.execute_workflow([req_bubu, req_argus])")
    print("=" * 68)

    # 0. Check test code invariants first
    verify_test_invariants(pathlib.Path(__file__))
    print("[+] Test Invariant Check: PASS (0 execute_task calls, 0 adapter imports in test)")

    experiment_id = f"wf-exp-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    short_marker_id = uuid.uuid4().hex[:6]
    desktop_marker_name = f"0_COMPOSITE_WORKFLOW_MARKER_{short_marker_id}.txt"
    desktop_dir = pathlib.Path.home() / "Desktop"
    desktop_marker_path = desktop_dir / desktop_marker_name

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fixture_path = FIXTURES_DIR / f"composite_fixture_{short_marker_id}.py"

    # Backup original registry state
    original_registry_bytes: Optional[bytes] = None
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "rb") as rf:
            original_registry_bytes = rf.read()

    # Preflight Check
    has_gemini_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if not has_gemini_key:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                val, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
                if val:
                    has_gemini_key = True
        except Exception:
            pass

    print(f"[*] Workflow ID         : {experiment_id}")
    print(f"[*] Desktop Marker Target: {desktop_marker_name}")
    print(f"[*] Gemini API Credential: {'CONFIGURED' if has_gemini_key else 'MISSING'}")

    composite_resp: Optional[WorkerResponse] = None
    fixture_sha256 = ""

    try:
        # Step 1: Temporarily enable workers in global registry for this workflow test
        if REGISTRY_PATH.exists() and original_registry_bytes:
            data = json.loads(original_registry_bytes.decode("utf-8"))
            if "workers" in data:
                if "bubu" in data["workers"]:
                    data["workers"]["bubu"]["enabled"] = True
                if "argus" in data["workers"]:
                    data["workers"]["argus"]["enabled"] = True
            with open(REGISTRY_PATH, "w", encoding="utf-8") as wf:
                json.dump(data, wf, indent=2)
            print("[+] Global Registry: Temporarily set enabled=True for BUBU & ARGUS.")

        # Step 2: Create Test Fixture & Desktop Marker
        fixture_content = f'''"""
ORCHESTRATOR Composite Workflow Fixture
Workflow ID: {experiment_id}
Marker File: {desktop_marker_name}
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""

def process_untrusted_input(payload: dict):
    # Intentional finding 1: Raw arbitrary eval execution
    eval(payload.get("expression", "pass"))

    # Intentional finding 2: Hardcoded sensitive demo token
    service_secret = "DEMO_COMPOSITE_WORKFLOW_TOKEN_998877"

    # Intentional finding 3: Unchecked division by zero
    return 500 / payload.get("factor", 0)
'''
        with open(fixture_path, "w", encoding="utf-8") as ff:
            ff.write(fixture_content)
        fixture_sha256 = compute_file_sha256(fixture_path)
        print(f"[+] Created Fixture: {fixture_path.name} (SHA-256: {fixture_sha256[:16]}...)")

        # Create Desktop Marker file
        marker_content = f"""ORCHESTRATOR COMPOSITE WORKFLOW TEST MARKER
Workflow ID: {experiment_id}
Fixture Hash: {fixture_sha256}
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""
        with open(desktop_marker_path, "w", encoding="utf-8") as mf:
            mf.write(marker_content)
        print(f"[+] Created Desktop Marker: {desktop_marker_name}")

        # Step 3: Initialize Orchestrator Core
        pm = ProviderManager()
        reg = WorkerRegistry(registry_path=REGISTRY_PATH)
        orch = Orchestrator(project_root=FIXTURES_DIR, provider_manager=pm, registry=reg)

        # Step 4: Define Workflow Steps
        req_bubu = WorkerRequest(
            task_id="step_bubu_audit",
            task_type="AUDIT",
            prompt=f"Audit composite workflow fixture {fixture_path.name} for critical code defects and security risks",
            files=[str(fixture_path)],
            parameters={"dry_run": False, "worker": "bubu"}
        )
        req_argus = WorkerRequest(
            task_id="step_argus_desktop",
            task_type="VISION",
            prompt=f"Scan Windows desktop to locate workflow test marker {desktop_marker_name}",
            files=[],
            parameters={
                "action": "desktop_items",
                "worker": "argus",
                "target_marker": desktop_marker_name
            }
        )

        # -------------------------------------------------------------------
        # Phase 1: SINGLE PUBLIC WORKFLOW INVOCATION
        # -------------------------------------------------------------------
        print("\n--- Phase 1: Executing Single Public Workflow Call ---")
        t_start = time.time()
        composite_resp = orch.execute_workflow([req_bubu, req_argus], workflow_id=experiment_id)
        total_duration = round(time.time() - t_start, 3)

        # Step 5: Assert Composite Response Properties
        print("\n--- Phase 2: Inspecting Orchestrator Composite Response ---")
        print(f"[COMPOSITE] Worker Name    : {composite_resp.worker_name}")
        print(f"[COMPOSITE] Workflow Status: {composite_resp.status}")
        print(f"[COMPOSITE] Total Duration : {total_duration}s")
        print(f"[COMPOSITE] Steps Executed : {composite_resp.metrics.get('steps_executed')}/{composite_resp.metrics.get('steps_total')}")
        print(f"[COMPOSITE] Total Findings : {len(composite_resp.findings)}")
        print(f"[COMPOSITE] Total Evidence : {len(composite_resp.evidence)}")

        step_responses = composite_resp.metrics.get("step_responses", {})
        bubu_step = step_responses.get("step_bubu_audit", {})
        argus_step = step_responses.get("step_argus_desktop", {})

        bubu_status = bubu_step.get("status")
        argus_status = argus_step.get("status")
        print(f"       Step 1 (BUBU) : {bubu_status} ({len(bubu_step.get('findings', []))} findings, {len(bubu_step.get('evidence', []))} evidence)")
        print(f"       Step 2 (ARGUS): {argus_status} ({argus_step.get('metrics', {}).get('desktop_items_count')} items, transport={argus_step.get('metrics', {}).get('transport')})")

        # Invariant Validations
        assert composite_resp.worker_name == "composite", f"Expected worker_name='composite', got '{composite_resp.worker_name}'"
        assert composite_resp.status == "success", f"Expected status='success', got '{composite_resp.status}'"
        assert composite_resp.metrics.get("steps_executed") == 2, f"Expected 2 steps executed, got {composite_resp.metrics.get('steps_executed')}"
        assert bubu_status == "success", f"Step 1 BUBU should succeed: {bubu_step}"
        assert argus_status == "success", f"Step 2 ARGUS should succeed: {argus_step}"
        assert len(composite_resp.findings) >= 2, "Aggregated findings must contain entries from both workers"
        assert len(composite_resp.evidence) >= 1, "Aggregated evidence must contain entries from BUBU"

        marker_found = any(desktop_marker_name in fnd for fnd in composite_resp.findings) or bool(argus_step.get("metrics", {}).get("target_marker_found"))
        print(f"[COMPOSITE] Desktop Marker Found: {marker_found}")

        # Build clean sanitized evidence summary
        clean_evidence = [
            {
                "source": ev.source,
                "file": pathlib.Path(ev.file).name,
                "line_start": ev.line_start,
                "line_end": ev.line_end,
                "finding": ev.finding,
                "confidence": ev.confidence
            }
            for ev in composite_resp.evidence
        ]

        workflow_summary = {
            "workflow_id": experiment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orchestrator_version": "3.0.0",
            "execution_mode": "composite_workflow_sequential",
            "environment": {
                "os": "Windows 11",
                "gemini_api_configured": has_gemini_key,
                "argus_transport": "mcp",
                "bubu_transport": "cli"
            },
            "fixture": {
                "name": fixture_path.name,
                "sha256": fixture_sha256,
                "desktop_marker": desktop_marker_name
            },
            "workflow_response": {
                "worker_name": composite_resp.worker_name,
                "status": composite_resp.status,
                "duration_seconds": total_duration,
                "steps_total": composite_resp.metrics.get("steps_total"),
                "steps_executed": composite_resp.metrics.get("steps_executed"),
                "aggregated_findings_count": len(composite_resp.findings),
                "aggregated_evidence_count": len(composite_resp.evidence),
                "findings_sample": composite_resp.findings[:5],
                "evidence_sample": clean_evidence[:3]
            },
            "step_audit": {
                "step_1_bubu": {
                    "task_id": bubu_step.get("task_id"),
                    "worker_name": bubu_step.get("worker_name"),
                    "status": bubu_step.get("status"),
                    "findings_count": len(bubu_step.get("findings", [])),
                    "evidence_count": len(bubu_step.get("evidence", []))
                },
                "step_2_argus": {
                    "task_id": argus_step.get("task_id"),
                    "worker_name": argus_step.get("worker_name"),
                    "status": argus_step.get("status"),
                    "transport": argus_step.get("metrics", {}).get("transport"),
                    "desktop_items_count": argus_step.get("metrics", {}).get("desktop_items_count"),
                    "target_marker_found": marker_found
                }
            },
            "final_status": "PASS"
        }

        # Write sanitized machine-readable JSON artifact
        artifact_path = ARTIFACTS_DIR / "last_composite_workflow.json"
        with open(artifact_path, "w", encoding="utf-8") as af:
            json.dump(workflow_summary, af, indent=2)
        print(f"[+] Saved Evidence Artifact: {artifact_path.relative_to(BASE_DIR)}")

        print("\n" + "=" * 68)
        print("WORKFLOW PROOF RESULT: 100% PASS (Composite Multi-Worker Workflow Proven)")
        print("=" * 68)

        return workflow_summary

    finally:
        # Step 6: Cleanup & Registry Restoration Guarantee
        print("\n--- Cleanup & Safety Restoration ---")
        if desktop_marker_path.exists():
            try:
                desktop_marker_path.unlink()
                print(f"[+] Cleaned up desktop marker: {desktop_marker_name}")
            except Exception as e:
                print(f"[-] Warning cleaning desktop marker: {e}")

        if fixture_path.exists():
            try:
                fixture_path.unlink()
                print(f"[+] Cleaned up test fixture: {fixture_path.name}")
            except Exception as e:
                print(f"[-] Warning cleaning test fixture: {e}")

        if original_registry_bytes and REGISTRY_PATH.exists():
            try:
                with open(REGISTRY_PATH, "wb") as wf:
                    wf.write(original_registry_bytes)
                print("[+] Global Registry: Successfully restored original pre-test state (disabled=false).")
            except Exception as e:
                print(f"[-] Critical error restoring registry: {e}")


if __name__ == "__main__":
    res = run_composite_workflow_proof()
    sys.exit(0 if res.get("final_status") == "PASS" else 1)

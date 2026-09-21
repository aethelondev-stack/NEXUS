"""
ORCHESTRATOR V3: Real Two-Worker End-to-End Integration Experiment
Coordinates real BUBU (Gemini Cloud API) and real ARGUS (FastMCP on-device vision/desktop discovery)
under a single unified experiment without mocks, stubs, or fake adapters.
Generates machine-readable evidence artifact at tests/artifacts/last_two_worker_integration.json.
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


def run_two_worker_integration() -> Dict[str, Any]:
    print("=" * 65)
    print("ORCHESTRATOR V3: REAL TWO-WORKER INTEGRATION EXPERIMENT")
    print("Coordinates real BUBU (Cloud LLM) + real ARGUS (Local FastMCP)")
    print("=" * 65)

    experiment_id = f"exp-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    short_marker_id = uuid.uuid4().hex[:6]
    desktop_marker_name = f"0_ORCHESTRATOR_INTEGRATION_MARKER_{short_marker_id}.txt"
    desktop_dir = pathlib.Path.home() / "Desktop"
    desktop_marker_path = desktop_dir / desktop_marker_name

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fixture_path = FIXTURES_DIR / f"integration_payload_{short_marker_id}.py"

    # Backup original registry state
    original_registry_bytes: Optional[bytes] = None
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "rb") as rf:
            original_registry_bytes = rf.read()

    # Step 0: Environment Preflight Check
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

    print(f"[*] Experiment ID        : {experiment_id}")
    print(f"[*] Desktop Marker Target: {desktop_marker_name}")
    print(f"[*] Gemini API Credential: {'CONFIGURED' if has_gemini_key else 'MISSING'}")

    bubu_resp: Optional[WorkerResponse] = None
    argus_resp: Optional[WorkerResponse] = None
    fixture_sha256 = ""
    marker_found_on_desktop = False

    try:
        # Step 1: Temporarily enable workers in global registry for this experiment
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
ORCHESTRATOR Integration Test Fixture
Experiment ID: {experiment_id}
Marker File: {desktop_marker_name}
Timestamp: {datetime.now(timezone.utc).isoformat()}
"""

def execute_untrusted_command(user_payload: dict):
    # Deliberate finding 1: Raw arbitrary eval execution
    eval(user_payload.get("code", "pass"))

    # Deliberate finding 2: Hardcoded sensitive demo token
    service_secret = "DEMO_HARDCODED_INTEGRATION_KEY_98765"

    # Deliberate finding 3: Unchecked division by zero
    return 100 / user_payload.get("divisor", 0)
'''
        with open(fixture_path, "w", encoding="utf-8") as ff:
            ff.write(fixture_content)
        fixture_sha256 = compute_file_sha256(fixture_path)
        print(f"[+] Created Fixture: {fixture_path.name} (SHA-256: {fixture_sha256[:16]}...)")

        # Create Desktop Marker file
        marker_content = f"""ORCHESTRATOR INTEGRATION TEST MARKER
Experiment: {experiment_id}
Fixture Hash: {fixture_sha256}
Timestamp: {datetime.now(timezone.utc).isoformat()}
Status: VERIFICATION_PENDING
"""
        with open(desktop_marker_path, "w", encoding="utf-8") as mf:
            mf.write(marker_content)
        print(f"[+] Created Desktop Marker: {desktop_marker_name}")

        # Step 3: Initialize Orchestrator Core
        pm = ProviderManager()
        reg = WorkerRegistry(registry_path=REGISTRY_PATH)
        orch = Orchestrator(project_root=FIXTURES_DIR, provider_manager=pm, registry=reg)

        # -------------------------------------------------------------------
        # Phase 1: Real BUBU Cloud Execution
        # -------------------------------------------------------------------
        print("\n--- Phase 1: BUBU Real Cloud API Execution ---")
        t_bubu_start = time.time()
        req_bubu = WorkerRequest(
            task_id=f"bubu-{experiment_id}",
            task_type="AUDIT",
            prompt=f"Audit integration fixture {fixture_path.name} for critical security vulnerabilities and code defects",
            files=[str(fixture_path)],
            parameters={"dry_run": False, "worker": "bubu"}
        )
        bubu_resp = orch.execute_task(req_bubu)
        bubu_dur = round(time.time() - t_bubu_start, 3)

        bubu_pass = (
            bubu_resp.status == "success"
            and len(bubu_resp.findings) > 0
            and len(bubu_resp.evidence) > 0
        )
        print(f"[BUBU] Status   : {bubu_resp.status} ({bubu_dur}s)")
        print(f"[BUBU] Findings : {len(bubu_resp.findings)}")
        print(f"[BUBU] Evidence : {len(bubu_resp.evidence)} items")
        for idx, fnd in enumerate(bubu_resp.findings[:3], 1):
            print(f"       ({idx}) {fnd[:90]}...")

        # -------------------------------------------------------------------
        # Phase 2: Real ARGUS Desktop Discovery Execution via MCP
        # -------------------------------------------------------------------
        print("\n--- Phase 2: ARGUS Real FastMCP Desktop Discovery ---")
        t_argus_start = time.time()
        req_argus = WorkerRequest(
            task_id=f"argus-{experiment_id}",
            task_type="VISION",
            prompt=f"Scan Windows desktop to discover integration marker {desktop_marker_name}",
            files=[],
            parameters={
                "action": "desktop_items",
                "worker": "argus",
                "target_marker": desktop_marker_name
            }
        )
        argus_resp = orch.execute_task(req_argus)
        argus_dur = round(time.time() - t_argus_start, 3)

        marker_found_on_desktop = (
            bool(argus_resp.metrics.get("target_marker_found"))
            or any(desktop_marker_name in fnd for fnd in argus_resp.findings)
        )
        argus_pass = (
            argus_resp.status == "success"
            and argus_resp.metrics.get("transport") == "mcp"
            and marker_found_on_desktop
        )
        print(f"[ARGUS] Status       : {argus_resp.status} ({argus_dur}s)")
        print(f"[ARGUS] Transport    : {argus_resp.metrics.get('transport')}")
        print(f"[ARGUS] Desktop Items: {argus_resp.metrics.get('desktop_items_count')}")
        print(f"[ARGUS] Marker Found : {marker_found_on_desktop} ({desktop_marker_name})")

        # -------------------------------------------------------------------
        # Phase 3: Combined Evidence Verification & Cross-Correlation
        # -------------------------------------------------------------------
        print("\n--- Phase 3: Combined Evidence Cross-Correlation ---")
        overall_pass = bubu_pass and argus_pass and marker_found_on_desktop

        # Build clean sanitized evidence summary
        clean_bubu_evidence = [
            {
                "file": pathlib.Path(ev.file).name,
                "line_start": ev.line_start,
                "line_end": ev.line_end,
                "finding": ev.finding,
                "confidence": ev.confidence
            }
            for ev in bubu_resp.evidence
        ]

        clean_argus_findings = [
            f for f in argus_resp.findings if desktop_marker_name in f
        ]
        if not clean_argus_findings and argus_resp.findings:
            clean_argus_findings = argus_resp.findings[:3]

        experiment_summary = {
            "experiment_id": experiment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "orchestrator_version": "3.0.0",
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
            "bubu_execution": {
                "task_id": bubu_resp.task_id,
                "worker_name": bubu_resp.worker_name,
                "status": bubu_resp.status,
                "duration_seconds": bubu_dur,
                "findings_count": len(bubu_resp.findings),
                "evidence_count": len(bubu_resp.evidence),
                "findings_sample": bubu_resp.findings[:3],
                "evidence_sample": clean_bubu_evidence[:3]
            },
            "argus_execution": {
                "task_id": argus_resp.task_id,
                "worker_name": argus_resp.worker_name,
                "status": argus_resp.status,
                "duration_seconds": argus_dur,
                "transport": argus_resp.metrics.get("transport"),
                "desktop_items_count": argus_resp.metrics.get("desktop_items_count"),
                "target_marker": desktop_marker_name,
                "target_marker_found": marker_found_on_desktop,
                "findings": clean_argus_findings
            },
            "cross_correlation": {
                "shared_experiment_id": experiment_id,
                "bubu_analyzed_fixture_sha256": fixture_sha256,
                "argus_discovered_desktop_marker": desktop_marker_name,
                "correlation_verified": marker_found_on_desktop and bubu_pass
            },
            "final_status": "PASS" if overall_pass else "FAIL"
        }

        # Write sanitized machine-readable JSON artifact
        artifact_path = ARTIFACTS_DIR / "last_two_worker_integration.json"
        with open(artifact_path, "w", encoding="utf-8") as af:
            json.dump(experiment_summary, af, indent=2)
        print(f"[+] Saved Evidence Artifact: {artifact_path.relative_to(BASE_DIR)}")

        print("\n" + "=" * 65)
        print(f"EXPERIMENT RESULT: {'100% PASS (Both workers executed and cross-correlated)' if overall_pass else 'FAILED'}")
        print("=" * 65)

        return experiment_summary

    finally:
        # Step 4: Cleanup & Registry Restoration Guarantee
        print("\n--- Cleanup & Safety Restoration ---")
        # 1. Delete temporary desktop marker
        if desktop_marker_path.exists():
            try:
                desktop_marker_path.unlink()
                print(f"[+] Cleaned up desktop marker: {desktop_marker_name}")
            except Exception as e:
                print(f"[-] Warning cleaning desktop marker: {e}")

        # 2. Delete temporary fixture file
        if fixture_path.exists():
            try:
                fixture_path.unlink()
                print(f"[+] Cleaned up test fixture: {fixture_path.name}")
            except Exception as e:
                print(f"[-] Warning cleaning test fixture: {e}")

        # 3. Restore original registry bytes
        if original_registry_bytes and REGISTRY_PATH.exists():
            try:
                with open(REGISTRY_PATH, "wb") as wf:
                    wf.write(original_registry_bytes)
                print("[+] Global Registry: Successfully restored original pre-test state (disabled=false).")
            except Exception as e:
                print(f"[-] Critical error restoring registry: {e}")


if __name__ == "__main__":
    result = run_two_worker_integration()
    sys.exit(0 if result.get("final_status") == "PASS" else 1)

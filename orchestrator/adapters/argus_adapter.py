"""
ORCHESTRATOR V3: ARGUS Vision Shield Adapter
Dispatches vision and UI automation tasks to ARGUS (server.py / argus.py).
Enforces perceptual circuit breaker, privacy redaction, and local GPU budget.
Standard-library only.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.adapters.base import BaseWorkerAdapter
from orchestrator.contracts import Evidence, WorkerError, WorkerRequest, WorkerResponse
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerDefinition


class ArgusAdapter(BaseWorkerAdapter):
    def is_available(self) -> Tuple[bool, str]:
        if not self.definition.enabled:
            return False, "ARGUS worker is disabled in registry."

        # Check either server_path or script path
        server_p = pathlib.Path(self.definition.server_path or "")
        if server_p.exists():
            return True, "ARGUS FastMCP server is available."

        ep = pathlib.Path(self.definition.entrypoint)
        if ep.exists():
            return True, "ARGUS entrypoint is available."

        return False, f"ARGUS server/entrypoint not found at: {server_p} or {ep}"

    def invoke(self, request: WorkerRequest) -> WorkerResponse:
        start_time = time.time()
        task_id = request.task_id

        # 1. Availability check
        available, reason = self.is_available()
        if not available:
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="not_available",
                summary=f"Worker {self.definition.worker_id} unavailable: {reason}",
                error=WorkerError(error_code="WORKER_NOT_AVAILABLE", message=reason, retryable=False),
                metrics={"duration_seconds": round(time.time() - start_time, 4)}
            )

        # 2. Determine action (desktop-items, scan, or status)
        action = request.parameters.get("action", "desktop_items")
        python_exe = sys.executable or self.definition.python_executable or "python"

        # If we have the server.py path, we can run a short python runner that calls the function
        # or use argus.py if available
        server_path = self.definition.server_path
        cmd: List[str] = []

        if action == "desktop_items":
            # Invoke desktop items via short python script using the engine or server
            py_code = (
                f"import sys; sys.path.insert(0, r'{os.path.dirname(server_path)}'); "
                "from engine import UIEngine; "
                "e = UIEngine(); items = e.get_desktop_items(); "
                "import json; print(json.dumps({'status': 'success', 'items_count': len(items), 'items': items[:25]}))"
            )
            cmd = [python_exe, "-c", py_code]
        elif action == "status":
            py_code = (
                f"import sys; sys.path.insert(0, r'{os.path.dirname(server_path)}'); "
                "from engine import UIEngine; "
                "e = UIEngine(); "
                "import json; print(json.dumps({'status': 'active', 'cuda': e.has_cuda, 'breaker_tripped': e.breaker.is_tripped}))"
            )
            cmd = [python_exe, "-c", py_code]
        else:
            # Default scan or decide
            py_code = (
                f"import sys; sys.path.insert(0, r'{os.path.dirname(server_path)}'); "
                "from engine import UIEngine; "
                "e = UIEngine(); "
                "can_proceed, msg = e.breaker.check_and_update(None, 'sim_scan'); "
                "import json; print(json.dumps({'status': 'success' if can_proceed else 'tripped', 'message': msg}))"
            )
            cmd = [python_exe, "-c", py_code]

        # 3. Execute subprocess
        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.definition.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="timeout",
                summary=f"Worker {self.definition.worker_id} timed out after {self.definition.timeout_seconds}s.",
                error=WorkerError(error_code="WORKER_TIMEOUT", message="Execution timeout exceeded", retryable=True),
                metrics={"duration_seconds": round(time.time() - start_time, 4)}
            )
        except Exception as e:
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="failed",
                summary=f"ARGUS execution failed: {e}",
                error=WorkerError(error_code="EXECUTION_FAILED", message=str(e), retryable=False),
                metrics={"duration_seconds": round(time.time() - start_time, 4)}
            )

        duration = round(time.time() - start_time, 4)
        raw_output = result.stdout.strip()

        # Parse JSON
        parsed_json: Optional[Dict[str, Any]] = None
        try:
            json_start = raw_output.find("{")
            json_end = raw_output.rfind("}")
            if json_start != -1 and json_end != -1:
                parsed_json = json.loads(raw_output[json_start : json_end + 1])
        except Exception:
            parsed_json = None

        if result.returncode != 0:
            err_msg = result.stderr.strip() or raw_output or f"Exited with code {result.returncode}"
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="failed",
                summary=f"ARGUS worker failed: {err_msg[:200]}",
                error=WorkerError(error_code="WORKER_ERROR", message=err_msg, retryable=False),
                metrics={"duration_seconds": duration}
            )

        if parsed_json and parsed_json.get("status") == "tripped":
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="blocked",
                summary=f"ARGUS Circuit Breaker tripped: {parsed_json.get('message')}",
                error=WorkerError(error_code="CIRCUIT_BREAKER_TRIPPED", message=parsed_json.get("message", ""), retryable=False),
                metrics={"duration_seconds": duration}
            )

        findings: List[str] = []
        if parsed_json and "items" in parsed_json:
            findings = [f"Desktop Item: {item}" for item in parsed_json["items"][:10]]
        else:
            findings = [raw_output[:200]]

        return WorkerResponse(
            task_id=task_id,
            worker_name=self.definition.worker_id,
            status="success",
            summary=f"ARGUS executed action '{action}' successfully (Zero Cloud Token Cost).",
            findings=findings,
            metrics={"duration_seconds": duration, "action": action, "token_cost": 0}
        )

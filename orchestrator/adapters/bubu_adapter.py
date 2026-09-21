"""
ORCHESTRATOR V3: BUBU Context Worker Adapter
Dispatches context tasks to the real BUBU worker (ai_worker.py) via subprocess CLI.
Respects ProviderManager quota, failure semantics, and evidence contracts.
Standard-library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.adapters.base import BaseWorkerAdapter
from orchestrator.contracts import Evidence, WorkerError, WorkerRequest, WorkerResponse
from orchestrator.provider_manager import HybridModeLevel, ProviderManager, ProviderState
from orchestrator.worker_registry import WorkerDefinition


class BubuAdapter(BaseWorkerAdapter):
    def is_available(self) -> Tuple[bool, str]:
        if not self.definition.enabled:
            return False, "BUBU worker is disabled in registry."

        ep = pathlib.Path(self.definition.entrypoint)
        if not ep.exists():
            return False, f"BUBU entrypoint not found at: {ep}"

        return True, "BUBU worker is available."

    def invoke(self, request: WorkerRequest) -> WorkerResponse:
        start_time = time.time()
        task_id = request.task_id

        # 1. Physical availability check
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

        # 2. Quota preflight check via ProviderManager
        is_dry_run = request.parameters.get("dry_run", False) or request.parameters.get("decide", False)
        if not is_dry_run:
            allowed, p_state, p_reason, h_level = self.provider_manager.preflight_check("gemini")
            if not allowed:
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=self.definition.worker_id,
                    status="quota_exhausted" if p_state == ProviderState.QUOTA_EXHAUSTED else "blocked",
                    summary=f"Execution blocked by ProviderManager: {p_reason}",
                    error=WorkerError(
                        error_code=f"PROVIDER_{p_state.value}",
                        message=p_reason,
                        retryable=(p_state == ProviderState.RATE_LIMITED),
                        details={"hybrid_level": h_level.value, "provider_state": p_state.value}
                    ),
                    metrics={"duration_seconds": round(time.time() - start_time, 4)}
                )

        # 3. Assemble subprocess command
        python_exe = self.definition.python_executable or "python"
        cmd = [python_exe, str(self.definition.entrypoint)]

        # Map task type
        task_type_arg = "ANALYZE"
        if request.task_type in ("DEBUG", "RESEARCH", "COMPARE", "DOCUMENT", "VALIDATE", "SUMMARIZE", "ANALYZE", "AUDIT"):
            task_type_arg = request.task_type
        cmd.extend(["--type", task_type_arg])

        if request.prompt:
            cmd.extend(["--prompt", request.prompt])

        if request.files:
            cmd.append("--files")
            cmd.extend([str(f) for f in request.files])

        if is_dry_run:
            if request.parameters.get("decide"):
                cmd.append("--decide")
            else:
                cmd.append("--dry-run")

        # 4. Execute subprocess
        try:
            cwd = str(self.project_root) if self.project_root.exists() else None
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
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
                summary=f"Worker subprocess execution failed: {e}",
                error=WorkerError(error_code="EXECUTION_FAILED", message=str(e), retryable=False),
                metrics={"duration_seconds": round(time.time() - start_time, 4)}
            )

        duration = round(time.time() - start_time, 4)
        raw_output = result.stdout.strip()
        raw_err = result.stderr.strip()

        # 5. Parse JSON output if present
        parsed_json: Optional[Dict[str, Any]] = None
        try:
            # Look for JSON block in output
            json_start = raw_output.find("{")
            json_end = raw_output.rfind("}")
            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_str = raw_output[json_start : json_end + 1]
                parsed_json = json.loads(json_str)
        except Exception:
            parsed_json = None

        # Check return code
        if result.returncode != 0:
            err_msg = raw_err or raw_output or f"Exited with code {result.returncode}"
            # Check for 429
            if "429" in err_msg or "quota" in err_msg.lower():
                self.provider_manager.record_failure("gemini", 429, err_msg)
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=self.definition.worker_id,
                    status="quota_exhausted",
                    summary="BUBU encountered 429 Quota Exhaustion from Gemini API.",
                    error=WorkerError(error_code="PROVIDER_429", message=err_msg, retryable=False),
                    metrics={"duration_seconds": duration}
                )

            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="failed",
                summary=f"BUBU worker failed: {err_msg[:200]}",
                error=WorkerError(error_code="WORKER_ERROR", message=err_msg, retryable=False),
                metrics={"duration_seconds": duration}
            )

        # 6. Extract evidence and findings
        evidence_list: List[Evidence] = []
        findings: List[str] = []

        if parsed_json:
            # Handle decide
            if parsed_json.get("decision") == "SKIP":
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=self.definition.worker_id,
                    status="routed_only",
                    summary=f"BUBU Auto-Mode recommended SKIP: {parsed_json.get('reason', '')}",
                    findings=[f"Reason: {parsed_json.get('reason', '')}"],
                    metrics={"duration_seconds": duration, "decision": "SKIP"}
                )

            for item in parsed_json.get("evidence", []):
                evidence_list.append(Evidence(
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start", 1),
                    line_end=item.get("line_end", 1),
                    content_hash=item.get("content_hash", ""),
                    verified=item.get("verified", True)
                ))
            findings = parsed_json.get("findings", [raw_output[:300]])
        else:
            findings = [line for line in raw_output.splitlines() if line.strip()][:5]

        # Ingest line evidence if files were inspected
        for f_path_str in request.files:
            p = pathlib.Path(f_path_str)
            if not p.is_absolute():
                p = self.project_root / p
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    c_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    evidence_list.append(Evidence(
                        file_path=str(p),
                        line_start=1,
                        line_end=len(content.splitlines()) or 1,
                        content_hash=c_hash,
                        verified=True
                    ))
                except Exception:
                    pass

        # Record success in provider manager
        if not is_dry_run:
            self.provider_manager.record_success("gemini", estimated_in=len(request.prompt), estimated_out=len(raw_output))

        return WorkerResponse(
            task_id=task_id,
            worker_name=self.definition.worker_id,
            status="success",
            summary=f"BUBU successfully executed {task_type_arg} on {len(request.files)} file(s).",
            findings=findings,
            evidence=evidence_list,
            metrics={"duration_seconds": duration, "files_analyzed": len(request.files), "dry_run": is_dry_run}
        )

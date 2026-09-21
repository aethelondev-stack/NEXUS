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
import sys
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

    def _get_execution_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if not env.get("GEMINI_API_KEY") and not env.get("GOOGLE_API_KEY"):
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    val, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
                    if val:
                        env["GEMINI_API_KEY"] = str(val)
            except Exception:
                pass
        return env

    def _resolve_target_dir_and_files(self, requested_files: List[str]) -> Tuple[pathlib.Path, List[str]]:
        target_dir = self.project_root.resolve() if (self.project_root and self.project_root.exists()) else pathlib.Path.cwd().resolve()
        rel_files: List[str] = []

        if requested_files:
            first_p = pathlib.Path(requested_files[0]).resolve()
            parent_dir = first_p.parent if first_p.is_file() else first_p
            try:
                first_p.relative_to(target_dir)
            except ValueError:
                target_dir = parent_dir

            for f_str in requested_files:
                p = pathlib.Path(f_str).resolve()
                try:
                    rel_p = p.relative_to(target_dir)
                    rel_files.append(str(rel_p))
                except ValueError:
                    rel_files.append(p.name)

        ai_worker_dir = target_dir / ".ai-worker"
        if not ai_worker_dir.exists():
            try:
                ai_worker_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        return target_dir, rel_files

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

        # 3. Resolve target directory, files, and project root anchor
        target_dir, rel_files = self._resolve_target_dir_and_files(request.files)

        # 4. Assemble subprocess command
        python_exe = sys.executable or self.definition.python_executable or "python"
        cmd = [python_exe, str(self.definition.entrypoint)]

        # Map task type
        task_type_arg = "ANALYZE"
        if request.task_type in ("DEBUG", "RESEARCH", "COMPARE", "DOCUMENT", "VALIDATE", "SUMMARIZE", "ANALYZE", "AUDIT"):
            task_type_arg = request.task_type
        cmd.extend(["--type", task_type_arg])

        if request.prompt:
            cmd.extend(["--prompt", request.prompt])

        if rel_files:
            cmd.append("--files")
            cmd.extend(rel_files)

        if is_dry_run:
            if request.parameters.get("decide"):
                cmd.append("--decide")
            else:
                cmd.append("--dry-run")
        else:
            # Override to active low-latency model to avoid 503/timeout on default gemini-3.6-flash
            active_model = request.parameters.get("model") or "gemini-3.5-flash-lite"
            cmd.extend(["--model", active_model])

        # 5. Execute subprocess
        env = self._get_execution_env()
        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                cwd=str(target_dir),
                env=env,
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
                    source="bubu",
                    file=item.get("file") or item.get("file_path", ""),
                    line_start=int(item.get("line") or item.get("line_start", 1)),
                    line_end=int(item.get("line_end", item.get("line", 1))),
                    content_hash=item.get("content_hash", ""),
                    commit_hash=item.get("commit_hash", "UNKNOWN"),
                    finding=item.get("note") or item.get("finding", ""),
                    confidence=float(item.get("confidence", 1.0))
                ))
            findings = parsed_json.get("findings", [raw_output[:300]])
        else:
            findings = [line for line in raw_output.splitlines() if line.strip()][:5]

        # Ingest line evidence if files were inspected
        for f_path_str in request.files:
            p = pathlib.Path(f_path_str)
            if not p.is_absolute():
                p = target_dir / p
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    c_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    evidence_list.append(Evidence(
                        source="bubu",
                        file=str(p),
                        line_start=1,
                        line_end=len(content.splitlines()) or 1,
                        content_hash=c_hash,
                        commit_hash="LOCAL",
                        finding=f"Inspected file {p.name}",
                        confidence=1.0
                    ))
                except Exception:
                    pass

        # Record success in provider manager
        if not is_dry_run:
            self.provider_manager.record_success("gemini", estimated_in_tokens=len(request.prompt), estimated_out_tokens=len(raw_output))

        return WorkerResponse(
            task_id=task_id,
            worker_name=self.definition.worker_id,
            status="success",
            summary=f"BUBU successfully executed {task_type_arg} on {len(request.files)} file(s).",
            findings=findings,
            evidence=evidence_list,
            metrics={"duration_seconds": duration, "files_analyzed": len(request.files), "dry_run": is_dry_run}
        )

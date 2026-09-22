"""
ORCHESTRATOR V3: Production-Grade Master Orchestrator
Phase 5: Direct Path First routing, task classification, finite state machine,
infinite-loop prevention, provider quota supervision, and verified evidence merging.
Standard-library only.
"""
from __future__ import annotations

import collections
import enum
import hashlib
import json
import os
import pathlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from orchestrator.contracts import (
    Evidence,
    WorkerError,
    WorkerRequest,
    WorkerResponse,
    SCHEMA_VERSION
)
from orchestrator.evidence_store import EvidenceStore
from orchestrator.provider_manager import HybridModeLevel, ProviderManager, ProviderState
from orchestrator.worker_registry import WorkerRegistry, WorkerDefinition
from orchestrator.adapters.bubu_adapter import BubuAdapter
from orchestrator.adapters.argus_adapter import ArgusAdapter
from orchestrator.session_state import SessionStateManager


class TaskClassification(enum.Enum):
    DIRECT = "DIRECT"
    CONTEXT_ANALYSIS = "CONTEXT_ANALYSIS"
    VISION = "VISION"
    COMBINED = "COMBINED"
    COMPLEX = "COMPLEX"
    UNKNOWN = "UNKNOWN"


class OrchestratorState(enum.Enum):
    CREATED = "CREATED"
    CLASSIFIED = "CLASSIFIED"
    PREFLIGHT = "PREFLIGHT"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    LOOP_DETECTED = "LOOP_DETECTED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class Orchestrator:
    def __init__(
        self,
        project_root: Optional[pathlib.Path] = None,
        provider_manager: Optional[ProviderManager] = None,
        registry: Optional[WorkerRegistry] = None,
        session_state: Optional[SessionStateManager] = None,
        max_retries: int = 3,
        max_replans: int = 2,
        max_wall_time_seconds: float = 60.0,
        loop_window_size: int = 6
    ):
        self.project_root = pathlib.Path(project_root or ".").resolve()
        self.provider_manager = provider_manager or ProviderManager()
        self.evidence_store = EvidenceStore(project_root=self.project_root)
        self.registry = registry or WorkerRegistry()
        self.session_state = session_state or SessionStateManager()
        self.max_retries = max_retries
        self.max_replans = max_replans
        self.max_wall_time_seconds = max_wall_time_seconds
        self.loop_window_size = loop_window_size

        # Execution ring-buffer for cyclic loop detection (A -> B -> A -> B etc.)
        self._action_history: collections.deque[str] = collections.deque(maxlen=self.loop_window_size)
        self._fingerprint_counts: Dict[str, int] = {}
        self._registered_workers: Dict[str, Callable[[WorkerRequest], WorkerResponse]] = {}

        # Auto-wire known adapters from global registry
        self._init_default_adapters()

    def _init_default_adapters(self) -> None:
        bubu_def = self.registry.get_worker("bubu")
        if bubu_def:
            bubu_adapter = BubuAdapter(bubu_def, self.project_root, self.provider_manager)
            self.register_worker("bubu", bubu_adapter.invoke)
            self.register_worker("ai-studio-worker", bubu_adapter.invoke)

        argus_def = self.registry.get_worker("argus")
        if argus_def:
            argus_adapter = ArgusAdapter(argus_def, self.project_root, self.provider_manager)
            self.register_worker("argus", argus_adapter.invoke)

    def register_worker(self, name: str, handler: Callable[[WorkerRequest], WorkerResponse]):
        self._registered_workers[name] = handler

    # -----------------------------------------------------------------------
    # Task Classifier (Deterministic - Rule 2: No Fake Intelligence)
    # -----------------------------------------------------------------------
    def classify_task(self, prompt: str, files: List[str], parameters: Optional[Dict[str, Any]] = None) -> TaskClassification:
        p_lower = prompt.lower()
        files = files or []
        params = parameters or {}

        # 1. Vision signals (Screen, Desktop, UI, BlueStacks, ADB)
        has_vision = (
            any(k in p_lower for k in ["screen", "ekran", "görsel", "screenshot", "ui", "desktop", "masaüstü", "bluestacks", "adb", "ocr"])
            or params.get("requires_vision")
            or params.get("action") in ("desktop_items", "scan", "click")
        )

        # 2. Context Analysis signals (Large multi-file, architecture, audit, memory leak, root cause)
        has_heavy_context = (
            len(files) >= 3
            or any(k in p_lower for k in ["architecture", "dependency", "audit", "memory leak", "race condition", "compare", "root cause", "refactor all"])
            or params.get("requires_bubu")
        )

        # Combined check
        if has_vision and has_heavy_context:
            return TaskClassification.COMBINED
        if has_vision:
            return TaskClassification.VISION
        if has_heavy_context:
            return TaskClassification.CONTEXT_ANALYSIS

        # 3. Direct Path Check: Single file or micro-edits without heavy keywords -> DIRECT
        if len(files) <= 1 and not has_heavy_context and not has_vision:
            return TaskClassification.DIRECT

        return TaskClassification.CONTEXT_ANALYSIS

    # -----------------------------------------------------------------------
    # Infinite-Loop & Ping-Pong Cycle Detector (Phase 4.5.25 & 3.4)
    # -----------------------------------------------------------------------
    def check_loop(self, action_signature: str) -> Tuple[bool, str]:
        """
        Detects immediate repeats (A -> A), alternating cycles (A -> B -> A -> B),
        and tertiary loops (A -> B -> C -> A -> B -> C).
        """
        self._action_history.append(action_signature)
        history = list(self._action_history)

        # Check immediate repeat (A -> A -> A)
        if len(history) >= 3 and history[-1] == history[-2] == history[-3]:
            return True, f"Immediate repetitive loop detected on action '{action_signature}'."

        # Check ping-pong cycle (A -> B -> A -> B)
        if len(history) >= 4:
            if history[-4] == history[-2] and history[-3] == history[-1] and history[-1] != history[-2]:
                return True, f"Ping-pong cycle detected between '{history[-2]}' and '{history[-1]}'."

        # Check 3-state cycle (A -> B -> C -> A -> B -> C)
        if len(history) >= 6:
            if history[-6:-3] == history[-3:]:
                return True, f"Triangular loop detected across actions: {history[-3:]}."

        return False, "No loop detected."

    def reset_history(self) -> None:
        """Resets action loop history and fingerprints between independent tasks."""
        self._action_history.clear()
        self._fingerprint_counts.clear()

    def is_worker_enabled(self, worker_name: str, target_dir: Optional[pathlib.Path] = None) -> bool:
        """
        Determines whether a worker is enabled.
        Authoritative source: Global Worker Registry (workers.json).
        Workspace policy: Checks project-level config if present in project_root or target_dir.
        """
        norm_id = "bubu" if worker_name in ("bubu", "ai-studio-worker") else worker_name

        # 0. Session-level preference check (Current chat / session override)
        if getattr(self, "session_state", None):
            session_enabled = self.session_state.is_worker_enabled(norm_id)
            if session_enabled is False:
                return False

        # 1. Authoritative global registry check
        if not self.registry.is_worker_enabled(norm_id):
            return False

        # 2. Local workspace configuration override
        root = target_dir or self.project_root
        if norm_id == "bubu":
            bubu_cfg = root / ".ai-worker" / "config.json"
            if bubu_cfg.is_file():
                try:
                    with open(bubu_cfg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("worker_mode") == "disabled" or data.get("mode") == "disabled":
                        return False
                except Exception:
                    pass
        elif norm_id == "argus":
            argus_cfg = root / ".argus" / "config.json"
            if argus_cfg.is_file():
                try:
                    with open(argus_cfg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("mode") == "direct" or data.get("argus_mode") == "direct":
                        return False
                except Exception:
                    pass

        return True

    # -----------------------------------------------------------------------
    # Core Pipeline: PLAN -> EXECUTE -> OBSERVE -> VERIFY -> DONE
    # -----------------------------------------------------------------------
    def execute_task(self, request: WorkerRequest) -> WorkerResponse:
        start_time = time.time()
        task_id = request.task_id

        # Determine target directory from request files if available
        req_dir = None
        if request.files:
            try:
                first_f = pathlib.Path(request.files[0])
                if first_f.is_absolute():
                    curr = first_f.parent
                    for p in [curr] + list(curr.parents):
                        if (p / ".ai-worker").is_dir() or (p / ".argus").is_dir() or (p / ".git").is_dir():
                            req_dir = p
                            break
            except Exception:
                pass

        # Check for explicit worker target
        explicit_worker = request.parameters.get("worker") or request.parameters.get("target_worker")

        if explicit_worker:
            # -------------------------------------------------------------------
            # EXPLICIT DISPATCH PATH
            # -------------------------------------------------------------------
            norm_explicit = "ai-studio-worker" if explicit_worker == "bubu" else explicit_worker
            if not self.is_worker_enabled(explicit_worker, target_dir=req_dir):
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=explicit_worker,
                    status="not_available",
                    summary=f"Explicitly requested worker '{explicit_worker}' is disabled in configuration.",
                    error=WorkerError(
                        error_code="WORKER_NOT_AVAILABLE",
                        message=f"Worker '{explicit_worker}' is disabled and cannot be dispatched.",
                        retryable=False
                    ),
                    metrics={"duration_seconds": round(time.time() - start_time, 4), "explicit_dispatch": True}
                )
            worker_name = norm_explicit
            classification = self.classify_task(request.prompt, request.files, request.parameters)
        else:
            # -------------------------------------------------------------------
            # AUTOMATIC ROUTING PATH
            # -------------------------------------------------------------------
            classification = self.classify_task(request.prompt, request.files, request.parameters)

            # 1. Direct Path First (Phase 1.1)
            if classification == TaskClassification.DIRECT:
                return WorkerResponse(
                    task_id=task_id,
                    worker_name="main_agent_direct",
                    status="direct",
                    summary="Direct Path First: Task is localized. Execution delegated directly to Lead Agent.",
                    findings=["Direct execution bypasses worker overhead."],
                    metrics={"duration_seconds": round(time.time() - start_time, 4), "routing": "DIRECT"}
                )

            # Candidate worker based on classification
            worker_name = "ai-studio-worker" if classification == TaskClassification.CONTEXT_ANALYSIS else ("argus" if classification == TaskClassification.VISION else "composite")

            # Check if candidate worker is disabled -> Fallback to Direct Path
            if not self.is_worker_enabled(worker_name, target_dir=req_dir):
                return WorkerResponse(
                    task_id=task_id,
                    worker_name="main_agent_direct",
                    status="direct",
                    summary=f"Worker '{worker_name}' is disabled in configuration. Fallback to Direct Path: Task delegated directly to Lead Agent.",
                    findings=[f"Target worker '{worker_name}' is disabled in configuration. Execution delegated to Lead Agent without worker overhead."],
                    metrics={
                        "duration_seconds": round(time.time() - start_time, 4),
                        "routing": "DIRECT_FALLBACK",
                        "disabled_worker": worker_name,
                        "classification": classification.value
                    }
                )

        # 2. Fingerprint check
        fp = request.compute_fingerprint()
        self._fingerprint_counts[fp] = self._fingerprint_counts.get(fp, 0) + 1
        if self._fingerprint_counts[fp] > self.max_retries:
            return WorkerResponse(
                task_id=task_id,
                worker_name="orchestrator",
                status="loop_detected",
                summary=f"Task fingerprint {fp[:8]} exceeded maximum repeat threshold ({self.max_retries}).",
                error=WorkerError(
                    error_code="LOOP_SUSPECTED",
                    message="Repeated identical task fingerprint detected without state change.",
                    retryable=False
                )
            )

        # 3. Provider Preflight Check
        allowed, p_state, p_reason, hybrid_level = self.provider_manager.preflight_check("gemini")

        # If provider is blocked/exhausted and task requires cloud LLM
        if not allowed:
            if classification in (TaskClassification.CONTEXT_ANALYSIS, TaskClassification.COMBINED):
                if hybrid_level == HybridModeLevel.LOCAL_ONLY or p_state in (ProviderState.QUOTA_EXHAUSTED, ProviderState.AUTH_FAILED):
                    # Deterministic fallback or blocked
                    return WorkerResponse(
                        task_id=task_id,
                        worker_name="orchestrator",
                        status="blocked",
                        summary=f"External provider blocked ({p_reason}). Hybrid level: {hybrid_level.value}.",
                        error=WorkerError(
                            error_code=f"PROVIDER_{p_state.value}",
                            message=p_reason,
                            retryable=False,
                            details={"hybrid_level": hybrid_level.value, "provider_state": p_state.value}
                        )
                    )

        # Loop check on worker routing
        is_loop, loop_msg = self.check_loop(f"{worker_name}:{classification.value}")
        if is_loop:
            return WorkerResponse(
                task_id=task_id,
                worker_name=worker_name,
                status="loop_detected",
                summary=loop_msg,
                error=WorkerError(error_code="CYCLE_DETECTED", message=loop_msg, retryable=False)
            )

        # 5. Worker Invocation (or fallback simulation if worker not directly bound in current process)
        handler = self._registered_workers.get(worker_name)
        if handler:
            try:
                resp = handler(request)
                # Ingest evidence
                if resp.evidence:
                    self.evidence_store.ingest_batch(resp.evidence)
                return resp
            except Exception as e:
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=worker_name,
                    status="failed",
                    summary=f"Worker exception: {e}",
                    error=WorkerError(error_code="WORKER_EXCEPTION", message=str(e), retryable=False)
                )

        # If running without registered handler for this worker
        return WorkerResponse(
            task_id=task_id,
            worker_name="orchestrator",
            status="routed_only",
            summary=f"Task routed to {worker_name} under {hybrid_level.value} mode, but no active worker handler registered.",
            metrics={"classification": classification.value, "hybrid_level": hybrid_level.value, "duration": round(time.time() - start_time, 4)}
        )

    # -----------------------------------------------------------------------
    # Composite Multi-Worker Workflow Engine (Sequential & Fail-Fast)
    # -----------------------------------------------------------------------
    def execute_workflow(
        self,
        steps: List[WorkerRequest],
        workflow_id: Optional[str] = None
    ) -> WorkerResponse:
        """
        Executes an ordered sequence of WorkerRequest steps through the Orchestrator pipeline.
        Each step is dispatched via self.execute_task(step), ensuring quota preflight,
        worker policy checks, loop prevention, and evidence store persistence are enforced.
        Aggregates findings and evidence across all steps into a composite WorkerResponse.
        """
        start_time = time.time()
        wf_id = workflow_id or f"wf-{uuid.uuid4().hex[:8]}"

        if not steps:
            return WorkerResponse(
                task_id=wf_id,
                worker_name="composite",
                status="failed",
                summary="Workflow execution rejected: steps list is empty.",
                error=WorkerError(
                    error_code="EMPTY_WORKFLOW",
                    message="At least one WorkerRequest step must be provided.",
                    retryable=False
                ),
                metrics={"duration_seconds": round(time.time() - start_time, 4), "steps_executed": 0}
            )

        step_responses: Dict[str, Dict[str, Any]] = {}
        aggregated_findings: List[str] = []
        aggregated_evidence: List[Evidence] = []
        workflow_status = "success"
        failure_error: Optional[WorkerError] = None
        failure_summary = ""

        for idx, step in enumerate(steps, 1):
            step_id = step.task_id or f"step_{idx}"
            if not step.task_id:
                step.task_id = f"{wf_id}-step_{idx}"

            # Execute step through the standard pipeline
            step_resp = self.execute_task(step)
            step_responses[step_id] = step_resp.to_dict()

            # Aggregate findings and evidence
            if step_resp.findings:
                aggregated_findings.extend(step_resp.findings)
            if step_resp.evidence:
                aggregated_evidence.extend(step_resp.evidence)

            # Check for failure (Fail-Fast policy)
            if step_resp.status != "success":
                workflow_status = "failed"
                failure_error = step_resp.error or WorkerError(
                    error_code="STEP_FAILED",
                    message=f"Workflow step '{step_id}' failed with status '{step_resp.status}'.",
                    retryable=False
                )
                failure_summary = f"Workflow failed at step {idx}/{len(steps)} ('{step_id}'): {step_resp.summary}"
                break

        duration = round(time.time() - start_time, 4)
        summary = (
            f"Composite workflow completed successfully across {len(step_responses)}/{len(steps)} step(s)."
            if workflow_status == "success"
            else failure_summary
        )

        return WorkerResponse(
            task_id=wf_id,
            worker_name="composite",
            status=workflow_status,
            summary=summary,
            findings=aggregated_findings,
            evidence=aggregated_evidence,
            error=failure_error,
            metrics={
                "duration_seconds": duration,
                "steps_total": len(steps),
                "steps_executed": len(step_responses),
                "step_responses": step_responses
            }
        )

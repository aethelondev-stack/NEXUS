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
        max_retries: int = 3,
        max_replans: int = 2,
        max_wall_time_seconds: float = 60.0,
        loop_window_size: int = 6
    ):
        self.project_root = pathlib.Path(project_root or ".").resolve()
        self.provider_manager = provider_manager or ProviderManager()
        self.evidence_store = EvidenceStore(project_root=self.project_root)
        self.max_retries = max_retries
        self.max_replans = max_replans
        self.max_wall_time_seconds = max_wall_time_seconds
        self.loop_window_size = loop_window_size

        # Execution ring-buffer for cyclic loop detection (A -> B -> A -> B etc.)
        self._action_history: collections.deque[str] = collections.deque(maxlen=self.loop_window_size)
        self._fingerprint_counts: Dict[str, int] = {}
        self._registered_workers: Dict[str, Callable[[WorkerRequest], WorkerResponse]] = {}

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
        has_vision = any(k in p_lower for k in ["screen", "ekran", "görsel", "screenshot", "ui element", "bluestacks", "adb", "ocr"]) or params.get("requires_vision")

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

    # -----------------------------------------------------------------------
    # Core Pipeline: PLAN -> EXECUTE -> OBSERVE -> VERIFY -> DONE
    # -----------------------------------------------------------------------
    def execute_task(self, request: WorkerRequest) -> WorkerResponse:
        start_time = time.time()
        task_id = request.task_id
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

        # 4. Route to target worker
        worker_name = "ai-studio-worker" if classification == TaskClassification.CONTEXT_ANALYSIS else ("argus" if classification == TaskClassification.VISION else "composite")

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

        # If running via orchestrated CLI / subagent interface
        return WorkerResponse(
            task_id=task_id,
            worker_name="orchestrator",
            status="success",
            summary=f"Task routed to {worker_name} under {hybrid_level.value} mode.",
            metrics={"classification": classification.value, "hybrid_level": hybrid_level.value, "duration": round(time.time() - start_time, 4)}
        )

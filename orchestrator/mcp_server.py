#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORCHESTRATOR V3: FastMCP Server Adapter (mcp_server.py)
Provides a clean, thin runtime bridge between Antigravity Lead Agent and Orchestrator Core.
Standard FastMCP stdio interface.
"""
from __future__ import annotations

import os
import pathlib
import sys
import uuid
from typing import Any, Dict, List, Optional
from pydantic import Field

# Ensure ORCHESTRATOR root is on sys.path and remove script_dir if it shadows the package
CURRENT_DIR = pathlib.Path(__file__).resolve().parent.parent
script_dir = str(pathlib.Path(__file__).resolve().parent)
if sys.path and sys.path[0] == script_dir:
    sys.path.pop(0)
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from orchestrator.contracts import WorkerRequest
from orchestrator.orchestrator import Orchestrator, TaskClassification
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerRegistry

try:
    from fastmcp import FastMCP
except ImportError:
    FastMCP = None


def create_mcp_server():
    if FastMCP is None:
        raise ImportError("FastMCP is not installed. Install with 'pip install fastmcp'.")

    mcp = FastMCP("Antigravity Orchestrator Server")

    pm = ProviderManager()
    reg = WorkerRegistry()
    orch = Orchestrator(provider_manager=pm, registry=reg)

    @mcp.tool()
    def orchestrator_status() -> Dict[str, Any]:
        """
        Returns Orchestrator status, provider quota health, and registered worker count.
        """
        summary = pm.get_status_summary()
        summary["registry_path"] = str(reg.registry_path)
        summary["registered_workers_count"] = len(reg.list_workers())
        return summary

    @mcp.tool()
    def orchestrator_worker_status() -> Dict[str, Any]:
        """
        Returns physical health, existence, and availability status of all registered workers (BUBU, ARGUS, etc.).
        """
        workers_info = {}
        for w in reg.list_workers(enabled_only=False):
            workers_info[w.worker_id] = reg.check_worker_status(w.worker_id)
        return {
            "registry_path": str(reg.registry_path),
            "workers": workers_info
        }

    @mcp.tool()
    def orchestrator_classify(
        prompt: str = Field(..., description="User prompt or task description"),
        files: List[str] = Field(default=[], description="File paths involved in the task")
    ) -> Dict[str, Any]:
        """
        Classifies a task deterministically without LLM calls:
        DIRECT (simple edit), CONTEXT_ANALYSIS (BUBU), VISION (ARGUS), or COMBINED.
        """
        classification = orch.classify_task(prompt, files)
        return {
            "prompt": prompt,
            "files": files,
            "classification": classification.value,
            "direct_path": classification == TaskClassification.DIRECT,
            "recommended_worker": (
                "none (lead agent direct)" if classification == TaskClassification.DIRECT
                else ("bubu" if classification == TaskClassification.CONTEXT_ANALYSIS
                      else ("argus" if classification == TaskClassification.VISION else "composite"))
            )
        }

    @mcp.tool()
    def orchestrator_plan(
        prompt: str = Field(..., description="User prompt or task description"),
        files: List[str] = Field(default=[], description="File paths involved in the task")
    ) -> Dict[str, Any]:
        """
        Generates a routing plan, checking provider preflight quota and active circuit breakers.
        """
        classification = orch.classify_task(prompt, files)
        allowed, p_state, p_reason, h_level = pm.preflight_check("gemini")

        target_worker = (
            "lead_agent_direct" if classification == TaskClassification.DIRECT
            else ("bubu" if classification == TaskClassification.CONTEXT_ANALYSIS
                  else ("argus" if classification == TaskClassification.VISION else "composite"))
        )

        return {
            "classification": classification.value,
            "target_worker": target_worker,
            "provider_allowed": allowed,
            "provider_state": p_state.value,
            "hybrid_level": h_level.value,
            "actionable": True if classification == TaskClassification.DIRECT or allowed else False,
            "direct_path_recommended": classification == TaskClassification.DIRECT
        }

    @mcp.tool()
    def orchestrator_dispatch(
        prompt: str = Field(..., description="Task prompt or instruction"),
        files: List[str] = Field(default=[], description="List of file paths"),
        task_type: str = Field(default="ANALYZE", description="Task type: ANALYZE, AUDIT, DEBUG, RESEARCH, etc."),
        action: Optional[str] = Field(default=None, description="Optional sub-action for vision workers (e.g. desktop_items, scan)"),
        dry_run: bool = Field(default=False, description="Run in dry-run mode without mutating or calling cloud APIs")
    ) -> Dict[str, Any]:
        """
        Executes task through the Orchestrator pipeline, routing to BUBU or ARGUS,
        or executing Direct Path First, returning real findings and evidence.
        """
        # Clean parameter values from FieldInfo if directly invoked
        actual_dry_run = bool(dry_run) if not hasattr(dry_run, "default") else False
        actual_action = str(action) if (action and not hasattr(action, "default")) else None
        actual_task_type = str(task_type) if not hasattr(task_type, "default") else "ANALYZE"
        actual_files = [str(f) for f in files] if not hasattr(files, "default") else []
        actual_prompt = str(prompt) if not hasattr(prompt, "default") else ""

        # Ensure adapters are dynamically fresh
        try:
            import importlib
            import orchestrator.adapters.argus_adapter as argus_mod
            import orchestrator.adapters.bubu_adapter as bubu_mod
            importlib.reload(argus_mod)
            importlib.reload(bubu_mod)
            orch._init_adapters()
        except Exception:
            pass

        params: Dict[str, Any] = {"dry_run": actual_dry_run}
        if actual_action:
            params["action"] = actual_action

        req = WorkerRequest(
            task_id=f"mcp-{uuid.uuid4().hex[:8]}",
            task_type=actual_task_type,
            prompt=actual_prompt,
            files=actual_files,
            parameters=params
        )
        resp = orch.execute_task(req)
        return resp.to_dict()

    @mcp.tool()
    def orchestrator_verify(
        file_path: str = Field(..., description="Absolute or relative file path to verify"),
        line_start: int = Field(default=1, description="Start line of evidence"),
        line_end: int = Field(default=1, description="End line of evidence"),
        content_hash: str = Field(..., description="Expected SHA-256 hash of the content")
    ) -> Dict[str, Any]:
        """
        Verifies line-level evidence against current disk state to detect STALE or modified files.
        """
        from orchestrator.contracts import Evidence
        ev = Evidence(
            source="manual_verification",
            file=file_path,
            line_start=line_start,
            line_end=line_end,
            content_hash=content_hash,
            commit_hash="LOCAL",
            finding="Verification check",
            confidence=1.0
        )
        orch.evidence_store.ingest_batch([ev])
        status = orch.evidence_store.verify_evidence(ev)
        return {
            "file_path": file_path,
            "verification_status": status.value,
            "is_valid": status.value == "VERIFIED"
        }

    return mcp


if __name__ == "__main__":
    server = create_mcp_server()
    server.run(transport="stdio")

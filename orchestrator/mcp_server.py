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

    def _sync():
        try:
            import importlib
            import orchestrator.orchestrator as orch_mod
            import orchestrator.worker_registry as reg_mod
            import orchestrator.adapters.argus_adapter as argus_mod
            import orchestrator.adapters.bubu_adapter as bubu_mod
            importlib.reload(orch_mod)
            importlib.reload(reg_mod)
            importlib.reload(argus_mod)
            importlib.reload(bubu_mod)
            orch.__class__ = orch_mod.Orchestrator
            reg.__class__ = reg_mod.WorkerRegistry
            reg.load()
            bubu_def = reg.get_worker("bubu")
            if bubu_def:
                b_adapter = bubu_mod.BubuAdapter(bubu_def, orch.project_root, pm)
                orch.register_worker("bubu", b_adapter.invoke)
                orch.register_worker("ai-studio-worker", b_adapter.invoke)
            argus_def = reg.get_worker("argus")
            if argus_def:
                a_adapter = argus_mod.ArgusAdapter(argus_def, orch.project_root, pm)
                orch.register_worker("argus", a_adapter.invoke)
        except Exception:
            pass

    @mcp.tool()
    def orchestrator_status() -> Dict[str, Any]:
        """
        Returns Orchestrator status, provider quota health, and registered worker count.
        """
        _sync()
        summary = pm.get_status_summary()
        summary["registry_path"] = str(reg.registry_path)
        summary["registered_workers_count"] = len(reg.list_workers())
        return summary

    @mcp.tool()
    def orchestrator_worker_status() -> Dict[str, Any]:
        """
        Returns physical health, existence, and availability status of all registered workers (BUBU, ARGUS, etc.).
        """
        _sync()
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
        _sync()
        classification = orch.classify_task(prompt, files)
        rec_worker = (
            "none (lead agent direct)" if classification == TaskClassification.DIRECT
            else ("bubu" if classification == TaskClassification.CONTEXT_ANALYSIS
                  else ("argus" if classification == TaskClassification.VISION else "composite"))
        )
        worker_enabled = orch.is_worker_enabled(rec_worker) if rec_worker != "none (lead agent direct)" else True
        return {
            "prompt": prompt,
            "files": files,
            "classification": classification.value,
            "direct_path": classification == TaskClassification.DIRECT or not worker_enabled,
            "recommended_worker": rec_worker if worker_enabled else f"lead_agent_direct (fallback: {rec_worker} disabled)",
            "worker_enabled": worker_enabled
        }

    @mcp.tool()
    def orchestrator_plan(
        prompt: str = Field(..., description="User prompt or task description"),
        files: List[str] = Field(default=[], description="File paths involved in the task")
    ) -> Dict[str, Any]:
        """
        Generates a routing plan, checking provider preflight quota and active circuit breakers.
        """
        _sync()
        classification = orch.classify_task(prompt, files)
        allowed, p_state, p_reason, h_level = pm.preflight_check("gemini")

        candidate_worker = (
            "lead_agent_direct" if classification == TaskClassification.DIRECT
            else ("bubu" if classification == TaskClassification.CONTEXT_ANALYSIS
                  else ("argus" if classification == TaskClassification.VISION else "composite"))
        )
        worker_enabled = orch.is_worker_enabled(candidate_worker) if candidate_worker != "lead_agent_direct" else True
        target_worker = candidate_worker if worker_enabled else f"lead_agent_direct (fallback: {candidate_worker} disabled)"

        return {
            "classification": classification.value,
            "target_worker": target_worker,
            "worker_enabled": worker_enabled,
            "provider_allowed": allowed,
            "provider_state": p_state.value,
            "hybrid_level": h_level.value,
            "actionable": True if classification == TaskClassification.DIRECT or not worker_enabled or allowed else False,
            "direct_path_recommended": classification == TaskClassification.DIRECT or not worker_enabled
        }

    @mcp.tool()
    def orchestrator_dispatch(
        prompt: str = Field(..., description="Task prompt or instruction"),
        files: List[str] = Field(default=[], description="List of file paths"),
        task_type: str = Field(default="ANALYZE", description="Task type: ANALYZE, AUDIT, DEBUG, RESEARCH, etc."),
        action: Optional[str] = Field(default=None, description="Optional sub-action for vision workers (e.g. desktop_items, scan)"),
        dry_run: bool = Field(default=False, description="Run in dry-run mode without mutating or calling cloud APIs"),
        worker: Optional[str] = Field(default=None, description="Optional explicit target worker: 'bubu', 'argus', etc.")
    ) -> Dict[str, Any]:
        """
        Executes task through the Orchestrator pipeline, routing to BUBU or ARGUS,
        or executing Direct Path First, returning real findings and evidence.
        """
        _sync()
        actual_dry_run = bool(dry_run) if not hasattr(dry_run, "default") else False
        actual_action = str(action) if (action and not hasattr(action, "default")) else None
        actual_worker = str(worker) if (worker and not hasattr(worker, "default")) else None
        actual_task_type = str(task_type) if not hasattr(task_type, "default") else "ANALYZE"
        actual_files = [str(f) for f in files] if not hasattr(files, "default") else []
        actual_prompt = str(prompt) if not hasattr(prompt, "default") else ""


        params: Dict[str, Any] = {"dry_run": actual_dry_run}
        if actual_action:
            params["action"] = actual_action
            if actual_action in ("bubu", "argus", "ai-studio-worker") or actual_action.startswith("worker:"):
                exp = actual_action.split(":", 1)[1] if ":" in actual_action else actual_action
                params["worker"] = exp
                params["target_worker"] = exp
        if actual_worker:
            params["worker"] = actual_worker
            params["target_worker"] = actual_worker

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


def main():
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

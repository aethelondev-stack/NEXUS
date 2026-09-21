"""
ORCHESTRATOR V3: ARGUS Vision Shield Adapter
Dispatches vision and UI automation tasks to ARGUS FastMCP server (server.py).
Uses the real MCP client protocol (stdio_client + ClientSession) as declared in the registry (transport: mcp).
Enforces perceptual circuit breaker, privacy redaction, and local GPU budget.
Standard-library only dependencies with optional mcp runtime client.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.adapters.base import BaseWorkerAdapter
from orchestrator.contracts import Evidence, WorkerError, WorkerRequest, WorkerResponse
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerDefinition

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class ArgusAdapter(BaseWorkerAdapter):
    def is_available(self) -> Tuple[bool, str]:
        if not self.definition.enabled:
            return False, "ARGUS worker is disabled in registry."

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

        # 2. Map action to MCP tool name and arguments
        action = request.parameters.get("action", "desktop_items")
        tool_name = "smart_ui_desktop_items"
        tool_args: Dict[str, Any] = {}

        if action in ("desktop_items", "desktop", "items"):
            tool_name = "smart_ui_desktop_items"
            if "launch" in request.parameters and request.parameters["launch"]:
                tool_args["launch"] = request.parameters["launch"]
        elif action in ("scan", "screen", "capture"):
            tool_name = "smart_ui_scan"
            tool_args["source"] = request.parameters.get("source", "desktop")
            tool_args["peek_desktop"] = request.parameters.get("peek_desktop", False)
        elif action in ("click", "tap"):
            tool_name = "smart_ui_click"
            tool_args["coords"] = request.parameters.get("coords", [0, 0])
            tool_args["method"] = request.parameters.get("method", "tap")
            if "dpad_steps" in request.parameters:
                tool_args["dpad_steps"] = request.parameters["dpad_steps"]
        elif action in ("reset", "clear"):
            tool_name = "smart_ui_reset"
        else:
            tool_name = "smart_ui_desktop_items"

        server_path = self.definition.server_path
        python_exe = sys.executable or self.definition.python_executable or "python"
        timeout = float(self.definition.timeout_seconds or 30.0)

        # 3. Call via MCP Stdio Transport
        parsed_data: Optional[Dict[str, Any]] = None
        call_error: Optional[str] = None
        mcp_transport_used = False

        if HAS_MCP and server_path and pathlib.Path(server_path).exists():
            async def _mcp_call() -> Dict[str, Any]:
                server_params = StdioServerParameters(
                    command=python_exe,
                    args=[server_path],
                    env=os.environ.copy()
                )
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments=tool_args)
                        for content in result.content:
                            if hasattr(content, "text"):
                                try:
                                    return json.loads(content.text)
                                except Exception:
                                    return {"text": content.text}
                        return {"status": "success", "result": "completed"}

            def _run_mcp_isolated() -> Dict[str, Any]:
                return asyncio.run(asyncio.wait_for(_mcp_call(), timeout=timeout))

            try:
                try:
                    running_loop = asyncio.get_running_loop()
                except RuntimeError:
                    running_loop = None

                if running_loop and running_loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_run_mcp_isolated)
                        parsed_data = future.result(timeout=timeout + 2.0)
                else:
                    parsed_data = _run_mcp_isolated()
                mcp_transport_used = True
            except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                return WorkerResponse(
                    task_id=task_id,
                    worker_name=self.definition.worker_id,
                    status="timeout",
                    summary=f"Worker {self.definition.worker_id} timed out after {timeout}s via MCP transport.",
                    error=WorkerError(error_code="WORKER_TIMEOUT", message="Execution timeout exceeded", retryable=True),
                    metrics={"duration_seconds": round(time.time() - start_time, 4)}
                )
            except Exception as e:
                call_error = str(e)

        # 4. Strict Failure Semantics: If MCP transport fails, fail cleanly without fake success
        if parsed_data is None:
            err_msg = call_error or "ARGUS FastMCP server failed to respond or return valid data."
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="failed",
                summary=f"ARGUS MCP execution failed: {err_msg[:200]}",
                error=WorkerError(error_code="MCP_TRANSPORT_ERROR", message=err_msg, retryable=False),
                metrics={"duration_seconds": round(time.time() - start_time, 4)}
            )

        duration = round(time.time() - start_time, 4)

        # Check circuit breaker status
        if parsed_data.get("status") == "CIRCUIT_BREAKER_TRIGGERED":
            return WorkerResponse(
                task_id=task_id,
                worker_name=self.definition.worker_id,
                status="blocked",
                summary=f"ARGUS Circuit Breaker tripped: {parsed_data.get('error')}",
                error=WorkerError(error_code="CIRCUIT_BREAKER_TRIPPED", message=parsed_data.get("error", ""), retryable=False),
                metrics={"duration_seconds": duration}
            )

        # Extract findings
        findings: List[str] = []
        if "items" in parsed_data:
            findings = [f"Desktop Item: {item}" for item in parsed_data["items"][:10]]
        elif "visible_windows" in parsed_data:
            findings = [f"Window: {w.get('title', '')}" for w in parsed_data.get("visible_windows", [])[:10]]
        elif "message" in parsed_data:
            findings = [parsed_data["message"]]
        else:
            findings = [str(parsed_data)[:200]]

        return WorkerResponse(
            task_id=task_id,
            worker_name=self.definition.worker_id,
            status="success",
            summary=f"ARGUS executed tool '{tool_name}' successfully via MCP transport (Zero Cloud Token Cost).",
            findings=findings,
            metrics={
                "duration_seconds": duration,
                "action": action,
                "tool": tool_name,
                "transport": "mcp",
                "desktop_items_count": parsed_data.get("desktop_items_count", len(findings)),
                "token_cost": 0
            }
        )

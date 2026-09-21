"""
ORCHESTRATOR V3: Worker Registry
Discovers, validates, and manages global worker definitions from ~/.gemini/orchestrator/workers.json.
Standard-library only.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class WorkerDefinition:
    worker_id: str
    worker_type: str
    name: str
    description: str
    transport: str
    entrypoint: str
    capabilities: List[str]
    enabled: bool = True
    version: str = "1.0.0"
    timeout_seconds: float = 60.0
    priority: int = 1
    execution_mode: str = "cloud_hybrid"  # cloud_hybrid, local_gpu, local_process
    cost_characteristics: Dict[str, Any] = dataclasses.field(default_factory=dict)
    server_path: Optional[str] = None
    python_executable: str = "python"
    tools: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkerDefinition:
        return cls(
            worker_id=data.get("worker_id", ""),
            worker_type=data.get("worker_type", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            transport=data.get("transport", "cli"),
            entrypoint=data.get("entrypoint", ""),
            capabilities=data.get("capabilities", []),
            enabled=data.get("enabled", True),
            version=data.get("version", "1.0.0"),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            priority=int(data.get("priority", 1)),
            execution_mode=data.get("execution_mode", "cloud_hybrid"),
            cost_characteristics=data.get("cost_characteristics", {}),
            server_path=data.get("server_path"),
            python_executable=data.get("python_executable", "python"),
            tools=data.get("tools", []),
        )


class WorkerRegistry:
    """
    Global Worker Registry manager.
    Reads global configuration to discover available workers without local project pollution.
    """
    DEFAULT_GLOBAL_PATH = pathlib.Path.home() / ".gemini" / "orchestrator" / "workers.json"

    def __init__(self, registry_path: Optional[pathlib.Path] = None):
        self.registry_path = pathlib.Path(registry_path or self.DEFAULT_GLOBAL_PATH).resolve()
        self._workers: Dict[str, WorkerDefinition] = {}
        self.load()

    def load(self) -> None:
        """Loads and parses the worker registry from disk."""
        if not self.registry_path.exists():
            self._workers = {}
            return

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            workers_raw = data.get("workers", {})
            self._workers = {
                w_id: WorkerDefinition.from_dict(w_dict)
                for w_id, w_dict in workers_raw.items()
            }
        except Exception:
            self._workers = {}

    def get_worker(self, worker_id: str) -> Optional[WorkerDefinition]:
        return self._workers.get(worker_id)

    def list_workers(self, enabled_only: bool = True) -> List[WorkerDefinition]:
        if enabled_only:
            return [w for w in self._workers.values() if w.enabled]
        return list(self._workers.values())

    def is_worker_enabled(self, worker_id: str) -> bool:
        norm_id = "bubu" if worker_id in ("bubu", "ai-studio-worker") else worker_id
        worker = self.get_worker(norm_id)
        if not worker:
            return False
        return bool(worker.enabled)

    def find_by_type(self, worker_type: str) -> List[WorkerDefinition]:
        return [w for w in self.list_workers() if w.worker_type == worker_type]

    def find_by_capability(self, capability: str) -> List[WorkerDefinition]:
        return [w for w in self.list_workers() if capability in w.capabilities]

    def check_worker_status(self, worker_id: str) -> Dict[str, Any]:
        """Checks file existence and health for a registered worker."""
        worker = self.get_worker(worker_id)
        if not worker:
            return {
                "worker_id": worker_id,
                "registered": False,
                "status": "NOT_REGISTERED",
                "healthy": False,
            }

        # Check physical existence of entrypoint
        ep_path = pathlib.Path(worker.entrypoint)
        ep_exists = ep_path.exists()

        server_exists = True
        if worker.server_path:
            server_exists = pathlib.Path(worker.server_path).exists()

        is_healthy = worker.enabled and (ep_exists or worker.transport == "mcp") and server_exists

        return {
            "worker_id": worker.worker_id,
            "name": worker.name,
            "registered": True,
            "enabled": worker.enabled,
            "transport": worker.transport,
            "entrypoint": str(worker.entrypoint),
            "entrypoint_exists": ep_exists,
            "server_path": str(worker.server_path) if worker.server_path else None,
            "server_path_exists": server_exists,
            "healthy": is_healthy,
            "execution_mode": worker.execution_mode,
            "status": "HEALTHY" if is_healthy else ("DISABLED" if not worker.enabled else "MISSING_FILES")
        }

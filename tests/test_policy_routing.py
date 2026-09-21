"""
Unit tests for Worker Enable/Disable Routing Policies (Phase 8).
Verifies the exact 8-case matrix across automatic routing vs explicit dispatch for BUBU and ARGUS.
"""
import json
import pathlib
import tempfile
import unittest

from orchestrator.contracts import WorkerRequest, WorkerResponse
from orchestrator.orchestrator import Orchestrator, TaskClassification
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerDefinition, WorkerRegistry


class TestPolicyRouting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = pathlib.Path(self.temp_dir.name)
        self.pm = ProviderManager(state_dir=self.project_root)

        # Base mock definitions
        self.bubu_def = WorkerDefinition(
            worker_id="bubu",
            worker_type="context_analysis",
            name="BUBU",
            description="BUBU Context Worker",
            transport="cli",
            entrypoint="python",
            capabilities=["code_audit"],
            enabled=True
        )
        self.argus_def = WorkerDefinition(
            worker_id="argus",
            worker_type="vision",
            name="ARGUS",
            description="ARGUS Vision Shield",
            transport="mcp",
            entrypoint="argus",
            capabilities=["screen_capture", "desktop_items"],
            enabled=True
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_orchestrator(self, bubu_enabled: bool = True, argus_enabled: bool = True) -> Orchestrator:
        b_def = WorkerDefinition(
            worker_id="bubu",
            worker_type="context_analysis",
            name="BUBU",
            description="BUBU",
            transport="cli",
            entrypoint="python",
            capabilities=["code_audit"],
            enabled=bubu_enabled
        )
        a_def = WorkerDefinition(
            worker_id="argus",
            worker_type="vision",
            name="ARGUS",
            description="ARGUS",
            transport="mcp",
            entrypoint="argus",
            capabilities=["desktop_items"],
            enabled=argus_enabled
        )

        reg = WorkerRegistry()
        reg._workers = {"bubu": b_def, "argus": a_def}

        orch = Orchestrator(project_root=self.project_root, provider_manager=self.pm, registry=reg)

        # Register mock worker handlers that return success
        orch.register_worker("bubu", lambda req: WorkerResponse(
            task_id=req.task_id, worker_name="bubu", status="success", summary="BUBU mock success"
        ))
        orch.register_worker("ai-studio-worker", lambda req: WorkerResponse(
            task_id=req.task_id, worker_name="bubu", status="success", summary="BUBU mock success"
        ))
        orch.register_worker("argus", lambda req: WorkerResponse(
            task_id=req.task_id, worker_name="argus", status="success", summary="ARGUS mock success"
        ))

        return orch

    # -----------------------------------------------------------------------
    # 1. BUBU Tests
    # -----------------------------------------------------------------------
    def test_bubu_enabled_automatic(self):
        """BUBU enabled + automatic routing -> BUBU executes."""
        orch = self._create_orchestrator(bubu_enabled=True)
        req = WorkerRequest(
            task_id="test-1",
            task_type="AUDIT",
            prompt="Architecture review and deep code audit",
            files=["app.py", "db.py", "auth.py"]
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "bubu")

    def test_bubu_disabled_automatic(self):
        """BUBU disabled + automatic routing -> BUBU must not run; fallback to Direct Path."""
        orch = self._create_orchestrator(bubu_enabled=False)
        req = WorkerRequest(
            task_id="test-2",
            task_type="AUDIT",
            prompt="Architecture review and deep code audit",
            files=["app.py", "db.py", "auth.py"]
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "direct")
        self.assertEqual(resp.worker_name, "main_agent_direct")
        self.assertEqual(resp.metrics.get("routing"), "DIRECT_FALLBACK")

    def test_bubu_enabled_explicit(self):
        """BUBU enabled + explicit dispatch -> BUBU executes."""
        orch = self._create_orchestrator(bubu_enabled=True)
        req = WorkerRequest(
            task_id="test-3",
            task_type="AUDIT",
            prompt="Specific audit",
            files=[],
            parameters={"worker": "bubu"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "bubu")

    def test_bubu_disabled_explicit(self):
        """BUBU disabled + explicit dispatch -> Returns WORKER_NOT_AVAILABLE without silent fallback."""
        orch = self._create_orchestrator(bubu_enabled=False)
        req = WorkerRequest(
            task_id="test-4",
            task_type="AUDIT",
            prompt="Specific audit",
            files=[],
            parameters={"worker": "bubu"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "not_available")
        self.assertIsNotNone(resp.error)
        self.assertEqual(resp.error.error_code, "WORKER_NOT_AVAILABLE")

    # -----------------------------------------------------------------------
    # 2. ARGUS Tests
    # -----------------------------------------------------------------------
    def test_argus_enabled_automatic(self):
        """ARGUS enabled + automatic routing -> ARGUS executes."""
        orch = self._create_orchestrator(argus_enabled=True)
        req = WorkerRequest(
            task_id="test-5",
            task_type="VISION",
            prompt="Scan desktop and list UI items",
            files=[],
            parameters={"action": "desktop_items"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "argus")

    def test_argus_disabled_automatic(self):
        """ARGUS disabled + automatic routing -> ARGUS must not run; fallback to Direct Path."""
        orch = self._create_orchestrator(argus_enabled=False)
        req = WorkerRequest(
            task_id="test-6",
            task_type="VISION",
            prompt="Scan desktop and list UI items",
            files=[],
            parameters={"action": "desktop_items"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "direct")
        self.assertEqual(resp.worker_name, "main_agent_direct")
        self.assertEqual(resp.metrics.get("routing"), "DIRECT_FALLBACK")

    def test_argus_enabled_explicit(self):
        """ARGUS enabled + explicit dispatch -> ARGUS executes."""
        orch = self._create_orchestrator(argus_enabled=True)
        req = WorkerRequest(
            task_id="test-7",
            task_type="VISION",
            prompt="Direct desktop items",
            files=[],
            parameters={"worker": "argus", "action": "desktop_items"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "argus")

    def test_argus_disabled_explicit(self):
        """ARGUS disabled + explicit dispatch -> Returns WORKER_NOT_AVAILABLE without silent fallback."""
        orch = self._create_orchestrator(argus_enabled=False)
        req = WorkerRequest(
            task_id="test-8",
            task_type="VISION",
            prompt="Direct desktop items",
            files=[],
            parameters={"worker": "argus", "action": "desktop_items"}
        )
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "not_available")
        self.assertIsNotNone(resp.error)
        self.assertEqual(resp.error.error_code, "WORKER_NOT_AVAILABLE")

    # -----------------------------------------------------------------------
    # 3. Workspace Config Preference Tests (.ai-worker / .argus)
    # -----------------------------------------------------------------------
    def test_workspace_bubu_config_override(self):
        """When .ai-worker/config.json has worker_mode: disabled, BUBU is treated as disabled for that workspace."""
        orch = self._create_orchestrator(bubu_enabled=True)
        # Write local workspace config
        ai_worker_dir = self.project_root / ".ai-worker"
        ai_worker_dir.mkdir(parents=True, exist_ok=True)
        with open(ai_worker_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump({"worker_mode": "disabled"}, f)

        # Automatic routing should fallback
        req = WorkerRequest(task_id="ws-1", task_type="AUDIT", prompt="Architecture audit", files=["a.py", "b.py", "c.py"])
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "direct")

        # Explicit dispatch should fail with WORKER_NOT_AVAILABLE
        req_exp = WorkerRequest(task_id="ws-2", task_type="AUDIT", prompt="Audit", files=[], parameters={"worker": "bubu"})
        resp_exp = orch.execute_task(req_exp)
        self.assertEqual(resp_exp.status, "not_available")
        self.assertEqual(resp_exp.error.error_code, "WORKER_NOT_AVAILABLE")

    def test_workspace_argus_config_override(self):
        """When .argus/config.json has mode: direct, ARGUS is treated as disabled for that workspace."""
        orch = self._create_orchestrator(argus_enabled=True)
        # Write local workspace config
        argus_dir = self.project_root / ".argus"
        argus_dir.mkdir(parents=True, exist_ok=True)
        with open(argus_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump({"mode": "direct"}, f)

        # Automatic routing should fallback
        req = WorkerRequest(task_id="ws-3", task_type="VISION", prompt="Desktop scan", files=[], parameters={"action": "desktop_items"})
        resp = orch.execute_task(req)
        self.assertEqual(resp.status, "direct")

        # Explicit dispatch should fail with WORKER_NOT_AVAILABLE
        req_exp = WorkerRequest(task_id="ws-4", task_type="VISION", prompt="Scan", files=[], parameters={"worker": "argus"})
        resp_exp = orch.execute_task(req_exp)
        self.assertEqual(resp_exp.status, "not_available")
        self.assertEqual(resp_exp.error.error_code, "WORKER_NOT_AVAILABLE")


if __name__ == "__main__":
    unittest.main()

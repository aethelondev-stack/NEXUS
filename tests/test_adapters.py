"""
Unit tests for Worker Adapters (BUBU & ARGUS).
Tests real dry-run invocation, error handling, quota gating, and failure semantics.
"""
import pathlib
import tempfile
import unittest

from orchestrator.adapters.bubu_adapter import BubuAdapter
from orchestrator.adapters.argus_adapter import ArgusAdapter
from orchestrator.contracts import WorkerRequest
from orchestrator.provider_manager import ProviderManager
from orchestrator.worker_registry import WorkerDefinition, WorkerRegistry


class TestWorkerAdapters(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = pathlib.Path(self.temp_dir.name)
        self.pm = ProviderManager(state_dir=self.state_dir)
        self.reg = WorkerRegistry()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bubu_adapter_dry_run(self):
        bubu_def = self.reg.get_worker("bubu")
        self.assertIsNotNone(bubu_def, "BUBU worker definition must exist in global registry")

        adapter = BubuAdapter(bubu_def, project_root=pathlib.Path(self.temp_dir.name), provider_manager=self.pm)
        available, msg = adapter.is_available()
        self.assertTrue(available, f"BUBU entrypoint should exist: {msg}")

        # Execute in dry-run mode
        req = WorkerRequest(
            task_id="test-bubu-dry",
            task_type="ANALYZE",
            prompt="Audit configuration files",
            files=[],
            parameters={"dry_run": True}
        )
        resp = adapter.invoke(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "bubu")
        self.assertTrue(resp.metrics.get("dry_run"))

    def test_bubu_adapter_quota_blocked(self):
        bubu_def = self.reg.get_worker("bubu")
        self.assertIsNotNone(bubu_def)

        # Simulate quota exhaustion in ProviderManager
        self.pm.record_failure("gemini", 429, "Resource has been exhausted: quota_exceeded")

        adapter = BubuAdapter(bubu_def, project_root=pathlib.Path(self.temp_dir.name), provider_manager=self.pm)
        req = WorkerRequest(
            task_id="test-bubu-quota",
            task_type="ANALYZE",
            prompt="Heavy audit that needs Gemini",
            files=["app.py", "db.py"],
            parameters={"dry_run": False}
        )
        resp = adapter.invoke(req)
        self.assertEqual(resp.status, "quota_exhausted")
        self.assertIsNotNone(resp.error)
        self.assertEqual(resp.error.error_code, "PROVIDER_QUOTA_EXHAUSTED")

    def test_bubu_adapter_external_files_dry_run(self):
        bubu_def = self.reg.get_worker("bubu")
        self.assertIsNotNone(bubu_def)

        # Create a sample file in isolated temp dir
        test_file = pathlib.Path(self.temp_dir.name) / "sample_service.py"
        test_file.write_text("def service():\n    return 'ok'\n")

        adapter = BubuAdapter(bubu_def, project_root=pathlib.Path(self.temp_dir.name), provider_manager=self.pm)
        req = WorkerRequest(
            task_id="test-bubu-ext-files",
            task_type="AUDIT",
            prompt="Audit service",
            files=[str(test_file)],
            parameters={"dry_run": True}
        )
        resp = adapter.invoke(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "bubu")
        self.assertGreaterEqual(len(resp.evidence), 1)


    def test_argus_adapter_desktop_items(self):
        argus_def = self.reg.get_worker("argus")
        self.assertIsNotNone(argus_def, "ARGUS worker definition must exist in global registry")

        adapter = ArgusAdapter(argus_def, project_root=pathlib.Path(self.temp_dir.name), provider_manager=self.pm)
        available, msg = adapter.is_available()
        self.assertTrue(available, f"ARGUS server should exist: {msg}")

        # Execute desktop items
        req = WorkerRequest(
            task_id="test-argus-items",
            task_type="VISION",
            prompt="List desktop items",
            files=[],
            parameters={"action": "desktop_items"}
        )
        resp = adapter.invoke(req)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.worker_name, "argus")
        self.assertEqual(resp.metrics.get("token_cost"), 0)
        self.assertGreater(len(resp.findings), 0)


if __name__ == "__main__":
    unittest.main()

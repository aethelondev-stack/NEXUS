"""
Unit tests for WorkerRegistry (Phase 7 / Integration).
Tests loading, validation, capability search, and physical health checking.
"""
import pathlib
import tempfile
import unittest
import json

from orchestrator.worker_registry import WorkerRegistry, WorkerDefinition


class TestWorkerRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reg_file = pathlib.Path(self.temp_dir.name) / "workers.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_valid_registry(self):
        data = {
            "version": "3.0.0",
            "workers": {
                "test_worker": {
                    "worker_id": "test_worker",
                    "worker_type": "context_analysis",
                    "name": "Test Worker",
                    "description": "A worker for testing",
                    "transport": "cli",
                    "entrypoint": str(self.reg_file),
                    "capabilities": ["code_audit", "memory_leak"],
                    "enabled": True,
                    "version": "1.0.0",
                    "timeout_seconds": 30.0,
                    "priority": 1,
                    "execution_mode": "cloud_hybrid"
                }
            }
        }
        with open(self.reg_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        reg = WorkerRegistry(registry_path=self.reg_file)
        worker = reg.get_worker("test_worker")
        self.assertIsNotNone(worker)
        self.assertEqual(worker.name, "Test Worker")
        self.assertEqual(worker.capabilities, ["code_audit", "memory_leak"])

        # Test find by type
        by_type = reg.find_by_type("context_analysis")
        self.assertEqual(len(by_type), 1)

        # Test find by capability
        by_cap = reg.find_by_capability("memory_leak")
        self.assertEqual(len(by_cap), 1)

    def test_physical_health_check(self):
        # Entrypoint exists
        valid_ep = pathlib.Path(self.temp_dir.name) / "entrypoint.py"
        valid_ep.write_text("#!/usr/bin/env python\nprint('ok')")

        data = {
            "workers": {
                "healthy_worker": {
                    "worker_id": "healthy_worker",
                    "worker_type": "context_analysis",
                    "name": "Healthy Worker",
                    "transport": "cli",
                    "entrypoint": str(valid_ep),
                    "capabilities": ["test"],
                    "enabled": True
                },
                "missing_worker": {
                    "worker_id": "missing_worker",
                    "worker_type": "vision",
                    "name": "Missing Worker",
                    "transport": "cli",
                    "entrypoint": str(pathlib.Path(self.temp_dir.name) / "non_existent.py"),
                    "capabilities": ["test"],
                    "enabled": True
                }
            }
        }
        with open(self.reg_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        reg = WorkerRegistry(registry_path=self.reg_file)
        st_healthy = reg.check_worker_status("healthy_worker")
        self.assertTrue(st_healthy["healthy"])
        self.assertEqual(st_healthy["status"], "HEALTHY")

        st_missing = reg.check_worker_status("missing_worker")
        self.assertFalse(st_missing["healthy"])
        self.assertEqual(st_missing["status"], "MISSING_FILES")

    def test_global_registry_loading(self):
        # Loads the actual ~/.gemini/orchestrator/workers.json
        reg = WorkerRegistry()
        if reg.registry_path.exists():
            workers = reg.list_workers()
            self.assertGreaterEqual(len(workers), 2)
            bubu = reg.get_worker("bubu")
            self.assertIsNotNone(bubu)
            self.assertEqual(bubu.worker_type, "context_analysis")

            argus = reg.get_worker("argus")
            self.assertIsNotNone(argus)
            self.assertEqual(argus.worker_type, "vision")


if __name__ == "__main__":
    unittest.main()

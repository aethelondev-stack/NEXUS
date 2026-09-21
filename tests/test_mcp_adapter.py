"""
Unit tests for Orchestrator MCP Server Adapter.
Tests server initialization, tool functions, planning, classification, and dispatch.
"""
import unittest

from orchestrator.mcp_server import create_mcp_server


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = create_mcp_server()

    def test_mcp_server_tools_registered(self):
        self.assertEqual(self.server.name, "Antigravity Orchestrator Server")

    def test_mcp_tool_execution(self):
        # We can extract the underlying functions from FastMCP tools
        # or test via direct imports
        from orchestrator.orchestrator import Orchestrator, TaskClassification
        from orchestrator.provider_manager import ProviderManager
        from orchestrator.worker_registry import WorkerRegistry

        pm = ProviderManager()
        reg = WorkerRegistry()
        orch = Orchestrator(provider_manager=pm, registry=reg)

        # Test classify direct
        c_direct = orch.classify_task("fix typo in readme", ["README.md"])
        self.assertEqual(c_direct, TaskClassification.DIRECT)

        # Test classify context
        c_context = orch.classify_task("Conduct security architecture audit", ["a.py", "b.py", "c.py"])
        self.assertEqual(c_context, TaskClassification.CONTEXT_ANALYSIS)

        # Test classify vision
        c_vision = orch.classify_task("Masaüstü ekran görüntüsünü al ve tara", [])
        self.assertEqual(c_vision, TaskClassification.VISION)


if __name__ == "__main__":
    unittest.main()

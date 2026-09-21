"""
ORCHESTRATOR V3: Mandatory Quota, Rate Limit & Infinite-Loop Test Suite
Implements Section 4.5.30 Verification Tests A through G.
Standard unittest framework with zero fake intelligence / zero fake pass.
"""
import json
import os
import pathlib
import shutil
import tempfile
import time
import unittest

from orchestrator.contracts import (
    Evidence,
    WorkerError,
    WorkerRequest,
    WorkerResponse,
    SCHEMA_VERSION
)
from orchestrator.evidence_store import EvidenceStore
from orchestrator.orchestrator import Orchestrator, TaskClassification
from orchestrator.provider_manager import (
    CircuitBreakerState,
    HybridModeLevel,
    ProviderManager,
    ProviderState
)


class TestQuotaAndResilience(unittest.TestCase):
    def setUp(self):
        self.temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="orch_test_"))
        self.state_dir = self.temp_dir / "provider-state"
        self.pm = ProviderManager(state_dir=self.state_dir, local_daily_request_limit=10, local_rpm_limit=5)
        self.orch = Orchestrator(project_root=self.temp_dir, provider_manager=self.pm)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # TEST A: DAILY QUOTA EXHAUSTION
    # -----------------------------------------------------------------------
    def test_a_daily_quota_exhaustion(self):
        """Verify 429 quota_exceeded triggers QUOTA_EXHAUSTED, sets persistent lock, and prevents API spam."""
        state, cd = self.pm.record_failure(
            "gemini", 429, "Resource has been exhausted (e.g. check quota): quota_exceeded"
        )
        self.assertEqual(state, ProviderState.QUOTA_EXHAUSTED)
        self.assertGreater(cd, 3600.0)  # Multi-hour cooldown

        # Subsequent preflight must strictly REJECT without network call
        allowed, p_state, reason, hybrid_lvl = self.pm.preflight_check("gemini")
        self.assertFalse(allowed)
        self.assertEqual(p_state, ProviderState.QUOTA_EXHAUSTED)
        self.assertEqual(hybrid_lvl, HybridModeLevel.LOCAL_ONLY)
        self.assertIn("quota exhausted", reason.lower())

    # -----------------------------------------------------------------------
    # TEST B: TRANSIENT RATE LIMIT
    # -----------------------------------------------------------------------
    def test_b_transient_rate_limit(self):
        """Verify 429 rate_limit_exceeded triggers RATE_LIMITED (not QUOTA_EXHAUSTED) and short backoff."""
        state, cd = self.pm.record_failure(
            "gemini", 429, "rate_limit_exceeded: Too many requests per minute."
        )
        self.assertEqual(state, ProviderState.RATE_LIMITED)
        self.assertNotEqual(state, ProviderState.QUOTA_EXHAUSTED)
        self.assertLessEqual(cd, 60.0)  # Short bounded backoff

        # Recovery upon success
        self.pm.record_success("gemini", estimated_in_tokens=100, estimated_out_tokens=50)
        summary = self.pm.get_status_summary()
        self.assertEqual(summary["providers"]["gemini"]["state"], ProviderState.HEALTHY.value)

    # -----------------------------------------------------------------------
    # TEST C: NEW SESSION / NEW CHAT PREFLIGHT (Zero-Spam Recovery)
    # -----------------------------------------------------------------------
    def test_c_new_session_preflight(self):
        """Verify a brand new process/session loads persisted quota state and refuses to blind-call Gemini."""
        # Session 1 trips quota
        self.pm.record_failure("gemini", 429, "Resource has been exhausted: quota_exceeded")

        # Session 2 starts fresh pointing to same state_dir
        session_2_pm = ProviderManager(state_dir=self.state_dir)
        allowed, p_state, reason, hybrid_lvl = session_2_pm.preflight_check("gemini")

        self.assertFalse(allowed)
        self.assertEqual(p_state, ProviderState.QUOTA_EXHAUSTED)
        self.assertEqual(hybrid_lvl, HybridModeLevel.LOCAL_ONLY)

    # -----------------------------------------------------------------------
    # TEST D: MULTIPLE SESSIONS SINGLE-FLIGHT LOCK
    # -----------------------------------------------------------------------
    def test_d_multi_session_lock(self):
        """Verify inter-process lock prevents concurrent access collision."""
        pm1 = ProviderManager(state_dir=self.state_dir)
        pm2 = ProviderManager(state_dir=self.state_dir)

        self.assertTrue(pm1.acquire_lock())
        # Second acquire must fail or wait
        self.assertFalse(pm2.acquire_lock(timeout_seconds=0.1))
        pm1.release_lock()
        # Now pm2 can acquire
        self.assertTrue(pm2.acquire_lock(timeout_seconds=0.5))
        pm2.release_lock()

    # -----------------------------------------------------------------------
    # TEST E: PREDICTIVE HYBRID MODE
    # -----------------------------------------------------------------------
    def test_e_predictive_hybrid_pressure(self):
        """Verify high request rate or nearing budget automatically elevates level: NORMAL -> CAUTIOUS -> HYBRID."""
        # Initial: NORMAL
        self.assertEqual(self.pm.evaluate_predictive_hybrid_level(), HybridModeLevel.NORMAL)

        # Record rapid requests in window
        for _ in range(3):
            self.pm.record_success("gemini", 100, 50)
        # Moderate pressure
        self.pm.record_failure("gemini", 429, "rate_limit_exceeded")
        lvl = self.pm.evaluate_predictive_hybrid_level()
        self.assertIn(lvl, (HybridModeLevel.CAUTIOUS, HybridModeLevel.HYBRID))

    # -----------------------------------------------------------------------
    # TEST F: LOCAL ONLY ON PROVIDER BLOCKED
    # -----------------------------------------------------------------------
    def test_f_local_only_graceful_routing(self):
        """Verify direct path tasks succeed even when provider is unavailable."""
        self.pm.record_failure("gemini", 401, "API_KEY_INVALID")

        req = WorkerRequest(task_id="t-direct-1", task_type="DIRECT", prompt="Fix typo in local readme", files=["README.md"])
        resp = self.orch.execute_task(req)
        # Direct path must succeed without needing external provider
        self.assertEqual(resp.status, "direct")

    # -----------------------------------------------------------------------
    # TEST G: INFINITE LOOP & CYCLE DETECTION
    # -----------------------------------------------------------------------
    def test_g_infinite_loop_detection(self):
        """Verify ping-pong cycle A -> B -> A -> B is caught and halted cleanly."""
        is_loop, _ = self.orch.check_loop("workerA:action")
        self.assertFalse(is_loop)
        is_loop, _ = self.orch.check_loop("workerB:action")
        self.assertFalse(is_loop)
        is_loop, _ = self.orch.check_loop("workerA:action")
        self.assertFalse(is_loop)
        # 4th action completes A -> B -> A -> B ping-pong cycle
        is_loop, msg = self.orch.check_loop("workerB:action")
        self.assertTrue(is_loop)
        self.assertIn("Ping-pong cycle", msg)


if __name__ == "__main__":
    unittest.main()

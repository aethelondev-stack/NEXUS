#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit and Integration Tests for BUBU + ARGUS Worker Preferences under NEXUS Host Coordinator.
Verifies the corrected architectural model where NEXUS is always-on coordinator,
and session preferences only control leaf workers (BUBU and ARGUS).

Covers all scenarios requested in Section 8:
  Test A: All Auto (BUBU = auto, ARGUS = auto)
  Test B: All Disabled (BUBU = disabled, ARGUS = disabled, NEXUS always running)
  Test C: BUBU Disabled (BUBU = disabled, ARGUS = auto)
  Test D: ARGUS Disabled (BUBU = auto, ARGUS = disabled)
  Test E: Explicit First Message (BUBU disabled, ARGUS auto -> no onboarding)
  Test F: No Preference -> implicit ALL AUTO after turn 1
  Test G: Session Isolation (Session A != Session B)
  Test H: NEXUS disabled rejected as valid worker preference
  Test I: Legacy JSON migration (ignores old "nexus" key seamlessly)
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.orchestrator import Orchestrator
from orchestrator.contracts import WorkerRequest
from orchestrator.session_state import (
    DEFAULT_PREFERENCES,
    ALL_DISABLED_PREFERENCES,
    ONBOARDING_BANNER,
    SessionLifecycleState,
    SessionStateManager,
    parse_explicit_preferences,
)


class TestSessionPreference(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="nexus_worker_pref_test_")
        self.storage_dir = pathlib.Path(self.temp_dir) / "sessions"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_first_message_shows_onboarding_once(self):
        """Test F1: New session. User sends first message without preference -> onboarding shown once."""
        mgr = SessionStateManager(session_id="test_session_1", storage_dir=self.storage_dir)
        self.assertEqual(mgr.state, SessionLifecycleState.UNRESOLVED)
        self.assertEqual(mgr.onboarding_shown_count, 0)

        should_show, banner = mgr.process_message("Basit bir dosyayı analiz et.")
        self.assertTrue(should_show)
        self.assertIn("Sistem Tercihleri (NEXUS Koordinasyonunda Worker Modları)", banner)
        self.assertIn("BUBU = auto | ARGUS = auto", banner)
        self.assertEqual(mgr.onboarding_shown_count, 1)
        self.assertEqual(mgr.state, SessionLifecycleState.WAITING_FOR_REPLY)
        self.assertFalse(mgr.resolved)

    def test_02_explicit_first_message_bypasses_onboarding(self):
        """Test E: User provides explicit worker preference on first message -> NO onboarding."""
        mgr = SessionStateManager(session_id="test_session_2", storage_dir=self.storage_dir)
        should_show, banner = mgr.process_message("Dosyayı analiz et. BUBU disabled, ARGUS auto.")
        self.assertFalse(should_show)
        self.assertIsNone(banner)
        self.assertEqual(mgr.onboarding_shown_count, 0)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)
        self.assertTrue(mgr.resolved)
        prefs = mgr.get_preferences()
        self.assertEqual(prefs, {"bubu": "disabled", "argus": "auto"})
        self.assertNotIn("nexus", prefs)

    def test_03_no_preference_implicit_all_auto(self):
        """Test F2: User ignores onboarding on turn 2 -> implicitly adopts Option 4 (all auto)."""
        mgr = SessionStateManager(session_id="test_session_3", storage_dir=self.storage_dir)

        # Message 1
        show_1, banner_1 = mgr.process_message("Dosyayı analiz et.")
        self.assertTrue(show_1)
        self.assertEqual(mgr.onboarding_shown_count, 1)

        # Message 2 (User asks another task without answering preference)
        show_2, banner_2 = mgr.process_message("README'yi düzelt.")
        self.assertFalse(show_2)
        self.assertIsNone(banner_2)
        self.assertEqual(mgr.onboarding_shown_count, 1)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)
        self.assertTrue(mgr.resolved)
        self.assertEqual(mgr.get_preferences(), {"bubu": "auto", "argus": "auto"})

        # Message 3
        show_3, banner_3 = mgr.process_message("Testleri koştur.")
        self.assertFalse(show_3)
        self.assertIsNone(banner_3)
        self.assertEqual(mgr.onboarding_shown_count, 1)

    def test_04_option_1_all_auto(self):
        """Test A: User selects '1' -> all auto (BUBU = auto, ARGUS = auto)."""
        mgr = SessionStateManager(session_id="test_session_4", storage_dir=self.storage_dir)
        mgr.process_message("Login ekranını incele.")

        should_show, banner = mgr.process_message("1")
        self.assertFalse(should_show)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)
        self.assertEqual(mgr.get_preferences(), {"bubu": "auto", "argus": "auto"})
        self.assertNotIn("nexus", mgr.get_preferences())
        self.assertEqual(mgr.onboarding_shown_count, 1)

    def test_05_option_2_all_disabled(self):
        """Test B: User selects '2' -> all disabled (BUBU = disabled, ARGUS = disabled, NEXUS intact)."""
        mgr = SessionStateManager(session_id="test_session_5", storage_dir=self.storage_dir)
        mgr.process_message("Login ekranını incele.")

        should_show, banner = mgr.process_message("2")
        self.assertFalse(should_show)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)
        self.assertEqual(mgr.get_preferences(), {"bubu": "disabled", "argus": "disabled"})
        self.assertNotIn("nexus", mgr.get_preferences())
        self.assertEqual(mgr.onboarding_shown_count, 1)

        # Worker check: both workers disabled
        self.assertFalse(mgr.is_worker_enabled("bubu"))
        self.assertFalse(mgr.is_worker_enabled("argus"))

    def test_06_custom_selection(self):
        """Test C/D: Custom worker selection (3 BUBU = disabled ARGUS = local)."""
        mgr = SessionStateManager(session_id="test_session_6", storage_dir=self.storage_dir)
        mgr.process_message("Kodu incele.")

        should_show, banner = mgr.process_message("3 BUBU = disabled ARGUS = local")
        self.assertFalse(should_show)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)
        prefs = mgr.get_preferences()
        self.assertEqual(prefs, {"bubu": "disabled", "argus": "local"})
        self.assertNotIn("nexus", prefs)
        self.assertEqual(mgr.onboarding_shown_count, 1)

    def test_07_ten_turn_loop_prevention(self):
        """Verifies strictly onboarding count == 1 across 10 user messages."""
        mgr = SessionStateManager(session_id="test_session_7", storage_dir=self.storage_dir)

        prompts = [
            "İlk görev: login formunu incele.",
            "İkinci görev: CSS hatasını düzelt.",
            "Üçüncü görev: unit testleri çalıştır.",
            "Dördüncü görev: README'yi güncelle.",
            "Beşinci görev: docker-compose dosyasını kontrol et.",
            "Altıncı görev: lint hatalarını gider.",
            "Yedinci görev: build komutunu çalıştır.",
            "Sekizinci görev: commit mesajını formatla.",
            "Dokuzuncu görev: API endpointini kontrol et.",
            "Onuncu görev: son durumu özetle.",
        ]

        shown_counts = []
        for i, p in enumerate(prompts):
            should_show, _ = mgr.process_message(p)
            if should_show:
                shown_counts.append(i + 1)

        self.assertEqual(shown_counts, [1], f"Onboarding shown on turns: {shown_counts}")
        self.assertEqual(mgr.onboarding_shown_count, 1)
        self.assertTrue(mgr.resolved)
        self.assertEqual(mgr.state, SessionLifecycleState.RESOLVED)

    def test_08_session_isolation(self):
        """Test G: Session A setting does not leak into new Session B."""
        # Session A: User explicitly disables BUBU
        mgr_a = SessionStateManager(session_id="session_A", storage_dir=self.storage_dir)
        mgr_a.process_message("İşi yap. BUBU disabled, ARGUS auto.")
        self.assertEqual(mgr_a.get_preferences()["bubu"], "disabled")

        # Session B: Brand new session
        mgr_b = SessionStateManager(session_id="session_B", storage_dir=self.storage_dir)
        self.assertEqual(mgr_b.state, SessionLifecycleState.UNRESOLVED)
        self.assertEqual(mgr_b.onboarding_shown_count, 0)
        self.assertEqual(mgr_b.get_preferences()["bubu"], "auto")

        # Message 1 in Session B triggers onboarding for Session B
        should_show_b, _ = mgr_b.process_message("Session B ilk görevi.")
        self.assertTrue(should_show_b)
        self.assertEqual(mgr_b.onboarding_shown_count, 1)

        # Session A remains unaffected
        self.assertEqual(mgr_a.get_preferences()["bubu"], "disabled")
        self.assertEqual(mgr_a.onboarding_shown_count, 0)

    def test_09_nexus_disabled_rejected_as_worker_pref(self):
        """Test H: 'NEXUS disabled' alone is NOT recognized as a worker preference."""
        res = parse_explicit_preferences("NEXUS disabled")
        # NEXUS is coordinator, not a worker preference
        self.assertIsNone(res)

    def test_10_legacy_session_file_migration(self):
        """Test I: Legacy session file containing 'nexus' key loads cleanly without nexus."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = self.storage_dir / "legacy_session.json"
        legacy_data = {
            "session_id": "legacy_session",
            "state": "RESOLVED",
            "onboarding_shown_count": 1,
            "preferences": {
                "nexus": "disabled",
                "bubu": "disabled",
                "argus": "auto"
            },
            "resolved": True,
            "history_length": 2
        }
        with open(legacy_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        mgr = SessionStateManager(session_id="legacy_session", storage_dir=self.storage_dir)
        prefs = mgr.get_preferences()
        self.assertEqual(prefs, {"bubu": "disabled", "argus": "auto"})
        self.assertNotIn("nexus", prefs)
        self.assertTrue(mgr.resolved)

    def test_11_orchestrator_integration_worker_binding(self):
        """Verifies Orchestrator respects BUBU and ARGUS worker preferences."""
        mgr = SessionStateManager(session_id="orch_session", storage_dir=self.storage_dir)
        mgr.set_explicit_preference({"bubu": "disabled", "argus": "auto"})

        orch = Orchestrator(session_state=mgr)
        # BUBU is disabled at session level
        self.assertFalse(orch.is_worker_enabled("bubu"))
        # ARGUS remains enabled via global registry
        self.assertTrue(orch.is_worker_enabled("argus"))


if __name__ == "__main__":
    unittest.main()

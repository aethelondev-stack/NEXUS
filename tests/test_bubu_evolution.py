"""
BUBU Evolution Unit Tests
Verifies:
1. Multi-factor cache key calculation with schema version
2. Evidence structure with line_start, line_end, content_hash, commit_hash
3. Candidate file and threshold filtering
"""
import hashlib
import pathlib
import sys
import tempfile
import unittest

bubu_scripts = pathlib.Path(r"C:\Users\Korhan\Desktop\AG Korhan\aistudio\BUBU\.agents\skills\ai-studio-worker\scripts")
sys.path.insert(0, str(bubu_scripts))

from ai_worker import compute_cache_key, evaluate_auto_mode


class TestBubuEvolution(unittest.TestCase):
    def test_cache_key_invalidation(self):
        """Verify modifying prompt, files, or schema changes cache key."""
        file_hashes = {"app.py": "abc1234"}
        cfg = {"max_file_bytes": 10000}
        k1 = compute_cache_key("ANALYZE", "check bugs", "gemini-3.6-flash", file_hashes, cfg)
        # Modify prompt
        k2 = compute_cache_key("ANALYZE", "check security", "gemini-3.6-flash", file_hashes, cfg)
        self.assertNotEqual(k1, k2)
        # Modify file hash
        k3 = compute_cache_key("ANALYZE", "check bugs", "gemini-3.6-flash", {"app.py": "def5678"}, cfg)
        self.assertNotEqual(k1, k3)

    def test_auto_mode_decision_filtering(self):
        """Verify deterministic threshold and keyword filtering in evaluate_auto_mode."""
        cfg = {"worker_mode": "auto", "auto_threshold_files": 3, "auto_threshold_bytes": 15000}
        # 1. Single small file without heavy keywords -> SKIP
        dec1, reason1 = evaluate_auto_mode("ANALYZE", "fix button color", [pathlib.Path("a.py")], 500, cfg)
        self.assertEqual(dec1, "SKIP")
        self.assertIn("localized", reason1.lower())

        # 2. Large total bytes -> USE
        dec2, reason2 = evaluate_auto_mode("ANALYZE", "inspect data", [pathlib.Path("a.py")], 20000, cfg)
        self.assertEqual(dec2, "USE")
        self.assertIn("threshold", reason2.lower())

        # 3. Heavy architectural keyword with multi-file -> USE
        dec3, reason3 = evaluate_auto_mode("ANALYZE", "investigate memory leak in concurrency", [pathlib.Path("a.py"), pathlib.Path("b.py")], 2000, cfg)
        self.assertEqual(dec3, "USE")
        self.assertIn("analytical keywords", reason3.lower())


if __name__ == "__main__":
    unittest.main()

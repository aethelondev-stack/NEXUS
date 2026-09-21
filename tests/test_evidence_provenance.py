"""
ORCHESTRATOR V3: Evidence Store & Provenance Verification Tests
Tests content-hash matching, stale file detection, and line range verification.
"""
import hashlib
import pathlib
import shutil
import tempfile
import unittest

from orchestrator.contracts import Evidence
from orchestrator.evidence_store import EvidenceStore


class TestEvidenceStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="ev_test_"))
        self.sample_file = self.temp_dir / "sample.py"
        self.sample_content = "line 1\ndef calculate():\n    return 42\n# end\n"
        self.sample_file.write_text(self.sample_content, encoding="utf-8")
        self.store = EvidenceStore(project_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_provenance_match(self):
        """Verify accurate content hash matches current file."""
        slice_text = "def calculate():\n    return 42\n"
        c_hash = hashlib.sha256(slice_text.encode("utf-8")).hexdigest()

        ev = Evidence(
            source="test",
            file="sample.py",
            line_start=2,
            line_end=3,
            content_hash=c_hash,
            commit_hash="abc1234",
            finding="Found calculate function",
            confidence=0.98
        )
        self.store.ingest(ev)
        valid, reason = self.store.verify_provenance(ev)
        self.assertTrue(valid)
        self.assertIn("Provenance verified", reason)

    def test_stale_evidence_modified_file(self):
        """Verify modifying the file flags evidence as STALE."""
        slice_text = "def calculate():\n    return 42\n"
        c_hash = hashlib.sha256(slice_text.encode("utf-8")).hexdigest()

        ev = Evidence(
            source="test",
            file="sample.py",
            line_start=2,
            line_end=3,
            content_hash=c_hash,
            commit_hash="abc1234",
            finding="Found calculate function",
            confidence=0.98
        )
        self.store.ingest(ev)

        # Modify file on disk
        self.sample_file.write_text("line 1\ndef calculate():\n    return 100\n# end\n", encoding="utf-8")
        valid, reason = self.store.verify_provenance(ev)
        self.assertFalse(valid)
        self.assertIn("Stale evidence", reason)

    def test_stale_evidence_deleted_file(self):
        """Verify deleted file flags evidence as missing."""
        ev = Evidence(
            source="test",
            file="missing.py",
            line_start=1,
            line_end=1,
            content_hash="abc",
            commit_hash="123",
            finding="Ghost file",
            confidence=0.5
        )
        valid, reason = self.store.verify_provenance(ev)
        self.assertFalse(valid)
        self.assertIn("no longer exists", reason)


if __name__ == "__main__":
    unittest.main()

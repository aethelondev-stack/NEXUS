"""
ORCHESTRATOR V3: Unified Evidence Store & Provenance Verifier
Phase 6: Multi-worker evidence ingestion, deduplication, content-hash verification,
and stale evidence detection. Standard-library only.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from orchestrator.contracts import Evidence


class EvidenceStore:
    def __init__(self, project_root: Optional[pathlib.Path] = None, store_file: Optional[pathlib.Path] = None):
        self.project_root = pathlib.Path(project_root or ".").resolve()
        if store_file:
            self.store_file = pathlib.Path(store_file)
        else:
            self.store_file = self.project_root / ".ai-worker" / "evidence_store.json"
        self._entries: Dict[str, Evidence] = {}
        self._load()

    def _load(self):
        if not self.store_file.is_file():
            return
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("items", []):
                    ev = Evidence.from_dict(item)
                    key = self._generate_key(ev)
                    self._entries[key] = ev
        except Exception:
            self._entries = {}

    def _save(self):
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        items = [ev.to_dict() for ev in self._entries.values()]
        tmp = self.store_file.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": "3.0.0", "updated_at": datetime.now(timezone.utc).isoformat(), "items": items}, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.store_file)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    @staticmethod
    def _generate_key(evidence: Evidence) -> str:
        return f"{evidence.file}:{evidence.line_start}:{evidence.line_end}:{evidence.content_hash[:16]}"

    def ingest(self, evidence: Evidence) -> str:
        """Stores evidence and returns unique key."""
        key = self._generate_key(evidence)
        self._entries[key] = evidence
        self._save()
        return key

    def ingest_batch(self, items: List[Evidence]) -> List[str]:
        keys = []
        for it in items:
            key = self._generate_key(it)
            self._entries[key] = it
            keys.append(key)
        self._save()
        return keys

    def verify_provenance(self, evidence: Evidence) -> Tuple[bool, str]:
        """
        Validates whether target file exists and content matches content_hash.
        Returns: (is_valid, reason)
        """
        target_path = self.project_root / evidence.file
        if not target_path.is_file():
            return False, f"File {evidence.file} no longer exists on disk (Stale evidence)."

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return False, f"Could not read {evidence.file}: {e}"

        max_lines = len(lines)
        if evidence.line_start < 1 or evidence.line_end > max_lines or evidence.line_start > evidence.line_end:
            return False, f"Line range [{evidence.line_start}-{evidence.line_end}] is out of bounds (file has {max_lines} lines)."

        target_slice = "".join(lines[evidence.line_start - 1 : evidence.line_end])
        curr_hash = hashlib.sha256(target_slice.encode("utf-8")).hexdigest()

        # Check full slice hash or snippet hash
        if evidence.content_hash and evidence.content_hash not in ("UNKNOWN", ""):
            if curr_hash == evidence.content_hash or hashlib.sha256(target_slice.strip().encode("utf-8")).hexdigest() == evidence.content_hash:
                return True, "Provenance verified: File content and hash match exactly."
            else:
                return False, "Stale evidence: File content has been modified since observation."

        return True, "Lines verified in current file (unhashed evidence)."

    def get_all(self) -> List[Evidence]:
        return list(self._entries.values())

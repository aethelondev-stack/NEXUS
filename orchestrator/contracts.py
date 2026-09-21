"""
ORCHESTRATOR V3: Shared Worker Contracts
Phase 4: Unified contract definitions between BUBU, ARGUS, and Orchestrator.
Standard-library only.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "3.0.0"


@dataclasses.dataclass
class Evidence:
    source: str
    file: str
    line_start: int
    line_end: int
    content_hash: str
    commit_hash: str
    finding: str
    confidence: float
    timestamp: str = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        return cls(
            source=str(data.get("source", "UNKNOWN")),
            file=str(data.get("file", "")),
            line_start=int(data.get("line_start", 1)),
            line_end=int(data.get("line_end", 1)),
            content_hash=str(data.get("content_hash", "")),
            commit_hash=str(data.get("commit_hash", "UNKNOWN")),
            finding=str(data.get("finding", "")),
            confidence=float(data.get("confidence", 0.0)),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            provenance=dict(data.get("provenance", {}))
        )


@dataclasses.dataclass
class Artifact:
    artifact_id: str
    artifact_type: str
    path: str
    content_hash: str
    created_at: str = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class WorkerError:
    error_code: str
    message: str
    retryable: bool = False
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class WorkerCapability:
    name: str
    version: str
    task_types: List[str]
    local_or_cloud: str  # "local", "cloud", "hybrid"
    requires_gpu: bool = False
    requires_api: bool = False
    estimated_cost_tier: str = "free"  # "free", "low", "medium", "high"
    max_payload_bytes: int = 500_000

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class WorkerRequest:
    task_id: str
    task_type: str  # DIRECT, CONTEXT_ANALYSIS, VISION, COMBINED, COMPLEX
    prompt: str
    files: List[str] = dataclasses.field(default_factory=list)
    parameters: Dict[str, Any] = dataclasses.field(default_factory=dict)
    max_tokens: int = 4096
    timeout_seconds: float = 60.0
    schema_version: str = SCHEMA_VERSION
    context_meta: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def compute_fingerprint(self) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.task_type.encode())
        hasher.update(self.prompt.strip().encode())
        hasher.update(";".join(sorted(self.files)).encode())
        hasher.update(json.dumps(self.parameters, sort_keys=True).encode())
        return hasher.hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerRequest":
        return cls(
            task_id=str(data["task_id"]),
            task_type=str(data.get("task_type", "DIRECT")),
            prompt=str(data.get("prompt", "")),
            files=list(data.get("files", [])),
            parameters=dict(data.get("parameters", {})),
            max_tokens=int(data.get("max_tokens", 4096)),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            context_meta=dict(data.get("context_meta", {}))
        )


@dataclasses.dataclass
class WorkerResponse:
    task_id: str
    worker_name: str
    status: str  # "success", "failed", "skipped", "fallback", "blocked", "loop_detected"
    summary: str = ""
    findings: List[str] = dataclasses.field(default_factory=list)
    evidence: List[Evidence] = dataclasses.field(default_factory=list)
    artifacts: List[Artifact] = dataclasses.field(default_factory=list)
    error: Optional[WorkerError] = None
    metrics: Dict[str, Any] = dataclasses.field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    timestamp: str = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        res = dataclasses.asdict(self)
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerResponse":
        raw_evidence = data.get("evidence", [])
        evidence_objs = [Evidence.from_dict(e) if isinstance(e, dict) else e for e in raw_evidence]
        raw_artifacts = data.get("artifacts", [])
        artifact_objs = [Artifact(**a) if isinstance(a, dict) else a for a in raw_artifacts]
        raw_error = data.get("error")
        error_obj = WorkerError(**raw_error) if isinstance(raw_error, dict) else raw_error

        return cls(
            task_id=str(data["task_id"]),
            worker_name=str(data.get("worker_name", "UNKNOWN")),
            status=str(data.get("status", "failed")),
            summary=str(data.get("summary", "")),
            findings=list(data.get("findings", [])),
            evidence=evidence_objs,
            artifacts=artifact_objs,
            error=error_obj,
            metrics=dict(data.get("metrics", {})),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat()))
        )

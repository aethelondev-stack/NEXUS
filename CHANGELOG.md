# Changelog

All notable changes to the ORCHESTRATOR project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-09-21

### Added
- **FastMCP Server Interface:** 6 standardized MCP tools (`orchestrator_status`, `orchestrator_worker_status`, `orchestrator_classify`, `orchestrator_plan`, `orchestrator_dispatch`, `orchestrator_verify`) for multi-host agent integration (Antigravity, Cursor, Claude Code, OpenCode, Generic MCP).
- **True MCP Transport for ARGUS:** `ArgusAdapter` connects directly to ARGUS FastMCP server via `mcp.client.stdio.stdio_client` and `ClientSession` with strict failure semantics (no silent shell fallbacks).
- **BUBU Project Root Anchoring:** `BubuAdapter` dynamically anchors project roots in empty workspaces, normalizes relative file paths, inherits Windows Registry credentials, and routes to low-latency cloud models.
- **Provider Quota Intelligence:** Multi-session file-locked supervisor distinguishing transient rate limits (429 RPM) from daily quota exhaustion with predictive hybrid step-downs (`NORMAL`, `CAUTIOUS`, `HYBRID`, `LOCAL_ONLY`, `BLOCKED`).
- **Deterministic Loop Breaker:** Halts immediate repeats (`A -> A`), ping-pong cycles (`A -> B -> A -> B`), and tertiary loops (`A -> B -> C -> A -> B -> C`).
- **Line-Level Evidence Provenance:** Captures file line ranges, content SHA-256 hashes, and detects STALE or modified files.
- **Empirical 6-Chain Verification Suite:** Automated test matrix covering CLI, MCP, and host integration chains without mock dependencies.
- **Packaging & Configuration:** Added `pyproject.toml`, `requirements.txt`, and `workers.example.json`.

---

## [2.0.0] - 2026-09-20
- Initial modular extraction of provider management, contracts, evidence store, and worker registry.

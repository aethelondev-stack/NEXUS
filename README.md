# NEXUS

> **Unified Multi-Worker Coordination, Quota Supervision, and Evidence Routing Layer for BUBU and ARGUS.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Standard](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io/)
[![Ecosystem: BUBU + ARGUS + NEXUS](https://img.shields.io/badge/Ecosystem-BUBU%20%2B%20ARGUS%20%2B%20NEXUS-blueviolet.svg)](#-the-ecosystem-bubu--argus--nexus)

---

## 📑 Table of Contents
- [🌐 The Ecosystem: BUBU + ARGUS + NEXUS](#-the-ecosystem-bubu--argus--nexus)
- [What is NEXUS?](#what-is-nexus)
- [Architecture](#architecture)
- [One System, Many Projects (Zero File Copying)](#one-system-many-projects-zero-file-copying)
- [Works With Your Coding Agent](#works-with-your-coding-agent)
  - [Antigravity](#antigravity)
  - [Cursor](#cursor)
  - [Claude Code](#claude-code)
  - [OpenCode](#opencode)
  - [Generic MCP Hosts](#generic-mcp-hosts)
- [Setup & User Preference Experience](#setup--user-preference-experience)
- [Central Capability & Proof Matrix](#central-capability--proof-matrix)
- [Real Multi-Worker Composite Workflow Proof](#real-multi-worker-composite-workflow-proof)
- [Global Worker Registry (`workers.json`)](#global-worker-registry-workersjson)
- [MCP Server Setup & Tools Reference](#mcp-server-setup--tools-reference)
- [Components](#components)
- [Requirements & Installation](#requirements--installation)
- [Installing BUBU](#installing-bubu)
- [Installing ARGUS](#installing-argus)
- [Troubleshooting](#troubleshooting)
- [Security & API Key Handling](#security--api-key-handling)
- [Cross-Platform Support](#cross-platform-support)
- [Development & Testing](#development--testing)
- [Repository Structure](#repository-structure)
- [License](#license)

---

## 🌐 The Ecosystem: BUBU + ARGUS + NEXUS

NEXUS does **not** replace specialized workers—it is the unified coordinator that brings them together into an autonomous execution pipeline:

| System | Role | Repository Link | Primary Responsibility |
| :--- | :--- | :--- | :--- |
| **BUBU** | LLM / Context Worker | [github.com/aethelondev-stack/BUBU](https://github.com/aethelondev-stack/BUBU) | Deep multi-file code audits, memory leak detection, and research offloading. |
| **ARGUS** | Vision Shield Worker | [github.com/aethelondev-stack/ARGUS](https://github.com/aethelondev-stack/ARGUS) | On-device visual grounding, desktop/emulator inspection, and token bleeding prevention. |
| **NEXUS** | Coordination Layer | [github.com/aethelondev-stack/NEXUS](https://github.com/aethelondev-stack/NEXUS) | Task routing, quota supervision, loop breaking, evidence aggregation, and workflow coordination. |

```text
                                  User / Coding Agent
                                           │
                                           ▼
                                         NEXUS
                     (Orchestration, Routing, Evidence, Workflow)
                               ┌───────────┴───────────┐
                               ▼                       ▼
                             BUBU                    ARGUS
                        (Context / LLM)         (Vision / UI)
```

---

## What is NEXUS?

**NEXUS** (formerly ORCHESTRATOR V3) is an open, Model Context Protocol (MCP)-accessible agent runtime supervisor. It acts as the central intermediary between primary AI coding agents (Antigravity, Cursor, Claude Code, OpenCode) and specialized execution workers:

### Core Capabilities
1. **Direct Path First:** Micro-edits and single-file tasks bypass workers with zero latency and zero token overhead.
2. **Provider Quota Intelligence:** Persistently tracks rate limits (429 RPM/TPM) vs daily quota exhaustion across agent sessions, eliminating retry storms and API token exhaustion.
3. **Predictive Hybrid Routing:** Dynamically steps down from cloud LLMs to local deterministic operations and on-device GPU processing under high rate pressure.
4. **Line-Level Evidence Provenance:** Captures file line ranges, content SHA-256 hashes, and detects STALE or modified evidence on disk before actions execute.
5. **Infinite-Loop & Ping-Pong Breaker:** Halts immediate repeats (`A -> A`), alternating cycles (`A -> B -> A -> B`), and tertiary cycles (`A -> B -> C -> A -> B -> C`) deterministically.
6. **Multi-Worker Composite Workflow Coordination:** Coordinates sequential multi-worker workflows (e.g. BUBU code analysis + ARGUS desktop inspection) via a single public call `execute_workflow()` and aggregates results into a unified `WorkerResponse(worker_name="composite")`.

> **Technical Note on Architecture & Compatibility:** While the project brand and documentation are officially **NEXUS**, internal Python modules and MCP tool endpoints remain named `orchestrator` (e.g., `orchestrator.py`, `orchestrator_dispatch`) to maintain 100% backward compatibility with existing MCP client configuration files.

---

## Architecture

```text
       Primary Coding Agent (Antigravity / Cursor / Claude Code / OpenCode)
                                        │
                                        │ (Model Context Protocol - Stdio JSON-RPC)
                                        ▼
                     ┌─────────────────────────────────────┐
                     │              NEXUS MCP              │
                     │       (orchestrator/mcp_server)     │
                     │                                     │
                     │  • Direct Path Router               │
                     │  • Deterministic Classifier         │
                     │  • Infinite-Loop Breaker            │
                     │  • Multi-Session Provider Manager   │
                     │  • Line-Level Evidence Store        │
                     │  • Multi-Worker Workflow Engine     │
                     └──────────────────┬──────────────────┘
                                        │
                                        ▼
                     ┌─────────────────────────────────────┐
                     │       GLOBAL WORKER REGISTRY        │
                     │    (~/.gemini/orchestrator/         │
                     │         workers.json)               │
                     └──────────┬─────────────────┬────────┘
                                │                 │
               CLI Subprocess   │                 │ MCP Client Stdio
             (Safe Path Anchor) │                 │ (JSON-RPC)
                                ▼                 ▼
                     ┌──────────────────┐  ┌──────────────────┐
                     │       BUBU       │  │      ARGUS       │
                     │  Context Worker  │  │  Vision Shield   │
                     │  (ai_worker.py)  │  │   (server.py)    │
                     └─────────┬────────┘  └─────────┬────────┘
                                │                     │
                     External Cloud LLM        Local GPU / Win32
                    (Gemini / OpenAI API)     (Florence-2 / Desktop)
                                │                     │
                                └──────────┬──────────┘
                                           │ Structured Findings & Evidence
                                           ▼
                               Single Composite Response
```

---

## One System, Many Projects (Zero File Copying)

Earlier agent tooling models required developers to manually copy worker scripts, skill folders, and configuration templates into every individual repository:

```text
[Legacy Model: Repetitive File Duplication]
Project A ──► Copy BUBU (.agents/skills/...) ──► Copy ARGUS (.agents/skills/...)
Project B ──► Copy BUBU (.agents/skills/...) ──► Copy ARGUS (.agents/skills/...)
Project C ──► Copy BUBU (.agents/skills/...) ──► Copy ARGUS (.agents/skills/...)
```

NEXUS establishes a centralized, project-independent architecture:

```text
[NEXUS Model: Centralized Multi-Project System]
                                  NEXUS
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
   Project A                    Project B                    Project C
(Clean codebase)             (Clean codebase)             (Clean codebase)
```

### How Project Independence Works
1. **Central Worker Registry:** Worker locations are defined once in `$HOME/.gemini/orchestrator/workers.json`.
2. **Central FastMCP Server:** The NEXUS MCP server runs globally from its installation directory.
3. **Safe Target Anchoring:** When an agent invokes NEXUS to inspect files in `Project A`, `BubuAdapter` dynamically anchors execution relative to `Project A`'s directory without polluting it with duplicated source files.
4. **Optional Local Overrides:** Projects do not need configuration files. However, if a project specifically requires disabling a worker, a minimal 2-line JSON (`.ai-worker/config.json` or `.argus/config.json`) acts as an optional workspace override.

> **Scope & Scalability Note:** The central registry (`workers.json`), global FastMCP stdio server, and dynamic directory anchoring (`BubuAdapter._resolve_target_dir_and_files`) architecturally decouple worker installations from individual project trees. While this eliminates the need for copying `.agents/` or worker folders into new projects, empirical verification has been conducted across targeted test workspaces; unlimited concurrent projects have not been benchmarked.

---

## Works With Your Coding Agent

NEXUS integrates with coding agents using the open **Model Context Protocol (MCP 1.0)** standard over stdio.

> **Important:** NEXUS does **not** require proprietary closed-source plugins. Any client that supports MCP stdio can supervise tasks through NEXUS.
>
> **Validation Note:** Antigravity is the primary empirical runtime where MCP tools and multi-worker workflows are continuously tested and proven. Cursor, Claude Code, and OpenCode interact through the standard FastMCP stdio interface. While MCP protocol compatibility is verified, end-to-end task flows inside third-party graphical client UIs have not been tested individually.

### Antigravity
Add to `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "orchestrator": {
      "command": "python",
      "args": ["C:\\Tools\\NEXUS\\orchestrator\\mcp_server.py"],
      "env": { "PYTHONPATH": "C:\\Tools\\NEXUS" }
    }
  }
}
```

### Cursor
Add to `.cursor/mcp.json` or Cursor Settings -> Features -> MCP:
```json
{
  "mcpServers": {
    "orchestrator": {
      "command": "python",
      "args": ["C:\\Tools\\NEXUS\\orchestrator\\mcp_server.py"],
      "env": { "PYTHONPATH": "C:\\Tools\\NEXUS" }
    }
  }
}
```

### Claude Code
Add via CLI or configuration file (`~/.claude.json`):
```bash
claude mcp add orchestrator python C:\Tools\NEXUS\orchestrator\mcp_server.py -e PYTHONPATH=C:\Tools\NEXUS
```

### OpenCode
Add to `opencode.json`:
```json
{
  "mcp": {
    "orchestrator": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\Tools\\NEXUS\\orchestrator\\mcp_server.py"],
      "env": { "PYTHONPATH": "C:\\Tools\\NEXUS" }
    }
  }
}
```

### Generic MCP Hosts
Command: `python`
Arguments: `["<path-to-NEXUS>/orchestrator/mcp_server.py"]`
Environment: `{"PYTHONPATH": "<path-to-NEXUS>"}`

---

## Setup & User Preference Experience

NEXUS enforces a non-intrusive, user-first operational contract based on clear architectural separation:

### 1. Architectural Model: Host Coordinator vs. Leaf Workers
* **NEXUS (Always-On Host Coordinator):** NEXUS is the central orchestration and routing backbone. It is not an optional worker that can be disabled—it is always active to classify tasks, manage quotas, break infinite loops, and aggregate evidence.
* **BUBU & ARGUS (Specialized Workers):** User preferences specifically govern the activation and execution modes of the leaf workers:
  * **BUBU:** `auto` (Recommended smart hybrid) | `enabled` (Always active) | `disabled` (Turned off).
  * **ARGUS:** `auto` (Recommended smart hybrid) | `local` (GPU Florence-2 only) | `direct` (Turned off).

### 2. One-Time Session Preference Onboarding Protocol
Every new conversation starts with an isolated session lifecycle (`UNRESOLVED` -> `WAITING_FOR_REPLY` -> `RESOLVED`):
1. **Turn 1 (First Message):** The lead agent **always fulfills the user's task first**. If no explicit worker preference was provided in the prompt, a one-time onboarding banner is appended to the response:
   - **Option 1 (Hepsi AUTO):** `BUBU = auto`, `ARGUS = auto` (NEXUS routes dynamically: simple edits -> Direct Path, audits -> BUBU, visual -> ARGUS).
   - **Option 2 (Hepsi KAPALI):** `BUBU = disabled`, `ARGUS = disabled` (NEXUS bypasses workers entirely; all tasks route to Lead Agent with zero worker overhead).
   - **Option 3 (Özel Seçim):** Custom combinations (e.g. `BUBU disabled, ARGUS local`).
   - **Option 4 (Default / No Reply):** If the user ignores the banner and sends a new task, **Option 1 (All AUTO)** is automatically resolved.
2. **Turn 2+ (Subsequent Messages):** Once resolved, the session is locked. **The onboarding banner is never displayed again** (guaranteed `onboarding_shown_count = 1`).
3. **Session Isolation:** Preferences are strictly session-scoped (`Session A != Session B`) via `ANTIGRAVITY_CONVERSATION_ID`. No configuration files (`.ai-worker/`, `.argus/`) are ever written to project workspaces.
4. **Fallback Mechanics:** If a worker is configured as `disabled`:
   - Automatic routing falls back to `DIRECT_FALLBACK` (delegated to Lead Agent).
   - Explicit dispatch (`worker="bubu"`) halts safely with `WORKER_NOT_AVAILABLE` without launching subprocesses.

---

## Central Capability & Proof Matrix

| Capability | Status | Evidence / Implementation |
| :--- | :---: | :--- |
| **BUBU Real Execution** | **PROVEN** | [`bubu_adapter.py`](orchestrator/adapters/bubu_adapter.py) via real Gemini Cloud API (`gemini-3.5-flash-lite`). |
| **ARGUS Real Execution** | **PROVEN** | [`argus_adapter.py`](orchestrator/adapters/argus_adapter.py) via real FastMCP Stdio RPC (`smart_ui_desktop_items`). |
| **NEXUS Sequential Workflow** | **PROVEN** | [`Orchestrator.execute_workflow()`](orchestrator/orchestrator.py) single public multi-worker invocation. |
| **Composite Response Aggregation** | **PROVEN** | Unified `WorkerResponse(worker_name="composite")` containing combined findings & evidence. |
| **Evidence Store Ingestion** | **PROVEN** | Line-level SHA-256 evidence hashing in [`evidence_store.py`](orchestrator/evidence_store.py). |
| **Fail-Fast Error Semantics** | **PROVEN** | Aborts subsequent steps immediately upon step failure, preserving step telemetry. |
| **MCP Workflow Dispatch** | **PROVEN** | `orchestrator_dispatch(steps=[...])` in [`mcp_server.py`](orchestrator/mcp_server.py). |
| **Non-Blocking Preference Flow** | **PROVEN** | `is_worker_enabled()` routing checks with zero-overhead fallback. |
| **Concurrent Workflow Execution** | *Not Proven* | Out of scope. Workflows execute sequentially (`for step in steps:`). |
| **Shared Inter-Worker State** | *Not Proven* | Out of scope. `workflow_id` serves as a correlation ID, not a shared state store. |
| **Worker Data Piping (BUBU -> ARGUS)** | *Not Proven* | Out of scope. Steps are executed as independent tasks within a composite workflow. |

---

## Real Multi-Worker Composite Workflow Proof

NEXUS includes an automated empirical test verifying that Orchestrator Core acts as a unified coordinator: executing multiple specialized workers—**BUBU** (Cloud LLM) and **ARGUS** (On-device Vision Shield)—via a single public workflow invocation (`orch.execute_workflow(...)`).

Detailed architectural proof documentation is available at:
👉 [`docs/PROOF_MULTI_WORKER_WORKFLOW.md`](docs/PROOF_MULTI_WORKER_WORKFLOW.md)

### Automated Test Command
```powershell
python tests/verify_composite_workflow.py
```

### Empirical Execution Output
```text
====================================================================
ORCHESTRATOR V3: COMPOSITE MULTI-WORKER WORKFLOW EXECUTION PROOF
Single Public Call: orch.execute_workflow([req_bubu, req_argus])
====================================================================
[+] Test Invariant Check: PASS (0 execute_task calls, 0 adapter imports in test)
[*] Workflow ID         : wf-exp-20260921234547-9b0298
[*] Desktop Marker Target: 0_COMPOSITE_WORKFLOW_MARKER_da2b46.txt
[*] Gemini API Credential: CONFIGURED
[+] Global Registry: Temporarily set enabled=True for BUBU & ARGUS.
[+] Created Fixture: composite_fixture_da2b46.py (SHA-256: 9b099ff311a89a0b...)
[+] Created Desktop Marker: 0_COMPOSITE_WORKFLOW_MARKER_da2b46.txt

--- Phase 1: Executing Single Public Workflow Call ---

--- Phase 2: Inspecting Orchestrator Composite Response ---
[COMPOSITE] Worker Name    : composite
[COMPOSITE] Workflow Status: success
[COMPOSITE] Total Duration : 4.606s
[COMPOSITE] Steps Executed : 2/2
[COMPOSITE] Total Findings : 18
[COMPOSITE] Total Evidence : 4
       Step 1 (BUBU) : success (3 findings, 4 evidence)
       Step 2 (ARGUS): success (46 items, transport=mcp)
[COMPOSITE] Desktop Marker Found: True
[+] Saved Evidence Artifact: tests\artifacts\last_composite_workflow.json

====================================================================
WORKFLOW PROOF RESULT: 100% PASS (Composite Multi-Worker Workflow Proven)
====================================================================

--- Cleanup & Safety Restoration ---
[+] Cleaned up desktop marker: 0_COMPOSITE_WORKFLOW_MARKER_da2b46.txt
[+] Cleaned up test fixture: composite_fixture_da2b46.py
[+] Global Registry: Successfully restored original pre-test state (disabled=false).
```

---

## Global Worker Registry (`workers.json`)

The global worker registry is located at:
- **Windows:** `C:\Users\<username>\.gemini\orchestrator\workers.json`
- **Linux / macOS:** `~/.gemini/orchestrator/workers.json`

### Supported Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `worker_id` | string | Unique worker identifier (`bubu`, `argus`). |
| `worker_type` | string | Category: `context_analysis`, `vision`, `security`, `custom`. |
| `name` | string | Human-readable name. |
| `description` | string | Short functional summary. |
| `transport` | string | Transport protocol: `"cli"` (subprocess) or `"mcp"` (stdio client). |
| `entrypoint` | string | Executable script path or alias. |
| `server_path` | string (optional) | Path to server script when `transport: "mcp"` (e.g. `server.py`). |
| `python_executable` | string | Python binary to invoke (`python` or path to virtualenv). |
| `capabilities` | array of strings | Capabilities supported by the worker. |
| `tools` | array of strings | Tool names exposed by the worker (for MCP transport). |
| `enabled` | boolean | Toggle worker activation. |
| `timeout_seconds` | float | Execution timeout (default: 60s for BUBU, 30s for ARGUS). |
| `execution_mode` | string | `cloud_hybrid`, `local_gpu`, or `local_process`. |
| `cost_characteristics` | object | Budget tier, cloud quota flags, and offline decide support. |

---

## MCP Server Setup & Tools Reference

NEXUS runs as a standard **FastMCP stdio server**:
- **Entrypoint:** `orchestrator/mcp_server.py`
- **Tools Exposed:**
  1. `orchestrator_status`: Returns provider states, quota consumption, and loop detector metrics.
  2. `orchestrator_worker_status`: Returns live health and availability of registered workers.
  3. `orchestrator_classify`: Deterministically classifies prompts and file sets.
  4. `orchestrator_plan`: Builds an execution plan with quota and token preflight estimates.
  5. `orchestrator_dispatch`: Executes single tasks or ordered composite workflows (`steps=[...]`).
  6. `orchestrator_verify`: Validates line-level evidence freshness against local disk files.

---

## Components

| Component | Repository Path | Role |
| :--- | :--- | :--- |
| **`orchestrator.orchestrator`** | `orchestrator/orchestrator.py` | State machine, classification, loop detection, and workflow execution. |
| **`orchestrator.provider_manager`** | `orchestrator/provider_manager.py` | Persistent quota tracking (`provider_state.json`) and multi-session locks. |
| **`orchestrator.evidence_store`** | `orchestrator/evidence_store.py` | Line-level SHA-256 provenance and stale file detection. |
| **`orchestrator.worker_registry`** | `orchestrator/worker_registry.py` | Worker discovery and validation from `workers.json`. |
| **`orchestrator.mcp_server`** | `orchestrator/mcp_server.py` | FastMCP stdio server exposing tools to agent hosts. |
| **`orchestrator.cli`** | `orchestrator/cli.py` | Standalone CLI for status inspection and dispatch. |
| **`orchestrator.adapters.bubu_adapter`** | `orchestrator/adapters/bubu_adapter.py` | Subprocess CLI bridge to BUBU with project anchoring. |
| **`orchestrator.adapters.argus_adapter`** | `orchestrator/adapters/argus_adapter.py` | FastMCP stdio client bridge to ARGUS. |

---

## Requirements & Installation

- **OS:** Windows 10/11 (Recommended for ARGUS desktop vision), Linux, or macOS.
- **Python:** Python `>= 3.10` (AMD64 / x86_64).
- **Core Dependencies:** `fastmcp>=0.4.0`, `mcp>=1.0.0`, `pydantic>=2.0.0`.

```powershell
# 1. Clone NEXUS repository
git clone https://github.com/aethelondev-stack/NEXUS.git C:\Tools\NEXUS

# 2. Navigate and install dependencies
cd C:\Tools\NEXUS
pip install -r requirements.txt

# 3. Create global configuration directory
mkdir -Force $HOME\.gemini\orchestrator
mkdir -Force $HOME\.gemini\provider-state

# 4. Copy template worker registry
Copy-Item workers.example.json $HOME\.gemini\orchestrator\workers.json

# 5. Verify CLI functionality
python -m orchestrator.cli --status
```

---

## Installing BUBU

[BUBU](https://github.com/aethelondev-stack/BUBU) is a provider-agnostic LLM context worker built with zero external dependencies (100% Python standard library).

```powershell
git clone https://github.com/aethelondev-stack/BUBU.git C:\Tools\BUBU
```

Set your Gemini API key in your environment:
```powershell
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your_key_here', 'User')
```

Health check:
```powershell
python "C:\Tools\BUBU\.agents\skills\ai-studio-worker\scripts\ai_worker.py" --dry-run
```

---

## Installing ARGUS

[ARGUS](https://github.com/aethelondev-stack/ARGUS) is an on-device vision shield and token guardian utilizing local GPU acceleration and FastMCP.

```powershell
git clone https://github.com/aethelondev-stack/ARGUS.git C:\Tools\ARGUS
cd C:\Tools\ARGUS
pip install -r requirements.txt
```

---

## Troubleshooting

### 1. MCP Server Does Not Appear in Host
- **Symptom:** Host reports `Server not found` or `failed to connect`.
- **Cause:** Incorrect `PYTHONPATH` or invalid Python path in host MCP JSON.
- **Fix:** Ensure `PYTHONPATH` points to the NEXUS root:
  ```json
  "env": { "PYTHONPATH": "C:\\Tools\\NEXUS" }
  ```

### 2. BUBU Path Traversal or Project Root Failure
- **Symptom:** BUBU returns `Path traversal detected or file outside project`.
- **Fix:** `BubuAdapter` automatically normalizes file paths relative to target directory.

### 3. BUBU Cloud Model Read Timeout
- **Symptom:** BUBU hangs and times out.
- **Fix:** `BubuAdapter` passes active low-latency model `--model gemini-3.5-flash-lite`.

### 4. ARGUS Child-Process Timeout (>30s)
- **Symptom:** ARGUS dispatches time out.
- **Fix:** `ArgusAdapter` connects directly to ARGUS FastMCP server via `mcp.client.stdio.stdio_client` with strict failure semantics.

---

## Security & API Key Handling

1. **Zero Hardcoded Secrets:** Never commit API keys, tokens, or credentials to Git.
2. **Environment Variable Precedence:** Keys are read from environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`) or Windows User Registry (`HKCU\Environment`).
3. **Local State Hygiene:** State files (`provider_state.json`, `evidence_store.json`, `*.lock`) are strictly ignored in `.gitignore`.

---

## Cross-Platform Support

| Feature | Windows | Linux | macOS |
| :--- | :---: | :---: | :---: |
| **NEXUS Core** | ✅ Supported | ✅ Supported | ✅ Supported |
| **Provider Quota Intelligence** | ✅ Supported | ✅ Supported | ✅ Supported |
| **Evidence Store** | ✅ Supported | ✅ Supported | ✅ Supported |
| **FastMCP Server** | ✅ Supported | ✅ Supported | ✅ Supported |
| **BUBU Context Worker** | ✅ Supported | ✅ Supported | ✅ Supported |
| **ARGUS Vision Shield** | ✅ Full Desktop & ADB | ⚠️ Limited to ADB / Headless | ⚠️ Limited to ADB / Headless |

---

## Development & Testing

Run the full test suite:
```powershell
python -m unittest discover -s tests
python tests/verify_root_cause_chains.py
python tests/verify_composite_workflow.py
```

---

## Repository Structure

```text
NEXUS/
├── .gitignore
├── LICENSE                          # MIT License
├── README.md                        # Master Documentation
├── pyproject.toml                   # Package Metadata & CLI Entrypoints
├── requirements.txt                 # Runtime Dependencies
├── workers.example.json             # Canonical Worker Registry Template
├── docs/
│   ├── HYBRID_MODE.md               # Predictive Hybrid Level Specs
│   ├── PROVIDER_QUOTA.md            # Quota Taxonomy & Error Codes
│   └── PROOF_MULTI_WORKER_WORKFLOW.md # Multi-Worker Empirical Verification
├── orchestrator/
│   ├── __init__.py
│   ├── cli.py                       # CLI Utilities (--status, --classify)
│   ├── contracts.py                 # Dataclasses (WorkerRequest, Evidence)
│   ├── evidence_store.py            # SHA-256 Provenance & Stale Detection
│   ├── mcp_server.py                # FastMCP Stdio Server (6 Tools)
│   ├── orchestrator.py              # Central Routing & Loop Detector
│   ├── provider_manager.py          # Quota Manager & Multi-Session Locks
│   ├── worker_registry.py           # Worker Discovery & Health Checks
│   └── adapters/
│       ├── __init__.py
│       ├── base.py                  # BaseWorkerAdapter Interface
│       ├── bubu_adapter.py          # BUBU CLI Adapter with Safe Anchoring
│       └── argus_adapter.py         # ARGUS FastMCP Transport Adapter
└── tests/
    ├── test_adapters.py             # Adapter Dry-Run & Quota Block Tests
    ├── test_argus_evolution.py      # Circuit Breaker & Privacy Tests
    ├── test_bubu_evolution.py       # Multi-factor Cache Key Tests
    ├── test_evidence_provenance.py  # Provenance & Hash Tests
    ├── test_mcp_adapter.py          # FastMCP Tool Binding Tests
    ├── test_quota_manager.py        # 429 Quota & Loop Detection Tests
    ├── test_worker_registry.py      # Registry Discovery Tests
    ├── verify_root_cause_chains.py  # Empirical 6-Chain Integration Matrix
    ├── verify_composite_workflow.py # Real Composite Multi-Worker Workflow Proof
    └── artifacts/                   # Sanitized Machine-Readable Evidence Run Logs
```

---

## License

- **NEXUS:** Licensed under the [MIT License](LICENSE). Copyright (c) 2026 aethelondev-stack.
- **BUBU:** Licensed under the [BUBU Source-Available & Commercial License (Version 1.0)](https://github.com/aethelondev-stack/BUBU).
- **ARGUS:** Licensed under the [MIT License](https://github.com/aethelondev-stack/ARGUS).

# ORCHESTRATOR V3

> **Production-Grade Agent Orchestrator, Quota Supervisor, and Multi-Worker Evidence Coordinator for MCP-Compatible AI Coding Agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Standard](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io/)
[![Architecture: V3](https://img.shields.io/badge/Architecture-V3-purple.svg)](#architecture)

---

## 📑 Table of Contents
- [What is Orchestrator?](#what-is-orchestrator)
- [Architecture](#architecture)
- [Components](#components)
- [Requirements](#requirements)
- [Installation Quick Start](#installation-quick-start)
- [Dependency & Worker Model](#dependency--worker-model)
- [Installing BUBU](#installing-bubu)
- [Installing ARGUS](#installing-argus)
- [Global Worker Registry (`workers.json`)](#global-worker-registry-workersjson)
- [MCP Server Setup](#mcp-server-setup)
- [Agent Host Integrations](#agent-host-integrations)
  - [Antigravity](#antigravity)
  - [Cursor](#cursor)
  - [Claude Code](#claude-code)
  - [OpenCode](#opencode)
  - [Generic MCP Hosts](#generic-mcp-hosts)
- [MCP Tools Reference](#mcp-tools-reference)
- [Configuration & State Management](#configuration--state-management)
- [Verification & Smoke Tests](#verification--smoke-tests)
- [Real Multi-Worker Composite Workflow Proof](#real-multi-worker-composite-workflow-proof)
- [Troubleshooting](#troubleshooting)
- [Security & API Key Handling](#security--api-key-handling)
- [Cross-Platform Support](#cross-platform-support)
- [Development & Testing](#development--testing)
- [Repository Structure](#repository-structure)
- [License](#license)

---

## What is Orchestrator?

**ORCHESTRATOR** is an open, Model Context Protocol (MCP)-accessible agent runtime supervisor. It acts as an intelligent intermediary between your primary AI coding agent (e.g. Antigravity Lead Agent, Cursor, Claude Code, OpenCode) and specialized execution workers:

- **BUBU Context Worker:** High-capacity LLM context engine for deep multi-file architectural audits, memory leak detection, and codebase diff investigation.
- **ARGUS Vision Shield:** On-device visual grounding engine using local GPU and FastMCP for desktop inspection, UI automation, and perceptual circuit breaking.

### Why Orchestrator?
1. **Direct Path First:** Micro-edits and single-file tasks bypass workers with zero latency and zero token overhead.
2. **Provider Quota Intelligence:** Persistently tracks rate limits (429 RPM/TPM) vs daily quota exhaustion across agent sessions, eliminating retry storms and API token exhaustion.
3. **Predictive Hybrid Routing:** Dynamically steps down from cloud LLMs to local deterministic operations and on-device GPU processing under high rate pressure.
4. **Line-Level Evidence Provenance:** Captures file line ranges, content SHA-256 hashes, and detects STALE or modified evidence on disk before actions execute.
5. **Infinite-Loop & Ping-Pong Breaker:** Halts immediate repeats (`A -> A`), alternating cycles (`A -> B -> A -> B`), and tertiary cycles (`A -> B -> C -> A -> B -> C`) deterministically.

---

## Architecture

```text
       Primary Coding Agent (Antigravity / Cursor / Claude Code / OpenCode)
                                        │
                                        │ (Model Context Protocol - Stdio JSON-RPC)
                                        ▼
                     ┌─────────────────────────────────────┐
                     │          ORCHESTRATOR MCP           │
                     │                                     │
                     │  • Direct Path Router               │
                     │  • Deterministic Classifier         │
                     │  • Infinite-Loop Breaker            │
                     │  • Multi-Session Provider Manager   │
                     │  • Line-Level Evidence Store        │
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
                                     Lead Agent
```

---

## Components

| Component | Repository Path / Module | Role |
| :--- | :--- | :--- |
| **`orchestrator.orchestrator`** | `orchestrator/orchestrator.py` | Main state machine, classification, loop detection, and task execution pipeline. |
| **`orchestrator.provider_manager`** | `orchestrator/provider_manager.py` | Persistent quota tracking (`provider_state.json`), bounded backoff, multi-session lock. |
| **`orchestrator.evidence_store`** | `orchestrator/evidence_store.py` | Line-level content hashing (SHA-256), stale file detection, and evidence verification. |
| **`orchestrator.worker_registry`** | `orchestrator/worker_registry.py` | Global worker discovery and validation from `workers.json`. |
| **`orchestrator.mcp_server`** | `orchestrator/mcp_server.py` | FastMCP stdio server exposing 6 standardized tools to agent hosts. |
| **`orchestrator.cli`** | `orchestrator/cli.py` | Standalone CLI for status inspection, classification, and test dispatch. |
| **`orchestrator.adapters.bubu_adapter`** | `orchestrator/adapters/bubu_adapter.py` | Subprocess CLI bridge to BUBU with project root anchoring and registry API key inheritance. |
| **`orchestrator.adapters.argus_adapter`** | `orchestrator/adapters/argus_adapter.py` | Real MCP stdio client bridge to ARGUS with strict failure semantics. |

---

## Requirements

- **Operating System:** Windows 10/11 (Recommended for full ARGUS desktop vision capabilities), Linux, or macOS.
- **Python:** Python `>= 3.10` (AMD64 / x86_64).
- **Core Dependencies:**
  - `fastmcp>=0.4.0`
  - `mcp>=1.0.0`
  - `pydantic>=2.0.0`
- **Optional Worker Requirements:**
  - **BUBU:** Python 3.10+ (Standard library only; requires `GEMINI_API_KEY` or `OPENAI_API_KEY` for cloud analysis).
  - **ARGUS:** NVIDIA GPU with CUDA support recommended for Florence-2 vision model; PyTorch, OpenCV, Pillow, PyAutoGUI.

---

## Installation Quick Start

```powershell
# 1. Clone Orchestrator repository
git clone https://github.com/aethelondev-stack/ORCHESTRATOR.git C:\Tools\ORCHESTRATOR

# 2. Navigate to directory and install dependencies
cd C:\Tools\ORCHESTRATOR
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

## Dependency & Worker Model

Orchestrator enforces a strict separation of concerns:

- **ORCHESTRATOR Core:** **Standalone & Required**. Operates independently. Direct Path tasks (`TaskClassification.DIRECT`) execute without workers.
- **BUBU:** **Optional (Recommended)**. Needed only if you require offloaded multi-file context audits, large log investigations, or deep codebase architecture reviews.
- **ARGUS:** **Optional (Recommended for GUI/Desktop agents)**. Needed only if you require on-device screen capture, desktop shortcut enumeration, or local visual grounding.

> **Important:** You do **not** need to copy the BUBU or ARGUS repositories into the Orchestrator directory. Orchestrator discovers workers globally via `workers.json` using absolute filesystem paths.

---

## Installing BUBU

[BUBU](https://github.com/aethelondev-stack/BUBU) is an AI Studio context-processing worker specialized in zero-token-waste context analysis.

### 1. Clone BUBU
```powershell
git clone https://github.com/aethelondev-stack/BUBU.git C:\Tools\BUBU
```

### 2. Expected Directory Structure
```text
C:\Tools\BUBU\
├── .agents\
│   └── skills\
│       └── ai-studio-worker\
│           └── scripts\
│               └── ai_worker.py    <-- Canonical Entrypoint
├── LICENSE
└── README.md
```

### 3. Dependencies & Credentials
`ai_worker.py` is written entirely with Python standard libraries (`urllib.request`, `json`, `hashlib`, `pathlib`). No extra pip packages are required.

Set your Gemini API key in your environment or Windows User Registry:
```powershell
# In PowerShell:
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your_gemini_api_key', 'User')
```

### 4. Register BUBU in `workers.json`
Edit `$HOME\.gemini\orchestrator\workers.json`:
```json
{
  "workers": {
    "bubu": {
      "worker_id": "bubu",
      "worker_type": "context_analysis",
      "name": "BUBU Context Worker",
      "description": "AI Studio context worker for multi-file architectural analysis.",
      "transport": "cli",
      "entrypoint": "C:\\Tools\\BUBU\\.agents\\skills\\ai-studio-worker\\scripts\\ai_worker.py",
      "python_executable": "python",
      "capabilities": ["context_analysis", "code_audit", "multi_file_analysis"],
      "enabled": true,
      "timeout_seconds": 60,
      "execution_mode": "cloud_hybrid"
    }
  }
}
```

### 5. Health Check
```powershell
python "C:\Tools\BUBU\.agents\skills\ai-studio-worker\scripts\ai_worker.py" --dry-run
```
Expected output: JSON containing `"status": "dry_run_success"`.

---

## Installing ARGUS

[ARGUS](https://github.com/aethelondev-stack/ARGUS) is an on-device vision shield and token guardian utilizing local GPU acceleration and FastMCP.

### 1. Clone ARGUS
```powershell
git clone https://github.com/aethelondev-stack/ARGUS.git C:\Tools\ARGUS
```

### 2. Expected Directory Structure & Dependencies
```text
C:\Tools\ARGUS\
├── server.py             <-- FastMCP Server Entrypoint
├── engine.py             <-- Local Vision & UI Engine
├── requirements.txt
└── README.md
```

Install ARGUS dependencies:
```powershell
cd C:\Tools\ARGUS
pip install -r requirements.txt
```

### 3. How Orchestrator Connects to ARGUS
Orchestrator communicates with ARGUS via standard **MCP stdio JSON-RPC**:
```text
Orchestrator (ArgusAdapter)
        │
        │ MCP Client Stdio Transport
        ▼
ARGUS FastMCP Server (server.py)
        │
        ▼
ARGUS Tools (smart_ui_desktop_items, smart_ui_scan, smart_ui_click, smart_ui_reset)
```
> **Architecture Note:** Orchestrator does **not** spawn separate `engine.py` or `UIEngine` subprocesses. It connects directly to the ARGUS FastMCP server declared in `workers.json` (`transport: mcp`).

### 4. Register ARGUS in `workers.json`
Edit `$HOME\.gemini\orchestrator\workers.json`:
```json
{
  "workers": {
    "argus": {
      "worker_id": "argus",
      "worker_type": "vision",
      "name": "ARGUS Vision Shield",
      "description": "Local GPU vision and desktop automation shield.",
      "transport": "mcp",
      "entrypoint": "argus",
      "server_path": "C:\\Tools\\ARGUS\\server.py",
      "python_executable": "python",
      "tools": [
        "smart_ui_scan",
        "smart_ui_desktop_items",
        "smart_ui_click",
        "smart_ui_reset"
      ],
      "capabilities": ["screen_capture", "desktop_items_listing", "circuit_breaker"],
      "enabled": true,
      "timeout_seconds": 30,
      "execution_mode": "local_gpu"
    }
  }
}
```

### 5. Health Check
```powershell
python -c "import asyncio, json; from mcp import ClientSession, StdioServerParameters; from mcp.client.stdio import stdio_client; p = StdioServerParameters(command='python', args=[r'C:\Tools\ARGUS\server.py']); asyncio.run((lambda: [print('ARGUS Ready:', r.content[0].text[:60]) for r in [asyncio.run(__import__('asyncio').wait_for((lambda: stdio_client(p))(), timeout=5))]])())"
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
| `python_executable` | string | Python binary to invoke (`python` or absolute path to virtualenv). |
| `capabilities` | array of strings | Capabilities supported by the worker. |
| `tools` | array of strings | Tool names exposed by the worker (for MCP transport). |
| `enabled` | boolean | Toggle worker activation. |
| `timeout_seconds` | float | Per-task execution timeout threshold (default: 60s for BUBU, 30s for ARGUS). |
| `execution_mode` | string | `cloud_hybrid`, `local_gpu`, or `local_process`. |
| `cost_characteristics` | object | Budget tier, cloud quota flags, and offline decide support. |

---

## MCP Server Setup

The Orchestrator MCP server runs as a standard **FastMCP stdio server**:
- **Entrypoint:** `orchestrator/mcp_server.py`
- **Execution Command:** `python C:\Tools\ORCHESTRATOR\orchestrator\mcp_server.py`
- **Required Environment:** `PYTHONPATH=C:\Tools\ORCHESTRATOR`

---

## Agent Host Integrations

Any coding-agent host that supports the Model Context Protocol (MCP) over stdio can connect to Orchestrator:

```text
Antigravity / Cursor / Claude Code / OpenCode / Generic MCP Host
                              │
                              ▼
                       Orchestrator MCP
                              │
                        BUBU / ARGUS
```

> **Operational Model:** In all hosts, Orchestrator does **not** secretly hijack every typed prompt. The host agent invokes Orchestrator's tools when it identifies multi-file complexity, visual tasks, or when directed by prompt directives.

---

### Antigravity

Antigravity natively manages MCP servers via its global configuration file:
- **Path:** `C:\Users\<username>\.gemini\config\mcp_config.json`

Add the `orchestrator` block:
```json
{
  "mcpServers": {
    "orchestrator": {
      "command": "python",
      "args": [
        "C:\\Tools\\ORCHESTRATOR\\orchestrator\\mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "C:\\Tools\\ORCHESTRATOR"
      }
    }
  }
}
```

---

### Cursor

Cursor supports MCP stdio servers via project-level or global MCP configuration:
- **Project Configuration:** `.cursor/mcp.json` in your project root
- **Global Configuration:** Cursor Settings -> Features -> MCP

Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "orchestrator": {
      "command": "python",
      "args": [
        "C:\\Tools\\ORCHESTRATOR\\orchestrator\\mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "C:\\Tools\\ORCHESTRATOR"
      }
    }
  }
}
```

---

### Claude Code

Claude Code supports adding MCP servers via CLI or its configuration files:

#### Option 1: CLI Configuration
```bash
claude mcp add orchestrator python C:\Tools\ORCHESTRATOR\orchestrator\mcp_server.py -e PYTHONPATH=C:\Tools\ORCHESTRATOR
```

#### Option 2: Configuration File (`~/.claude.json` or `claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "orchestrator": {
      "command": "python",
      "args": [
        "C:\\Tools\\ORCHESTRATOR\\orchestrator\\mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "C:\\Tools\\ORCHESTRATOR"
      }
    }
  }
}
```

---

### OpenCode

OpenCode supports MCP servers through `opencode.json` in your workspace or global config:
```json
{
  "mcp": {
    "orchestrator": {
      "type": "stdio",
      "command": "python",
      "args": [
        "C:\\Tools\\ORCHESTRATOR\\orchestrator\\mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "C:\\Tools\\ORCHESTRATOR"
      }
    }
  }
}
```

---

### Generic MCP Hosts

Any MCP-compatible client supporting stdio transport can connect to Orchestrator using:
- **Command:** `python`
- **Arguments:** `["<path-to-ORCHESTRATOR>/orchestrator/mcp_server.py"]`
- **Environment:** `{"PYTHONPATH": "<path-to-ORCHESTRATOR>"}`

---

## MCP Tools Reference

Orchestrator exposes 6 standardized tools:

### 1. `orchestrator_status`
Returns provider health, active hybrid mode, and registered worker count.
```json
// Tool output:
{
  "status": "active",
  "hybrid_level": "NORMAL",
  "providers": { "gemini": { "state": "HEALTHY", "circuit_breaker": "CLOSED" } },
  "registered_workers_count": 2
}
```

### 2. `orchestrator_worker_status`
Inspects the physical filesystem health and availability of all workers defined in `workers.json`.
```json
// Tool output:
{
  "workers": {
    "bubu": { "healthy": true, "status": "HEALTHY", "entrypoint_exists": true },
    "argus": { "healthy": true, "status": "HEALTHY", "server_path_exists": true }
  }
}
```

### 3. `orchestrator_classify`
Classifies a task prompt deterministically without making LLM calls:
- **Arguments:** `prompt` (string), `files` (list of strings).
- **Classifications:** `DIRECT`, `CONTEXT_ANALYSIS`, `VISION`, `COMBINED`.

### 4. `orchestrator_plan`
Preflight checks provider quota and circuit breaker state, returning whether the task is actionable.

### 5. `orchestrator_dispatch`
Dispatches the task through Orchestrator to the appropriate worker (or executes Direct Path).
- **Arguments:**
  - `prompt`: Task instruction.
  - `files`: Target file paths (optional).
  - `task_type`: `ANALYZE`, `AUDIT`, `DEBUG`, `RESEARCH`, `COMPARE`, `SUMMARIZE`, `DOCUMENT`, `VALIDATE`.
  - `action`: Vision sub-action (e.g. `desktop_items`, `scan`, `click`, `reset`).
  - `dry_run`: Boolean to validate without making cloud API calls.
- **Example Usage:**
```json
{
  "prompt": "Audit authentication security and database pooling",
  "files": ["src/auth.py", "src/database.py"],
  "task_type": "AUDIT",
  "dry_run": false
}
```

### 6. `orchestrator_verify`
Empirically verifies line-level evidence against disk state by checking SHA-256 line content hashes, detecting `STALE` or `MODIFIED` files.

---

## Configuration & State Management

Orchestrator maintains persistent state to survive process restarts:
- **Provider State:** `~/.gemini/provider-state/provider_state.json`
- **Inter-Process Lock:** `~/.gemini/provider-state/provider.lock`
- **Evidence Storage:** `~/.gemini/provider-state/evidence_store.json`

### Error Taxonomy
| Status Code / State | Meaning | Orchestrator Action |
| :--- | :--- | :--- |
| `RATE_LIMITED` | Temporary 429 RPM/TPM limit | Bounded exponential backoff (5s to 60s). |
| `QUOTA_EXHAUSTED` | Daily API quota exhaustion | Multi-hour lock until verified Pacific Time midnight reset. |
| `AUTH_FAILED` | Invalid or missing API key (401/403) | Permanent halt; prompts user to configure keys without retrying. |
| `CIRCUIT_BREAKER_TRIPPED` | ARGUS detected screen freeze or repetitive loop | Halts automation to prevent infinite clicking loops. |

---

## Verification & Smoke Tests

### Test Scenarios

#### Scenario A: Orchestrator Core Only (Zero Workers)
```powershell
python -m unittest discover -s tests
```
Verifies ProviderManager, EvidenceStore, Classifier, and Loop Detectors pass without workers installed.

#### Scenario B: Orchestrator + BUBU
```powershell
python -m orchestrator.cli --dispatch "Audit sample files" --dry-run
```

#### Scenario C: Orchestrator + ARGUS
```powershell
python -m orchestrator.cli --dispatch "List desktop items" --action desktop_items
```

#### Scenario D: Full 6-Chain Verification
Run the automated end-to-end integration matrix:
```powershell
python tests/verify_root_cause_chains.py
```
Expected output:
```text
[1/6] Test A (CLI -> BUBU): PASS
[2/6] Test B (MCP -> Orchestrator -> BUBU Dry Run): PASS
[3/6] Test C (MCP -> Orchestrator -> BUBU Real API): PASS
[4/6] Test D (Direct FastMCP -> ARGUS): PASS
[5/6] Test E (MCP -> Orchestrator -> ARGUS Transport): PASS
[6/6] Test F (Orchestrator Loop Detector): PASS
OVERALL RESULT: 100% PASS
```

---

## Real Multi-Worker Composite Workflow Proof

ORCHESTRATOR V3 provides an automated end-to-end composite workflow test verifying that Orchestrator Core acts as a unified coordinator: executing multiple specialized workers—**BUBU** (Cloud LLM Context Worker) and **ARGUS** (On-device FastMCP Vision Shield)—via a single public workflow invocation (`Orchestrator.execute_workflow(...)`) and aggregating their findings into a single composite `WorkerResponse`.

Unlike simple multi-step test scripts, the test harness does **not** coordinate the workers directly. Orchestrator Core sequentially dispatches each step, enforces fail-fast error semantics, aggregates all findings and evidence, and returns a unified composite response.

### Automated Test Command
```powershell
python tests/verify_composite_workflow.py
```

### Verification Methodology
1. **Static Invariant Guarding:** The test statically verifies (via AST/source check) that 0 direct `orch.execute_task` calls and 0 adapter imports exist in the test logic. Orchestration is strictly delegated to `Orchestrator.execute_workflow([req_bubu, req_argus])`.
2. **Dynamic Test Fixture & Marker:** Generates an isolated Python fixture (`composite_fixture_<hex>.py`) with intentional vulnerabilities (arbitrary `eval()`, hardcoded token, unchecked division) and places a temporary desktop marker (`0_COMPOSITE_WORKFLOW_MARKER_<hex>.txt`).
3. **Single Public Workflow Call:** Invokes `orch.execute_workflow([req_bubu, req_argus], workflow_id=...)`.
4. **Step 1 — BUBU Real Cloud API:** Orchestrator dispatches the code audit step to BUBU via real Gemini Cloud API (`--model gemini-3.5-flash-lite`), capturing line-level evidence and structured findings.
5. **Step 2 — ARGUS Real FastMCP Desktop Discovery:** Orchestrator dispatches desktop inspection to ARGUS via native FastMCP JSON-RPC stdio transport (`smart_ui_desktop_items`), discovering the active desktop marker.
6. **Orchestrator Aggregation:** Orchestrator Core aggregates all findings (BUBU code findings + ARGUS desktop items) and line-level evidence into a single `WorkerResponse` with `worker_name="composite"`, preserving per-step results in `metrics["step_responses"]`.
7. **Machine-Readable Evidence Artifact:** Generates a sanitized JSON artifact saved to `tests/artifacts/last_composite_workflow.json`.
8. **Guaranteed Cleanup & Registry Restoration:** A deterministic `try ... finally` block deletes the temporary marker, cleans up the test fixture, and restores `workers.json` to its pre-test configuration state.

### Empirical Execution Output
```text
====================================================================
ORCHESTRATOR V3: COMPOSITE MULTI-WORKER WORKFLOW EXECUTION PROOF
Single Public Call: orch.execute_workflow([req_bubu, req_argus])
====================================================================
[+] Test Invariant Check: PASS (0 execute_task calls, 0 adapter imports in test)
[*] Workflow ID         : wf-exp-20260921233212-60edb4
[*] Desktop Marker Target: 0_COMPOSITE_WORKFLOW_MARKER_cfb5b0.txt
[*] Gemini API Credential: CONFIGURED
[+] Global Registry: Temporarily set enabled=True for BUBU & ARGUS.
[+] Created Fixture: composite_fixture_cfb5b0.py (SHA-256: 5548c4e475c660d5...)
[+] Created Desktop Marker: 0_COMPOSITE_WORKFLOW_MARKER_cfb5b0.txt

--- Phase 1: Executing Single Public Workflow Call ---

--- Phase 2: Inspecting Orchestrator Composite Response ---
[COMPOSITE] Worker Name    : composite
[COMPOSITE] Workflow Status: success
[COMPOSITE] Total Duration : 5.275s
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
[+] Cleaned up desktop marker: 0_COMPOSITE_WORKFLOW_MARKER_cfb5b0.txt
[+] Cleaned up test fixture: composite_fixture_cfb5b0.py
[+] Global Registry: Successfully restored original pre-test state (disabled=false).
```

---

## Troubleshooting

### 1. MCP Server Does Not Appear in Host
- **Symptom:** Host reports `Server not found` or `failed to connect`.
- **Cause:** Incorrect `PYTHONPATH` or invalid Python path in host MCP JSON.
- **Fix:** Ensure `PYTHONPATH` points to the ORCHESTRATOR root:
  ```json
  "env": { "PYTHONPATH": "C:\\Tools\\ORCHESTRATOR" }
  ```
- **Verification:** Run `python C:\Tools\ORCHESTRATOR\orchestrator\mcp_server.py` in your shell; it should wait quietly for stdio JSON-RPC.

### 2. BUBU Path Traversal or Project Root Failure
- **Symptom:** BUBU returns `Path traversal detected or file outside project`.
- **Cause:** BUBU requires a project root indicator (`.ai-worker`, `.agents`, or `.git`) to safely validate paths.
- **Fix:** `BubuAdapter` automatically normalizes file paths relative to target directory and ensures `.ai-worker` exists.
- **Verification:** Run `python tests/test_adapters.py`.

### 3. BUBU Cloud Model Read Timeout / 503
- **Symptom:** BUBU hangs for 60 seconds and times out.
- **Cause:** Google's `gemini-3.6-flash` endpoint returned 503 / read timeouts under rate pressure.
- **Fix:** `BubuAdapter` passes active low-latency model `--model gemini-3.5-flash-lite`.
- **Verification:** Run `python tests/verify_root_cause_chains.py` (Test C passes in <1s).

### 4. ARGUS Child-Process Timeout (>30s)
- **Symptom:** ARGUS dispatches time out after 30s.
- **Cause:** Invoking heavy PyTorch/PyAutoGUI imports from within non-interactive child processes blocks on Windows.
- **Fix:** `ArgusAdapter` connects directly to ARGUS FastMCP server via `mcp.client.stdio.stdio_client` with strict failure semantics (no silent fallback or fake success).
- **Verification:** Test E runs in ~1.5s with zero token cost.

### 5. Loop Detected / Cycle Halted
- **Symptom:** Task returns status `"loop_detected"`.
- **Cause:** An identical prompt and file set was dispatched 3 consecutive times without state change.
- **Fix:** Expected behavior. Orchestrator halts repetitive loops to protect user budgets.

---

## Security & API Key Handling

1. **Zero Hardcoded Secrets:** Never commit API keys, tokens, passwords, or credentials to Git.
2. **Environment Variable Precedence:**
   - Keys are read from environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`) or Windows User Registry (`HKCU\Environment`).
   - Keys are masked in all logs (`[REDACTED_API_KEY]`).
3. **Local State Hygiene:** State files (`provider_state.json`, `evidence_store.json`, `*.lock`) are strictly ignored in `.gitignore`.

---

## Cross-Platform Support

| Feature | Windows | Linux | macOS |
| :--- | :---: | :---: | :---: |
| **Orchestrator Core** | ✅ Supported | ✅ Supported | ✅ Supported |
| **Provider Quota Intelligence** | ✅ Supported | ✅ Supported | ✅ Supported |
| **Evidence Store** | ✅ Supported | ✅ Supported | ✅ Supported |
| **FastMCP Server** | ✅ Supported | ✅ Supported | ✅ Supported |
| **BUBU Context Worker** | ✅ Supported | ✅ Supported | ✅ Supported |
| **ARGUS Vision Shield** | ✅ Full Desktop & ADB | ⚠️ Limited to ADB / Headless | ⚠️ Limited to ADB / Headless |

> **Platform Note:** ARGUS desktop window enumeration and interactive session control rely on the Windows Desktop API (`user32.dll`). On Linux and macOS, ARGUS operates in headless ADB mode or via simulated inputs.

---

## Development & Testing

Run the full unit test suite:
```powershell
python -m unittest discover -s tests
```

Run specific test modules:
```powershell
python -m unittest tests.test_quota_manager
python -m unittest tests.test_adapters
python -m unittest tests.test_evidence_provenance
python -m unittest tests.test_worker_registry
```

---

## Repository Structure

```text
ORCHESTRATOR/
├── .gitignore
├── LICENSE                          # MIT License
├── README.md                        # Master Documentation
├── pyproject.toml                   # Package Metadata & CLI Entrypoints
├── requirements.txt                 # Runtime Dependencies
├── workers.example.json             # Canonical Worker Registry Template
├── docs/
│   ├── HYBRID_MODE.md               # Predictive Hybrid Level Specs
│   └── PROVIDER_QUOTA.md            # Quota Taxonomy & Error Codes
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
    ├── verify_two_worker_integration.py # Real End-to-End BUBU + ARGUS Proof
    └── artifacts/                   # Sanitized Machine-Readable Evidence Run Logs
```

---

## License

- **ORCHESTRATOR:** Licensed under the [MIT License](LICENSE). Copyright (c) 2026 aethelondev-stack.
- **BUBU:** Licensed under the [BUBU Source-Available & Commercial License (Version 1.0)](https://github.com/aethelondev-stack/BUBU). Commercial deployment requires an agreement from aethelondev-stack.
- **ARGUS:** Licensed under the [MIT License](https://github.com/aethelondev-stack/ARGUS). Copyright (c) 2026 Aethelion / aethelondev-stack.

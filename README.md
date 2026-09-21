# ORCHESTRATOR V3: Production-Grade Agent Routing & Quota Supervisor

> **Phase-Gated Master Orchestrator, Quota Supervisor, and Multi-Worker Evidence Coordinator for Autonomous AI Coding Agents (Google Antigravity, Cursor, Cline).**

---

## 📑 Table of Contents
- [Architecture Overview](#-architecture-overview)
- [Core Principles](#-core-principles)
- [Provider & Quota Intelligence](#-provider--quota-intelligence)
- [Predictive Hybrid Mode](#-predictive-hybrid-mode)
- [Infinite Loop & Cycle Protection](#-infinite-loop--cycle-protection)
- [Quick Start](#-quick-start)
- [Verification & Tests](#-verification--tests)
- [License](#-license)

---

## 🏗️ Architecture Overview

```text
                         MAIN AGENT
                             │
                             ▼
                    ┌─────────────────┐
                    │  ORCHESTRATOR   │
                    │                 │
                    │ routing         │
                    │ planning        │
                    │ state           │
                    │ verification    │
                    │ retry           │
                    │ budget          │
                    └────────┬────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │ PROVIDER / QUOTA      │
                 │       MANAGER         │
                 │                       │
                 │ health                │
                 │ quota                 │
                 │ rate limit            │
                 │ budget                │
                 │ usage accounting      │
                 │ prediction            │
                 │ cooldown              │
                 │ provider selection    │
                 └───────────┬───────────┘
                             │
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
            BUBU           ARGUS        Future Workers
              │              │
              ▼              ▼
         External AI      Local Vision
              │
              └──────────────┬──────────────┘
                             ▼
                       EVIDENCE STORE
                             │
                             ▼
                        MAIN AGENT
```

---

## 🛡️ Core Principles

1. **Direct Path First:** Simple localized edits or single-file changes bypass worker overhead completely. The Orchestrator does not intercept tasks that the lead agent can execute directly.
2. **No Fake Intelligence:** All deterministic functions (hashing, state machine, rate limits, quota accounting, budget limits, loop detection) run via 100% deterministic code without calling LLMs.
3. **No Fake Pass:** Statuses are strictly classified (`PASS`, `FAIL`, `BLOCKED`, `SKIPPED`, `NOT_MEASURED`, `UNKNOWN`). Zero mock falsifications.
4. **Zero-Token Lazy Onboarding:** Preserves context and hardware tokens by never loading expensive models or running network health checks before user confirmation.

---

## ⚡ Provider & Quota Intelligence

The `ProviderManager` maintains persistent cross-session state (`~/.gemini/provider-state/provider_state.json`):
- **Rate Limit vs Quota Exhaustion:** Distinguishes temporary RPM limit (`RATE_LIMITED`, bounded backoff) from daily exhaustion (`QUOTA_EXHAUSTED`, cooldown until reset).
- **New Session Preflight:** When a new chat begins, existing quota state is checked **BEFORE** making any API calls, eliminating blind retry storms.
- **Single-Flight Coordination:** Inter-process file locking coordinates multiple agent sessions to prevent concurrent API stampedes.

---

## 🔄 Predictive Hybrid Mode

Dynamically shifts execution mode based on real-time RPM pressure and local budget limits:
- **`NORMAL`:** Standard execution.
- **`CAUTIOUS`:** Caches and local deterministic operations prioritized.
- **`HYBRID`:** Only high-value LLM tasks offloaded; low-priority tasks deferred.
- **`LOCAL_ONLY`:** Cloud API calls halted; local deterministic and ARGUS local GPU vision continue.
- **`BLOCKED`:** Tasks strictly requiring cloud LLM halt safely without token bleeding.

---

## ⚡ Quick Start

```powershell
# Check provider health and hybrid level
python -m orchestrator.cli --status

# Classify task prompt deterministically
python -m orchestrator.cli --classify "Refactor authentication layer" --files auth.py session.py user.py

# Run test suite
python -m unittest discover tests
```

---

## 📄 License
MIT License. Copyright (c) 2026 aethelondev-stack.

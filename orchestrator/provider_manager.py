"""
ORCHESTRATOR V3: Provider, Quota & Token Resilience Manager
Phase 4.5: Centralized, persistent, cross-session provider health, rate-limiting,
quota intelligence, circuit breaker, single-flight coordination, and predictive hybrid mode.
Standard-library only.
"""
from __future__ import annotations

import enum
import hashlib
import json
import os
import pathlib
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


class ProviderState(enum.Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_FAILED = "AUTH_FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    DISABLED = "DISABLED"
    RECOVERING = "RECOVERING"


class HybridModeLevel(enum.Enum):
    NORMAL = "NORMAL"
    CAUTIOUS = "CAUTIOUS"
    HYBRID = "HYBRID"
    LOCAL_ONLY = "LOCAL_ONLY"
    BLOCKED = "BLOCKED"


class CircuitBreakerState(enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ProviderManager:
    """
    Central provider supervisor managing quota exhaustion, rate limits,
    predictive hybrid mode, persistent state, and cross-session circuit breaking.
    """

    def __init__(
        self,
        state_dir: Optional[pathlib.Path] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 16.0,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 60.0,
        local_daily_request_limit: int = 1400,
        local_rpm_limit: int = 12
    ):
        if state_dir is None:
            # Default to global ~/.gemini/provider-state or current project
            global_home = pathlib.Path.home() / ".gemini"
            if global_home.exists():
                self.state_dir = global_home / "provider-state"
            else:
                self.state_dir = pathlib.Path(".ai-worker") / "provider-state"
        else:
            self.state_dir = pathlib.Path(state_dir)

        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "provider_state.json"
        self.lock_file = self.state_dir / "provider.lock"

        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_cooldown_seconds = circuit_cooldown_seconds
        self.local_daily_request_limit = local_daily_request_limit
        self.local_rpm_limit = local_rpm_limit

        # In-memory lock fallback
        self._lock_held = False

    # -----------------------------------------------------------------------
    # Persistent State Management (Cross-Session & Cross-Process)
    # -----------------------------------------------------------------------
    def _read_persisted_state(self) -> Dict[str, Any]:
        if not self.state_file.is_file():
            return {
                "version": "3.0.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "providers": {},
                "accounting": {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "estimated_input_tokens": 0,
                    "estimated_output_tokens": 0,
                    "rate_limit_events": 0,
                    "quota_events": 0,
                    "recent_timestamps": []
                },
                "hybrid_level": HybridModeLevel.NORMAL.value
            }
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "version": "3.0.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "providers": {},
                "accounting": {"total_requests": 0, "successful_requests": 0, "failed_requests": 0, "recent_timestamps": []},
                "hybrid_level": HybridModeLevel.NORMAL.value
            }

    def _write_persisted_state(self, state_data: Dict[str, Any]):
        state_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp_file = self.state_file.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            tmp_file.replace(self.state_file)
        except Exception:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass

    # -----------------------------------------------------------------------
    # Single-Flight Inter-Process Coordination Lock
    # -----------------------------------------------------------------------
    def acquire_lock(self, timeout_seconds: float = 5.0) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                # Open exclusively
                self._lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                self._lock_held = True
                return True
            except FileExistsError:
                # Check stale lock (> 30s)
                try:
                    mtime = self.lock_file.stat().st_mtime
                    if time.time() - mtime > 30.0:
                        try:
                            self.lock_file.unlink()
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(0.05)
            except Exception:
                time.sleep(0.05)
        return False

    def release_lock(self):
        if self._lock_held and hasattr(self, "_lock_fd"):
            try:
                os.close(self._lock_fd)
            except Exception:
                pass
            try:
                if self.lock_file.is_file():
                    self.lock_file.unlink()
            except Exception:
                pass
            self._lock_held = False

    # -----------------------------------------------------------------------
    # Error Classification (Gemini / OpenAI Error Taxonomies)
    # -----------------------------------------------------------------------
    @staticmethod
    def classify_error(status_code: int, error_body: str) -> Tuple[ProviderState, bool, str]:
        """
        Classifies errors into strict ProviderState.
        Returns: (state, is_retryable, reason)
        Strict rule: 429 quota != 429 rate limit.
        """
        body_lower = error_body.lower()

        # Auth failures (Permanent)
        if status_code in (401, 403) or "api_key_invalid" in body_lower or "permission_denied" in body_lower:
            return ProviderState.AUTH_FAILED, False, "Authentication failed: invalid or unauthorized API credentials."

        # Model not found / unavailable
        if status_code == 404 or "model not found" in body_lower or "is not supported" in body_lower:
            return ProviderState.MODEL_UNAVAILABLE, False, f"Requested model unavailable or unrecognized (HTTP {status_code})."

        # 429 Distinctions: Quota vs Rate Limit
        if status_code == 429:
            # Explicit Google Quota Exhaustion checks
            if any(k in body_lower for k in ["quota_exceeded", "daily quota", "quota exceeded", "resource_exhausted: quota"]):
                return ProviderState.QUOTA_EXHAUSTED, False, "Daily API quota exhausted on provider project. Cooldown until reset."
            # Rate limit (per-minute or concurrency)
            return ProviderState.RATE_LIMITED, True, "Transient rate limit exceeded (RPM/TPM). Bounded backoff cooldown active."

        # 503 / 500 / 504 (Temporary Server Degradation)
        if status_code in (500, 502, 503, 504) or "service_unavailable" in body_lower or "deadline_exceeded" in body_lower:
            return ProviderState.DEGRADED, True, f"Provider service temporarily degraded (HTTP {status_code})."

        # Client error (Invalid prompt, malformed schema)
        if 400 <= status_code < 500:
            return ProviderState.DEGRADED, False, f"Non-retryable client validation error (HTTP {status_code}): {error_body[:120]}"

        return ProviderState.DEGRADED, True, f"Unclassified error (HTTP {status_code})."

    # -----------------------------------------------------------------------
    # Preflight Check (Called BEFORE any API call is made)
    # -----------------------------------------------------------------------
    def preflight_check(self, provider_name: str = "gemini") -> Tuple[bool, ProviderState, str, HybridModeLevel]:
        """
        Determines if an API call is permissible.
        Returns: (allowed, current_state, reason, hybrid_level)
        """
        state_data = self._read_persisted_state()
        providers = state_data.get("providers", {})
        provider_info = providers.get(provider_name, {})
        current_state_str = provider_info.get("state", ProviderState.UNKNOWN.value)
        current_state = ProviderState(current_state_str)
        cooldown_until = provider_info.get("cooldown_until", 0)
        now = time.time()

        # Check circuit breaker
        circuit_state_str = provider_info.get("circuit_breaker", CircuitBreakerState.CLOSED.value)
        circuit_state = CircuitBreakerState(circuit_state_str)

        # 1. Quota Exhausted Check (Strict zero-spam guarantee)
        if current_state == ProviderState.QUOTA_EXHAUSTED:
            # Check if cooldown/reset time has elapsed
            if now < cooldown_until:
                remaining_wait = int(cooldown_until - now)
                return False, ProviderState.QUOTA_EXHAUSTED, f"Provider '{provider_name}' quota exhausted. Preflight blocked ({remaining_wait}s remaining in lock).", HybridModeLevel.LOCAL_ONLY
            else:
                # Reset window arrived -> transition to RECOVERING / HALF_OPEN
                current_state = ProviderState.RECOVERING
                circuit_state = CircuitBreakerState.HALF_OPEN
                provider_info["state"] = current_state.value
                provider_info["circuit_breaker"] = circuit_state.value
                state_data["providers"][provider_name] = provider_info
                self._write_persisted_state(state_data)

        # 2. Rate Limited Cooldown Check
        if current_state == ProviderState.RATE_LIMITED:
            if now < cooldown_until:
                remaining_wait = int(cooldown_until - now)
                return False, ProviderState.RATE_LIMITED, f"Provider '{provider_name}' in rate-limit cooldown ({remaining_wait}s remaining).", HybridModeLevel.CAUTIOUS
            else:
                # Cooldown expired -> recover
                current_state = ProviderState.HEALTHY
                circuit_state = CircuitBreakerState.CLOSED
                provider_info["state"] = current_state.value
                provider_info["circuit_breaker"] = circuit_state.value
                state_data["providers"][provider_name] = provider_info
                self._write_persisted_state(state_data)

        # 3. Auth Failed Check (Permanent stop)
        if current_state == ProviderState.AUTH_FAILED:
            return False, ProviderState.AUTH_FAILED, f"Provider '{provider_name}' authentication failed. Review API credentials.", HybridModeLevel.LOCAL_ONLY

        # 4. Circuit Breaker Open Check
        if circuit_state == CircuitBreakerState.OPEN:
            if now < cooldown_until:
                remaining = int(cooldown_until - now)
                return False, ProviderState.UNAVAILABLE, f"Circuit breaker OPEN for '{provider_name}' ({remaining}s remaining).", HybridModeLevel.HYBRID
            else:
                circuit_state = CircuitBreakerState.HALF_OPEN
                provider_info["circuit_breaker"] = circuit_state.value
                state_data["providers"][provider_name] = provider_info
                self._write_persisted_state(state_data)

        # 5. Local Hard Budget Check
        accounting = state_data.get("accounting", {})
        daily_reqs = accounting.get("total_requests", 0)
        if daily_reqs >= self.local_daily_request_limit:
            return False, ProviderState.BUDGET_BLOCKED, f"Local daily request budget ({self.local_daily_request_limit}) reached.", HybridModeLevel.LOCAL_ONLY

        # 6. Evaluate Predictive Hybrid Level
        hybrid_level = self.evaluate_predictive_hybrid_level(state_data)

        if hybrid_level == HybridModeLevel.LOCAL_ONLY:
            return False, ProviderState.BUDGET_BLOCKED, "Predictive quota pressure forced LOCAL_ONLY mode.", hybrid_level

        return True, current_state, "Preflight passed.", hybrid_level

    # -----------------------------------------------------------------------
    # Predictive Hybrid Mode Engine
    # -----------------------------------------------------------------------
    def evaluate_predictive_hybrid_level(self, state_data: Optional[Dict[str, Any]] = None) -> HybridModeLevel:
        if state_data is None:
            state_data = self._read_persisted_state()

        accounting = state_data.get("accounting", {})
        total_reqs = accounting.get("total_requests", 0)
        failed_reqs = accounting.get("failed_requests", 0)
        rate_limits = accounting.get("rate_limit_events", 0)

        # Calculate recent usage pressure
        now = time.time()
        recent_timestamps = accounting.get("recent_timestamps", [])
        # Keep timestamps in the last 60 seconds
        recent_in_window = [t for t in recent_timestamps if now - t < 60.0]
        recent_rpm = len(recent_in_window)

        # Level 1: Extreme pressure / quota exhaustion -> LOCAL_ONLY
        providers = state_data.get("providers", {})
        if any(p.get("state") == ProviderState.QUOTA_EXHAUSTED.value for p in providers.values()):
            return HybridModeLevel.LOCAL_ONLY

        # Level 2: High RPM or local budget near limit (> 85%) -> HYBRID
        if total_reqs >= int(self.local_daily_request_limit * 0.85) or recent_rpm >= (self.local_rpm_limit - 2):
            return HybridModeLevel.HYBRID

        # Level 3: Moderate pressure or sporadic failures -> CAUTIOUS
        if rate_limits > 0 or failed_reqs > 2 or recent_rpm >= int(self.local_rpm_limit * 0.6):
            return HybridModeLevel.CAUTIOUS

        return HybridModeLevel.NORMAL

    # -----------------------------------------------------------------------
    # Event Reporting & Outcome Accounting
    # -----------------------------------------------------------------------
    def record_success(self, provider_name: str, estimated_in_tokens: int = 0, estimated_out_tokens: int = 0):
        if not self.acquire_lock():
            return
        try:
            state_data = self._read_persisted_state()
            providers = state_data.setdefault("providers", {})
            p_info = providers.setdefault(provider_name, {})
            p_info["state"] = ProviderState.HEALTHY.value
            p_info["circuit_breaker"] = CircuitBreakerState.CLOSED.value
            p_info["failure_count"] = 0
            p_info["last_success"] = datetime.now(timezone.utc).isoformat()
            p_info["cooldown_until"] = 0

            acc = state_data.setdefault("accounting", {})
            acc["total_requests"] = acc.get("total_requests", 0) + 1
            acc["successful_requests"] = acc.get("successful_requests", 0) + 1
            acc["estimated_input_tokens"] = acc.get("estimated_input_tokens", 0) + estimated_in_tokens
            acc["estimated_output_tokens"] = acc.get("estimated_output_tokens", 0) + estimated_out_tokens

            now = time.time()
            ts = acc.get("recent_timestamps", [])
            ts.append(now)
            acc["recent_timestamps"] = [t for t in ts if now - t < 60.0]

            state_data["hybrid_level"] = self.evaluate_predictive_hybrid_level(state_data).value
            self._write_persisted_state(state_data)
        finally:
            self.release_lock()

    def record_failure(self, provider_name: str, status_code: int, error_body: str) -> Tuple[ProviderState, float]:
        """
        Records an error, applies classification, updates circuit breaker,
        and sets precise cooldown.
        Returns: (resulting_state, cooldown_seconds)
        """
        state, is_retryable, reason = self.classify_error(status_code, error_body)

        if not self.acquire_lock():
            return state, 0.0

        try:
            state_data = self._read_persisted_state()
            providers = state_data.setdefault("providers", {})
            p_info = providers.setdefault(provider_name, {})

            p_info["state"] = state.value
            p_info["last_failure"] = datetime.now(timezone.utc).isoformat()
            p_info["last_failure_reason"] = reason
            failures = p_info.get("failure_count", 0) + 1
            p_info["failure_count"] = failures

            now = time.time()
            cooldown_seconds = 0.0

            if state == ProviderState.QUOTA_EXHAUSTED:
                # Quota exhaustion: set long cooldown (e.g. 6 hours or until reset)
                cooldown_seconds = 21600.0  # 6 hours
                p_info["cooldown_until"] = now + cooldown_seconds
                p_info["circuit_breaker"] = CircuitBreakerState.OPEN.value
                state_data.setdefault("accounting", {})["quota_events"] = state_data["accounting"].get("quota_events", 0) + 1

            elif state == ProviderState.RATE_LIMITED:
                # Bounded backoff for rate limits: 5s base * 2^(failures-1), max 60s
                cooldown_seconds = min(60.0, 5.0 * (2 ** min(failures - 1, 4)))
                p_info["cooldown_until"] = now + cooldown_seconds
                state_data.setdefault("accounting", {})["rate_limit_events"] = state_data["accounting"].get("rate_limit_events", 0) + 1

            elif state == ProviderState.AUTH_FAILED:
                # Non-retryable
                p_info["cooldown_until"] = now + 86400.0
                p_info["circuit_breaker"] = CircuitBreakerState.OPEN.value

            else:
                # General degradation: open circuit if threshold exceeded
                if failures >= self.circuit_failure_threshold:
                    p_info["circuit_breaker"] = CircuitBreakerState.OPEN.value
                    cooldown_seconds = self.circuit_cooldown_seconds
                    p_info["cooldown_until"] = now + cooldown_seconds

            acc = state_data.setdefault("accounting", {})
            acc["total_requests"] = acc.get("total_requests", 0) + 1
            acc["failed_requests"] = acc.get("failed_requests", 0) + 1

            state_data["hybrid_level"] = self.evaluate_predictive_hybrid_level(state_data).value
            self._write_persisted_state(state_data)
            return state, cooldown_seconds
        finally:
            self.release_lock()

    # -----------------------------------------------------------------------
    # Observability & Inspection Contract
    # -----------------------------------------------------------------------
    def get_status_summary(self) -> Dict[str, Any]:
        state_data = self._read_persisted_state()
        now = time.time()
        providers = state_data.get("providers", {})
        summary_providers = {}

        for name, info in providers.items():
            st = info.get("state", ProviderState.UNKNOWN.value)
            cooldown = info.get("cooldown_until", 0)
            in_cooldown = cooldown > now
            summary_providers[name] = {
                "state": st,
                "circuit_breaker": info.get("circuit_breaker", CircuitBreakerState.CLOSED.value),
                "in_cooldown": in_cooldown,
                "cooldown_remaining_seconds": max(0, int(cooldown - now)) if in_cooldown else 0,
                "last_failure_reason": info.get("last_failure_reason", "None")
            }

        accounting = state_data.get("accounting", {})
        return {
            "status": "active",
            "hybrid_level": state_data.get("hybrid_level", HybridModeLevel.NORMAL.value),
            "providers": summary_providers,
            "accounting_mode": "ESTIMATED_LOCAL",
            "total_requests": accounting.get("total_requests", 0),
            "successful_requests": accounting.get("successful_requests", 0),
            "failed_requests": accounting.get("failed_requests", 0),
            "rate_limit_events": accounting.get("rate_limit_events", 0),
            "quota_events": accounting.get("quota_events", 0),
            "estimated_input_tokens": accounting.get("estimated_input_tokens", 0),
            "estimated_output_tokens": accounting.get("estimated_output_tokens", 0)
        }

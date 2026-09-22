"""
ORCHESTRATOR V3 / NEXUS: Session Preference State Machine
Manages one-time onboarding and per-session preferences for BUBU, ARGUS, and NEXUS
without writing any configuration files to project workspaces.
Standard-library only.
"""
from __future__ import annotations

import enum
import json
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


class SessionLifecycleState(str, enum.Enum):
    UNRESOLVED = "UNRESOLVED"
    WAITING_FOR_REPLY = "WAITING_FOR_REPLY"
    RESOLVED = "RESOLVED"


ONBOARDING_BANNER = (
    "---\n"
    "📌 **Sistem Tercihleri (NEXUS Koordinasyonunda Worker Modları):**\n"
    "NEXUS daima aktif koordinatördür. Aşağıdaki seçimler BUBU ve ARGUS worker'larını belirler:\n"
    "1. **Hepsi AUTO:** BUBU = auto | ARGUS = auto (Önerilen - Akıllı Hibrit)\n"
    "2. **Hepsi KAPALI:** BUBU = disabled | ARGUS = disabled (Tüm görevler doğrudan Lead Agent ile)\n"
    "3. **ÖZEL SEÇİM:** Belirtebilirsiniz:\n"
    "   - BUBU: `auto` | `enabled` | `disabled`\n"
    "   - ARGUS: `auto` | `local` | `direct`\n"
    "4. **Cevap Yoksa:** Varsayılan olarak otomatik *Hepsi AUTO* uygulanır.\n"
    "---"
)

DEFAULT_PREFERENCES: Dict[str, str] = {
    "bubu": "auto",
    "argus": "auto",
}

ALL_DISABLED_PREFERENCES: Dict[str, str] = {
    "bubu": "disabled",
    "argus": "disabled",
}


def parse_explicit_preferences(text: str) -> Optional[Dict[str, str]]:
    """
    Parses user text for explicit preference options or keywords.
    Returns a dictionary of worker preferences if matched, or None.
    """
    if not text:
        return None

    stripped = text.strip()
    lower = stripped.lower()

    # 1. Direct single-option replies (e.g., "1", "2", "3", "4")
    if stripped == "1" or lower in ("hepsi auto", "all auto", "ikisi de auto", "hepsi otomatik", "tümü auto"):
        return dict(DEFAULT_PREFERENCES)

    if stripped == "2" or lower in ("hepsi kapalı", "all disabled", "hepsi disabled", "tümü kapalı", "hepsi off"):
        return dict(ALL_DISABLED_PREFERENCES)

    if stripped == "4" or lower in ("default", "varsayılan", "auto"):
        return dict(DEFAULT_PREFERENCES)

    # 2. Key-value style explicit commands (Turkish & English supported)
    # 2. Key-value style explicit commands (Turkish & English supported)
    # e.g.: "BUBU disabled, ARGUS auto"
    #       "bubu kapalı, argus local"
    #       "bubu: enabled"
    found: Dict[str, str] = {}

    # BUBU regex
    bubu_match = re.search(r"\bbubu\s*[:=]?\s*(auto|enabled|disabled|kapalı|aktif|açık|off|on)\b", lower)
    if bubu_match:
        val = bubu_match.group(1)
        if val in ("kapalı", "off"):
            found["bubu"] = "disabled"
        elif val in ("aktif", "açık", "on"):
            found["bubu"] = "enabled"
        else:
            found["bubu"] = val

    # ARGUS regex
    argus_match = re.search(r"\bargus\s*[:=]?\s*(auto|local|direct|disabled|enabled|kapalı|aktif|açık|off|on)\b", lower)
    if argus_match:
        val = argus_match.group(1)
        if val in ("kapalı", "off"):
            found["argus"] = "disabled"
        elif val in ("aktif", "açık", "on"):
            found["argus"] = "enabled"
        else:
            found["argus"] = val

    # If any specific worker was explicitly mentioned with a mode, fill unspecified with default "auto"
    if found:
        result = dict(DEFAULT_PREFERENCES)
        result.update(found)
        return result

    # Check for Option 3 prefix with embedded spec: "3 BUBU = disabled ARGUS = local"
    if stripped.startswith("3") and (bubu_match or argus_match):
        result = dict(DEFAULT_PREFERENCES)
        result.update(found)
        return result

    return None


class SessionStateManager:
    """
    Session-level preference and onboarding manager.
    Lifecycle:
        UNRESOLVED -> (explicit preference found) -> RESOLVED
        UNRESOLVED -> (onboarding shown) -> WAITING_FOR_REPLY
        WAITING_FOR_REPLY -> (valid reply) -> RESOLVED
        WAITING_FOR_REPLY -> (unrelated task) -> RESOLVED (default auto/auto/auto)
        RESOLVED -> Lock (no repeated onboarding, no loops)
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        storage_dir: Optional[pathlib.Path] = None,
        persist: bool = True,
    ):
        self.session_id = session_id or os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "default_session")
        self.persist = persist

        if storage_dir:
            self.storage_dir = pathlib.Path(storage_dir)
        else:
            self.storage_dir = (
                pathlib.Path.home()
                / ".gemini"
                / "antigravity"
                / "plugin_data"
                / "bubu-argus"
                / "sessions"
            )

        self.state: SessionLifecycleState = SessionLifecycleState.UNRESOLVED
        self.onboarding_shown_count: int = 0
        self.preferences: Dict[str, str] = dict(DEFAULT_PREFERENCES)
        self.resolved: bool = False
        self.history_length: int = 0

        if self.persist:
            self._load()

    @property
    def session_file(self) -> pathlib.Path:
        safe_name = re.sub(r"[^\w\-.]", "_", self.session_id) + ".json"
        return self.storage_dir / safe_name

    def _load(self) -> None:
        try:
            if self.session_file.is_file():
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.state = SessionLifecycleState(data.get("state", SessionLifecycleState.UNRESOLVED.value))
                self.onboarding_shown_count = data.get("onboarding_shown_count", 0)
                raw_prefs = data.get("preferences", {})
                self.preferences = {
                    "bubu": raw_prefs.get("bubu", DEFAULT_PREFERENCES["bubu"]),
                    "argus": raw_prefs.get("argus", DEFAULT_PREFERENCES["argus"]),
                }
                self.resolved = data.get("resolved", False)
                self.history_length = data.get("history_length", 0)
        except Exception:
            # Degrade gracefully to clean default in-memory state
            pass

    def _save(self) -> None:
        if not self.persist:
            return
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_id": self.session_id,
                "state": self.state.value,
                "onboarding_shown_count": self.onboarding_shown_count,
                "preferences": self.preferences,
                "resolved": self.resolved,
                "history_length": self.history_length,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            temp_file = self.session_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.session_file)
        except Exception:
            pass

    def process_message(self, user_message: str) -> Tuple[bool, Optional[str]]:
        """
        Processes a user message turn according to the strict state machine.
        Returns:
            (should_show_onboarding: bool, onboarding_banner: Optional[str])
        """
        text = (user_message or "").strip()
        explicit = parse_explicit_preferences(text)
        self.history_length += 1

        if self.state == SessionLifecycleState.UNRESOLVED:
            if explicit:
                self.preferences.update(explicit)
                self.state = SessionLifecycleState.RESOLVED
                self.resolved = True
                self._save()
                return False, None
            else:
                self.state = SessionLifecycleState.WAITING_FOR_REPLY
                self.onboarding_shown_count += 1
                self._save()
                return True, ONBOARDING_BANNER

        elif self.state == SessionLifecycleState.WAITING_FOR_REPLY:
            if explicit:
                self.preferences.update(explicit)
            else:
                # User sent next task without preference -> implicitly Option 4 (auto/auto/auto)
                self.preferences = dict(DEFAULT_PREFERENCES)
            self.state = SessionLifecycleState.RESOLVED
            self.resolved = True
            self._save()
            return False, None

        elif self.state == SessionLifecycleState.RESOLVED:
            # Already locked/resolved: NEVER show onboarding again
            if explicit:
                # Explicit mid-session preference update
                self.preferences.update(explicit)
                self._save()
            return False, None

        return False, None

    def get_preferences(self) -> Dict[str, str]:
        return dict(self.preferences)

    def get_worker_preference(self, worker_name: str) -> str:
        norm = "bubu" if worker_name in ("bubu", "ai-studio-worker") else worker_name
        return self.preferences.get(norm, "auto")

    def is_worker_enabled(self, worker_name: str) -> Optional[bool]:
        pref = self.get_worker_preference(worker_name)
        if pref in ("disabled", "direct"):
            return False
        if pref == "enabled":
            return True
        # "auto" or "local" returns None indicating delegating to standard routing / registry
        return None

    def set_explicit_preference(self, preferences: Dict[str, str]) -> None:
        self.preferences.update(preferences)
        self.state = SessionLifecycleState.RESOLVED
        self.resolved = True
        self._save()

    def reset(self) -> None:
        self.state = SessionLifecycleState.UNRESOLVED
        self.onboarding_shown_count = 0
        self.preferences = dict(DEFAULT_PREFERENCES)
        self.resolved = False
        self.history_length = 0
        if self.persist and self.session_file.is_file():
            try:
                self.session_file.unlink()
            except Exception:
                pass

"""
ORCHESTRATOR V3: CLI Management Interface
Provides observability, state inspection, task classification, and simulation harnesses.
"""
from __future__ import annotations

import argparse
import json
import sys
from orchestrator.orchestrator import Orchestrator, TaskClassification
from orchestrator.provider_manager import ProviderManager, ProviderState


def main():
    parser = argparse.ArgumentParser(description="Antigravity Orchestrator V3 CLI")
    parser.add_argument("--status", action="store_true", help="Display provider and quota health")
    parser.add_argument("--classify", type=str, help="Classify a task prompt")
    parser.add_argument("--files", nargs="*", default=[], help="File paths for classification")
    parser.add_argument("--simulate-error", choices=["rate_limit", "quota_exhausted", "503", "auth_failed"], help="Simulate a provider error")
    parser.add_argument("--simulate-success", action="store_true", help="Simulate a successful provider request")
    parser.add_argument("--reset-state", action="store_true", help="Reset local provider state (Testing only)")

    args = parser.parse_args()
    pm = ProviderManager()
    orch = Orchestrator(provider_manager=pm)

    if args.status:
        summary = pm.get_status_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        sys.exit(0)

    if args.classify:
        classification = orch.classify_task(args.classify, args.files)
        out = {
            "prompt": args.classify,
            "files": args.files,
            "classification": classification.value,
            "direct_path": classification == TaskClassification.DIRECT
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        sys.exit(0)

    if args.simulate_error:
        err_map = {
            "rate_limit": (429, "rate_limit_exceeded: Too many requests per minute."),
            "quota_exhausted": (429, "Resource has been exhausted (e.g. check quota): quota_exceeded."),
            "503": (503, "The service is currently unavailable."),
            "auth_failed": (401, "API_KEY_INVALID: User API key is not authorized.")
        }
        status_code, body = err_map[args.simulate_error]
        st, cd = pm.record_failure("gemini", status_code, body)
        print(json.dumps({"simulated": args.simulate_error, "resulting_state": st.value, "cooldown_seconds": cd}, indent=2))
        sys.exit(0)

    if args.simulate_success:
        pm.record_success("gemini", estimated_in_tokens=250, estimated_out_tokens=100)
        print(json.dumps({"simulated": "success", "status": "recorded"}, indent=2))
        sys.exit(0)

    if args.reset_state:
        if pm.state_file.exists():
            pm.state_file.unlink()
        print(json.dumps({"status": "state_reset"}, indent=2))
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()

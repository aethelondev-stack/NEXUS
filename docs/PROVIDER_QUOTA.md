# Provider & Quota Management Specification

## 1. Provider State Taxonomy
- **`UNKNOWN`:** Provider registered but unverified.
- **`HEALTHY`:** Operational, responding normally within rate limits.
- **`DEGRADED`:** Intermittent 503 or network latency; bounded backoff active.
- **`RATE_LIMITED`:** Temporary 429 RPM/TPM limit; short exponential backoff.
- **`QUOTA_EXHAUSTED`:** Daily 429 quota exhaustion; cooldown locked until daily reset.
- **`AUTH_FAILED`:** 401/403 Invalid API key; permanent halt without retry.
- **`BUDGET_BLOCKED`:** Local user-defined safety limit reached.

## 2. Quota Reality & Accounting
- **`KNOWN`:** Explicit status code and reason returned directly by the provider API.
- **`ESTIMATED`:** Local token and request estimations computed on device.
- **`UNKNOWN`:** Unverified metrics; never hallucinated as exact values.

## 3. Cooldown Policies
- **Rate Limit:** 5s * 2^(attempts-1), capped at 60s.
- **Quota Exhausted:** Multi-hour lock until verified Pacific Time midnight reset or explicit user override.

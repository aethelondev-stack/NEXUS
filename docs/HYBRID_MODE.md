# Predictive Hybrid Mode Specification

## 1. Operating Levels
- **`NORMAL`:** Standard execution, cloud worker available.
- **`CAUTIOUS`:** Moderate RPM pressure; aggressive cache hits and deterministic routines prioritized.
- **`HYBRID`:** High RPM or budget near threshold (>85%); only essential complex tasks sent to cloud.
- **`LOCAL_ONLY`:** Cloud access locked; ARGUS local GPU vision and deterministic tasks continue.
- **`BLOCKED`:** Task strictly requires unavailable cloud provider; halted cleanly.

## 2. Dynamic Threshold Triggers
- `recent_rpm >= limit - 2` -> `HYBRID`
- `failures > 2` or `recent_rpm >= 60% limit` -> `CAUTIOUS`
- `QUOTA_EXHAUSTED` -> `LOCAL_ONLY`

# Security Policy: ORCHESTRATOR

## 1. Security Architecture & Principles

ORCHESTRATOR adheres to strict security and privacy standards:

1. **Zero Hardcoded Secrets:** No API keys, credentials, tokens, or private metadata are stored in source code.
2. **Environment & Registry Precedence:** Sensitive API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`) are read strictly from OS environment variables or secure local registry stores (`HKCU\Environment` on Windows).
3. **Log Sanitization:** All sensitive credentials detected in stderr, stdout, or HTTP error bodies are automatically scrubbed and redacted to `[REDACTED_API_KEY]`.
4. **Path Traversal Protection:** BUBU and Orchestrator strictly validate file boundaries, ensuring file arguments resolve within designated project trees to prevent unauthorized filesystem read/write operations.
5. **Circuit Breaking for Freeze & Loop Lockout:** Repeated identical requests and rapid cycling visual triggers are automatically halted by deterministic circuit breakers to prevent token drain and runaway loops.

---

## 2. Reporting Security Vulnerabilities

If you discover a potential security defect, credential leak risk, or path traversal vulnerability in ORCHESTRATOR:

- Please report it responsibly via GitHub Security Advisories at [https://github.com/aethelondev-stack/ORCHESTRATOR/security/advisories](https://github.com/aethelondev-stack/ORCHESTRATOR/security/advisories).
- Do NOT open public issues containing sensitive vulnerability details or proof-of-concept exploits.
- Security reports will be reviewed and addressed promptly by the maintainers.

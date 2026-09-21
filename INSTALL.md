# Installation & Integration Guide: ORCHESTRATOR V3

This guide provides step-by-step instructions for installing ORCHESTRATOR and connecting it to your AI coding agent environment.

---

## 1. System Requirements

- **Python:** Version 3.10 or higher.
- **Operating System:** Windows 10/11, Ubuntu/Debian Linux, or macOS.
- **Package Manager:** `pip`.

---

## 2. Installing ORCHESTRATOR Core

### Windows (PowerShell)
```powershell
git clone https://github.com/aethelondev-stack/ORCHESTRATOR.git C:\Tools\ORCHESTRATOR
cd C:\Tools\ORCHESTRATOR
pip install -r requirements.txt
```

### Linux / macOS (Bash)
```bash
git clone https://github.com/aethelondev-stack/ORCHESTRATOR.git ~/tools/ORCHESTRATOR
cd ~/tools/ORCHESTRATOR
pip install -r requirements.txt
```

---

## 3. Configuring the Global Worker Registry

Orchestrator reads its global worker definitions from `~/.gemini/orchestrator/workers.json`.

### Windows Setup
```powershell
mkdir -Force $HOME\.gemini\orchestrator
mkdir -Force $HOME\.gemini\provider-state
Copy-Item workers.example.json $HOME\.gemini\orchestrator\workers.json
```

### Linux / macOS Setup
```bash
mkdir -p ~/.gemini/orchestrator
mkdir -p ~/.gemini/provider-state
cp workers.example.json ~/.gemini/orchestrator/workers.json
```

---

## 4. Optional Workers Setup

### A. BUBU (Context Worker)
- **Repository:** `https://github.com/aethelondev-stack/BUBU`
- **Installation:**
  ```powershell
  git clone https://github.com/aethelondev-stack/BUBU.git C:\Tools\BUBU
  ```
- **Credentials:** Set `GEMINI_API_KEY` or `OPENAI_API_KEY` in your environment.
- **Registry Entry:** Ensure `entrypoint` in `workers.json` points to `C:\Tools\BUBU\.agents\skills\ai-studio-worker\scripts\ai_worker.py`.

### B. ARGUS (Vision Shield)
- **Repository:** `https://github.com/aethelondev-stack/ARGUS`
- **Installation:**
  ```powershell
  git clone https://github.com/aethelondev-stack/ARGUS.git C:\Tools\ARGUS
  cd C:\Tools\ARGUS
  pip install -r requirements.txt
  ```
- **Registry Entry:** Ensure `server_path` in `workers.json` points to `C:\Tools\ARGUS\server.py`.

---

## 5. Agent Host MCP Configurations

### Antigravity (`~/.gemini/config/mcp_config.json`)
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

### Cursor (`.cursor/mcp.json`)
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

### Claude Code CLI
```bash
claude mcp add orchestrator python C:\Tools\ORCHESTRATOR\orchestrator\mcp_server.py -e PYTHONPATH=C:\Tools\ORCHESTRATOR
```

### OpenCode (`opencode.json`)
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

## 6. Verification Commands

```powershell
# Check provider and registry status
python -m orchestrator.cli --status

# Check registered workers health
python -m orchestrator.cli --workers

# Run automated unit test suite
python -m unittest discover -s tests

# Run end-to-end integration test matrix
python tests/verify_root_cause_chains.py
```

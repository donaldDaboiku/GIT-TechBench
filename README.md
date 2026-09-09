# GIT TechBench

Professional PC Diagnostics & IT Support Toolkit for Windows 10/11.

Phase 2 adds core diagnostics: keyboard, mouse, display, battery health, storage/SMART, memory inventory, network tests, a full-diagnostic runner, and a JSON rule-based recommendation engine.

## Requirements

- Windows 10 or 11
- Python 3.12 or newer
- `PySide6-Essentials`, `psutil`, `pywin32`, `WMI`
- Administrator rights are **not** required for inventory. SMART and some WMI battery classes may be richer when elevated. Windows Memory Diagnostic prompts for elevation.

## Install

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

CLI inventory:

```powershell
python -m app.core.system_info
```

Internet check URL and DNS hostname are in `config/app_config.json` and can be overridden in Settings. Recommendation rules are in `config/recommendation_rules.json`.

## Tests

```powershell
python -m unittest discover -s tests -t . -v
```

## Safety

- No formatting, file deletion, or registry edits
- No automatic driver installs
- Memory Diagnostic is never launched without confirmation
- Untested keyboard keys are never auto-failed
- Missing SMART is never treated as healthy
- Recommendation text is a suggestion with a confidence level, not a confirmed diagnosis

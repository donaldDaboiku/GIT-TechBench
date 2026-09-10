# GIT TechBench

Professional PC Diagnostics & IT Support Toolkit for Windows 10/11.

Phase 5 adds SQLite session history, searchable past reports, and PDF/JSON export. Storage Health identifies SSD vs HDD from Windows Storage MediaType.

## Requirements

- Windows 10 or 11
- Python 3.12 or newer
- `PySide6-Essentials`, `psutil`, `pywin32`, `WMI`
- Optional: `opencv-python-headless` for in-app camera preview and still capture
- Administrator rights are **not** required for inventory. SFC, DISM, and Check Disk require elevation and confirmation.

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

`main.py` uses the project `.venv` automatically if the current Python does not have PySide6. You can also run `.\\.venv\\Scripts\\python.exe main.py` after activating the venv.

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

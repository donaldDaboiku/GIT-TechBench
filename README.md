# GIT TechBench

Professional PC Diagnostics & IT Support Toolkit for Windows 10/11.

Phase 6 is portable USB: copy one folder to a flash drive and run it. Nothing is installed on the PC under test. Settings, history, logs, and reports stay in that folder.

## Portable USB (no per-PC install)

On a build machine (once):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\scripts\build_portable.ps1
```

Copy `dist\GIT-TechBench-Portable` onto a USB stick. On each PC, plug in the stick and run `TechBench.exe` (or `Launch-TechBench.bat`).

The `_internal` folder must stay next to the exe. A Python venv cannot be copied to USB — Windows venv paths are machine-specific; the portable folder is the supported method.

Windows may show a SmartScreen prompt the first time. That is not an install. SFC / DISM / Check Disk still require administrator rights on the machine you are diagnosing.

## Development run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

`main.py` uses the project `.venv` automatically if the current Python does not have PySide6.

CLI inventory:

```powershell
python -m app.core.system_info
```

Internet check URL and DNS hostname are in `config/app_config.json` and can be overridden in Settings (`config/techbench.ini` in the app folder). Recommendation rules are in `config/recommendation_rules.json`.

## Tests

```powershell
python -m unittest discover -s tests -t . -v
```

## Safety

- No formatting, file deletion, or registry edits
- Settings are an INI file in the app folder, not the Registry
- No automatic driver installs
- Memory Diagnostic is never launched without confirmation
- Untested keyboard keys are never auto-failed
- Missing SMART is never treated as healthy
- Recommendation text is a suggestion with a confidence level, not a confirmed diagnosis

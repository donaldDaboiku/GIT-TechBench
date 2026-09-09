"""Load JSON config from the project config/ directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    return project_root() / "config"


def load_json(filename: str) -> dict[str, Any]:
    path = config_dir() / filename
    with path.open(encoding="utf-8") as handle:
        data = json.loads(handle.read())
    if not isinstance(data, dict):
        raise ValueError(f"{filename} must contain a JSON object")
    return data


def load_app_config() -> dict[str, Any]:
    try:
        return load_json("app_config.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "network": {
                "internet_check_url": "http://www.msftconnecttest.com/connecttest.txt",
                "dns_test_hostname": "www.msftconnecttest.com",
                "ping_count": 4,
                "timeout_seconds": 10,
            },
            "storage": {"space_warning_percent": 90},
        }

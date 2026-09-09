"""Rule-based recommendations for WARNING/FAIL results.

Suggestions are starting points for the technician — never a confirmed diagnosis.
Rules live in config/recommendation_rules.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import config_dir
from app.models.diagnostic_result import Confidence, DiagnosticResult, Status

logger = logging.getLogger("techbench.recommend")

_CONF = {item.value.lower(): item for item in Confidence}


class RecommendationEngine:
    def __init__(self, rules_path: Path | None = None) -> None:
        self.rules_path = rules_path or (config_dir() / "recommendation_rules.json")
        self.rules = self._load()

    def _load(self) -> list[dict[str, object]]:
        try:
            raw = json.loads(self.rules_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Could not load recommendation rules from %s", self.rules_path)
            return []
        rules = raw.get("rules", raw) if isinstance(raw, dict) else raw
        if not isinstance(rules, list):
            return []
        return [item for item in rules if isinstance(item, dict)]

    def annotate(self, result: DiagnosticResult) -> DiagnosticResult:
        """Fill likely_cause / action / confidence when status is WARNING or FAIL.

        UNKNOWN is left alone unless a rule explicitly targets it.
        Existing technician_override is never overwritten.
        """
        if result.technician_override:
            return result
        if result.status not in {Status.WARNING, Status.FAIL, Status.UNKNOWN}:
            return result
        rule = self._match(result)
        if rule is None:
            return result
        result.likely_cause = str(rule.get("likely_cause", ""))
        result.recommended_action = str(rule.get("recommended_action", ""))
        conf = str(rule.get("confidence", "")).lower()
        result.confidence = _CONF.get(conf)
        return result

    def _match(self, result: DiagnosticResult) -> dict[str, object] | None:
        for rule in self.rules:
            if str(rule.get("module", "")) != result.module:
                continue
            allowed = rule.get("status") or []
            if isinstance(allowed, str):
                allowed = [allowed]
            if result.status.value not in allowed:
                continue
            details = rule.get("detail_match") or {}
            if isinstance(details, dict) and not _details_match(result.details, details):
                continue
            return rule
        return None


def _details_match(actual: dict[str, str], expected: dict[str, object]) -> bool:
    for key, want in expected.items():
        if actual.get(str(key)) != str(want):
            return False
    return True

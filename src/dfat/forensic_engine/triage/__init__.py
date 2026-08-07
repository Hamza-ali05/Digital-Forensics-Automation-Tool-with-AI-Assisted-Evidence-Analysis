"""DFAT Forensic Engine — triage scoring and prioritisation."""

from dfat.forensic_engine.triage.aggregator import TriageAggregator, TriageSummary
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.rules import (
    DEFAULT_TRIAGE_RULES,
    TriageRule,
    get_rule,
    rules_for_category,
)
from dfat.forensic_engine.triage.scoring import ScoredArtefact, ScoringEngine

__all__ = [
    "DEFAULT_TRIAGE_RULES",
    "RuleBasedTriageEngine",
    "ScoredArtefact",
    "ScoringEngine",
    "TriageAggregator",
    "TriageRule",
    "TriageSummary",
    "get_rule",
    "rules_for_category",
]

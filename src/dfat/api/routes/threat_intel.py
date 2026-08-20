"""Threat intelligence API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dfat.api.dependencies import (
    get_artefact_repository,
    get_feed_manager,
    get_mitre_mapper,
    get_sigma_engine,
    get_yara_engine,
    require_permission,
)
from dfat.api.schemas.extension import (
    MITRECoverageResponse,
    SigmaRulesResponse,
    ThreatIntelScanRequest,
    ThreatIntelSummaryResponse,
    YaraRulesResponse,
)
from dfat.database.models.user import UserORM
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.threat_intel.feed_manager import ThreatFeedManager, ThreatScanResult
from dfat.threat_intel.mitre_mapper import MITREMapper
from dfat.threat_intel.sigma_engine import SigmaEngine
from dfat.threat_intel.yara_engine import YARAEngine

router = APIRouter(prefix="/threat-intel", tags=["Threat Intelligence"])


@router.get("/summary", response_model=ThreatIntelSummaryResponse)
async def threat_intel_summary(
    _: UserORM = Depends(require_permission("threat_intel", "read")),
    feed_manager: ThreatFeedManager = Depends(get_feed_manager),
) -> ThreatIntelSummaryResponse:
    """Return a summary of loaded threat intelligence."""
    summary = await feed_manager.get_intel_summary()
    return ThreatIntelSummaryResponse(summary=summary)


@router.post("/scan", response_model=ThreatScanResult)
async def scan_threat_intel(
    body: ThreatIntelScanRequest,
    _: UserORM = Depends(require_permission("threat_intel", "read")),
    feed_manager: ThreatFeedManager = Depends(get_feed_manager),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
) -> ThreatScanResult:
    """Scan all artefacts for an evidence item against loaded threat intelligence."""
    artefact_set = await artefact_repo.get(body.evidence_id)
    if artefact_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artefact set not found for evidence {body.evidence_id}",
        )
    return await feed_manager.scan_artefacts_against_intel(artefact_set)


@router.get("/mitre", response_model=MITRECoverageResponse)
async def mitre_coverage(
    _: UserORM = Depends(require_permission("threat_intel", "read")),
    mitre_mapper: MITREMapper = Depends(get_mitre_mapper),
) -> MITRECoverageResponse:
    """Return the embedded MITRE ATT&CK technique catalogue."""
    techniques = [
        {"technique_id": technique_id, **info}
        for technique_id, info in mitre_mapper.TECHNIQUE_DB.items()
    ]
    tactics: dict[str, list[str]] = {}
    for technique_id, info in mitre_mapper.TECHNIQUE_DB.items():
        tactic = info["tactic"]
        tactics.setdefault(tactic, []).append(technique_id)
    for tactic in tactics:
        tactics[tactic] = sorted(tactics[tactic])
    return MITRECoverageResponse(techniques=techniques, tactics=tactics)


@router.get("/yara/rules", response_model=YaraRulesResponse)
async def list_yara_rules(
    _: UserORM = Depends(require_permission("threat_intel", "read")),
    yara_engine: YARAEngine = Depends(get_yara_engine),
) -> YaraRulesResponse:
    """List loaded YARA rule files."""
    return YaraRulesResponse(
        rule_files=yara_engine.list_rule_files(),
        loaded_count=yara_engine.get_loaded_rules_count(),
    )


@router.get("/sigma/rules", response_model=SigmaRulesResponse)
async def list_sigma_rules(
    _: UserORM = Depends(require_permission("threat_intel", "read")),
    sigma_engine: SigmaEngine = Depends(get_sigma_engine),
) -> SigmaRulesResponse:
    """List loaded Sigma rules."""
    rules = sigma_engine.list_loaded_rules()
    return SigmaRulesResponse(rules=rules, loaded_count=len(rules))

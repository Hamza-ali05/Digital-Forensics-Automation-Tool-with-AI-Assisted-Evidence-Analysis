"""Request/response schemas for dataset, knowledge, ML, and threat-intel APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from dfat.api.schemas.base import APIModel
from dfat.knowledge.ioc_database import IOCEntry
from dfat.knowledge.retriever import RetrievalResult
from dfat.ml.predictor import MLPrediction
from dfat.threat_intel.feed_manager import FeedIngestionResult, ThreatScanResult
from dfat.threat_intel.mitre_mapper import MITREMapping
from dfat.threat_intel.sigma_engine import SigmaMatch
from dfat.threat_intel.yara_engine import YARAMatch


class DatasetScanRequest(BaseModel):
    """Optional scan path override for dataset discovery."""

    scan_path: Optional[str] = None


class DatasetRecordResponse(APIModel):
    """Dataset intelligence registry record."""

    dataset_id: str
    name: str
    file_path: str
    category: str
    format: str
    status: str
    file_size_bytes: int
    hash_sha256: str
    discovered_at: datetime
    validated_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None
    indexing_status: str
    tags: list[str] = Field(default_factory=list)


class DatasetScanResponse(APIModel):
    """Dataset scan summary."""

    scan_path: str
    datasets_found: int
    new_count: int
    updated_count: int
    failed_count: int


class DatasetStatisticsResponse(APIModel):
    """Aggregate dataset registry statistics."""

    statistics: dict[str, Any] = Field(default_factory=dict)


class DatasetActionResponse(APIModel):
    """Generic dataset admin action response."""

    dataset_id: str
    action: str
    message: str


class KnowledgeQueryRequest(BaseModel):
    """Knowledge base unified retrieval request."""

    query: str = Field(min_length=1)
    sources: Optional[list[str]] = None
    max_results: int = Field(default=10, ge=1, le=100)


class KnowledgeStatsResponse(APIModel):
    """Aggregate knowledge-base statistics."""

    vector_collections: dict[str, Any] = Field(default_factory=dict)
    ioc_statistics: dict[str, Any] = Field(default_factory=dict)
    graph_statistics: dict[str, Any] = Field(default_factory=dict)


class IOCSearchResponse(APIModel):
    """IOC search results."""

    query: str
    ioc_type: Optional[str] = None
    matches: list[IOCEntry] = Field(default_factory=list)
    total: int = 0


class MLTrainRequest(BaseModel):
    """Manual model training request."""

    model_name: str = Field(min_length=1)
    source_datasets: Optional[list[str]] = None
    hyperparameters: Optional[dict[str, Any]] = None


class MLPredictRequest(BaseModel):
    """Batch ML inference request."""

    model_name: str = Field(min_length=1)
    artefact_ids: list[str] = Field(min_length=1)


class TrainedModelResponse(APIModel):
    """Registered trained-model metadata."""

    model_id: str
    model_name: str
    version: str
    model_path: str
    training_dataset: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    feature_names: list[str] = Field(default_factory=list)
    trained_at: datetime


class ExperimentResponse(APIModel):
    """ML experiment record."""

    experiment_id: str
    model_name: str
    dataset_name: str
    status: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    artifact_paths: list[str] = Field(default_factory=list)


class MLTrainResponse(APIModel):
    """Model training outcome."""

    model_name: str
    model_id: str
    version: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class MLRetrainResponse(APIModel):
    """Auto-retrain check outcome."""

    retrained_models: list[str] = Field(default_factory=list)


class MLPredictResponse(APIModel):
    """Batch inference response."""

    model_name: str
    predictions: list[MLPrediction] = Field(default_factory=list)


class ThreatIntelScanRequest(BaseModel):
    """Threat intelligence scan request."""

    evidence_id: str = Field(min_length=1)


class ThreatIntelSummaryResponse(APIModel):
    """Threat intelligence summary."""

    summary: dict[str, Any] = Field(default_factory=dict)


class MITRECoverageResponse(APIModel):
    """MITRE ATT&CK technique catalogue and tactic grouping."""

    techniques: list[dict[str, str]] = Field(default_factory=list)
    tactics: dict[str, list[str]] = Field(default_factory=dict)


class YaraRulesResponse(APIModel):
    """Loaded YARA rule inventory."""

    rule_files: list[str] = Field(default_factory=list)
    loaded_count: int = 0


class SigmaRulesResponse(APIModel):
    """Loaded Sigma rule inventory."""

    rules: list[dict[str, str]] = Field(default_factory=list)
    loaded_count: int = 0


# Re-export domain result models for OpenAPI response typing where useful.
__all__ = [
    "DatasetActionResponse",
    "DatasetRecordResponse",
    "DatasetScanRequest",
    "DatasetScanResponse",
    "DatasetStatisticsResponse",
    "ExperimentResponse",
    "FeedIngestionResult",
    "IOCSearchResponse",
    "KnowledgeQueryRequest",
    "KnowledgeStatsResponse",
    "MITRECoverageResponse",
    "MITREMapping",
    "MLPredictRequest",
    "MLPredictResponse",
    "MLRetrainResponse",
    "MLTrainRequest",
    "MLTrainResponse",
    "RetrievalResult",
    "SigmaMatch",
    "SigmaRulesResponse",
    "ThreatIntelScanRequest",
    "ThreatIntelSummaryResponse",
    "ThreatScanResult",
    "TrainedModelResponse",
    "YARAMatch",
    "YaraRulesResponse",
]

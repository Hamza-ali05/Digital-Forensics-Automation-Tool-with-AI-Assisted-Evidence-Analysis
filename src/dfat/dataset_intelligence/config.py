"""Configuration for the dataset intelligence extension package."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class DatasetIntelligenceSettings(BaseModel):
    """Settings for dataset discovery, indexing, and preprocessing."""

    datasets_dir: Path = Path("data/datasets")
    scan_on_startup: bool = True
    watch_for_changes: bool = True
    watch_interval_seconds: int = 60
    max_dataset_size_gb: int = 100
    auto_index: bool = True
    auto_preprocess: bool = True
    supported_extensions: set[str] = Field(
        default_factory=lambda: {
            ".dd",
            ".raw",
            ".e01",
            ".vmem",
            ".pcap",
            ".evtx",
            ".csv",
            ".json",
            ".xml",
            ".yar",
            ".yml",
            ".stix",
            ".txt",
            ".zip",
            ".gz",
        }
    )
    vector_store_path: Path = Path("data/knowledge/vector_store")
    knowledge_graph_path: Path = Path("data/knowledge/graph")
    ioc_database_path: Path = Path("data/knowledge/ioc_db")
    ml_models_path: Path = Path("data/ml/models")
    experiments_path: Path = Path("data/ml/experiments")

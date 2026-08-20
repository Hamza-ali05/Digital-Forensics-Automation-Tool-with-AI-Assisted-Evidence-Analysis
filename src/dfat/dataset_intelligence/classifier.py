"""Heuristic dataset classification for discovered datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat
from dfat.dataset_intelligence.models import DatasetRecord


@dataclass(frozen=True)
class ClassificationRule:
    """Ordered heuristic rule for assigning one or more dataset categories."""

    keywords: tuple[str, ...] = ()
    formats: tuple[DatasetFormat, ...] = ()
    categories: tuple[DatasetCategory, ...] = (DatasetCategory.USER_UPLOADED,)
    require_ml_naming: bool = False


class DatasetClassifier:
    """Classify dataset records from path, naming, and format heuristics."""

    CLASSIFICATION_RULES: list[ClassificationRule] = [
        ClassificationRule(
            keywords=("dfrws",),
            categories=(
                DatasetCategory.BENCHMARK,
                DatasetCategory.FORENSIC_CHALLENGE,
            ),
        ),
        ClassificationRule(
            keywords=("cfreds", "nist"),
            categories=(
                DatasetCategory.BENCHMARK,
                DatasetCategory.FORENSIC_CHALLENGE,
            ),
        ),
        ClassificationRule(
            keywords=("digital-corpora",),
            categories=(
                DatasetCategory.BENCHMARK,
                DatasetCategory.FORENSIC_CHALLENGE,
            ),
        ),
        ClassificationRule(
            keywords=("malware", "samples"),
            categories=(
                DatasetCategory.MACHINE_LEARNING,
                DatasetCategory.THREAT_INTELLIGENCE,
            ),
        ),
        ClassificationRule(
            keywords=("yara",),
            formats=(DatasetFormat.YARA_RULES,),
            categories=(DatasetCategory.THREAT_INTELLIGENCE,),
        ),
        ClassificationRule(
            keywords=("sigma",),
            formats=(DatasetFormat.SIGMA_RULES,),
            categories=(DatasetCategory.THREAT_INTELLIGENCE,),
        ),
        ClassificationRule(
            keywords=("stix", "taxii"),
            categories=(DatasetCategory.THREAT_INTELLIGENCE,),
        ),
        ClassificationRule(
            keywords=("mitre", "att&ck"),
            categories=(DatasetCategory.THREAT_INTELLIGENCE,),
        ),
        ClassificationRule(
            keywords=("ioc", "indicators"),
            categories=(DatasetCategory.THREAT_INTELLIGENCE,),
        ),
        ClassificationRule(
            keywords=("phishing",),
            categories=(DatasetCategory.MACHINE_LEARNING,),
        ),
        ClassificationRule(
            keywords=("ransomware",),
            categories=(
                DatasetCategory.MACHINE_LEARNING,
                DatasetCategory.THREAT_INTELLIGENCE,
            ),
        ),
        ClassificationRule(
            formats=(DatasetFormat.DISK_IMAGE, DatasetFormat.MEMORY_DUMP),
            categories=(DatasetCategory.FORENSIC_OPERATIONAL,),
        ),
        ClassificationRule(
            formats=(DatasetFormat.PCAP,),
            categories=(DatasetCategory.FORENSIC_OPERATIONAL,),
        ),
        ClassificationRule(
            formats=(DatasetFormat.EVTX, DatasetFormat.REGISTRY_HIVE),
            categories=(DatasetCategory.FORENSIC_OPERATIONAL,),
        ),
        ClassificationRule(
            formats=(DatasetFormat.CSV, DatasetFormat.JSON),
            categories=(DatasetCategory.MACHINE_LEARNING,),
            require_ml_naming=True,
        ),
    ]

    def classify(self, dataset: DatasetRecord) -> DatasetRecord:
        """Classify a dataset record and enrich it with derived metadata."""
        categories = self._match_categories(dataset)
        primary_category = categories[0]
        secondary_categories = [category.value for category in categories[1:]]

        dataset.category = primary_category
        dataset.tags = self._dedupe(
            [
                *dataset.tags,
                primary_category.value,
                dataset.format.value,
                *self._extract_keyword_tags(dataset),
                *secondary_categories,
            ]
        )
        dataset.associated_research_objectives = self._map_to_research_objectives(
            primary_category,
            dataset.format,
        )
        dataset.supported_forensic_modules = self._infer_supported_modules(
            primary_category,
            dataset.format,
        )
        dataset.metadata = {
            **dataset.metadata,
            "secondary_categories": secondary_categories,
            "classification_source": "heuristic_rules",
        }
        return dataset

    def classify_batch(self, datasets: list[DatasetRecord]) -> list[DatasetRecord]:
        """Classify a batch of datasets in order."""
        return [self.classify(dataset) for dataset in datasets]

    def _map_to_research_objectives(
        self,
        category: DatasetCategory,
        format: DatasetFormat,
    ) -> list[str]:
        """Map dataset category and format to dissertation research objectives."""
        objectives: list[str] = []

        if category is DatasetCategory.FORENSIC_OPERATIONAL:
            objectives.append("RQ1")
        if category is DatasetCategory.THREAT_INTELLIGENCE:
            objectives.append("RQ2")
        if category is DatasetCategory.MACHINE_LEARNING:
            objectives.append("RQ3")
        if category in {
            DatasetCategory.BENCHMARK,
            DatasetCategory.FORENSIC_CHALLENGE,
        }:
            objectives.append("RQ4")
        if format in {DatasetFormat.YARA_RULES, DatasetFormat.SIGMA_RULES, DatasetFormat.STIX_BUNDLE}:
            objectives.append("RQ2")
        if format in {DatasetFormat.DISK_IMAGE, DatasetFormat.MEMORY_DUMP, DatasetFormat.PCAP}:
            objectives.append("RQ1")

        return self._dedupe(objectives)

    def _infer_supported_modules(
        self,
        category: DatasetCategory,
        format: DatasetFormat,
    ) -> list[str]:
        """Map a dataset to the DFAT modules most likely to process it."""
        modules: list[str] = []

        if format is DatasetFormat.DISK_IMAGE:
            modules.extend(["DiskImageHandler", "FileSystemParser", "BrowserHistoryParser"])
        if format is DatasetFormat.MEMORY_DUMP:
            modules.extend(
                [
                    "MemoryDumpHandler",
                    "ProcessListParser",
                    "NetworkArtefactParser",
                    "CodeInjectionParser",
                    "MemoryRegistryParser",
                ]
            )
        if format is DatasetFormat.PCAP:
            modules.append("NetworkArtefactParser")
        if format is DatasetFormat.EVTX:
            modules.append("EventLogParser")
        if format is DatasetFormat.REGISTRY_HIVE:
            modules.extend(["RegistryParser", "MemoryRegistryParser"])
        if format is DatasetFormat.YARA_RULES:
            modules.append("IOCRuleMatching")
        if format in {DatasetFormat.SIGMA_RULES, DatasetFormat.STIX_BUNDLE}:
            modules.append("ThreatIntelCorrelation")
        if category is DatasetCategory.BENCHMARK:
            modules.append("BenchmarkComparator")
        if category is DatasetCategory.MACHINE_LEARNING:
            modules.append("DatasetPreprocessing")

        return self._dedupe(modules)

    def _match_categories(self, dataset: DatasetRecord) -> tuple[DatasetCategory, ...]:
        searchable = self._searchable_text(dataset.file_path, dataset.name)

        for rule in self.CLASSIFICATION_RULES:
            if rule.keywords and not any(keyword in searchable for keyword in rule.keywords):
                continue
            if rule.formats and dataset.format not in rule.formats:
                continue
            if rule.require_ml_naming and not self._has_ml_naming(dataset):
                continue
            return rule.categories

        return (DatasetCategory.USER_UPLOADED,)

    @staticmethod
    def _searchable_text(file_path: Path, name: str) -> str:
        return f"{file_path.as_posix()} {name}".lower()

    @staticmethod
    def _has_ml_naming(dataset: DatasetRecord) -> bool:
        searchable = DatasetClassifier._searchable_text(dataset.file_path, dataset.name)
        return any(
            keyword in searchable
            for keyword in (
                "train",
                "training",
                "test",
                "validation",
                "labels",
                "features",
                "model",
                "dataset",
                "corpus",
                "benign",
                "malicious",
            )
        )

    @staticmethod
    def _extract_keyword_tags(dataset: DatasetRecord) -> list[str]:
        searchable = DatasetClassifier._searchable_text(dataset.file_path, dataset.name)
        tags: list[str] = []
        for keyword in (
            "dfrws",
            "cfreds",
            "nist",
            "digital-corpora",
            "malware",
            "samples",
            "yara",
            "sigma",
            "stix",
            "taxii",
            "mitre",
            "att&ck",
            "ioc",
            "indicators",
            "phishing",
            "ransomware",
        ):
            if keyword in searchable:
                tags.append(keyword)
        return tags

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped

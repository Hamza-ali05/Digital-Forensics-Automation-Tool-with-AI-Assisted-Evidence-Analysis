"""Build forensic RAG context blocks for LLM prompt injection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.knowledge.knowledge_graph import NodeType
from dfat.knowledge.retriever import RetrievalResult

if TYPE_CHECKING:
    from dfat.ai_engine.preprocessing.truncator import TokenTruncator
    from dfat.knowledge.retriever import UnifiedRetriever


class RAGContextBuilder:
    """Format retrieved forensic knowledge into prompt-ready context blocks."""

    def __init__(
        self,
        retriever: UnifiedRetriever,
        truncator: TokenTruncator,
    ) -> None:
        self._retriever = retriever
        self._truncator = truncator
        self._serializer = ArtefactSerializer()

    async def build_classification_context(self, artefacts: list[Artefact]) -> str:
        """Build classification context from similar cases, IOCs, and MITRE data."""
        context, _ = await self.build_classification_context_with_sources(artefacts)
        return context

    async def build_classification_context_with_sources(
        self,
        artefacts: list[Artefact],
    ) -> tuple[str, list[str]]:
        """Build classification context and the datasets that contributed to it.

        Returns an empty context string when the knowledge base has no matches
        so callers can fall back to the original (non-RAG) prompts.
        """
        sections: list[str] = []
        sources: list[str] = []

        for artefact in artefacts:
            result = await self._retriever.retrieve_for_artefact(artefact)
            if not self._result_has_knowledge(result):
                continue
            sources.extend(self._collect_source_labels(result))
            level = self._infer_similar_classification_level(result)
            reasoning = self._infer_similar_reasoning(result)
            ioc_list = ", ".join(
                f"{item.ioc_type}:{item.value}" for item in result.ioc_matches[:5]
            ) or "none"
            techniques = ", ".join(self._extract_mitre_techniques(result)) or "none"
            sections.append(
                "FORENSIC CONTEXT: "
                f"Similar artefacts from previous cases were classified as {level} "
                f"because {reasoning}. "
                f"Related IOCs: {ioc_list}. "
                f"MITRE techniques: {techniques}."
            )
            formatted = self._format_retrieval_as_context(result)
            if formatted:
                sections.append(formatted)

        if not sections:
            return "", []
        context = "\n\n".join(section for section in sections if section.strip())
        return self._truncator.truncate(context, reserve_tokens=2000), self._dedupe(sources)

    async def build_summary_context(self, ranked: list[RankedArtefact]) -> str:
        """Build summary context from threat patterns and historical findings."""
        context, _ = await self.build_summary_context_with_sources(ranked)
        return context

    async def build_summary_context_with_sources(
        self,
        ranked: list[RankedArtefact],
    ) -> tuple[str, list[str]]:
        """Build summary context and the datasets that contributed to it."""
        if not ranked:
            return "", []

        query_parts = [
            self._serializer.serialize_ranked_artefact(item) for item in ranked[:10]
        ]
        query = "\n".join(query_parts)
        result = await self._retriever.retrieve(
            query=query,
            sources=["knowledge", "threat_intel", "iocs", "graph", "artefacts"],
            max_results=12,
        )
        if not self._result_has_knowledge(result):
            return "", []

        source_list = self._collect_source_labels(result)
        threat_patterns = self._extract_threat_patterns(result)
        techniques = ", ".join(self._extract_mitre_techniques(result)) or "none"
        historical = self._extract_historical_findings(result)
        sources = ", ".join(source_list) or "none"

        context = (
            "FORENSIC SUMMARY CONTEXT:\n"
            f"Related threat patterns: {threat_patterns}\n"
            f"MITRE mappings: {techniques}\n"
            f"Historical case findings: {historical}\n"
            f"Grounded in datasets: {sources}\n\n"
            f"{self._format_retrieval_as_context(result)}"
        )
        return self._truncator.truncate(context, reserve_tokens=2500), source_list

    async def build_qa_context(self, question: str, artefact_set: ArtefactSet) -> str:
        """Build investigator Q&A context from the question and artefact set."""
        artefact_summary = self._serializer.serialize_artefact_set(artefact_set, max_artefacts=100)
        query = f"{question}\n\nEvidence context:\n{artefact_summary}"
        result = await self._retriever.retrieve(
            query=query,
            sources=["knowledge", "threat_intel", "iocs", "graph", "artefacts"],
            max_results=10,
        )
        if not self._result_has_knowledge(result):
            return ""
        sources = ", ".join(self._collect_source_labels(result)) or "none"
        context = (
            f"INVESTIGATOR QUESTION CONTEXT:\n"
            f"Question: {question}\n"
            f"Grounded in datasets: {sources}\n\n"
            f"{self._format_retrieval_as_context(result)}"
        )
        return self._truncator.truncate(context, reserve_tokens=2000)

    def _format_retrieval_as_context(self, result: RetrievalResult) -> str:
        """Render a retrieval result as a compact context block."""
        lines: list[str] = [f"Retrieval query: {result.query}"]

        if result.vector_results:
            lines.append("Vector matches:")
            for item in result.vector_results[:5]:
                metadata = item.get("metadata", {})
                dataset_name = metadata.get("dataset_name") or metadata.get("source_dataset")
                prefix = f"- [{item.get('source')}]"
                if dataset_name:
                    prefix += f" ({dataset_name})"
                snippet = str(item.get("document", "")).replace("\n", " ")[:240]
                lines.append(f"{prefix} {snippet}")

        if result.ioc_matches:
            lines.append("IOC matches:")
            for item in result.ioc_matches[:5]:
                lines.append(
                    f"- {item.ioc_type}:{item.value} "
                    f"(confidence={item.confidence}, source={item.source_dataset})"
                )

        if result.graph_connections:
            lines.append("Graph connections:")
            for item in result.graph_connections[:5]:
                lines.append(
                    f"- {item.get('node_type')}:{item.get('label')} "
                    f"related={len(item.get('related_nodes', []))}"
                )

        return "\n".join(lines)

    @staticmethod
    def _result_has_knowledge(result: RetrievalResult) -> bool:
        """Return True when retrieval produced at least one grounded hit."""
        return bool(result.vector_results or result.ioc_matches or result.graph_connections)

    def _collect_source_labels(self, result: RetrievalResult) -> list[str]:
        """Return dataset names, falling back to collection/source labels."""
        sources = self._attribute_sources(result)
        if sources:
            return sources
        labels: list[str] = []
        for item in result.vector_results:
            source = item.get("source") or item.get("collection")
            if source:
                labels.append(str(source))
        if result.ioc_matches:
            labels.append("iocs")
        if result.graph_connections:
            labels.append("graph")
        return self._dedupe(labels)

    def _attribute_sources(self, result: RetrievalResult) -> list[str]:
        """Return dataset names that contributed to the retrieved context."""
        sources: list[str] = []

        for item in result.ioc_matches:
            if item.source_dataset:
                sources.append(item.source_dataset)

        for item in result.vector_results:
            metadata = item.get("metadata", {})
            for key in ("dataset_name", "source_dataset", "case_id"):
                value = metadata.get(key)
                if value:
                    sources.append(str(value))

        for item in result.graph_connections:
            for node in item.get("related_nodes", []):
                if node.get("node_type") == NodeType.DATASET.value:
                    label = node.get("label")
                    if label:
                        sources.append(str(label))

        return self._dedupe(sources)

    @staticmethod
    def _infer_similar_classification_level(result: RetrievalResult) -> str:
        for item in result.vector_results:
            document = str(item.get("document", "")).lower()
            for level in ("critical", "high", "medium", "low", "informational"):
                if f"suspicion_level: {level}" in document or f" {level} " in document:
                    return level
            metadata = item.get("metadata", {})
            if metadata.get("category"):
                return str(metadata["category"])
        return "unknown"

    @staticmethod
    def _infer_similar_reasoning(result: RetrievalResult) -> str:
        for item in result.vector_results:
            document = str(item.get("document", ""))
            if "reasoning:" in document:
                return document.split("reasoning:", maxsplit=1)[1].split("\n", maxsplit=1)[0].strip()
            metadata = item.get("metadata", {})
            if metadata.get("description"):
                return str(metadata["description"])
        if result.ioc_matches and result.ioc_matches[0].description:
            return result.ioc_matches[0].description
        return "prior case correlation and threat intelligence overlap"

    @staticmethod
    def _extract_mitre_techniques(result: RetrievalResult) -> list[str]:
        techniques: list[str] = []
        for item in result.ioc_matches:
            techniques.extend(item.mitre_techniques)
        for item in result.graph_connections:
            if item.get("node_type") == NodeType.MITRE_TECHNIQUE.value:
                label = item.get("label")
                if label:
                    techniques.append(str(label))
            for node in item.get("related_nodes", []):
                if node.get("node_type") == NodeType.MITRE_TECHNIQUE.value:
                    label = node.get("label")
                    if label:
                        techniques.append(str(label))
        return RAGContextBuilder._dedupe(techniques)

    @staticmethod
    def _extract_threat_patterns(result: RetrievalResult) -> str:
        patterns: list[str] = []
        for item in result.vector_results:
            if item.get("source") in {"threat_intel", "knowledge", "iocs"}:
                snippet = str(item.get("document", "")).replace("\n", " ")[:120]
                if snippet:
                    patterns.append(snippet)
        for item in result.ioc_matches:
            if item.description:
                patterns.append(item.description)
        if not patterns:
            return "none identified"
        return "; ".join(RAGContextBuilder._dedupe(patterns)[:5])

    @staticmethod
    def _extract_historical_findings(result: RetrievalResult) -> str:
        findings: list[str] = []
        for item in result.vector_results:
            if item.get("source") == "artefacts":
                metadata = item.get("metadata", {})
                case_id = metadata.get("case_id")
                category = metadata.get("category")
                if case_id or category:
                    findings.append(
                        f"case={case_id or 'unknown'} category={category or 'unknown'}"
                    )
        if not findings:
            return "no directly matching prior case findings"
        return "; ".join(RAGContextBuilder._dedupe(findings)[:5])

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped

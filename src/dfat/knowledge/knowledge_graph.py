"""NetworkX-based forensic knowledge graph for cross-entity correlation."""

from __future__ import annotations

import pickle
from enum import Enum
from pathlib import Path
from typing import Any

import networkx as nx

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.knowledge.ioc_database import IOCEntry


class NodeType(str, Enum):
    """Supported knowledge-graph node categories."""

    ARTEFACT = "ARTEFACT"
    IOC = "IOC"
    MITRE_TECHNIQUE = "MITRE_TECHNIQUE"
    DATASET = "DATASET"
    PROCESS = "PROCESS"
    FILE = "FILE"
    REGISTRY_KEY = "REGISTRY_KEY"
    NETWORK_ENDPOINT = "NETWORK_ENDPOINT"
    USER_ACCOUNT = "USER_ACCOUNT"
    THREAT_ACTOR = "THREAT_ACTOR"


class EdgeType(str, Enum):
    """Supported knowledge-graph relationship categories."""

    RELATED_TO = "RELATED_TO"
    INDICATES = "INDICATES"
    USES_TECHNIQUE = "USES_TECHNIQUE"
    FOUND_IN = "FOUND_IN"
    COMMUNICATES_WITH = "COMMUNICATES_WITH"
    MODIFIES = "MODIFIES"
    CREATES = "CREATES"
    DETECTED_BY = "DETECTED_BY"


_CATEGORY_EDGE_MAP: dict[frozenset[ArtefactCategory], EdgeType] = {
    frozenset({ArtefactCategory.RUNNING_PROCESS, ArtefactCategory.NETWORK_CONNECTION}): (
        EdgeType.COMMUNICATES_WITH
    ),
    frozenset({ArtefactCategory.REGISTRY_KEY, ArtefactCategory.FILESYSTEM_METADATA}): (
        EdgeType.MODIFIES
    ),
    frozenset({ArtefactCategory.RUNNING_PROCESS, ArtefactCategory.INJECTED_CODE}): (
        EdgeType.CREATES
    ),
    frozenset({ArtefactCategory.EVENT_LOG, ArtefactCategory.RUNNING_PROCESS}): (
        EdgeType.DETECTED_BY
    ),
}


class ForensicKnowledgeGraph:
    """Persistent NetworkX graph linking forensic entities and threat intelligence."""

    def __init__(self, persist_path: Path) -> None:
        self._persist_path = Path(persist_path)
        if self._persist_path.suffix in {".pkl", ".pickle", ".graphml"}:
            self._graph_file = self._persist_path
        else:
            self._graph_file = self._persist_path / "knowledge_graph.pkl"
        self._graph: nx.Graph = nx.Graph()
        if self._graph_file.exists():
            self.load()

    @property
    def graph(self) -> nx.Graph:
        """Return the underlying NetworkX graph."""
        return self._graph

    def add_artefact_relationships(self, artefact_set: ArtefactSet) -> int:
        """Add artefact nodes and edges derived from correlation metadata."""
        added_edges = 0
        by_id = {artefact.artefact_id: artefact for artefact in artefact_set.artefacts}

        for artefact in artefact_set.artefacts:
            artefact_node = self._node_id(NodeType.ARTEFACT, artefact.artefact_id)
            self._add_node(
                artefact_node,
                node_type=NodeType.ARTEFACT.value,
                label=artefact.artefact_id,
                category=artefact.category.value,
                evidence_id=artefact.source_evidence_id,
            )
            added_edges += self._link_artefact_entities(artefact, artefact_node)

            related_ids = artefact.metadata.get("correlated_artefact_ids") or []
            if not isinstance(related_ids, list):
                continue
            for other_id in related_ids:
                if other_id not in by_id or other_id == artefact.artefact_id:
                    continue
                other = by_id[other_id]
                edge_type = self._infer_artefact_edge_type(artefact, other)
                if self._add_edge(
                    artefact_node,
                    self._node_id(NodeType.ARTEFACT, other_id),
                    edge_type=edge_type.value,
                ):
                    added_edges += 1
        return added_edges

    def add_ioc_relationships(self, iocs: list[IOCEntry]) -> int:
        """Link IOC nodes to MITRE techniques, datasets, and threat actors."""
        added_edges = 0
        for ioc in iocs:
            ioc_node = self._node_id(NodeType.IOC, ioc.ioc_id)
            self._add_node(
                ioc_node,
                node_type=NodeType.IOC.value,
                label=ioc.value,
                ioc_type=ioc.ioc_type,
                confidence=ioc.confidence,
                description=ioc.description or "",
            )

            dataset_node = self._node_id(NodeType.DATASET, ioc.source_dataset)
            self._add_node(
                dataset_node,
                node_type=NodeType.DATASET.value,
                label=ioc.source_dataset,
            )
            if self._add_edge(ioc_node, dataset_node, edge_type=EdgeType.FOUND_IN.value):
                added_edges += 1

            for technique in ioc.mitre_techniques:
                technique_node = self._node_id(NodeType.MITRE_TECHNIQUE, technique)
                self._add_node(
                    technique_node,
                    node_type=NodeType.MITRE_TECHNIQUE.value,
                    label=technique,
                )
                if self._add_edge(
                    ioc_node,
                    technique_node,
                    edge_type=EdgeType.USES_TECHNIQUE.value,
                ):
                    added_edges += 1

            for tag in ioc.tags:
                actor_name = self._normalise_threat_actor(tag)
                if actor_name is None:
                    continue
                actor_node = self._node_id(NodeType.THREAT_ACTOR, actor_name)
                self._add_node(
                    actor_node,
                    node_type=NodeType.THREAT_ACTOR.value,
                    label=actor_name,
                )
                if self._add_edge(ioc_node, actor_node, edge_type=EdgeType.INDICATES.value):
                    added_edges += 1
        return added_edges

    def add_mitre_mapping(self, technique_id: str, artefact_ids: list[str]) -> None:
        """Map a MITRE technique to one or more artefact nodes."""
        technique_node = self._node_id(NodeType.MITRE_TECHNIQUE, technique_id)
        self._add_node(
            technique_node,
            node_type=NodeType.MITRE_TECHNIQUE.value,
            label=technique_id,
        )
        for artefact_id in artefact_ids:
            artefact_node = self._node_id(NodeType.ARTEFACT, artefact_id)
            if artefact_node not in self._graph:
                self._add_node(
                    artefact_node,
                    node_type=NodeType.ARTEFACT.value,
                    label=artefact_id,
                )
            self._add_edge(
                artefact_node,
                technique_node,
                edge_type=EdgeType.USES_TECHNIQUE.value,
            )

    def query_related(self, node_id: str, max_depth: int = 2) -> list[dict[str, Any]]:
        """Return nodes reachable within ``max_depth`` hops of ``node_id``."""
        if node_id not in self._graph:
            return []

        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}
        related: list[dict[str, Any]] = [self._node_payload(node_id)]

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for current in frontier:
                for neighbour in self._graph.neighbors(current):
                    if neighbour in visited:
                        continue
                    visited.add(neighbour)
                    next_frontier.add(neighbour)
                    related.append(self._node_payload(neighbour))
            frontier = next_frontier
            if not frontier:
                break
        return related

    def query_path(self, from_id: str, to_id: str) -> list[list[str]]:
        """Return simple paths between two node identifiers."""
        if from_id not in self._graph or to_id not in self._graph:
            return []
        try:
            return list(nx.all_simple_paths(self._graph, from_id, to_id, cutoff=6))
        except nx.NetworkXNoPath:
            return []

    def get_clusters(self) -> list[list[str]]:
        """Return connected components as node-id clusters."""
        components = [list(component) for component in nx.connected_components(self._graph)]
        components.sort(key=lambda cluster: (-len(cluster), cluster[0] if cluster else ""))
        return components

    def get_statistics(self) -> dict[str, Any]:
        """Return node and edge counts grouped by semantic type."""
        node_counts: dict[str, int] = {}
        for _, attrs in self._graph.nodes(data=True):
            node_type = str(attrs.get("node_type", "UNKNOWN"))
            node_counts[node_type] = node_counts.get(node_type, 0) + 1

        edge_counts: dict[str, int] = {}
        for _, _, attrs in self._graph.edges(data=True):
            edge_type = str(attrs.get("edge_type", "UNKNOWN"))
            edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1

        return {
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "node_counts_by_type": node_counts,
            "edge_counts_by_type": edge_counts,
            "cluster_count": len(self.get_clusters()),
            "persist_path": str(self._graph_file),
        }

    def save(self) -> None:
        """Serialize the graph to the configured persistence path."""
        self._graph_file.parent.mkdir(parents=True, exist_ok=True)
        if self._graph_file.suffix == ".graphml":
            nx.write_graphml(self._graph, self._graph_file)
            return
        with self._graph_file.open("wb") as handle:
            pickle.dump(self._graph, handle)

    def load(self) -> None:
        """Deserialize the graph from the configured persistence path."""
        if not self._graph_file.exists():
            return
        if self._graph_file.suffix == ".graphml":
            self._graph = nx.read_graphml(self._graph_file)
            return
        with self._graph_file.open("rb") as handle:
            self._graph = pickle.load(handle)

    def _link_artefact_entities(self, artefact: Artefact, artefact_node: str) -> int:
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        added = 0

        if artefact.category is ArtefactCategory.RUNNING_PROCESS:
            process_name = str(raw.get("name") or raw.get("process_name") or artefact.artefact_id)
            process_node = self._node_id(NodeType.PROCESS, process_name)
            self._add_node(process_node, node_type=NodeType.PROCESS.value, label=process_name)
            if self._add_edge(artefact_node, process_node, edge_type=EdgeType.FOUND_IN.value):
                added += 1

        if artefact.category is ArtefactCategory.FILESYSTEM_METADATA:
            file_path = str(raw.get("path") or raw.get("filename") or artefact.source_path or artefact.artefact_id)
            file_node = self._node_id(NodeType.FILE, file_path)
            self._add_node(file_node, node_type=NodeType.FILE.value, label=file_path)
            if self._add_edge(artefact_node, file_node, edge_type=EdgeType.FOUND_IN.value):
                added += 1

        if artefact.category is ArtefactCategory.REGISTRY_KEY:
            registry_key = str(raw.get("key_path") or artefact.source_path or artefact.artefact_id)
            registry_node = self._node_id(NodeType.REGISTRY_KEY, registry_key)
            self._add_node(registry_node, node_type=NodeType.REGISTRY_KEY.value, label=registry_key)
            if self._add_edge(artefact_node, registry_node, edge_type=EdgeType.FOUND_IN.value):
                added += 1

        if artefact.category is ArtefactCategory.NETWORK_CONNECTION:
            endpoint = str(raw.get("remote_address") or raw.get("local_address") or artefact.artefact_id)
            endpoint_node = self._node_id(NodeType.NETWORK_ENDPOINT, endpoint)
            self._add_node(endpoint_node, node_type=NodeType.NETWORK_ENDPOINT.value, label=endpoint)
            if self._add_edge(artefact_node, endpoint_node, edge_type=EdgeType.FOUND_IN.value):
                added += 1

        user_account = raw.get("username") or raw.get("user") or raw.get("account")
        if user_account:
            account_node = self._node_id(NodeType.USER_ACCOUNT, str(user_account))
            self._add_node(
                account_node,
                node_type=NodeType.USER_ACCOUNT.value,
                label=str(user_account),
            )
            if self._add_edge(artefact_node, account_node, edge_type=EdgeType.FOUND_IN.value):
                added += 1

        return added

    def _add_node(self, node_id: str, **attrs: Any) -> None:
        existing = dict(self._graph.nodes.get(node_id, {}))
        existing.update(attrs)
        self._graph.add_node(node_id, **existing)

    def _add_edge(self, left_id: str, right_id: str, *, edge_type: str) -> bool:
        if self._graph.has_edge(left_id, right_id):
            current = self._graph.edges[left_id, right_id].get("edge_type")
            if current == edge_type:
                return False
        self._graph.add_edge(left_id, right_id, edge_type=edge_type)
        return True

    def _node_payload(self, node_id: str) -> dict[str, Any]:
        attrs = dict(self._graph.nodes[node_id])
        return {"node_id": node_id, **attrs}

    @staticmethod
    def _node_id(node_type: NodeType, identifier: str) -> str:
        return f"{node_type.value}:{identifier}"

    @staticmethod
    def _infer_artefact_edge_type(left: Artefact, right: Artefact) -> EdgeType:
        key = frozenset({left.category, right.category})
        return _CATEGORY_EDGE_MAP.get(key, EdgeType.RELATED_TO)

    @staticmethod
    def _normalise_threat_actor(tag: str) -> str | None:
        lowered = tag.strip().lower()
        if not lowered:
            return None
        if lowered.startswith("apt") or lowered.startswith("group") or "actor" in lowered:
            return tag.strip()
        return None

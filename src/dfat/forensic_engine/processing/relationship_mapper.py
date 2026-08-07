"""Relationship mapping — adjacency graph and clusters from correlations."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet

_RELATIONSHIP_TYPES: dict[frozenset[ArtefactCategory], str] = {
    frozenset(
        {ArtefactCategory.RUNNING_PROCESS, ArtefactCategory.NETWORK_CONNECTION}
    ): "process_network",
    frozenset(
        {ArtefactCategory.REGISTRY_KEY, ArtefactCategory.FILESYSTEM_METADATA}
    ): "registry_file",
    frozenset(
        {ArtefactCategory.RUNNING_PROCESS, ArtefactCategory.INJECTED_CODE}
    ): "process_injection",
    frozenset(
        {ArtefactCategory.EVENT_LOG, ArtefactCategory.RUNNING_PROCESS}
    ): "event_process",
}


class RelationshipMap(BaseModel):
    """Adjacency-oriented summary of artefact correlations.

    Attributes:
        edges: Undirected relationship edges as
            ``(artefact_id_a, artefact_id_b, relationship_type)``.
        clusters: Connected components of related artefact IDs.
        total_relationships: Number of unique edges.
    """

    model_config = ConfigDict(frozen=False)

    edges: list[tuple[str, str, str]] = Field(default_factory=list)
    clusters: list[list[str]] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_relationships(self) -> int:
        """Return the number of unique relationship edges."""
        return len(self.edges)


class RelationshipMapper:
    """Build a relationship graph from ``correlated_artefact_ids`` metadata."""

    def build_map(self, artefact_set: ArtefactSet) -> RelationshipMap:
        """Create an adjacency-list-backed relationship map and clusters.

        Args:
            artefact_set: Artefact collection with correlation metadata.

        Returns:
            ``RelationshipMap`` with unique edges and connected clusters.
        """
        by_id = {artefact.artefact_id: artefact for artefact in artefact_set.artefacts}
        adjacency: dict[str, set[str]] = defaultdict(set)

        for artefact in artefact_set.artefacts:
            related = artefact.metadata.get("correlated_artefact_ids") or []
            if not isinstance(related, list):
                continue
            for other_id in related:
                if other_id not in by_id or other_id == artefact.artefact_id:
                    continue
                adjacency[artefact.artefact_id].add(other_id)
                adjacency[other_id].add(artefact.artefact_id)

        edges = self._build_edges(adjacency, by_id)
        clusters = self._build_clusters(adjacency, set(by_id.keys()))
        return RelationshipMap(edges=edges, clusters=clusters)

    def _build_edges(
        self,
        adjacency: dict[str, set[str]],
        by_id: dict[str, Artefact],
    ) -> list[tuple[str, str, str]]:
        """Emit unique undirected edges with inferred relationship types."""
        edges: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for left_id, neighbours in adjacency.items():
            for right_id in neighbours:
                pair = (left_id, right_id) if left_id < right_id else (right_id, left_id)
                if pair in seen:
                    continue
                seen.add(pair)
                rel_type = self._relationship_type(by_id.get(pair[0]), by_id.get(pair[1]))
                edges.append((pair[0], pair[1], rel_type))
        edges.sort(key=lambda item: (item[0], item[1], item[2]))
        return edges

    def _build_clusters(
        self,
        adjacency: dict[str, set[str]],
        all_ids: set[str],
    ) -> list[list[str]]:
        """Compute connected components; singleton nodes are omitted."""
        visited: set[str] = set()
        clusters: list[list[str]] = []
        # Only traverse nodes that participate in at least one edge.
        linked_ids = {node for node, neighbours in adjacency.items() if neighbours}
        for start in sorted(linked_ids):
            if start in visited:
                continue
            component: list[str] = []
            queue: deque[str] = deque([start])
            visited.add(start)
            while queue:
                current = queue.popleft()
                component.append(current)
                for neighbour in sorted(adjacency.get(current, ())):
                    if neighbour not in visited:
                        visited.add(neighbour)
                        queue.append(neighbour)
            if len(component) > 1:
                clusters.append(sorted(component))
        clusters.sort(key=lambda cluster: (-len(cluster), cluster[0] if cluster else ""))
        return clusters

    @staticmethod
    def _relationship_type(
        left: Optional[Artefact],
        right: Optional[Artefact],
    ) -> str:
        """Infer a relationship label from the categories of both artefacts."""
        if left is None or right is None:
            return "related"
        key = frozenset({left.category, right.category})
        return _RELATIONSHIP_TYPES.get(key, "related")

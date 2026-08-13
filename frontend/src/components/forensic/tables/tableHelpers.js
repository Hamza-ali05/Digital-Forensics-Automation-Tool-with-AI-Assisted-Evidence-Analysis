import React from "react";
import { Badge, Button } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBrain,
  faEye,
  faProjectDiagram,
} from "@fortawesome/free-solid-svg-icons";

import StatusBadge from "components/common/StatusBadge";

/**
 * Shared suspicion + score columns for category artefact tables.
 */
export function suspicionScoreColumns() {
  return [
    {
      key: "suspicion_level",
      header: "Suspicion",
      render: (row) => (
        <StatusBadge status={row.suspicion_level} type="suspicion" />
      ),
    },
    {
      key: "relevance_score",
      header: "Score",
      render: (row) => (
        <span>{(Number(row.relevance_score) || 0).toFixed(2)}</span>
      ),
    },
  ];
}

/**
 * Optional action buttons renderer for category tables.
 */
export function renderArtefactActions(row, handlers = {}) {
  const { onViewDetails, onAiExplain, onViewCorrelations } = handlers;
  if (!onViewDetails && !onAiExplain && !onViewCorrelations) return null;

  const hasCorrelations = (row.metadata?.correlated_artefact_ids || []).length > 0;

  return (
    <div className="d-flex flex-wrap gap-1 justify-content-end">
      {onViewDetails ? (
        <Button
          size="sm"
          variant="outline-primary"
          onClick={() => onViewDetails(row)}
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          Details
        </Button>
      ) : null}
      {onAiExplain ? (
        <Button
          size="sm"
          variant="outline-secondary"
          onClick={() => onAiExplain(row)}
        >
          <FontAwesomeIcon icon={faBrain} className="me-1" />
          AI Explain
        </Button>
      ) : null}
      {onViewCorrelations && hasCorrelations ? (
        <Button
          size="sm"
          variant="outline-info"
          onClick={() => onViewCorrelations(row)}
        >
          <FontAwesomeIcon icon={faProjectDiagram} className="me-1" />
          Correlations
        </Button>
      ) : null}
    </div>
  );
}

export function truncateText(value, max = 60) {
  if (value == null || value === "") return "—";
  const text = String(value);
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

export function raw(row) {
  return row?.raw_data && typeof row.raw_data === "object" ? row.raw_data : {};
}

/**
 * Deleted-file badge used by filesystem tables.
 */
export function DeletedBadge({ deleted }) {
  if (!deleted) {
    return <Badge bg="light" text="dark">No</Badge>;
  }
  return <Badge bg="danger">Yes</Badge>;
}

import React, { useMemo } from "react";
import {
  Badge,
  Button,
  ListGroup,
  Modal,
  ProgressBar,
} from "@themesberg/react-bootstrap";
import { Link } from "react-router-dom";

import StatusBadge from "components/common/StatusBadge";
import { formatArtefactId } from "utils/formatters";
import { Routes } from "routes";

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function flattenRawData(rawData) {
  if (!rawData || typeof rawData !== "object") return [];
  return Object.entries(rawData).map(([key, value]) => ({
    key,
    value: formatValue(value),
  }));
}

/**
 * Modal showing full artefact details including raw_data and correlations.
 *
 * @param {{
 *   show: boolean,
 *   onHide: () => void,
 *   artefact?: object | null,
 *   evidenceId?: string,
 *   onSelectArtefact?: (artefactId: string) => void,
 * }} props
 */
export default function ArtefactDetailModal({
  show,
  onHide,
  artefact,
  evidenceId,
  onSelectArtefact,
}) {
  const rawFields = useMemo(
    () => flattenRawData(artefact?.raw_data),
    [artefact]
  );

  const correlatedIds = useMemo(() => {
    const ids = artefact?.metadata?.correlated_artefact_ids;
    return Array.isArray(ids) ? ids.filter(Boolean) : [];
  }, [artefact]);

  const scorePercent = Math.round(
    Math.min(100, Math.max(0, (Number(artefact?.relevance_score) || 0) * 100))
  );

  if (!artefact) {
    return (
      <Modal show={show} onHide={onHide} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title>Artefact Details</Modal.Title>
        </Modal.Header>
        <Modal.Body className="text-muted">No artefact selected.</Modal.Body>
      </Modal>
    );
  }

  const metadataEntries =
    artefact.metadata && typeof artefact.metadata === "object"
      ? Object.entries(artefact.metadata).filter(
          ([key]) => key !== "correlated_artefact_ids"
        )
      : [];

  return (
    <Modal show={show} onHide={onHide} size="lg" centered scrollable>
      <Modal.Header closeButton>
        <Modal.Title>
          Artefact {formatArtefactId(artefact.artefact_id)}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <dl className="row mb-3">
          <dt className="col-sm-3">ID</dt>
          <dd className="col-sm-9">
            <code>{artefact.artefact_id}</code>
          </dd>

          <dt className="col-sm-3">Category</dt>
          <dd className="col-sm-9">{humanise(artefact.category)}</dd>

          <dt className="col-sm-3">Suspicion</dt>
          <dd className="col-sm-9">
            <StatusBadge
              status={artefact.suspicion_level}
              type="suspicion"
            />
          </dd>

          <dt className="col-sm-3">Relevance</dt>
          <dd className="col-sm-9">
            <div className="d-flex align-items-center gap-2">
              <ProgressBar
                now={scorePercent}
                label={`${scorePercent}%`}
                style={{ minWidth: 140, flex: "1 1 auto" }}
                variant={
                  scorePercent >= 75
                    ? "danger"
                    : scorePercent >= 50
                      ? "warning"
                      : "info"
                }
              />
              <span className="text-muted small">
                {(Number(artefact.relevance_score) || 0).toFixed(2)}
              </span>
            </div>
          </dd>

          {artefact.source_path ? (
            <>
              <dt className="col-sm-3">Source path</dt>
              <dd className="col-sm-9">
                <code className="small">{artefact.source_path}</code>
              </dd>
            </>
          ) : null}
        </dl>

        {artefact.classification_reasoning ? (
          <>
            <h6 className="text-uppercase text-muted small fw-bold">
              Classification reasoning
            </h6>
            <p className="small">{artefact.classification_reasoning}</p>
          </>
        ) : null}

        <h6 className="text-uppercase text-muted small fw-bold mt-4">
          Raw data
        </h6>
        {rawFields.length ? (
          <ListGroup className="mb-3">
            {rawFields.map(({ key, value }) => (
              <ListGroup.Item key={key}>
                <div className="fw-bold small text-muted">{humanise(key)}</div>
                <pre
                  className="mb-0 small text-break"
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {value}
                </pre>
              </ListGroup.Item>
            ))}
          </ListGroup>
        ) : (
          <p className="text-muted small">No raw data fields.</p>
        )}

        {metadataEntries.length ? (
          <>
            <h6 className="text-uppercase text-muted small fw-bold mt-4">
              Metadata
            </h6>
            <ListGroup className="mb-3">
              {metadataEntries.map(([key, value]) => (
                <ListGroup.Item key={key}>
                  <div className="fw-bold small text-muted">{humanise(key)}</div>
                  <pre
                    className="mb-0 small text-break"
                    style={{ whiteSpace: "pre-wrap" }}
                  >
                    {formatValue(value)}
                  </pre>
                </ListGroup.Item>
              ))}
            </ListGroup>
          </>
        ) : null}

        {correlatedIds.length ? (
          <>
            <h6 className="text-uppercase text-muted small fw-bold mt-4">
              Correlated artefacts
            </h6>
            <div className="d-flex flex-wrap gap-2">
              {correlatedIds.map((id) =>
                typeof onSelectArtefact === "function" ? (
                  <Button
                    key={id}
                    size="sm"
                    variant="outline-primary"
                    onClick={() => onSelectArtefact(id)}
                  >
                    {formatArtefactId(id)}
                  </Button>
                ) : (
                  <Badge
                    key={id}
                    as={Link}
                    bg="secondary"
                    to={
                      evidenceId
                        ? Routes.Artefacts.path.replace(":id", evidenceId)
                        : "#"
                    }
                    className="text-decoration-none"
                  >
                    {formatArtefactId(id)}
                  </Badge>
                )
              )}
            </div>
          </>
        ) : null}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
}

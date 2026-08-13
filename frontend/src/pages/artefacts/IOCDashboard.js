import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";
import {
  faBug,
  faExclamationTriangle,
  faShieldAlt,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  ArcElement,
  Legend,
  Tooltip,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import StatCard from "components/forensic/StatCard";
import { formatArtefactId } from "utils/formatters";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  loadArtefactsForEvidence,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import { detectIocs, iocDisplayType } from "utils/iocDetect";
import { Routes } from "routes";

ChartJS.register(ArcElement, Legend, Tooltip);

const CONFIDENCE_COLOURS = {
  high: "#dc3545",
  medium: "#fd7e14",
  low: "#ffc107",
};

const TYPE_COLOURS = {
  process: "#dc3545",
  registry: "#6f42c1",
  network: "#0d6efd",
  file: "#198754",
  injection: "#fd7e14",
};

function ConfidenceBadge({ confidence }) {
  const key = String(confidence || "").toLowerCase();
  const colour = CONFIDENCE_COLOURS[key] || "#6c757d";
  const textColour = key === "low" ? "#212529" : "#fff";
  return (
    <Badge style={{ backgroundColor: colour, color: textColour }}>
      {key ? key.replace(/\b\w/g, (c) => c.toUpperCase()) : "—"}
    </Badge>
  );
}

function useQueryEvidenceId() {
  const location = useLocation();
  const params = new URLSearchParams(location.search || "");
  return params.get("evidence_id") || params.get("evidence") || "";
}

/**
 * Indicators of Compromise dashboard derived from pipeline artefacts.
 */
export default function IOCDashboard() {
  const history = useHistory();
  const queryEvidenceId = useQueryEvidenceId();

  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState(queryEvidenceId);
  const [artefacts, setArtefacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [detailArtefact, setDetailArtefact] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    if (queryEvidenceId && queryEvidenceId !== selectedEvidenceId) {
      setSelectedEvidenceId(queryEvidenceId);
    }
  }, [queryEvidenceId, selectedEvidenceId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const options = await loadEvidenceOptions();
      setEvidenceOptions(options);
      if (selectedEvidenceId) {
        const { artefacts: rows } = await loadArtefactsForEvidence(
          selectedEvidenceId
        );
        setArtefacts(rows);
      } else {
        setArtefacts([]);
      }
    } catch (err) {
      setError(err);
      setArtefacts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedEvidenceId]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  const handleEvidenceChange = (event) => {
    const nextId = event.target.value;
    setSelectedEvidenceId(nextId);
    if (nextId) {
      history.replace(`${Routes.ArtefactsIOCs.path}?evidence_id=${nextId}`);
    } else {
      history.replace(Routes.ArtefactsIOCs.path);
    }
  };

  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const iocs = useMemo(() => detectIocs(artefacts), [artefacts]);

  const summary = useMemo(() => {
    const byConfidence = { high: 0, medium: 0, low: 0 };
    const byType = {};
    iocs.forEach((ioc) => {
      const conf = String(ioc.confidence || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(byConfidence, conf)) {
        byConfidence[conf] += 1;
      }
      const type = iocDisplayType(ioc.ioc_type);
      byType[type] = (byType[type] || 0) + 1;
    });
    return { total: iocs.length, byConfidence, byType };
  }, [iocs]);

  const chartData = useMemo(() => {
    const labels = Object.keys(summary.byType);
    return {
      labels: labels.map((label) =>
        String(label).replace(/\b\w/g, (c) => c.toUpperCase())
      ),
      datasets: [
        {
          data: labels.map((label) => summary.byType[label]),
          backgroundColor: labels.map(
            (label) => TYPE_COLOURS[label] || "#6c757d"
          ),
          borderWidth: 1,
        },
      ],
    };
  }, [summary]);

  const openArtefact = useCallback(
    (artefactId) => {
      const found = artefactById.get(artefactId);
      if (found) {
        setDetailArtefact(found);
        setDetailOpen(true);
      }
    },
    [artefactById]
  );

  const columns = useMemo(
    () => [
      {
        key: "ioc_type",
        header: "IOC Type",
        render: (row) => (
          <Badge
            bg="light"
            text="dark"
            className="text-uppercase"
          >
            {iocDisplayType(row.ioc_type)}
          </Badge>
        ),
      },
      {
        key: "indicator",
        header: "Indicator",
        render: (row) => (
          <code className="small text-break">{row.indicator}</code>
        ),
      },
      {
        key: "confidence",
        header: "Confidence",
        render: (row) => <ConfidenceBadge confidence={row.confidence} />,
      },
      {
        key: "description",
        header: "Description",
        render: (row) => <span className="small">{row.description}</span>,
      },
      {
        key: "matched_rule",
        header: "Matched Rule",
        render: (row) => (
          <code className="small">{row.matched_rule}</code>
        ),
      },
      {
        key: "artefact",
        header: "Artefact",
        render: (row) => (
          <Button
            size="sm"
            variant="link"
            className="p-0"
            onClick={() => openArtefact(row.artefact_id)}
          >
            {formatArtefactId(row.artefact_id)}
          </Button>
        ),
      },
    ],
    [openArtefact]
  );

  if (loading && !artefacts.length && !evidenceOptions.length) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader variant="card" count={3} />
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Indicators of Compromise"
        subtitle="Pattern-based threat indicators detected in pipeline artefacts"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Indicators of Compromise" },
        ]}
        actions={
          <Form.Select
            value={selectedEvidenceId}
            onChange={handleEvidenceChange}
            style={{ minWidth: 260 }}
            aria-label="Evidence selector"
          >
            <option value="">Select evidence…</option>
            {evidenceOptions.map((item) => {
              const eid = evidenceOptionId(item);
              return (
                <option key={eid} value={eid}>
                  {evidenceOptionLabel(item)}
                </option>
              );
            })}
          </Form.Select>
        }
      />

      {error ? (
        <ApiErrorDisplay
          error={error}
          onRetry={() => refresh().catch(() => {})}
          className="mb-3"
        />
      ) : null}

      {!selectedEvidenceId ? (
        <EmptyState
          title="No evidence selected"
          description="Choose an evidence item with a completed pipeline report to scan for IOCs."
        />
      ) : loading ? (
        <SkeletonLoader variant="card" count={3} />
      ) : !artefacts.length ? (
        <EmptyState
          title="No artefacts available"
          description="Complete a pipeline run for this evidence to identify indicators of compromise."
          actionLabel="Run pipeline"
          onAction={() => history.push(Routes.PipelineRun.path)}
        />
      ) : !iocs.length ? (
        <EmptyState
          title="No IOCs identified"
          description="Artefacts were loaded, but no indicator patterns matched. Review the artefact explorer for lower-confidence findings."
          actionLabel="Open explorer"
          onAction={() =>
            history.push(
              Routes.Artefacts.path.replace(":id", selectedEvidenceId)
            )
          }
        />
      ) : (
        <>
          <Row className="g-3 mb-4">
            <Col xs={12} sm={6} xl={3}>
              <StatCard
                title="Total IOCs"
                value={summary.total}
                icon={faBug}
                colour="danger"
              />
            </Col>
            <Col xs={12} sm={6} xl={3}>
              <StatCard
                title="High Confidence"
                value={summary.byConfidence.high}
                icon={faExclamationTriangle}
                colour="danger"
              />
            </Col>
            <Col xs={12} sm={6} xl={3}>
              <StatCard
                title="Medium Confidence"
                value={summary.byConfidence.medium}
                icon={faShieldAlt}
                colour="warning"
              />
            </Col>
            <Col xs={12} sm={6} xl={3}>
              <StatCard
                title="Low Confidence"
                value={summary.byConfidence.low}
                icon={faShieldAlt}
                colour="secondary"
              />
            </Col>
          </Row>

          <Row className="g-3 mb-4">
            <Col xs={12} lg={4}>
              <Card border="light" className="shadow-sm h-100">
                <Card.Header className="border-bottom border-light">
                  <h5 className="mb-0">By IOC Type</h5>
                </Card.Header>
                <Card.Body>
                  {summary.total ? (
                    <div style={{ maxWidth: 280, margin: "0 auto" }}>
                      <Doughnut
                        data={chartData}
                        options={{
                          plugins: {
                            legend: { position: "bottom" },
                          },
                          maintainAspectRatio: true,
                        }}
                      />
                    </div>
                  ) : (
                    <p className="text-muted small mb-0 text-center py-4">
                      No IOC types to chart.
                    </p>
                  )}
                  <div className="d-flex flex-wrap gap-2 justify-content-center mt-3">
                    {Object.entries(summary.byType).map(([type, count]) => (
                      <Badge
                        key={type}
                        style={{
                          backgroundColor: TYPE_COLOURS[type] || "#6c757d",
                          color: "#fff",
                        }}
                      >
                        {String(type).replace(/\b\w/g, (c) => c.toUpperCase())}:{" "}
                        {count}
                      </Badge>
                    ))}
                  </div>
                </Card.Body>
              </Card>
            </Col>
            <Col xs={12} lg={8}>
              <Card border="light" className="shadow-sm h-100">
                <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
                  <h5 className="mb-0">IOC Matches</h5>
                  {selectedEvidenceId ? (
                    <Button
                      as={Link}
                      to={Routes.Artefacts.path.replace(
                        ":id",
                        selectedEvidenceId
                      )}
                      size="sm"
                      variant="outline-primary"
                    >
                      Open explorer
                    </Button>
                  ) : null}
                </Card.Header>
                <Card.Body className="p-0">
                  <DataTable
                    columns={columns}
                    data={iocs}
                    emptyMessage="No indicators of compromise matched for this evidence."
                  />
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </>
      )}

      <ArtefactDetailModal
        show={detailOpen}
        onHide={() => setDetailOpen(false)}
        artefact={detailArtefact}
        evidenceId={selectedEvidenceId}
        onSelectArtefact={(id) => {
          const found = artefactById.get(id);
          if (found) setDetailArtefact(found);
        }}
      />
    </Container>
  );
}

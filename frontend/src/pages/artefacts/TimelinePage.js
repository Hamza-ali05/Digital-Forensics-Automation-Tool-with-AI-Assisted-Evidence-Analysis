import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  ButtonGroup,
  Card,
  Col,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faClock,
  faCode,
  faFolder,
  faGlobe,
  faHdd,
  faKey,
  faNetworkWired,
  faListAlt,
  faStream,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import SuspicionFilter from "components/forensic/SuspicionFilter";
import {
  ARTEFACT_CATEGORY,
  SUSPICION_COLOURS,
} from "utils/constants";
import { formatArtefactId, formatDate } from "utils/formatters";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  loadArtefactsForEvidence,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import {
  TIMELINE_ZOOM_OPTIONS,
  applyTimelineZoom,
  buildTimelineEntries,
  groupTimelineWindows,
} from "utils/timeline";
import { Routes } from "routes";

const CATEGORY_OPTIONS = [
  { value: ARTEFACT_CATEGORY.FILESYSTEM_METADATA, label: "File System", icon: faHdd },
  { value: ARTEFACT_CATEGORY.REGISTRY_KEY, label: "Registry", icon: faKey },
  { value: ARTEFACT_CATEGORY.BROWSER_HISTORY, label: "Browser History", icon: faGlobe },
  { value: ARTEFACT_CATEGORY.EVENT_LOG, label: "Event Logs", icon: faListAlt },
  { value: ARTEFACT_CATEGORY.RUNNING_PROCESS, label: "Processes", icon: faStream },
  { value: ARTEFACT_CATEGORY.NETWORK_CONNECTION, label: "Network", icon: faNetworkWired },
  { value: ARTEFACT_CATEGORY.INJECTED_CODE, label: "Injected Code", icon: faCode },
];

const CATEGORY_ICON_MAP = CATEGORY_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.icon;
  return acc;
}, {});

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function useQueryEvidenceId() {
  const location = useLocation();
  const params = new URLSearchParams(location.search || "");
  return params.get("evidence_id") || params.get("evidence") || "";
}

/**
 * Chronological artefact timeline with zoom and suspicion colouring.
 */
export default function TimelinePage() {
  const history = useHistory();
  const queryEvidenceId = useQueryEvidenceId();

  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState(queryEvidenceId);
  const [artefacts, setArtefacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [zoom, setZoom] = useState("all");
  const [suspicionFilter, setSuspicionFilter] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState([]);

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
      history.replace(`${Routes.ArtefactsTimeline.path}?evidence_id=${nextId}`);
    } else {
      history.replace(Routes.ArtefactsTimeline.path);
    }
  };

  const allEntries = useMemo(
    () => buildTimelineEntries(artefacts),
    [artefacts]
  );

  const filteredEntries = useMemo(() => {
    let rows = applyTimelineZoom(allEntries, zoom);

    if (categoryFilter.length) {
      const allowed = new Set(categoryFilter.map((c) => String(c).toLowerCase()));
      rows = rows.filter((row) =>
        allowed.has(String(row.category || "").toLowerCase())
      );
    }

    if (suspicionFilter.length) {
      const allowed = new Set(
        suspicionFilter.map((level) => String(level).toLowerCase())
      );
      rows = rows.filter((row) =>
        allowed.has(String(row.suspicion_level || "").toLowerCase())
      );
    }

    return rows;
  }, [allEntries, zoom, categoryFilter, suspicionFilter]);

  const windows = useMemo(
    () => groupTimelineWindows(filteredEntries, 3600),
    [filteredEntries]
  );

  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const openDetails = (entry) => {
    const found = entry.artefact || artefactById.get(entry.artefact_id);
    if (found) {
      setDetailArtefact(found);
      setDetailOpen(true);
    }
  };

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
        title="Timeline Analysis"
        subtitle="Chronological view of timestamped artefact events"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Timeline Analysis" },
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
          description="Choose an evidence item to build a timeline from pipeline artefacts."
        />
      ) : loading ? (
        <SkeletonLoader variant="card" count={2} />
      ) : !allEntries.length ? (
        <EmptyState
          title="Run the pipeline to generate timeline data."
          description="No timestamped artefact fields were found for this evidence. Complete a pipeline run first."
          actionLabel="Run pipeline"
          onAction={() => history.push(Routes.PipelineRun.path)}
        />
      ) : (
        <>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3 align-items-end">
                <Col xs={12} lg={4}>
                  <SuspicionFilter
                    value={suspicionFilter}
                    onChange={setSuspicionFilter}
                  />
                </Col>
                <Col xs={12} md={6} lg={4}>
                  <Form.Label className="small text-muted text-uppercase fw-bold">
                    Category
                  </Form.Label>
                  <Form.Select
                    multiple
                    htmlSize={4}
                    value={categoryFilter}
                    onChange={(event) => {
                      setCategoryFilter(
                        Array.from(event.target.selectedOptions, (opt) => opt.value)
                      );
                    }}
                  >
                    {CATEGORY_OPTIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
                <Col xs={12} md={6} lg={4}>
                  <Form.Label className="small text-muted text-uppercase fw-bold d-block">
                    Zoom
                  </Form.Label>
                  <ButtonGroup>
                    {TIMELINE_ZOOM_OPTIONS.map(({ value, label }) => (
                      <Button
                        key={value}
                        size="sm"
                        variant={zoom === value ? "primary" : "outline-primary"}
                        onClick={() => setZoom(value)}
                      >
                        {label}
                      </Button>
                    ))}
                  </ButtonGroup>
                  <div className="small text-muted mt-2">
                    Showing {filteredEntries.length} of {allEntries.length} events
                    {selectedEvidenceId ? (
                      <>
                        {" · "}
                        <Link
                          to={Routes.Artefacts.path.replace(
                            ":id",
                            selectedEvidenceId
                          )}
                        >
                          Open explorer
                        </Link>
                      </>
                    ) : null}
                  </div>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          {!filteredEntries.length ? (
            <EmptyState
              title="No events in this view"
              description="Adjust zoom or filters to see timeline events."
            />
          ) : (
            <div className="dfat-timeline">
              {windows.map((window) => (
                <div
                  key={`${window.window_start.toISOString()}-${window.window_end.toISOString()}`}
                  className="mb-4"
                >
                  <div className="d-flex align-items-center gap-2 mb-3">
                    <FontAwesomeIcon icon={faClock} className="text-muted" />
                    <span className="fw-bold small text-uppercase text-muted">
                      {formatDate(window.window_start.toISOString())}
                      {" – "}
                      {formatDate(window.window_end.toISOString())}
                    </span>
                    <Badge bg="light" text="dark">
                      {window.entries.length} event
                      {window.entries.length === 1 ? "" : "s"}
                    </Badge>
                  </div>

                  <div
                    className="ps-3"
                    style={{
                      borderLeft: "3px solid #dee2e6",
                      marginLeft: 6,
                    }}
                  >
                    {window.entries.map((entry) => {
                      const colour =
                        SUSPICION_COLOURS[
                          String(entry.suspicion_level || "").toLowerCase()
                        ] || "#6c757d";
                      const icon =
                        CATEGORY_ICON_MAP[entry.category] || faFolder;
                      return (
                        <div
                          key={entry.id}
                          className="position-relative mb-3"
                          style={{ paddingLeft: 18 }}
                        >
                          <span
                            aria-hidden
                            style={{
                              position: "absolute",
                              left: -10,
                              top: 10,
                              width: 14,
                              height: 14,
                              borderRadius: "50%",
                              backgroundColor: colour,
                              border: "2px solid #fff",
                              boxShadow: `0 0 0 2px ${colour}`,
                            }}
                          />
                          <Card
                            border="light"
                            className="shadow-sm"
                            style={{
                              borderLeft: `4px solid ${colour}`,
                            }}
                          >
                            <Card.Body className="py-3">
                              <div className="d-flex flex-wrap justify-content-between gap-2 mb-2">
                                <div className="d-flex align-items-center gap-2">
                                  <FontAwesomeIcon
                                    icon={icon}
                                    className="text-muted"
                                  />
                                  <span className="small text-muted">
                                    {formatDate(entry.timestamp.toISOString())}
                                  </span>
                                  <Badge bg="light" text="dark">
                                    {humanise(entry.category)}
                                  </Badge>
                                </div>
                                <StatusBadge
                                  status={entry.suspicion_level}
                                  type="suspicion"
                                />
                              </div>
                              <p className="mb-2 small">{entry.description}</p>
                              <div className="d-flex flex-wrap gap-2">
                                <Button
                                  size="sm"
                                  variant="outline-primary"
                                  onClick={() => openDetails(entry)}
                                >
                                  View artefact {formatArtefactId(entry.artefact_id)}
                                </Button>
                                <code className="small text-muted align-self-center">
                                  {entry.source_field}
                                </code>
                              </div>
                            </Card.Body>
                          </Card>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
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

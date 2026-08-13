import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Modal,
  Nav,
  Row,
  Spinner,
  Tab,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBrain,
  faEye,
  faLink,
  faProjectDiagram,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import SearchInput from "components/common/SearchInput";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import SuspicionFilter from "components/forensic/SuspicionFilter";
import FileSystemTable from "components/forensic/tables/FileSystemTable";
import RegistryTable from "components/forensic/tables/RegistryTable";
import BrowserHistoryTable from "components/forensic/tables/BrowserHistoryTable";
import EventLogTable from "components/forensic/tables/EventLogTable";
import ProcessTable from "components/forensic/tables/ProcessTable";
import NetworkTable from "components/forensic/tables/NetworkTable";
import InjectedCodeTable from "components/forensic/tables/InjectedCodeTable";
import {
  ARTEFACT_CATEGORY,
  JOB_STATUS,
  SUSPICION_LEVEL,
} from "utils/constants";
import {
  formatArtefactId,
  formatSuspicionLevel,
} from "utils/formatters";
import useNotification from "hooks/useNotification";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import aiService from "services/ai.service";
import { Routes } from "routes";

const COMPLETED = new Set([JOB_STATUS.COMPLETED, "completed"]);

const TAB_ITEMS = [
  { eventKey: "all", label: "All", category: null },
  {
    eventKey: ARTEFACT_CATEGORY.FILESYSTEM_METADATA,
    label: "File System",
    category: ARTEFACT_CATEGORY.FILESYSTEM_METADATA,
  },
  {
    eventKey: ARTEFACT_CATEGORY.REGISTRY_KEY,
    label: "Registry",
    category: ARTEFACT_CATEGORY.REGISTRY_KEY,
  },
  {
    eventKey: ARTEFACT_CATEGORY.BROWSER_HISTORY,
    label: "Browser History",
    category: ARTEFACT_CATEGORY.BROWSER_HISTORY,
  },
  {
    eventKey: ARTEFACT_CATEGORY.EVENT_LOG,
    label: "Event Logs",
    category: ARTEFACT_CATEGORY.EVENT_LOG,
  },
  {
    eventKey: ARTEFACT_CATEGORY.RUNNING_PROCESS,
    label: "Processes",
    category: ARTEFACT_CATEGORY.RUNNING_PROCESS,
  },
  {
    eventKey: ARTEFACT_CATEGORY.NETWORK_CONNECTION,
    label: "Network",
    category: ARTEFACT_CATEGORY.NETWORK_CONNECTION,
  },
  {
    eventKey: ARTEFACT_CATEGORY.INJECTED_CODE,
    label: "Injected Code",
    category: ARTEFACT_CATEGORY.INJECTED_CODE,
  },
];

const CATEGORY_OPTIONS = TAB_ITEMS.filter((tab) => tab.category).map((tab) => ({
  value: tab.category,
  label: tab.label,
}));

const SORT_OPTIONS = [
  { value: "relevance_score", label: "Relevance score" },
  { value: "category", label: "Category" },
  { value: "timestamp", label: "Timestamp" },
];

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function evidenceLabel(item) {
  if (!item) return "—";
  const name = item.filename || item.name || item.label;
  if (name) return `${name} (${shortId(item.id || item.evidence_id)})`;
  return shortId(item.id || item.evidence_id);
}

function artefactTimestamp(artefact) {
  const raw = artefact?.raw_data || {};
  const candidates = [
    raw.timestamp,
    raw.time,
    raw.event_time,
    raw.created_at,
    raw.modified_at,
    raw.last_accessed,
    raw.access_time,
    artefact?.metadata?.timestamp,
  ];
  for (const value of candidates) {
    if (!value) continue;
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.getTime();
  }
  return 0;
}

function rawDataSearchText(rawData) {
  if (rawData == null) return "";
  if (typeof rawData !== "object") return String(rawData).toLowerCase();
  try {
    return JSON.stringify(rawData).toLowerCase();
  } catch {
    return String(rawData).toLowerCase();
  }
}

function buildSummary(artefact) {
  const raw = artefact?.raw_data || {};
  const parts = [
    raw.path,
    raw.file_path,
    raw.name,
    raw.process_name,
    raw.command_line,
    raw.url,
    raw.key_path,
    raw.registry_path,
    raw.event_id,
    raw.remote_address,
    raw.local_address,
    raw.description,
    raw.title,
  ].filter(Boolean);
  if (parts.length) return String(parts[0]).slice(0, 120);
  const keys = Object.keys(raw);
  if (!keys.length) return "—";
  const preview = keys
    .slice(0, 3)
    .map((key) => `${key}: ${formatPreview(raw[key])}`)
    .join(" · ");
  return preview.slice(0, 120);
}

function formatPreview(value) {
  if (value == null) return "";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value).slice(0, 40);
    } catch {
      return String(value).slice(0, 40);
    }
  }
  return String(value).slice(0, 40);
}

function findLatestReportJob(jobs, evidenceId) {
  const matches = (jobs || []).filter(
    (job) =>
      String(job.evidence_id) === String(evidenceId) &&
      job.report_id &&
      COMPLETED.has(String(job.status || "").toLowerCase())
  );
  if (!matches.length) return null;
  return matches.sort((a, b) => {
    const aTime = new Date(a.completed_at || a.created_at || 0).getTime();
    const bTime = new Date(b.completed_at || b.created_at || 0).getTime();
    return bTime - aTime;
  })[0];
}

/**
 * Unified columns for the All tab only.
 */
function getUnifiedColumns(handlers) {
  return [
    {
      key: "artefact_id",
      header: "ID",
      render: (row) => (
        <code title={row.artefact_id}>{formatArtefactId(row.artefact_id)}</code>
      ),
    },
    {
      key: "category",
      header: "Category",
      render: (row) => humanise(row.category),
    },
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
    {
      key: "summary",
      header: "Summary",
      render: (row) => (
        <span className="small text-muted">{buildSummary(row)}</span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <div className="d-flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="outline-primary"
            onClick={() => handlers.onViewDetails(row)}
          >
            <FontAwesomeIcon icon={faEye} className="me-1" />
            Details
          </Button>
          <Button
            size="sm"
            variant="outline-secondary"
            onClick={() => handlers.onAiExplain(row)}
          >
            <FontAwesomeIcon icon={faBrain} className="me-1" />
            AI Explain
          </Button>
          {(row.metadata?.correlated_artefact_ids || []).length ? (
            <Button
              size="sm"
              variant="outline-info"
              onClick={() => handlers.onViewCorrelations(row)}
            >
              <FontAwesomeIcon icon={faProjectDiagram} className="me-1" />
              Correlations
            </Button>
          ) : null}
        </div>
      ),
    },
  ];
}

function renderCategoryTable(tabKey, data, loading, emptyMessage, handlers) {
  const shared = {
    data,
    loading,
    emptyMessage,
    onViewDetails: handlers.onViewDetails,
    onAiExplain: handlers.onAiExplain,
    onViewCorrelations: handlers.onViewCorrelations,
  };

  switch (tabKey) {
    case ARTEFACT_CATEGORY.FILESYSTEM_METADATA:
      return <FileSystemTable {...shared} />;
    case ARTEFACT_CATEGORY.REGISTRY_KEY:
      return <RegistryTable {...shared} />;
    case ARTEFACT_CATEGORY.BROWSER_HISTORY:
      return <BrowserHistoryTable {...shared} />;
    case ARTEFACT_CATEGORY.EVENT_LOG:
      return <EventLogTable {...shared} />;
    case ARTEFACT_CATEGORY.RUNNING_PROCESS:
      return <ProcessTable {...shared} />;
    case ARTEFACT_CATEGORY.NETWORK_CONNECTION:
      return <NetworkTable {...shared} />;
    case ARTEFACT_CATEGORY.INJECTED_CODE:
      return <InjectedCodeTable {...shared} />;
    default:
      return (
        <DataTable
          columns={getUnifiedColumns(handlers)}
          data={data}
          loading={loading}
          emptyMessage={emptyMessage}
        />
      );
  }
}

/**
 * Artefact explorer with tabbed categories, filters, search, and sort.
 */
export default function ArtefactExplorer() {
  const { id: evidenceIdParam } = useParams();
  const history = useHistory();
  const { error: notifyError } = useNotification();

  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [artefacts, setArtefacts] = useState([]);
  const [reportMeta, setReportMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeTab, setActiveTab] = useState("all");
  const [suspicionFilter, setSuspicionFilter] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("relevance_score");

  const [detailArtefact, setDetailArtefact] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const [correlationArtefact, setCorrelationArtefact] = useState(null);
  const [correlationOpen, setCorrelationOpen] = useState(false);

  const [explainArtefact, setExplainArtefact] = useState(null);
  const [explainOpen, setExplainOpen] = useState(false);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainResult, setExplainResult] = useState(null);
  const [explainError, setExplainError] = useState(null);

  const selectedEvidenceId = evidenceIdParam || "";

  const loadInventory = useCallback(async () => {
    const inventory = await evidenceService.getInventory();
    const items = Array.isArray(inventory)
      ? inventory
      : inventory?.items || inventory?.evidence || [];
    setEvidenceOptions(items);
    return items;
  }, []);

  const loadArtefactsForEvidence = useCallback(async (evidenceId) => {
    if (!evidenceId) {
      setArtefacts([]);
      setReportMeta(null);
      return;
    }
    const jobs = await pipelineService.listJobs();
    const job = findLatestReportJob(jobs, evidenceId);
    if (!job?.report_id) {
      setArtefacts([]);
      setReportMeta(null);
      return;
    }
    const json = await reportsService.getJson(job.report_id);
    const rows = Array.isArray(json?.artefacts) ? json.artefacts : [];
    setArtefacts(rows);
    setReportMeta({
      reportId: job.report_id,
      jobId: job.job_id || job.id,
      summaryStatistics: json?.summary_statistics || null,
    });
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadInventory();
      await loadArtefactsForEvidence(selectedEvidenceId);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [loadInventory, loadArtefactsForEvidence, selectedEvidenceId]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const tabCategory = useMemo(() => {
    const tab = TAB_ITEMS.find((item) => item.eventKey === activeTab);
    return tab?.category || null;
  }, [activeTab]);

  const filteredArtefacts = useMemo(() => {
    let rows = [...artefacts];

    if (tabCategory) {
      rows = rows.filter(
        (row) => String(row.category).toLowerCase() === tabCategory
      );
    }

    if (categoryFilter.length) {
      const allowed = new Set(categoryFilter.map((c) => String(c).toLowerCase()));
      rows = rows.filter((row) =>
        allowed.has(String(row.category).toLowerCase())
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

    const query = searchQuery.trim().toLowerCase();
    if (query) {
      rows = rows.filter((row) => {
        const haystack = [
          row.artefact_id,
          row.category,
          row.suspicion_level,
          row.source_path,
          row.classification_reasoning,
          rawDataSearchText(row.raw_data),
          rawDataSearchText(row.metadata),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      });
    }

    rows.sort((a, b) => {
      if (sortBy === "category") {
        const cmp = String(a.category || "").localeCompare(String(b.category || ""));
        if (cmp !== 0) return cmp;
        return (Number(b.relevance_score) || 0) - (Number(a.relevance_score) || 0);
      }
      if (sortBy === "timestamp") {
        return artefactTimestamp(b) - artefactTimestamp(a);
      }
      return (Number(b.relevance_score) || 0) - (Number(a.relevance_score) || 0);
    });

    return rows;
  }, [
    artefacts,
    tabCategory,
    categoryFilter,
    suspicionFilter,
    searchQuery,
    sortBy,
  ]);

  const summaryStats = useMemo(() => {
    const bySuspicion = {};
    Object.values(SUSPICION_LEVEL).forEach((level) => {
      bySuspicion[level] = 0;
    });
    const byCategory = {};
    Object.values(ARTEFACT_CATEGORY).forEach((cat) => {
      byCategory[cat] = 0;
    });

    filteredArtefacts.forEach((row) => {
      const suspicion = String(row.suspicion_level || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(bySuspicion, suspicion)) {
        bySuspicion[suspicion] += 1;
      }
      const category = String(row.category || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(byCategory, category)) {
        byCategory[category] += 1;
      }
    });

    return {
      total: filteredArtefacts.length,
      bySuspicion,
      byCategory,
    };
  }, [filteredArtefacts]);

  const handleEvidenceChange = (event) => {
    const nextId = event.target.value;
    if (nextId) {
      history.push(Routes.Artefacts.path.replace(":id", nextId));
    }
  };

  const openDetails = useCallback((artefact) => {
    setDetailArtefact(artefact);
    setDetailOpen(true);
  }, []);

  const openCorrelations = useCallback((artefact) => {
    setCorrelationArtefact(artefact);
    setCorrelationOpen(true);
  }, []);

  const openExplain = useCallback(async (artefact) => {
    setExplainArtefact(artefact);
    setExplainOpen(true);
    setExplainLoading(true);
    setExplainResult(null);
    setExplainError(null);
    try {
      const response = await aiService.explain(artefact.artefact_id);
      setExplainResult(response?.explanation || response);
    } catch (err) {
      setExplainError(err);
      notifyError(
        "AI Explain failed",
        err?.response?.data?.detail || err?.message || "Unable to explain artefact."
      );
    } finally {
      setExplainLoading(false);
    }
  }, [notifyError]);

  const selectArtefactById = useCallback(
    (artefactId) => {
      const found = artefactById.get(artefactId);
      if (found) {
        setDetailArtefact(found);
        setDetailOpen(true);
        setCorrelationOpen(false);
      }
    },
    [artefactById]
  );

  const tableHandlers = useMemo(
    () => ({
      onViewDetails: openDetails,
      onAiExplain: openExplain,
      onViewCorrelations: openCorrelations,
    }),
    [openDetails, openExplain, openCorrelations]
  );

  const correlatedRows = useMemo(() => {
    const ids = correlationArtefact?.metadata?.correlated_artefact_ids || [];
    return ids
      .map((id) => artefactById.get(id))
      .filter(Boolean);
  }, [correlationArtefact, artefactById]);

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
        title="Artefact Explorer"
        subtitle={
          selectedEvidenceId ? (
            <>
              Evidence{" "}
              <Link
                to={Routes.EvidenceDetail.path.replace(
                  ":id",
                  selectedEvidenceId
                )}
              >
                {shortId(selectedEvidenceId)}
              </Link>
              {reportMeta?.reportId ? (
                <>
                  {" · Report "}
                  <Link
                    to={Routes.ReportDetail.path.replace(
                      ":id",
                      reportMeta.reportId
                    )}
                  >
                    {shortId(reportMeta.reportId)}
                  </Link>
                </>
              ) : null}
            </>
          ) : (
            "Select evidence with a completed pipeline report to explore artefacts."
          )
        }
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Artefact Explorer" },
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
              const eid = item.id || item.evidence_id;
              return (
                <option key={eid} value={eid}>
                  {evidenceLabel(item)}
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
          message="Choose an evidence item from the dropdown to load parsed artefacts."
        />
      ) : !loading && !artefacts.length ? (
        <EmptyState
          title="No artefacts available"
          message="Run a completed pipeline job for this evidence to generate a report with artefacts."
          action={
            reportMeta?.jobId ? (
              <Button
                as={Link}
                to={Routes.PipelineDetail.path.replace(
                  ":jobId",
                  reportMeta.jobId
                )}
                variant="primary"
                size="sm"
              >
                View pipeline job
              </Button>
            ) : (
              <Button
                as={Link}
                to={Routes.PipelineRun.path}
                variant="primary"
                size="sm"
              >
                Run pipeline
              </Button>
            )
          }
        />
      ) : (
        <>
          {/* Summary bar */}
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3 align-items-center">
                <Col xs="auto">
                  <span className="text-muted small text-uppercase fw-bold">
                    Total
                  </span>
                  <div className="h4 mb-0">{summaryStats.total}</div>
                </Col>
                <Col xs={12} md={5}>
                  <span className="text-muted small text-uppercase fw-bold d-block mb-2">
                    By suspicion
                  </span>
                  <div className="d-flex flex-wrap gap-2">
                    {Object.values(SUSPICION_LEVEL).map((level) => {
                      const count = summaryStats.bySuspicion[level] || 0;
                      const { label, colour } = formatSuspicionLevel(level);
                      return (
                        <Badge
                          key={level}
                          style={{ backgroundColor: colour, color: "#fff" }}
                        >
                          {label}: {count}
                        </Badge>
                      );
                    })}
                  </div>
                </Col>
                <Col xs={12} md>
                  <span className="text-muted small text-uppercase fw-bold d-block mb-2">
                    By category
                  </span>
                  <div className="d-flex flex-wrap gap-1">
                    {CATEGORY_OPTIONS.map(({ value, label }) => {
                      const count = summaryStats.byCategory[value] || 0;
                      if (!count) return null;
                      return (
                        <Badge key={value} bg="light" text="dark" className="border">
                          {label}: {count}
                        </Badge>
                      );
                    })}
                  </div>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          {/* Filters */}
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3">
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
                      const selected = Array.from(
                        event.target.selectedOptions,
                        (opt) => opt.value
                      );
                      setCategoryFilter(selected);
                    }}
                  >
                    {CATEGORY_OPTIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Form.Select>
                  <Form.Text muted>Hold Ctrl/Cmd to select multiple.</Form.Text>
                </Col>
                <Col xs={12} md={6} lg={4}>
                  <Form.Label className="small text-muted text-uppercase fw-bold">
                    Search &amp; sort
                  </Form.Label>
                  <SearchInput
                    placeholder="Search raw_data fields…"
                    value={searchQuery}
                    onChange={setSearchQuery}
                    className="mb-2"
                  />
                  <Form.Select
                    value={sortBy}
                    onChange={(event) => setSortBy(event.target.value)}
                    aria-label="Sort artefacts"
                  >
                    {SORT_OPTIONS.map(({ value, label }) => (
                      <option key={value} value={value}>
                        Sort by {label}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          {/* Tabs + table */}
          <Tab.Container activeKey={activeTab} onSelect={setActiveTab}>
            <Card border="light" className="shadow-sm">
              <Card.Header className="border-bottom border-light p-0">
                <Nav variant="tabs" className="nav-tabs-sm px-3 pt-2">
                  {TAB_ITEMS.map((tab) => (
                    <Nav.Item key={tab.eventKey}>
                      <Nav.Link eventKey={tab.eventKey}>{tab.label}</Nav.Link>
                    </Nav.Item>
                  ))}
                </Nav>
              </Card.Header>
              <Card.Body className="p-0">
                <Tab.Content>
                  {TAB_ITEMS.map((tab) => (
                    <Tab.Pane key={tab.eventKey} eventKey={tab.eventKey}>
                      {renderCategoryTable(
                        tab.eventKey,
                        filteredArtefacts,
                        loading,
                        `No ${tab.label.toLowerCase()} artefacts match the current filters.`,
                        tableHandlers
                      )}
                    </Tab.Pane>
                  ))}
                </Tab.Content>
              </Card.Body>
            </Card>
          </Tab.Container>
        </>
      )}

      <ArtefactDetailModal
        show={detailOpen}
        onHide={() => setDetailOpen(false)}
        artefact={detailArtefact}
        evidenceId={selectedEvidenceId}
        onSelectArtefact={selectArtefactById}
      />

      <Modal
        show={correlationOpen}
        onHide={() => setCorrelationOpen(false)}
        centered
        size="lg"
      >
        <Modal.Header closeButton>
          <Modal.Title>
            <FontAwesomeIcon icon={faProjectDiagram} className="me-2" />
            Correlated artefacts
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {correlationArtefact ? (
            <>
              <p className="small text-muted mb-3">
                Correlations for artefact{" "}
                <code>{formatArtefactId(correlationArtefact.artefact_id)}</code>
              </p>
              {correlatedRows.length ? (
                <DataTable
                  columns={[
                    {
                      key: "artefact_id",
                      header: "ID",
                      render: (row) => formatArtefactId(row.artefact_id),
                    },
                    {
                      key: "category",
                      header: "Category",
                      render: (row) => humanise(row.category),
                    },
                    {
                      key: "suspicion_level",
                      header: "Suspicion",
                      render: (row) => (
                        <StatusBadge
                          status={row.suspicion_level}
                          type="suspicion"
                        />
                      ),
                    },
                    {
                      key: "summary",
                      header: "Summary",
                      render: (row) => buildSummary(row),
                    },
                    {
                      key: "link",
                      header: "",
                      render: (row) => (
                        <Button
                          size="sm"
                          variant="link"
                          onClick={() => selectArtefactById(row.artefact_id)}
                        >
                          <FontAwesomeIcon icon={faLink} className="me-1" />
                          Open
                        </Button>
                      ),
                    },
                  ]}
                  data={correlatedRows}
                  emptyMessage="No correlated artefacts found in this report."
                />
              ) : (
                <EmptyState
                  title="No correlations in report"
                  message="Related artefact IDs were listed in metadata but are not present in the loaded report."
                />
              )}
            </>
          ) : null}
        </Modal.Body>
      </Modal>

      <Modal
        show={explainOpen}
        onHide={() => setExplainOpen(false)}
        centered
        size="lg"
        scrollable
      >
        <Modal.Header closeButton>
          <Modal.Title>
            <FontAwesomeIcon icon={faBrain} className="me-2" />
            AI Explanation
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {explainArtefact ? (
            <p className="small text-muted">
              Artefact{" "}
              <code>{formatArtefactId(explainArtefact.artefact_id)}</code>
              {" · "}
              {humanise(explainArtefact.category)}
            </p>
          ) : null}
          {explainLoading ? (
            <div className="text-center py-4">
              <Spinner animation="border" role="status" />
              <p className="text-muted small mt-2 mb-0">
                Generating explanation…
              </p>
            </div>
          ) : explainError ? (
            <ApiErrorDisplay error={explainError} />
          ) : explainResult ? (
            <>
              <p>{explainResult.explanation_text || explainResult.text}</p>
              {explainResult.forensic_significance ? (
                <>
                  <h6 className="text-uppercase text-muted small fw-bold">
                    Forensic significance
                  </h6>
                  <p className="small">{explainResult.forensic_significance}</p>
                </>
              ) : null}
              {(explainResult.suggested_actions || []).length ? (
                <>
                  <h6 className="text-uppercase text-muted small fw-bold">
                    Suggested actions
                  </h6>
                  <ul className="small">
                    {explainResult.suggested_actions.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {(explainResult.related_artefact_ids || []).length ? (
                <>
                  <h6 className="text-uppercase text-muted small fw-bold">
                    Related artefacts
                  </h6>
                  <div className="d-flex flex-wrap gap-2">
                    {explainResult.related_artefact_ids.map((id) => (
                      <Button
                        key={id}
                        size="sm"
                        variant="outline-secondary"
                        onClick={() => selectArtefactById(id)}
                      >
                        {formatArtefactId(id)}
                      </Button>
                    ))}
                  </div>
                </>
              ) : null}
            </>
          ) : (
            <p className="text-muted mb-0">No explanation returned.</p>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setExplainOpen(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}

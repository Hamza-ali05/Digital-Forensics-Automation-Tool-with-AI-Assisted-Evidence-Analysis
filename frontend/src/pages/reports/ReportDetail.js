import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Nav,
  Row,
  Spinner,
  Tab,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faCode,
  faDownload,
  faFileAlt,
  faFilePdf,
  faShieldAlt,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import HashSetDisplay from "components/forensic/HashSetDisplay";
import JSONTreeViewer from "components/forensic/JSONTreeViewer";
import NarrativeSummary, {
  parseNarrativeMeta,
} from "components/forensic/NarrativeSummary";
import StatusTimeline from "components/forensic/StatusTimeline";
import {
  ARTEFACT_CATEGORY,
  PIPELINE_STAGE,
  SUSPICION_COLOURS,
  SUSPICION_LEVEL,
} from "utils/constants";
import {
  formatDate,
  formatDuration,
  formatHash,
  formatSuspicionLevel,
} from "utils/formatters";
import {
  extractArtefacts,
  listCompletedReports,
} from "utils/artefactLoader";
import useNotification from "hooks/useNotification";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import { Routes } from "routes";

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip);

const STAGE_ORDER = [
  PIPELINE_STAGE.ACQUISITION,
  PIPELINE_STAGE.PARSING,
  PIPELINE_STAGE.AI_TRIAGE,
  PIPELINE_STAGE.REPORTING,
  PIPELINE_STAGE.EVALUATION,
];

const STAGE_COLOURS = ["#0d6efd", "#198754", "#fd7e14", "#6f42c1", "#20c997"];

const CUSTODY_COLOURS = {
  acquired: "success",
  accessed: "info",
  transferred: "warning",
  analysed: "primary",
  analyzed: "primary",
  sealed: "dark",
  released: "secondary",
};

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function actionLabel(action) {
  return humanise(action);
}

function narrativeText(raw) {
  if (raw == null) return "";
  if (typeof raw === "string") return raw;
  return raw.summary_text || "";
}

function computeStats(artefacts, summaryStatistics) {
  const byCategory = {};
  Object.values(ARTEFACT_CATEGORY).forEach((key) => {
    byCategory[key] = summaryStatistics?.by_category?.[key] || 0;
  });
  const bySuspicion = {};
  Object.values(SUSPICION_LEVEL).forEach((key) => {
    bySuspicion[key] = summaryStatistics?.by_suspicion_level?.[key] || 0;
  });

  if (!summaryStatistics) {
    artefacts.forEach((row) => {
      const cat = String(row.category || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(byCategory, cat)) {
        byCategory[cat] += 1;
      }
      const level = String(row.suspicion_level || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(bySuspicion, level)) {
        bySuspicion[level] += 1;
      }
    });
  }

  return {
    total:
      summaryStatistics?.total_artefacts != null
        ? summaryStatistics.total_artefacts
        : artefacts.length,
    byCategory,
    bySuspicion,
  };
}

function stageDuration(stageExecutions, key) {
  const item = stageExecutions?.[key] || {};
  if (typeof item.duration_seconds === "number") return item.duration_seconds;
  return 0;
}

function VerifyFlag({ ok, label }) {
  return (
    <span className="d-inline-flex align-items-center me-3 mb-1">
      <FontAwesomeIcon
        icon={ok ? faCheckCircle : faTimesCircle}
        className={`me-1 ${ok ? "text-success" : "text-danger"}`}
      />
      <span className={ok ? "text-success" : "text-danger"}>{label}</span>
    </span>
  );
}

function MatchBadge({ ok, label }) {
  return (
    <Badge bg={ok ? "success" : "danger"} className="me-2 mb-1">
      {label}: {ok ? "Match" : "Differ"}
    </Badge>
  );
}

/**
 * Forensic report detail with overview, narrative, JSON, custody, audit, export.
 */
export default function ReportDetail() {
  const { id } = useParams();
  const { info, error: notifyError, success } = useNotification();

  const [activeTab, setActiveTab] = useState("overview");
  const [meta, setMeta] = useState(null);
  const [jsonDoc, setJsonDoc] = useState(null);
  const [narrative, setNarrative] = useState("");
  const [job, setJob] = useState(null);
  const [otherReports, setOtherReports] = useState([]);
  const [custody, setCustody] = useState(null);
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [custodyError, setCustodyError] = useState(null);
  const [auditError, setAuditError] = useState(null);

  const [exportBusy, setExportBusy] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);

  const [compareId, setCompareId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [compareResult, setCompareResult] = useState(null);
  const [compareError, setCompareError] = useState(null);

  const [detailArtefact, setDetailArtefact] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const loadReport = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    setCustodyError(null);
    setAuditError(null);
    setVerifyResult(null);
    setCompareResult(null);
    try {
      const [metaResult, jsonResult, narrativeResult, jobs, reports] =
        await Promise.all([
          reportsService.getById(id),
          reportsService.getJson(id),
          reportsService.getNarrative(id).catch(() => ""),
          pipelineService.listJobs().catch(() => []),
          listCompletedReports().catch(() => []),
        ]);
      setMeta(metaResult);
      setJsonDoc(jsonResult);
      setNarrative(narrativeText(narrativeResult));
      const match = (jobs || []).find(
        (item) => String(item.report_id) === String(id)
      );
      setJob(match || null);
      setOtherReports(
        (reports || []).filter((item) => String(item.reportId) !== String(id))
      );

      const [custodySettled, auditSettled] = await Promise.allSettled([
        reportsService.getCustodyReport(id),
        reportsService.getAuditTrail(id),
      ]);
      if (custodySettled.status === "fulfilled") {
        setCustody(custodySettled.value);
      } else {
        setCustody(null);
        setCustodyError(custodySettled.reason);
      }
      if (auditSettled.status === "fulfilled") {
        setAudit(auditSettled.value);
      } else {
        setAudit(null);
        setAuditError(auditSettled.reason);
      }
    } catch (err) {
      setError(err);
      setMeta(null);
      setJsonDoc(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadReport().catch(() => {});
  }, [loadReport]);

  const artefacts = useMemo(() => extractArtefacts(jsonDoc), [jsonDoc]);
  const stats = useMemo(
    () => computeStats(artefacts, jsonDoc?.summary_statistics),
    [artefacts, jsonDoc]
  );
  const aiMeta = useMemo(
    () => parseNarrativeMeta(narrative, jsonDoc),
    [narrative, jsonDoc]
  );

  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const stageExecutions = job?.stage_executions || {};
  const durationSeconds =
    typeof meta?.pipeline_duration_seconds === "number"
      ? meta.pipeline_duration_seconds
      : job?.total_duration_seconds || 0;

  const stageChart = useMemo(() => {
    const timings = job?.stage_timings || jsonDoc?.stage_timings || {};
    const labels = STAGE_ORDER.map(humanise);
    const data = STAGE_ORDER.map((key) => {
      if (typeof timings[key] === "number") return timings[key];
      const alias =
        key === PIPELINE_STAGE.AI_TRIAGE
          ? timings.triage_seconds
          : timings[`${key}_seconds`];
      if (typeof alias === "number") return alias;
      return stageDuration(stageExecutions, key);
    });
    return {
      labels,
      datasets: [
        {
          label: "Seconds",
          data,
          backgroundColor: STAGE_COLOURS,
        },
      ],
    };
  }, [job, jsonDoc, stageExecutions]);

  const custodyChain = useMemo(() => {
    const chain = custody?.chain || [];
    return [...chain].reverse();
  }, [custody]);

  const auditEntries = useMemo(() => {
    const entries = audit?.entries || [];
    return [...entries].slice().reverse();
  }, [audit]);

  const handleCopied = useCallback(() => {
    info("Copied", "JSON node copied to clipboard.");
  }, [info]);

  const openArtefact = (artefactId) => {
    const found = artefactById.get(artefactId);
    setDetailArtefact(found || { artefact_id: artefactId, raw_data: {}, metadata: {} });
    setDetailOpen(true);
  };

  const runExport = async (kind) => {
    setExportBusy(kind);
    try {
      if (kind === "pdf") await reportsService.exportPdf(id);
      else if (kind === "html") await reportsService.exportHtml(id);
      else await reportsService.exportJson(id);
      info("Download started", `${kind.toUpperCase()} export for ${shortId(id)}.`);
    } catch (err) {
      notifyError(
        "Export failed",
        err?.message || `Could not export ${kind.toUpperCase()}.`
      );
    } finally {
      setExportBusy(null);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const result = await reportsService.verify(id);
      setVerifyResult(result);
      if (result.is_valid) {
        success("Integrity verified", `Report ${shortId(id)} passed verification.`);
      }
    } catch (err) {
      setVerifyError(err);
      setVerifyResult(null);
    } finally {
      setVerifying(false);
    }
  };

  const handleCompare = async () => {
    if (!compareId) return;
    setComparing(true);
    setCompareError(null);
    try {
      const result = await reportsService.compare({
        report_id_a: id,
        report_id_b: compareId,
      });
      setCompareResult(result);
    } catch (err) {
      setCompareError(err);
      setCompareResult(null);
    } finally {
      setComparing(false);
    }
  };

  const schemaVersion =
    jsonDoc?.schema_version || jsonDoc?.reproducibility?.schema_version || "—";

  const exportButtons = (
    <div className="d-flex flex-wrap gap-2">
      <Button
        variant="outline-primary"
        disabled={Boolean(exportBusy)}
        onClick={() => runExport("pdf")}
      >
        {exportBusy === "pdf" ? (
          <Spinner animation="border" size="sm" className="me-2" />
        ) : (
          <FontAwesomeIcon icon={faFilePdf} className="me-2" />
        )}
        Export PDF
      </Button>
      <Button
        variant="outline-secondary"
        disabled={Boolean(exportBusy)}
        onClick={() => runExport("html")}
      >
        {exportBusy === "html" ? (
          <Spinner animation="border" size="sm" className="me-2" />
        ) : (
          <FontAwesomeIcon icon={faFileAlt} className="me-2" />
        )}
        Export HTML
      </Button>
      <Button
        variant="outline-secondary"
        disabled={Boolean(exportBusy)}
        onClick={() => runExport("json")}
      >
        {exportBusy === "json" ? (
          <Spinner animation="border" size="sm" className="me-2" />
        ) : (
          <FontAwesomeIcon icon={faCode} className="me-2" />
        )}
        Download JSON
      </Button>
    </div>
  );

  if (loading) {
    return (
      <Container fluid className="px-0">
        <PageHeader
          title="Report Detail"
          breadcrumbs={[
            { label: "Home", to: Routes.Dashboard.path },
            { label: "Reports", to: Routes.Reports.path },
            { label: "Detail" },
          ]}
        />
        <SkeletonLoader type="detail" rows={8} />
      </Container>
    );
  }

  if (error || !meta) {
    return (
      <Container fluid className="px-0">
        <PageHeader
          title="Report Detail"
          breadcrumbs={[
            { label: "Home", to: Routes.Dashboard.path },
            { label: "Reports", to: Routes.Reports.path },
            { label: "Detail" },
          ]}
        />
        {error ? (
          <ApiErrorDisplay error={error} onRetry={loadReport} />
        ) : (
          <EmptyState
            title="Report not found"
            description="This report could not be loaded."
          />
        )}
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title={`Report ${shortId(id)}`}
        subtitle={meta.case_name || "Forensic dual-output report"}
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Reports", to: Routes.Reports.path },
          { label: shortId(id) },
        ]}
        actions={exportButtons}
      />

      <Tab.Container
        activeKey={activeTab}
        onSelect={(key) => key && setActiveTab(key)}
      >
        <Card border="light" className="shadow-sm">
          <Card.Header className="border-bottom border-light bg-white">
            <Nav variant="tabs" className="flex-nowrap">
              <Nav.Item>
                <Nav.Link eventKey="overview">Overview</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="narrative">Narrative Summary</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="json">JSON Data</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="custody">Chain of Custody</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="audit">Audit Trail</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="export">Export</Nav.Link>
              </Nav.Item>
            </Nav>
          </Card.Header>
          <Card.Body>
            <Tab.Content>
              <Tab.Pane eventKey="overview">
                <Row className="mb-4">
                  <Col xs={12} lg={4} className="mb-4 mb-lg-0">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h6 className="mb-0">Case information</h6>
                      </Card.Header>
                      <Card.Body>
                        <dl className="row mb-0 small">
                          <dt className="col-5 text-muted">Case</dt>
                          <dd className="col-7">
                            {job?.case_id ? (
                              <Link
                                to={Routes.CaseDetail.path.replace(
                                  ":id",
                                  job.case_id
                                )}
                              >
                                {meta.case_name}
                              </Link>
                            ) : (
                              meta.case_name || "—"
                            )}
                          </dd>
                          <dt className="col-5 text-muted">Report ID</dt>
                          <dd className="col-7">
                            <code>{id}</code>
                          </dd>
                          <dt className="col-5 text-muted">Evidence</dt>
                          <dd className="col-7">
                            {job?.evidence_id || jsonDoc?.evidence_id ? (
                              <Link
                                to={Routes.EvidenceDetail.path.replace(
                                  ":id",
                                  job?.evidence_id || jsonDoc.evidence_id
                                )}
                              >
                                {shortId(job?.evidence_id || jsonDoc.evidence_id)}
                              </Link>
                            ) : (
                              "—"
                            )}
                          </dd>
                          <dt className="col-5 text-muted">Generated</dt>
                          <dd className="col-7">{formatDate(meta.generated_at)}</dd>
                          <dt className="col-5 text-muted">Pipeline duration</dt>
                          <dd className="col-7">{formatDuration(durationSeconds)}</dd>
                          {job?.job_id ? (
                            <>
                              <dt className="col-5 text-muted">Pipeline job</dt>
                              <dd className="col-7">
                                <Link
                                  to={Routes.PipelineDetail.path.replace(
                                    ":jobId",
                                    job.job_id
                                  )}
                                >
                                  {shortId(job.job_id)}
                                </Link>
                              </dd>
                            </>
                          ) : null}
                        </dl>
                      </Card.Body>
                    </Card>
                  </Col>
                  <Col xs={12} lg={8}>
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h6 className="mb-0">Stage timings</h6>
                      </Card.Header>
                      <Card.Body>
                        <div style={{ minHeight: 220 }}>
                          <Bar
                            data={stageChart}
                            options={{
                              responsive: true,
                              maintainAspectRatio: true,
                              plugins: { legend: { display: false } },
                              scales: {
                                y: {
                                  beginAtZero: true,
                                  ticks: { precision: 0 },
                                },
                              },
                            }}
                          />
                        </div>
                      </Card.Body>
                    </Card>
                  </Col>
                </Row>

                <Row>
                  <Col xs={12} lg={7} className="mb-4 mb-lg-0">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h6 className="mb-0">Artefact summary</h6>
                      </Card.Header>
                      <Card.Body>
                        <div className="h4 mb-3">{stats.total} artefacts</div>
                        <div className="text-muted small text-uppercase fw-bold mb-2">
                          By suspicion
                        </div>
                        <div className="d-flex flex-wrap gap-2 mb-3">
                          {Object.values(SUSPICION_LEVEL).map((level) => {
                            const count = stats.bySuspicion[level] || 0;
                            const { label, colour } = formatSuspicionLevel(level);
                            return (
                              <Badge
                                key={level}
                                style={{
                                  backgroundColor:
                                    colour || SUSPICION_COLOURS[level],
                                  color: "#fff",
                                }}
                              >
                                {label}: {count}
                              </Badge>
                            );
                          })}
                        </div>
                        <div className="text-muted small text-uppercase fw-bold mb-2">
                          By category
                        </div>
                        <div className="d-flex flex-wrap gap-1">
                          {Object.entries(stats.byCategory)
                            .filter(([, count]) => count > 0)
                            .map(([key, count]) => (
                              <Badge
                                key={key}
                                bg="light"
                                text="dark"
                                className="border"
                              >
                                {humanise(key)}: {count}
                              </Badge>
                            ))}
                          {!Object.values(stats.byCategory).some((n) => n > 0) ? (
                            <span className="text-muted small">No category counts</span>
                          ) : null}
                        </div>
                      </Card.Body>
                    </Card>
                  </Col>
                  <Col xs={12} lg={5}>
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h6 className="mb-0">AI metadata</h6>
                      </Card.Header>
                      <Card.Body>
                        <dl className="row mb-0 small">
                          <dt className="col-5 text-muted">Model</dt>
                          <dd className="col-7">{aiMeta.model}</dd>
                          <dt className="col-5 text-muted">Prompt version</dt>
                          <dd className="col-7">
                            <Badge bg="light" text="dark">
                              {aiMeta.promptVersion}
                            </Badge>
                          </dd>
                          <dt className="col-5 text-muted">Confidence</dt>
                          <dd className="col-7">
                            {aiMeta.confidence != null
                              ? `${Math.round(aiMeta.confidence * 100)}%`
                              : "—"}
                          </dd>
                          <dt className="col-5 text-muted">Schema</dt>
                          <dd className="col-7">
                            <Badge bg="secondary">{schemaVersion}</Badge>
                          </dd>
                          {job?.use_fallback_analyzer ? (
                            <>
                              <dt className="col-5 text-muted">Mode</dt>
                              <dd className="col-7">
                                <Badge bg="warning" text="dark">
                                  Rule-based fallback
                                </Badge>
                              </dd>
                            </>
                          ) : null}
                        </dl>
                      </Card.Body>
                    </Card>
                  </Col>
                </Row>
              </Tab.Pane>

              <Tab.Pane eventKey="narrative">
                <NarrativeSummary
                  narrative={narrative}
                  jsonDoc={jsonDoc}
                  onArtefactClick={openArtefact}
                  reportId={id}
                />
              </Tab.Pane>

              <Tab.Pane eventKey="json">
                {jsonDoc ? (
                  <JSONTreeViewer
                    data={jsonDoc}
                    searchable
                    maxDepth={2}
                    onCopied={handleCopied}
                  />
                ) : (
                  <EmptyState
                    title="JSON report unavailable"
                    description="The structured artefact layer could not be loaded."
                  />
                )}
              </Tab.Pane>

              <Tab.Pane eventKey="custody">
                {custodyError ? (
                  <ApiErrorDisplay error={custodyError} className="mb-3" />
                ) : null}
                {!custody && !custodyError ? (
                  <EmptyState
                    title="No custody report"
                    description="A chain-of-custody report is not available for this evidence."
                  />
                ) : custody ? (
                  <>
                    <Row className="mb-4">
                      <Col xs={12} md={6} className="mb-3 mb-md-0">
                        <dl className="row mb-0 small">
                          <dt className="col-4 text-muted">Case</dt>
                          <dd className="col-8">{custody.case_name || "—"}</dd>
                          <dt className="col-4 text-muted">Evidence ID</dt>
                          <dd className="col-8">
                            {custody.evidence_id ? (
                              <Link
                                to={Routes.EvidenceDetail.path.replace(
                                  ":id",
                                  custody.evidence_id
                                )}
                              >
                                {shortId(custody.evidence_id)}
                              </Link>
                            ) : (
                              "—"
                            )}
                          </dd>
                          <dt className="col-4 text-muted">Chain length</dt>
                          <dd className="col-8">{custody.chain_length ?? custodyChain.length}</dd>
                          <dt className="col-4 text-muted">Integrity</dt>
                          <dd className="col-8">
                            <Badge
                              bg={custody.integrity_verified ? "success" : "danger"}
                            >
                              {custody.integrity_verified ? "Verified" : "Unverified"}
                            </Badge>
                          </dd>
                          <dt className="col-4 text-muted">First acquired</dt>
                          <dd className="col-8">{formatDate(custody.first_acquired)}</dd>
                          <dt className="col-4 text-muted">Last action</dt>
                          <dd className="col-8">{formatDate(custody.last_action)}</dd>
                        </dl>
                      </Col>
                      <Col xs={12} md={6}>
                        <HashSetDisplay
                          hashSet={custody.hash_set || {}}
                          integrityVerified={custody.integrity_verified}
                        />
                      </Col>
                    </Row>
                    <StatusTimeline
                      entries={custodyChain}
                      emptyTitle="No custody records"
                      emptyDescription="Custody actions are recorded when evidence is acquired or accessed."
                      renderEntry={(entry, _index, isCurrent) => {
                        const action = String(entry.action || "").toLowerCase();
                        return (
                          <div>
                            <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                              <Badge bg={CUSTODY_COLOURS[action] || "secondary"}>
                                {actionLabel(entry.action)}
                              </Badge>
                              {entry.entry_number != null ? (
                                <span className="small text-muted">
                                  #{entry.entry_number}
                                </span>
                              ) : null}
                              {isCurrent ? <Badge bg="primary">Latest</Badge> : null}
                            </div>
                            <div className="small text-muted">
                              {formatDate(entry.timestamp)} ·{" "}
                              {entry.performed_by_name ||
                                entry.performed_by_user_id ||
                                "system"}
                            </div>
                            {entry.reason ? (
                              <div className="small mt-1">{entry.reason}</div>
                            ) : null}
                            {entry.hash_at_action ? (
                              <div className="small mt-1">
                                Hash:{" "}
                                <code>{formatHash(entry.hash_at_action, 12)}</code>
                              </div>
                            ) : null}
                          </div>
                        );
                      }}
                    />
                  </>
                ) : null}
              </Tab.Pane>

              <Tab.Pane eventKey="audit">
                {auditError ? (
                  <ApiErrorDisplay error={auditError} className="mb-3" />
                ) : null}
                {!audit && !auditError ? (
                  <EmptyState
                    title="No audit trail"
                    description="No audit entries were recorded for this evidence."
                  />
                ) : audit ? (
                  <>
                    <Row className="mb-4">
                      <Col xs={12} md={6}>
                        <dl className="row mb-0 small">
                          <dt className="col-5 text-muted">Total entries</dt>
                          <dd className="col-7">{audit.total_entries ?? 0}</dd>
                          <dt className="col-5 text-muted">Earliest</dt>
                          <dd className="col-7">{formatDate(audit.earliest_action)}</dd>
                          <dt className="col-5 text-muted">Latest</dt>
                          <dd className="col-7">{formatDate(audit.latest_action)}</dd>
                          <dt className="col-5 text-muted">Users involved</dt>
                          <dd className="col-7">
                            {(audit.users_involved || []).length
                              ? (audit.users_involved || []).join(", ")
                              : "—"}
                          </dd>
                        </dl>
                      </Col>
                      <Col xs={12} md={6}>
                        <div className="text-muted small text-uppercase fw-bold mb-2">
                          Entries by stage
                        </div>
                        <div className="d-flex flex-wrap gap-1">
                          {Object.entries(audit.entries_by_stage || {}).map(
                            ([stage, count]) => (
                              <Badge
                                key={stage}
                                bg="light"
                                text="dark"
                                className="border"
                              >
                                {humanise(stage)}: {count}
                              </Badge>
                            )
                          )}
                        </div>
                        {(audit.integrity_events || []).length ? (
                          <div className="mt-3 small">
                            Integrity events: {audit.integrity_events.length}
                          </div>
                        ) : null}
                      </Col>
                    </Row>
                    <StatusTimeline
                      entries={auditEntries}
                      emptyTitle="No audit entries"
                      emptyDescription="Pipeline audit events will appear here."
                      renderEntry={(entry) => (
                        <div>
                          <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                            <Badge bg="secondary">{humanise(entry.stage)}</Badge>
                            <span className="fw-semibold small">{entry.action}</span>
                            {entry.entry_number != null ? (
                              <span className="small text-muted">
                                #{entry.entry_number}
                              </span>
                            ) : null}
                          </div>
                          <div className="small text-muted">
                            {formatDate(entry.timestamp)}
                          </div>
                          {entry.hash_before || entry.hash_after ? (
                            <div className="small mt-1">
                              {entry.hash_before ? (
                                <span className="me-2">
                                  Before:{" "}
                                  <code>{formatHash(entry.hash_before, 10)}</code>
                                </span>
                              ) : null}
                              {entry.hash_after ? (
                                <span>
                                  After:{" "}
                                  <code>{formatHash(entry.hash_after, 10)}</code>
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          {entry.details && Object.keys(entry.details).length ? (
                            <div className="small text-muted mt-1">
                              {Object.entries(entry.details)
                                .slice(0, 4)
                                .map(([key, value]) => `${key}=${value}`)
                                .join(" · ")}
                            </div>
                          ) : null}
                        </div>
                      )}
                    />
                  </>
                ) : null}
              </Tab.Pane>

              <Tab.Pane eventKey="export">
                <Row>
                  <Col xs={12} lg={6} className="mb-4">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h6 className="mb-0">Export formats</h6>
                      </Card.Header>
                      <Card.Body>
                        <p className="small text-muted">
                          Downloads use the verified export endpoints (PDF, HTML,
                          and JSON file).
                        </p>
                        {exportButtons}
                      </Card.Body>
                    </Card>
                  </Col>
                  <Col xs={12} lg={6} className="mb-4">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
                        <h6 className="mb-0">Integrity verification</h6>
                        <Button
                          size="sm"
                          variant="outline-success"
                          onClick={handleVerify}
                          disabled={verifying}
                        >
                          {verifying ? (
                            <Spinner animation="border" size="sm" className="me-1" />
                          ) : (
                            <FontAwesomeIcon icon={faShieldAlt} className="me-1" />
                          )}
                          Verify Integrity
                        </Button>
                      </Card.Header>
                      <Card.Body>
                        {verifyError ? (
                          <ApiErrorDisplay error={verifyError} className="mb-3" />
                        ) : null}
                        {verifyResult ? (
                          <>
                            <div className="mb-2">
                              <VerifyFlag
                                ok={Boolean(verifyResult.integrity_hash_match)}
                                label={
                                  verifyResult.integrity_hash_match
                                    ? "Integrity hash match"
                                    : "Integrity hash mismatch"
                                }
                              />
                              <VerifyFlag
                                ok={Boolean(verifyResult.schema_version_valid)}
                                label={
                                  verifyResult.schema_version_valid
                                    ? `Schema version valid (${schemaVersion})`
                                    : "Schema version invalid"
                                }
                              />
                              <VerifyFlag
                                ok={Boolean(verifyResult.is_valid)}
                                label={
                                  verifyResult.is_valid
                                    ? "Validation passed"
                                    : "Validation failed"
                                }
                              />
                            </div>
                            {(verifyResult.issues || []).length ? (
                              <Alert variant="warning" className="mb-0 py-2">
                                {(verifyResult.issues || []).map((issue) => (
                                  <div key={issue}>{issue}</div>
                                ))}
                              </Alert>
                            ) : (
                              <p className="small text-muted mb-0">
                                Verified{" "}
                                {verifyResult.verified_at
                                  ? formatDate(verifyResult.verified_at)
                                  : ""}
                              </p>
                            )}
                          </>
                        ) : (
                          <p className="text-muted small mb-0">
                            Run verification to compare the stored integrity hash
                            against the artefact payload.
                          </p>
                        )}
                      </Card.Body>
                    </Card>
                  </Col>
                </Row>

                <Card border="light" className="shadow-sm">
                  <Card.Header className="border-bottom border-light">
                    <h6 className="mb-0">Reproducibility comparison</h6>
                  </Card.Header>
                  <Card.Body>
                    <p className="small text-muted">
                      Compare artefact-layer hashes of this report against another
                      completed pipeline run.
                    </p>
                    <Row className="g-3 align-items-end mb-3">
                      <Col xs={12} md={8}>
                        <Form.Group className="mb-0">
                          <Form.Label className="small text-muted mb-1">
                            Compare with
                          </Form.Label>
                          <Form.Select
                            value={compareId}
                            onChange={(event) => {
                              setCompareId(event.target.value);
                              setCompareResult(null);
                            }}
                            aria-label="Select report to compare"
                          >
                            <option value="">Select another report…</option>
                            {otherReports.map((item) => (
                              <option key={item.reportId} value={item.reportId}>
                                {shortId(item.reportId)} · evidence{" "}
                                {shortId(item.evidenceId)}
                                {item.completedAt
                                  ? ` · ${formatDate(item.completedAt)}`
                                  : ""}
                              </option>
                            ))}
                          </Form.Select>
                        </Form.Group>
                      </Col>
                      <Col xs={12} md={4}>
                        <Button
                          variant="primary"
                          disabled={!compareId || comparing}
                          onClick={handleCompare}
                        >
                          {comparing ? (
                            <Spinner animation="border" size="sm" className="me-2" />
                          ) : (
                            <FontAwesomeIcon icon={faDownload} className="me-2" />
                          )}
                          Compare hashes
                        </Button>
                      </Col>
                    </Row>

                    {compareError ? (
                      <ApiErrorDisplay error={compareError} className="mb-3" />
                    ) : null}

                    {compareResult ? (
                      <>
                        <Alert
                          variant={
                            compareResult.is_reproducible ? "success" : "warning"
                          }
                        >
                          {compareResult.is_reproducible
                            ? "Artefact layers are reproducible (hashes match)."
                            : "Artefact layers differ between the two reports."}
                        </Alert>
                        <Table responsive size="sm" className="mb-3">
                          <thead>
                            <tr>
                              <th>Field</th>
                              <th>This report</th>
                              <th>Compared report</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td>Integrity hash</td>
                              <td>
                                <code>{formatHash(compareResult.hash_a, 16)}</code>
                              </td>
                              <td>
                                <code>{formatHash(compareResult.hash_b, 16)}</code>
                              </td>
                            </tr>
                          </tbody>
                        </Table>
                        <div className="mb-3">
                          <MatchBadge
                            ok={Boolean(compareResult.hashes_match)}
                            label="Hashes"
                          />
                          <MatchBadge
                            ok={Boolean(compareResult.artefact_count_match)}
                            label="Artefact count"
                          />
                          <MatchBadge
                            ok={Boolean(compareResult.category_distribution_match)}
                            label="Category distribution"
                          />
                          <MatchBadge
                            ok={Boolean(
                              compareResult.suspicion_distribution_match
                            )}
                            label="Suspicion distribution"
                          />
                        </div>
                        {(compareResult.differences || []).length ? (
                          <>
                            <div className="text-muted small text-uppercase fw-bold mb-2">
                              Artefact diff
                            </div>
                            <ul className="small mb-0">
                              {compareResult.differences.map((diff) => (
                                <li key={diff}>{diff}</li>
                              ))}
                            </ul>
                          </>
                        ) : (
                          <p className="small text-muted mb-0">
                            No artefact differences recorded.
                          </p>
                        )}
                      </>
                    ) : null}
                  </Card.Body>
                </Card>
              </Tab.Pane>
            </Tab.Content>
          </Card.Body>
        </Card>
      </Tab.Container>

      <ArtefactDetailModal
        show={detailOpen}
        artefact={detailArtefact}
        onHide={() => setDetailOpen(false)}
      />
    </Container>
  );
}

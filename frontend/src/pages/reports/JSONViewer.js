import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faDownload,
  faShieldAlt,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import JSONTreeViewer from "components/forensic/JSONTreeViewer";
import {
  ARTEFACT_CATEGORY,
  SUSPICION_COLOURS,
  SUSPICION_LEVEL,
} from "utils/constants";
import { formatDate, formatSuspicionLevel } from "utils/formatters";
import {
  extractArtefacts,
  listCompletedReports,
} from "utils/artefactLoader";
import reportsService from "services/reports.service";
import useNotification from "hooks/useNotification";
import { Routes } from "routes";

function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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

function VerifyFlag({ ok, label }) {
  return (
    <span className="d-inline-flex align-items-center me-3">
      <FontAwesomeIcon
        icon={ok ? faCheckCircle : faTimesCircle}
        className={`me-1 ${ok ? "text-success" : "text-danger"}`}
      />
      <span className={ok ? "text-success" : "text-danger"}>{label}</span>
    </span>
  );
}

/**
 * Structured JSON artefact report viewer with integrity verification.
 */
export default function JSONViewer() {
  const history = useHistory();
  const location = useLocation();
  const { info } = useNotification();
  const handleCopied = useCallback(() => {
    info("Copied", "JSON node copied to clipboard.");
  }, [info]);
  const query = useMemo(
    () => new URLSearchParams(location.search || ""),
    [location.search]
  );

  const [reports, setReports] = useState([]);
  const [reportId, setReportId] = useState(query.get("report_id") || "");
  const [document, setDocument] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listCompletedReports();
        if (!cancelled) setReports(list);
      } catch {
        if (!cancelled) setReports([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadJson = useCallback(async (id) => {
    if (!id) {
      setDocument(null);
      setVerifyResult(null);
      return;
    }
    setLoading(true);
    setError(null);
    setVerifyResult(null);
    try {
      const json = await reportsService.getJson(id);
      setDocument(json);
    } catch (err) {
      setError(err);
      setDocument(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadJson(reportId).catch(() => {});
  }, [reportId, loadJson]);

  const artefacts = useMemo(() => extractArtefacts(document), [document]);
  const stats = useMemo(
    () => computeStats(artefacts, document?.summary_statistics),
    [artefacts, document]
  );

  const handleSelect = (event) => {
    const next = event.target.value;
    setReportId(next);
    history.replace(
      next
        ? `${Routes.JSONViewer.path}?report_id=${next}`
        : Routes.JSONViewer.path
    );
  };

  const handleVerify = async () => {
    if (!reportId) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const result = await reportsService.verify(reportId);
      setVerifyResult(result);
    } catch (err) {
      setVerifyError(err);
      setVerifyResult(null);
    } finally {
      setVerifying(false);
    }
  };

  const schemaVersion =
    document?.schema_version || document?.reproducibility?.schema_version || "—";

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="JSON Artefact Data"
        subtitle="Structured evidential JSON layer with integrity verification"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Reports", to: Routes.Reports.path },
          { label: "JSON Artefact Data" },
        ]}
        actions={
          <Form.Select
            value={reportId}
            onChange={handleSelect}
            aria-label="Report selector"
            style={{ minWidth: 260 }}
          >
            <option value="">Select report…</option>
            {reports.map((item) => (
              <option key={item.reportId} value={item.reportId}>
                {shortId(item.reportId)} · evidence {shortId(item.evidenceId)}
                {item.completedAt ? ` · ${formatDate(item.completedAt)}` : ""}
              </option>
            ))}
          </Form.Select>
        }
      />

      {error ? (
        <ApiErrorDisplay
          error={error}
          onRetry={() => loadJson(reportId)}
          className="mb-3"
        />
      ) : null}

      {!reportId ? (
        <EmptyState
          title="No report selected"
          description="Choose a completed pipeline report to inspect its structured JSON artefact layer."
        />
      ) : loading ? (
        <SkeletonLoader type="detail" rows={6} />
      ) : !document ? (
        <EmptyState
          title="JSON report unavailable"
          description="The selected report could not be loaded."
        />
      ) : (
        <>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3 align-items-center">
                <Col xs="auto">
                  <span className="text-muted small text-uppercase fw-bold">
                    Total artefacts
                  </span>
                  <div className="h4 mb-0">{stats.total}</div>
                </Col>
                <Col xs={12} md={5}>
                  <span className="text-muted small text-uppercase fw-bold d-block mb-2">
                    By suspicion
                  </span>
                  <div className="d-flex flex-wrap gap-2">
                    {Object.values(SUSPICION_LEVEL).map((level) => {
                      const count = stats.bySuspicion[level] || 0;
                      const { label, colour } = formatSuspicionLevel(level);
                      return (
                        <Badge
                          key={level}
                          style={{ backgroundColor: colour || SUSPICION_COLOURS[level], color: "#fff" }}
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
                    {Object.entries(stats.byCategory)
                      .filter(([, count]) => count > 0)
                      .map(([key, count]) => (
                        <Badge key={key} bg="light" text="dark" className="border">
                          {String(key).replace(/_/g, " ")}: {count}
                        </Badge>
                      ))}
                  </div>
                </Col>
                <Col xs="auto">
                  <span className="text-muted small text-uppercase fw-bold d-block">
                    Schema
                  </span>
                  <Badge bg="secondary">{schemaVersion}</Badge>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm mb-4">
            <Card.Header className="border-bottom border-light d-flex flex-wrap justify-content-between align-items-center gap-2">
              <h5 className="mb-0">Integrity</h5>
              <div className="d-flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline-primary"
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
                <Button
                  size="sm"
                  variant="outline-secondary"
                  onClick={() =>
                    downloadJson(`report-${shortId(reportId)}.json`, document)
                  }
                >
                  <FontAwesomeIcon icon={faDownload} className="me-1" />
                  Download JSON
                </Button>
                {reportId ? (
                  <Button
                    as={Link}
                    to={`${Routes.AISummary.path}?report_id=${reportId}`}
                    size="sm"
                    variant="outline-secondary"
                  >
                    View summary
                  </Button>
                ) : null}
              </div>
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
                  Run verification to compare the stored integrity hash against
                  the artefact payload.
                </p>
              )}
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm mb-4">
            <Card.Header className="border-bottom border-light">
              <h5 className="mb-0">JSON tree</h5>
            </Card.Header>
            <Card.Body>
              <JSONTreeViewer
                data={document}
                searchable
                maxDepth={2}
                onCopied={handleCopied}
              />
            </Card.Body>
          </Card>
        </>
      )}
    </Container>
  );
}

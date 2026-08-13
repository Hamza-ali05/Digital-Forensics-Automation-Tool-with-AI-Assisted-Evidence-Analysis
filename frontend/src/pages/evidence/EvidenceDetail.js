import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  ListGroup,
  Nav,
  Row,
  Spinner,
  Tab,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faExclamationTriangle,
  faPlay,
  faShieldAlt,
  faTimesCircle,
  faBan,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ConfirmDialog from "components/common/ConfirmDialog";
import HashSetDisplay from "components/forensic/HashSetDisplay";
import StatusTimeline from "components/forensic/StatusTimeline";
import { EVIDENCE_STATUS, EVIDENCE_TYPE } from "utils/constants";
import {
  formatBytes,
  formatCaseId,
  formatDate,
  formatHash,
} from "utils/formatters";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import { Routes } from "routes";

const CUSTODY_COLOURS = {
  acquired: "success",
  accessed: "info",
  transferred: "warning",
  analysed: "primary",
  analyzed: "primary",
  sealed: "dark",
  released: "secondary",
};

function basename(path) {
  if (!path) return "—";
  const parts = String(path).replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

function typeLabel(type) {
  if (type === EVIDENCE_TYPE.DISK_IMAGE) return "Disk Image";
  if (type === EVIDENCE_TYPE.MEMORY_DUMP) return "Memory Dump";
  return String(type || "—")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function actionLabel(action) {
  return String(action || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Evidence detail — metadata, hashes, status, custody, analysis links.
 */
export default function EvidenceDetail() {
  const { id: evidenceId } = useParams();
  const history = useHistory();
  const { canUpdate, canRead } = usePermission("evidence");
  const analysisPerm = usePermission("analysis");
  const { success, error: notifyError, warning, info } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const [detail, setDetail] = useState(null);
  const [statusPayload, setStatusPayload] = useState(null);
  const [custody, setCustody] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [integrity, setIntegrity] = useState(null);
  const [validation, setValidation] = useState(null);
  const [chainVerify, setChainVerify] = useState(null);

  const load = useCallback(async () => {
    if (!evidenceId) return;
    setLoading(true);
    setError(null);
    try {
      const [detailResult, statusResult, custodyResult, jobsResult] =
        await Promise.all([
          evidenceService.getDetail(evidenceId),
          evidenceService.getStatus(evidenceId).catch(() => null),
          evidenceService.getCustody(evidenceId).catch(() => null),
          pipelineService.listJobs().catch(() => []),
        ]);
      setDetail(detailResult);
      setStatusPayload(statusResult);
      setCustody(custodyResult);
      const related = (Array.isArray(jobsResult) ? jobsResult : []).filter(
        (job) => job.evidence_id === evidenceId
      );
      related.sort((a, b) => {
        const ta = new Date(a.completed_at || a.created_at || 0).getTime();
        const tb = new Date(b.completed_at || b.created_at || 0).getTime();
        return tb - ta;
      });
      setJobs(related);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [evidenceId]);

  useEffect(() => {
    load();
  }, [load]);

  const metadata = detail?.metadata || {};
  const hashSet = metadata.hash_set || {};
  const status =
    detail?.status ||
    statusPayload?.current_status ||
    EVIDENCE_STATUS.REGISTERED;

  const lastVerifiedAt = useMemo(() => {
    if (integrity?.timestamp) return integrity.timestamp;
    const entries = custody?.entries || detail?.custody_chain || [];
    const accessed = [...entries]
      .reverse()
      .find((e) => String(e.action || "").toLowerCase() === "accessed");
    return accessed?.timestamp || hashSet.computed_at || null;
  }, [integrity, custody, detail, hashSet]);

  const statusHistory = useMemo(() => {
    const fromStatus = statusPayload?.history || [];
    const fromDetail = detail?.status_history || [];
    const rows = fromStatus.length ? fromStatus : fromDetail;
    return [...rows].sort(
      (a, b) =>
        new Date(b.changed_at || 0).getTime() -
        new Date(a.changed_at || 0).getTime()
    );
  }, [statusPayload, detail]);

  const custodyEntries = useMemo(() => {
    const fromCustody = custody?.entries || [];
    const fromDetail = detail?.custody_chain || [];
    const rows = fromCustody.length ? fromCustody : fromDetail;
    return [...rows].sort((a, b) => {
      const na = Number(a.entry_number) || 0;
      const nb = Number(b.entry_number) || 0;
      if (na && nb) return na - nb;
      return (
        new Date(a.timestamp || 0).getTime() -
        new Date(b.timestamp || 0).getTime()
      );
    });
  }, [custody, detail]);

  // Timeline shows newest first for status; custody chronological ascending then reverse for display newest first
  const custodyTimeline = useMemo(
    () => [...custodyEntries].reverse(),
    [custodyEntries]
  );

  const latestJob = jobs[0] || null;
  const artefactCount = jobs.reduce(
    (max, job) => Math.max(max, Number(job.artefact_count) || 0),
    0
  );

  const handleVerifyIntegrity = async () => {
    setBusy(true);
    try {
      const result = await evidenceService.verifyIntegrity(evidenceId);
      setIntegrity(result);
      if (result?.integrity_verified) {
        success("Integrity verified", "File hashes match the registered set.");
      } else {
        warning(
          "Integrity mismatch",
          "Current hashes differ from the registered digest."
        );
      }
      await load();
    } catch (err) {
      notifyError("Verify failed", err?.message || "Could not verify integrity.");
    } finally {
      setBusy(false);
    }
  };

  const handleRevalidate = async () => {
    setBusy(true);
    try {
      const result = await evidenceService.validate(evidenceId);
      setValidation(result);
      if (result?.validation_passed) {
        success("Validation passed", "Evidence format and metadata are valid.");
      } else {
        warning(
          "Validation failed",
          (result?.validation_failures || []).join("; ") ||
            "Evidence did not pass validation."
        );
      }
      await load();
    } catch (err) {
      notifyError("Validate failed", err?.message || "Could not re-validate.");
    } finally {
      setBusy(false);
    }
  };

  const handleQuarantine = async () => {
    let reason;
    try {
      reason = await openDialog({
        title: "Quarantine evidence?",
        message:
          "Quarantine marks this evidence as unsafe for further processing. Provide a reason.",
        confirmLabel: "Quarantine",
        variant: "danger",
        requireReason: true,
        reasonLabel: "Quarantine reason",
      });
    } catch {
      return;
    }

    setBusy(true);
    try {
      await evidenceService.quarantine(evidenceId, { reason });
      success("Quarantined", "Evidence has been quarantined.");
      await load();
    } catch (err) {
      notifyError("Quarantine failed", err?.message || "Could not quarantine.");
    } finally {
      setBusy(false);
    }
  };

  const handleVerifyChain = async () => {
    setBusy(true);
    setChainVerify(null);
    try {
      const result = await evidenceService.verifyCustody(evidenceId);
      setChainVerify(result);
      if (result.is_valid) {
        success(
          "Custody chain valid",
          `${result.total_entries} entries verified with matching integrity.`
        );
      } else {
        warning(
          "Custody issues found",
          (result.issues || []).slice(0, 2).join(" · ") ||
            "Chain verification reported problems."
        );
      }
      await load();
    } catch (err) {
      notifyError("Chain verify failed", err?.message || "Could not verify chain.");
    } finally {
      setBusy(false);
    }
  };

  if (loading && !detail) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="detail" rows={8} />
      </Container>
    );
  }

  if (error && !detail) {
    return (
      <Container fluid className="px-0">
        <PageHeader title="Evidence Detail" />
        <ApiErrorDisplay error={error} onRetry={load} />
        <Button
          variant="outline-secondary"
          className="mt-3"
          onClick={() => history.push(Routes.Evidence.path)}
        >
          Back to inventory
        </Button>
      </Container>
    );
  }

  const fileName = basename(detail?.file_path);
  const isQuarantined =
    String(status).toLowerCase() === EVIDENCE_STATUS.QUARANTINED;

  return (
    <Container fluid className="px-0">
      <PageHeader
        title={fileName}
        subtitle={String(evidenceId || "").slice(0, 8)}
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Evidence", to: Routes.Evidence.path },
          { label: fileName },
        ]}
        actions={
          <div className="d-flex flex-wrap align-items-center gap-2">
            <Badge
              bg={
                detail?.evidence_type === EVIDENCE_TYPE.MEMORY_DUMP
                  ? "info"
                  : "secondary"
              }
            >
              {typeLabel(detail?.evidence_type)}
            </Badge>
            <StatusBadge status={status} type="evidence" />
            {canRead ? (
              <Button
                size="sm"
                variant="outline-info"
                disabled={busy}
                onClick={handleVerifyIntegrity}
              >
                {busy ? (
                  <Spinner animation="border" size="sm" className="me-1" />
                ) : (
                  <FontAwesomeIcon icon={faShieldAlt} className="me-1" />
                )}
                Verify Integrity
              </Button>
            ) : null}
            {canUpdate ? (
              <Button
                size="sm"
                variant="outline-success"
                disabled={busy}
                onClick={handleRevalidate}
              >
                <FontAwesomeIcon icon={faCheckCircle} className="me-1" />
                Re-validate
              </Button>
            ) : null}
            {canUpdate && !isQuarantined ? (
              <Button
                size="sm"
                variant="outline-danger"
                disabled={busy}
                onClick={handleQuarantine}
              >
                <FontAwesomeIcon icon={faBan} className="me-1" />
                Quarantine
              </Button>
            ) : null}
          </div>
        }
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={load} className="mb-3" />
      ) : null}

      {integrity ? (
        <Alert
          variant={integrity.integrity_verified ? "success" : "danger"}
          className="mb-3"
          dismissible
          onClose={() => setIntegrity(null)}
        >
          <FontAwesomeIcon
            icon={
              integrity.integrity_verified ? faCheckCircle : faTimesCircle
            }
            className="me-2"
          />
          {integrity.integrity_verified
            ? "Integrity verification passed."
            : "Integrity verification failed."}{" "}
          <span className="small text-muted">
            {formatDate(integrity.timestamp)}
          </span>
        </Alert>
      ) : null}

      {validation ? (
        <Alert
          variant={validation.validation_passed ? "success" : "warning"}
          className="mb-3"
          dismissible
          onClose={() => setValidation(null)}
        >
          {validation.validation_passed
            ? "Re-validation passed."
            : `Re-validation issues: ${(
                validation.validation_failures || []
              ).join("; ")}`}
        </Alert>
      ) : null}

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
                <Nav.Link eventKey="status">Status History</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="custody">Chain of Custody</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="metadata">Metadata</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="analysis">Analysis</Nav.Link>
              </Nav.Item>
            </Nav>
          </Card.Header>
          <Card.Body>
            <Tab.Content>
              <Tab.Pane eventKey="overview">
                <Row>
                  <Col xs={12} lg={6} className="mb-4">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Header className="border-bottom border-light">
                        <h5 className="mb-0">Info</h5>
                      </Card.Header>
                      <Card.Body>
                        <Table borderless className="mb-0">
                          <tbody>
                            <tr>
                              <th className="ps-0 text-muted" style={{ width: "35%" }}>
                                File path
                              </th>
                              <td className="text-break">
                                <code>{detail?.file_path || "—"}</code>
                              </td>
                            </tr>
                            <tr>
                              <th className="ps-0 text-muted">Type</th>
                              <td>{typeLabel(detail?.evidence_type)}</td>
                            </tr>
                            <tr>
                              <th className="ps-0 text-muted">Size</th>
                              <td>
                                {formatBytes(
                                  detail?.file_size_bytes ??
                                    metadata.file_size_bytes
                                )}
                              </td>
                            </tr>
                            <tr>
                              <th className="ps-0 text-muted">MIME type</th>
                              <td>{metadata.mime_type || "—"}</td>
                            </tr>
                            <tr>
                              <th className="ps-0 text-muted">Registered</th>
                              <td>
                                {formatDate(
                                  detail?.acquired_at || metadata.extracted_at
                                )}
                              </td>
                            </tr>
                            <tr>
                              <th className="ps-0 text-muted">Case</th>
                              <td>
                                {detail?.case_id ? (
                                  <Link
                                    to={Routes.CaseDetail.path.replace(
                                      ":id",
                                      detail.case_id
                                    )}
                                  >
                                    {detail.case_name ||
                                      formatCaseId(detail.case_id)}
                                  </Link>
                                ) : (
                                  "—"
                                )}
                              </td>
                            </tr>
                          </tbody>
                        </Table>
                      </Card.Body>
                    </Card>
                  </Col>
                  <Col xs={12} lg={6} className="mb-4">
                    <HashSetDisplay
                      hashSet={
                        integrity?.hash_set &&
                        Object.keys(integrity.hash_set).length
                          ? integrity.hash_set
                          : hashSet.sha256
                            ? hashSet
                            : {
                                sha256: detail?.original_hash,
                                md5: hashSet.md5,
                                sha1: hashSet.sha1,
                                computed_at: hashSet.computed_at,
                              }
                      }
                      lastVerifiedAt={lastVerifiedAt}
                      integrityVerified={
                        integrity ? integrity.integrity_verified : null
                      }
                      discrepancies={integrity?.discrepancies || {}}
                    />
                  </Col>
                  <Col xs={12}>
                    <Card border="light" className="shadow-sm">
                      <Card.Header className="border-bottom border-light">
                        <h5 className="mb-0">Validation</h5>
                      </Card.Header>
                      <Card.Body>
                        <div className="mb-2">
                          Format valid:{" "}
                          {metadata.is_valid_format === true ? (
                            <span className="text-success fw-bold">
                              <FontAwesomeIcon
                                icon={faCheckCircle}
                                className="me-1"
                              />
                              Yes
                            </span>
                          ) : metadata.is_valid_format === false ? (
                            <span className="text-danger fw-bold">
                              <FontAwesomeIcon
                                icon={faTimesCircle}
                                className="me-1"
                              />
                              No
                            </span>
                          ) : (
                            "—"
                          )}
                        </div>
                        <div className="small text-muted mb-2">
                          Validated at:{" "}
                          {formatDate(
                            metadata.extracted_at ||
                              validation?.metadata?.extracted_at
                          ) || "—"}
                        </div>
                        {(metadata.validation_notes || []).length ? (
                          <ListGroup variant="flush">
                            {metadata.validation_notes.map((note, index) => (
                              <ListGroup.Item
                                key={index}
                                className="px-0 small"
                              >
                                {note}
                              </ListGroup.Item>
                            ))}
                          </ListGroup>
                        ) : (
                          <p className="text-muted mb-0 small">
                            No validation notes recorded.
                          </p>
                        )}
                      </Card.Body>
                    </Card>
                  </Col>
                </Row>
              </Tab.Pane>

              <Tab.Pane eventKey="status">
                <StatusTimeline
                  entries={statusHistory}
                  emptyTitle="No status transitions"
                  emptyDescription="Status changes will appear here after lifecycle actions."
                  renderEntry={(entry, _index, isCurrent) => (
                    <div
                      className={isCurrent ? "p-2 rounded bg-light" : ""}
                    >
                      <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                        <StatusBadge
                          status={entry.new_status || entry.status}
                          type="evidence"
                        />
                        {entry.previous_status ? (
                          <span className="small text-muted">
                            from {actionLabel(entry.previous_status)}
                          </span>
                        ) : null}
                        {isCurrent ? (
                          <Badge bg="primary">Current</Badge>
                        ) : null}
                      </div>
                      <div className="small text-muted">
                        {formatDate(entry.changed_at)} ·{" "}
                        {entry.changed_by_user_id || "system"}
                      </div>
                      {entry.reason ? (
                        <div className="small mt-1">{entry.reason}</div>
                      ) : null}
                    </div>
                  )}
                />
              </Tab.Pane>

              <Tab.Pane eventKey="custody">
                <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                  <h5 className="mb-0">Custody chain</h5>
                  <Button
                    size="sm"
                    variant="outline-primary"
                    disabled={busy}
                    onClick={handleVerifyChain}
                  >
                    <FontAwesomeIcon icon={faShieldAlt} className="me-1" />
                    Verify Chain
                  </Button>
                </div>

                {chainVerify ? (
                  <Alert
                    variant={chainVerify.is_valid ? "success" : "warning"}
                    className="mb-3"
                  >
                    <div className="fw-bold mb-1">
                      {chainVerify.is_valid
                        ? "Chain verification passed"
                        : "Chain verification found issues"}
                    </div>
                    <div className="small">
                      Entries: {chainVerify.total_entries} · Integrity:{" "}
                      {chainVerify.integrity_verified ? "OK" : "Failed"}
                    </div>
                    {(chainVerify.issues || []).length ? (
                      <ul className="mb-0 mt-2 small">
                        {chainVerify.issues.map((issue, i) => (
                          <li key={i}>{issue}</li>
                        ))}
                      </ul>
                    ) : null}
                  </Alert>
                ) : null}

                <StatusTimeline
                  entries={custodyTimeline}
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
                          {isCurrent ? (
                            <Badge bg="primary">Latest</Badge>
                          ) : null}
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
                            <Button
                              variant="link"
                              size="sm"
                              className="p-0 ms-2"
                              onClick={() => {
                                if (navigator.clipboard?.writeText) {
                                  navigator.clipboard.writeText(
                                    entry.hash_at_action
                                  );
                                  info("Copied", "Custody hash copied.");
                                }
                              }}
                            >
                              Copy
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    );
                  }}
                />
              </Tab.Pane>

              <Tab.Pane eventKey="metadata">
                <Row>
                  <Col xs={12} lg={5} className="mb-4">
                    <h5 className="mb-3">File timestamps</h5>
                    <Table borderless>
                      <tbody>
                        <tr>
                          <th className="ps-0 text-muted">Created</th>
                          <td>{formatDate(metadata.file_created_at)}</td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Modified</th>
                          <td>{formatDate(metadata.file_modified_at)}</td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Accessed</th>
                          <td>{formatDate(metadata.file_accessed_at)}</td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">MIME method</th>
                          <td>
                            <Badge bg="secondary">
                              {metadata.mime_detected_from ||
                                "unknown"}
                            </Badge>
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Extension</th>
                          <td>{metadata.file_extension || "—"}</td>
                        </tr>
                      </tbody>
                    </Table>
                  </Col>
                  <Col xs={12} lg={7}>
                    <h5 className="mb-3">Full metadata</h5>
                    <pre
                      className="bg-light border rounded p-3 small mb-0"
                      style={{
                        maxHeight: 420,
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {JSON.stringify(metadata, null, 2) || "{}"}
                    </pre>
                  </Col>
                </Row>
              </Tab.Pane>

              <Tab.Pane eventKey="analysis">
                <Row>
                  <Col xs={12} md={6} className="mb-4">
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Body>
                        <h5 className="mb-3">Artefact summary</h5>
                        {latestJob ? (
                          <>
                            <p className="mb-2">
                              Artefacts recovered:{" "}
                              <strong>{artefactCount}</strong>
                            </p>
                            <p className="mb-2 small text-muted">
                              Latest job status:{" "}
                              <StatusBadge
                                status={latestJob.status}
                                type="pipeline"
                              />
                            </p>
                            <Button
                              as={Link}
                              to={Routes.PipelineDetail.path.replace(
                                ":jobId",
                                latestJob.job_id
                              )}
                              variant="outline-primary"
                              size="sm"
                              className="me-2"
                            >
                              View pipeline job
                            </Button>
                            {latestJob.report_id ? (
                              <Button
                                as={Link}
                                to={Routes.ReportDetail.path.replace(
                                  ":id",
                                  latestJob.report_id
                                )}
                                variant="outline-secondary"
                                size="sm"
                              >
                                View report
                              </Button>
                            ) : null}
                          </>
                        ) : (
                          <EmptyState
                            title="No pipeline run yet"
                            description="Run the analysis pipeline to recover artefacts from this evidence."
                          />
                        )}
                      </Card.Body>
                    </Card>
                  </Col>
                  <Col xs={12} md={6}>
                    <Card border="light" className="shadow-sm h-100">
                      <Card.Body className="d-flex flex-column justify-content-center">
                        <h5 className="mb-3">Actions</h5>
                        {analysisPerm.canCreate ? (
                          <Button
                            variant="primary"
                            onClick={() =>
                              history.push(
                                `${Routes.PipelineRun.path}?evidenceId=${encodeURIComponent(
                                  evidenceId
                                )}&caseId=${encodeURIComponent(
                                  detail?.case_id || ""
                                )}`
                              )
                            }
                          >
                            <FontAwesomeIcon icon={faPlay} className="me-2" />
                            Run Pipeline
                          </Button>
                        ) : (
                          <Alert variant="secondary" className="mb-0">
                            <FontAwesomeIcon
                              icon={faExclamationTriangle}
                              className="me-2"
                            />
                            Your role cannot start pipeline jobs.
                          </Alert>
                        )}
                      </Card.Body>
                    </Card>
                  </Col>
                </Row>
              </Tab.Pane>
            </Tab.Content>
          </Card.Body>
        </Card>
      </Tab.Container>

      <ConfirmDialog {...dialogProps} />
    </Container>
  );
}

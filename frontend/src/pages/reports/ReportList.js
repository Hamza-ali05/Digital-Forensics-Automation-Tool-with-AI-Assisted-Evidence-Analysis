import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faCode,
  faEye,
  faFileAlt,
  faFilePdf,
  faShieldAlt,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import { formatDate, formatDuration } from "utils/formatters";
import {
  evidenceOptionId,
  loadEvidenceOptions,
  normaliseEvidenceList,
} from "utils/artefactLoader";
import useNotification from "hooks/useNotification";
import casesService from "services/cases.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import { Routes } from "routes";

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function jobDurationSeconds(job, meta) {
  if (typeof meta?.pipeline_duration_seconds === "number") {
    return meta.pipeline_duration_seconds;
  }
  if (typeof job?.total_duration_seconds === "number") {
    return job.total_duration_seconds;
  }
  return 0;
}

function resolveAiModel(job, jsonDoc) {
  const aiMeta = jsonDoc?.ai_metadata || {};
  if (aiMeta.model_used && aiMeta.model_used !== "none") {
    return aiMeta.model_used;
  }
  if (jsonDoc?.llm_model_used) return jsonDoc.llm_model_used;
  if (job?.use_fallback_analyzer) return "Rule-based fallback";
  return aiMeta.model || "LLaMA-3";
}

function uniqueReportJobs(jobs) {
  const byId = new Map();
  (jobs || []).forEach((job) => {
    const reportId = job?.report_id;
    if (!reportId) return;
    const existing = byId.get(reportId);
    if (!existing) {
      byId.set(reportId, job);
      return;
    }
    const existingTime = new Date(
      existing.completed_at || existing.created_at || 0
    ).getTime();
    const nextTime = new Date(job.completed_at || job.created_at || 0).getTime();
    if (nextTime >= existingTime) byId.set(reportId, job);
  });
  return Array.from(byId.values()).sort((a, b) => {
    const ta = new Date(a.completed_at || a.created_at || 0).getTime();
    const tb = new Date(b.completed_at || b.created_at || 0).getTime();
    return tb - ta;
  });
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
 * Forensic reports list with export and integrity actions.
 */
export default function ReportList() {
  const { success, error: notifyError, info } = useNotification();

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const pageSize = 20;

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobs, inventory, caseResult] = await Promise.all([
        pipelineService.listJobs(),
        evidenceServiceSafe(),
        casesService.list().catch(() => ({ cases: [] })),
      ]);

      const evidenceItems = Array.isArray(inventory)
        ? inventory
        : normaliseEvidenceList(inventory);
      const evidenceMap = {};
      evidenceItems.forEach((item) => {
        const id = evidenceOptionId(item);
        if (id) evidenceMap[id] = item;
      });

      const caseItems = Array.isArray(caseResult?.cases)
        ? caseResult.cases
        : Array.isArray(caseResult)
          ? caseResult
          : [];
      const caseMap = {};
      caseItems.forEach((item) => {
        if (item?.case_id) caseMap[item.case_id] = item;
      });

      const uniqueJobs = uniqueReportJobs(jobs);
      const enriched = await Promise.all(
        uniqueJobs.map(async (job) => {
          const reportId = job.report_id;
          const [meta, jsonDoc] = await Promise.all([
            reportsService.getById(reportId).catch(() => null),
            reportsService.getJson(reportId).catch(() => null),
          ]);
          const evidence = evidenceMap[job.evidence_id];
          const caseRow = caseMap[job.case_id];
          return {
            id: reportId,
            report_id: reportId,
            job_id: job.job_id || job.id,
            case_id: job.case_id,
            case_name:
              meta?.case_name || caseRow?.case_name || shortId(job.case_id),
            evidence_id: job.evidence_id,
            evidence_name:
              evidence?.file_name ||
              evidence?.filename ||
              evidence?.name ||
              shortId(job.evidence_id),
            generated_at:
              meta?.generated_at || job.completed_at || job.created_at,
            duration_seconds: jobDurationSeconds(job, meta),
            ai_model: resolveAiModel(job, jsonDoc),
            use_fallback: Boolean(job.use_fallback_analyzer),
          };
        })
      );
      setRows(enriched);
    } catch (err) {
      setError(err);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReports().catch(() => {});
  }, [loadReports]);

  const pagedRows = useMemo(() => {
    const start = (Math.max(1, page) - 1) * pageSize;
    return rows.slice(start, start + pageSize);
  }, [rows, page]);

  const runExport = async (row, kind) => {
    const id = row.report_id;
    setBusy({ id, kind });
    try {
      if (kind === "pdf") await reportsService.exportPdf(id);
      else if (kind === "html") await reportsService.exportHtml(id);
      else await reportsService.exportJson(id);
      info("Download started", `Report ${shortId(id)} ${kind.toUpperCase()} export.`);
    } catch (err) {
      notifyError(
        "Export failed",
        err?.message || `Could not export ${kind.toUpperCase()}.`
      );
    } finally {
      setBusy(null);
    }
  };

  const runVerify = async (row) => {
    const id = row.report_id;
    setBusy({ id, kind: "verify" });
    setVerifyResult(null);
    try {
      const result = await reportsService.verify(id);
      setVerifyResult({ reportId: id, ...result });
      if (result.is_valid) {
        success(
          "Integrity verified",
          `Report ${shortId(id)} passed integrity verification.`
        );
      } else {
        notifyError(
          "Integrity check failed",
          (result.issues || []).join("; ") || `Report ${shortId(id)} is not valid.`
        );
      }
    } catch (err) {
      notifyError(
        "Verify failed",
        err?.message || "Could not verify report integrity."
      );
    } finally {
      setBusy(null);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "report_id",
        header: "Report ID",
        sortable: true,
        render: (row) => (
          <Link
            to={Routes.ReportDetail.path.replace(":id", row.report_id)}
            className="fw-bold"
          >
            {shortId(row.report_id)}
          </Link>
        ),
      },
      {
        key: "case",
        header: "Case",
        render: (row) =>
          row.case_id ? (
            <Link to={Routes.CaseDetail.path.replace(":id", row.case_id)}>
              {row.case_name}
            </Link>
          ) : (
            row.case_name || "—"
          ),
      },
      {
        key: "evidence",
        header: "Evidence",
        render: (row) =>
          row.evidence_id ? (
            <Link to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}>
              {row.evidence_name}
            </Link>
          ) : (
            "—"
          ),
      },
      {
        key: "generated_at",
        header: "Generated At",
        sortable: true,
        render: (row) => formatDate(row.generated_at),
      },
      {
        key: "duration",
        header: "Duration",
        render: (row) => formatDuration(row.duration_seconds),
      },
      {
        key: "ai_model",
        header: "AI Model",
        render: (row) => (
          <span>
            {row.ai_model}
            {row.use_fallback ? (
              <Badge bg="warning" text="dark" className="ms-2">
                Fallback
              </Badge>
            ) : null}
          </span>
        ),
      },
    ],
    []
  );

  const renderActions = (row) => {
    const isBusy = busy?.id === row.report_id;
    const spinning = (kind) => isBusy && busy.kind === kind;
    return (
      <div className="d-flex justify-content-end flex-wrap gap-1">
        <Button
          as={Link}
          to={Routes.ReportDetail.path.replace(":id", row.report_id)}
          variant="outline-primary"
          size="sm"
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          View
        </Button>
        <Button
          variant="outline-secondary"
          size="sm"
          disabled={isBusy}
          onClick={() => runExport(row, "pdf")}
        >
          {spinning("pdf") ? (
            <Spinner animation="border" size="sm" className="me-1" />
          ) : (
            <FontAwesomeIcon icon={faFilePdf} className="me-1" />
          )}
          Export PDF
        </Button>
        <Button
          variant="outline-secondary"
          size="sm"
          disabled={isBusy}
          onClick={() => runExport(row, "html")}
        >
          {spinning("html") ? (
            <Spinner animation="border" size="sm" className="me-1" />
          ) : (
            <FontAwesomeIcon icon={faFileAlt} className="me-1" />
          )}
          Export HTML
        </Button>
        <Button
          variant="outline-secondary"
          size="sm"
          disabled={isBusy}
          onClick={() => runExport(row, "json")}
        >
          {spinning("json") ? (
            <Spinner animation="border" size="sm" className="me-1" />
          ) : (
            <FontAwesomeIcon icon={faCode} className="me-1" />
          )}
          Download JSON
        </Button>
        <Button
          variant="outline-success"
          size="sm"
          disabled={isBusy}
          onClick={() => runVerify(row)}
        >
          {spinning("verify") ? (
            <Spinner animation="border" size="sm" className="me-1" />
          ) : (
            <FontAwesomeIcon icon={faShieldAlt} className="me-1" />
          )}
          Verify Integrity
        </Button>
      </div>
    );
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Forensic Reports"
        subtitle="Generated dual-output reports with export and integrity verification"
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={loadReports} className="mb-3" />
      ) : null}

      {verifyResult ? (
        <Alert
          variant={verifyResult.is_valid ? "success" : "warning"}
          dismissible
          onClose={() => setVerifyResult(null)}
          className="mb-3"
        >
          <div className="fw-bold mb-2">
            Integrity result for {shortId(verifyResult.reportId)}
          </div>
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
                ? "Schema version valid"
                : "Schema version invalid"
            }
          />
          <VerifyFlag
            ok={Boolean(verifyResult.is_valid)}
            label={verifyResult.is_valid ? "Validation passed" : "Validation failed"}
          />
          {(verifyResult.issues || []).length ? (
            <ul className="mb-0 mt-2 small">
              {verifyResult.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          ) : null}
        </Alert>
      ) : null}

      <Card border="light" className="shadow-sm">
        <Card.Body className="pt-0">
          <DataTable
            columns={columns}
            data={pagedRows}
            loading={loading}
            emptyMessage="No forensic reports yet"
            sortable
            actions={renderActions}
            pagination={{ page, pageSize, total: rows.length }}
            onPageChange={setPage}
          />
        </Card.Body>
      </Card>
    </Container>
  );
}

async function evidenceServiceSafe() {
  try {
    return await loadEvidenceOptions();
  } catch {
    return [];
  }
}

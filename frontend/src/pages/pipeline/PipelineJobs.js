import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Container,
  Form,
  ProgressBar,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBan,
  faEye,
  faPlay,
  faPlus,
} from "@fortawesome/free-solid-svg-icons";
import Datetime from "react-datetime";
import moment from "moment-timezone";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import ConfirmDialog from "components/common/ConfirmDialog";
import PipelineProgressBar from "components/forensic/PipelineProgressBar";
import { JOB_STATUS } from "utils/constants";
import {
  formatDateRelative,
  formatDuration,
} from "utils/formatters";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import usePolling from "hooks/usePolling";
import pipelineService from "services/pipeline.service";
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import { Routes } from "routes";

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: JOB_STATUS.QUEUED, label: "Queued" },
  { value: JOB_STATUS.RUNNING, label: "Running" },
  { value: JOB_STATUS.COMPLETED, label: "Completed" },
  { value: JOB_STATUS.FAILED, label: "Failed" },
  { value: JOB_STATUS.CANCELLED, label: "Cancelled" },
];

const ACTIVE_STATUSES = new Set([
  JOB_STATUS.QUEUED,
  JOB_STATUS.INITIALISING,
  JOB_STATUS.RUNNING,
  JOB_STATUS.STAGE_COMPLETE,
  "initializing",
  "in_progress",
]);

const CANCELABLE = new Set([
  JOB_STATUS.QUEUED,
  JOB_STATUS.INITIALISING,
  JOB_STATUS.RUNNING,
  JOB_STATUS.STAGE_COMPLETE,
  "initializing",
]);

function toMoment(value) {
  if (!value) return null;
  if (moment.isMoment(value)) return value.isValid() ? value : null;
  const m = moment(value);
  return m.isValid() ? m : null;
}

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function modeLabel(mode) {
  const m = String(mode || "full").toLowerCase();
  if (m === "parse-only") return "Parse Only";
  if (m === "triage-only") return "Triage Only";
  return "Full";
}

function jobDurationSeconds(job) {
  if (typeof job.total_duration_seconds === "number") {
    return job.total_duration_seconds;
  }
  const start = job.started_at || job.created_at;
  if (!start) return 0;
  const end = job.completed_at || new Date().toISOString();
  return Math.max(
    0,
    (new Date(end).getTime() - new Date(start).getTime()) / 1000
  );
}

function synthesiseProgress(job) {
  const status = String(job.status || "").toLowerCase();
  const stages = job.stage_executions || {};
  const stageKeys = Object.keys(stages);
  const completed = stageKeys.filter(
    (key) => String(stages[key]?.status || "").toLowerCase() === "completed"
  ).length;
  const total = 5;
  let percent = 0;
  if (status === JOB_STATUS.COMPLETED) percent = 100;
  else if (status === JOB_STATUS.FAILED) percent = Math.max(10, (completed / total) * 100);
  else if (ACTIVE_STATUSES.has(status)) {
    percent = Math.min(95, (completed / total) * 100 + (status === JOB_STATUS.RUNNING ? 10 : 0));
  }
  return {
    job_id: job.job_id,
    status: job.status,
    current_stage: job.current_stage,
    stages_completed: completed,
    stages_total: total,
    percent_complete: Math.round(percent * 10) / 10,
    current_parser: null,
    elapsed_seconds: jobDurationSeconds(job),
    estimated_remaining_seconds: null,
    artefacts_found_so_far: job.artefact_count || 0,
  };
}

/**
 * Pipeline job monitor with filters, progress, and cancel actions.
 */
export default function PipelineJobs() {
  const history = useHistory();
  const { canCreate } = usePermission("analysis");
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const [cases, setCases] = useState([]);
  const [evidenceMap, setEvidenceMap] = useState({});
  const [caseMap, setCaseMap] = useState({});
  const [statusFilter, setStatusFilter] = useState("");
  const [caseFilter, setCaseFilter] = useState("");
  const [dateFrom, setDateFrom] = useState(null);
  const [dateTo, setDateTo] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [progressMap, setProgressMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [actionBusy, setActionBusy] = useState(null);
  const pageSize = 20;

  const filtersRef = useRef({ statusFilter, caseFilter, dateFrom, dateTo });
  filtersRef.current = { statusFilter, caseFilter, dateFrom, dateTo };

  useEffect(() => {
    casesService
      .list()
      .then((result) => {
        const items = Array.isArray(result?.cases) ? result.cases : [];
        setCases(items);
        const map = {};
        items.forEach((c) => {
          map[c.case_id] = c;
        });
        setCaseMap(map);
      })
      .catch(() => setCases([]));

    evidenceService
      .getInventory()
      .then((result) => {
        const items = Array.isArray(result?.items) ? result.items : [];
        const map = {};
        items.forEach((item) => {
          map[item.evidence_id] = item;
        });
        setEvidenceMap(map);
      })
      .catch(() => setEvidenceMap({}));
  }, []);

  const applyClientFilters = useCallback((list) => {
    const { statusFilter: status, caseFilter: caseId, dateFrom: from, dateTo: to } =
      filtersRef.current;
    let items = Array.isArray(list) ? [...list] : [];

    if (status) {
      if (status === JOB_STATUS.RUNNING) {
        items = items.filter((job) =>
          ACTIVE_STATUSES.has(String(job.status || "").toLowerCase())
        );
      } else {
        items = items.filter(
          (job) => String(job.status || "").toLowerCase() === status
        );
      }
    }
    if (caseId) {
      items = items.filter((job) => job.case_id === caseId);
    }

    const fromM = toMoment(from)?.startOf("day");
    const toM = toMoment(to)?.endOf("day");
    if (fromM || toM) {
      items = items.filter((job) => {
        const stamp = toMoment(job.started_at || job.created_at);
        if (!stamp) return false;
        if (fromM && stamp.isBefore(fromM)) return false;
        if (toM && stamp.isAfter(toM)) return false;
        return true;
      });
    }

    items.sort((a, b) => {
      const ta = new Date(a.started_at || a.created_at || 0).getTime();
      const tb = new Date(b.started_at || b.created_at || 0).getTime();
      return tb - ta;
    });
    return items;
  }, []);

  const fetchJobs = useCallback(async () => {
    const { statusFilter: status, caseFilter: caseId } = filtersRef.current;
    const params = {};
    // Server supports exact status; "Running" UI filter includes several active states client-side
    if (status && status !== JOB_STATUS.RUNNING) params.status = status;
    if (caseId) params.case_id = caseId;

    const list = await pipelineService.listJobs(params);
    return applyClientFilters(list);
  }, [applyClientFilters]);

  const refreshProgress = useCallback(async (jobList) => {
    const active = (jobList || []).filter((job) =>
      ACTIVE_STATUSES.has(String(job.status || "").toLowerCase())
    );
    if (!active.length) {
      setProgressMap({});
      return {};
    }
    const entries = await Promise.all(
      active.map(async (job) => {
        try {
          const progress = await pipelineService.getProgress(job.job_id);
          return [job.job_id, progress];
        } catch {
          return [job.job_id, synthesiseProgress(job)];
        }
      })
    );
    const next = {};
    entries.forEach(([id, progress]) => {
      next[id] = progress;
    });
    setProgressMap(next);
    return next;
  }, []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filtered = await fetchJobs();
      setJobs(filtered);
      await refreshProgress(filtered);
      return filtered;
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchJobs, refreshProgress]);

  useEffect(() => {
    loadJobs().catch(() => {});
  }, [loadJobs]);

  useEffect(() => {
    setPage(1);
    loadJobs().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, caseFilter, dateFrom, dateTo]);

  const hasRunning = useMemo(
    () =>
      jobs.some((job) =>
        ACTIVE_STATUSES.has(String(job.status || "").toLowerCase())
      ),
    [jobs]
  );

  const pollJobs = useCallback(async () => {
    const filtered = await fetchJobs();
    setJobs(filtered);
    await refreshProgress(filtered);
    return filtered;
  }, [fetchJobs, refreshProgress]);

  usePolling(pollJobs, 5000, hasRunning);

  const pagedJobs = useMemo(() => {
    const start = (Math.max(1, page) - 1) * pageSize;
    return jobs.slice(start, start + pageSize).map((job) => ({
      ...job,
      id: job.job_id,
    }));
  }, [jobs, page]);

  const handleCancel = async (job) => {
    try {
      await openDialog({
        title: "Cancel pipeline job?",
        message: `Cancel job ${shortId(job.job_id)}? In-flight stage work may stop after the current step.`,
        confirmLabel: "Cancel Job",
        variant: "danger",
      });
    } catch {
      return;
    }

    setActionBusy(job.job_id);
    try {
      await pipelineService.cancel(job.job_id);
      success("Job cancelled", `Pipeline ${shortId(job.job_id)} was cancelled.`);
      await loadJobs();
    } catch (err) {
      notifyError("Cancel failed", err?.message || "Could not cancel the job.");
    } finally {
      setActionBusy(null);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "job_id",
        header: "Job ID",
        sortable: true,
        render: (row) => (
          <Link
            to={Routes.PipelineDetail.path.replace(":jobId", row.job_id)}
            className="fw-bold"
          >
            {shortId(row.job_id)}
          </Link>
        ),
      },
      {
        key: "evidence",
        header: "Evidence",
        render: (row) => {
          const ev = evidenceMap[row.evidence_id];
          const label = ev?.file_name || shortId(row.evidence_id);
          return (
            <Link
              to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}
            >
              {label}
            </Link>
          );
        },
      },
      {
        key: "case",
        header: "Case",
        render: (row) => {
          const c = caseMap[row.case_id];
          return (
            <Link to={Routes.CaseDetail.path.replace(":id", row.case_id)}>
              {c?.case_name || shortId(row.case_id)}
            </Link>
          );
        },
      },
      {
        key: "status",
        header: "Status",
        sortable: true,
        render: (row) => <StatusBadge status={row.status} type="pipeline" />,
      },
      {
        key: "mode",
        header: "Mode",
        render: (row) => modeLabel(row.mode),
      },
      {
        key: "progress",
        header: "Progress",
        render: (row) => {
          const status = String(row.status || "").toLowerCase();
          if (status === JOB_STATUS.COMPLETED) {
            return <ProgressBar now={100} variant="success" style={{ height: 8 }} />;
          }
          if (status === JOB_STATUS.FAILED) {
            return <ProgressBar now={100} variant="danger" style={{ height: 8 }} />;
          }
          if (!ACTIVE_STATUSES.has(status)) {
            return "—";
          }
          const progress = progressMap[row.job_id] || synthesiseProgress(row);
          return <PipelineProgressBar progress={progress} compact />;
        },
      },
      {
        key: "duration",
        header: "Duration",
        render: (row) => formatDuration(jobDurationSeconds(row)),
      },
      {
        key: "artefact_count",
        header: "Artefacts Found",
        sortable: true,
        render: (row) =>
          progressMap[row.job_id]?.artefacts_found_so_far ??
          row.artefact_count ??
          0,
      },
      {
        key: "started_at",
        header: "Started",
        sortable: true,
        render: (row) =>
          formatDateRelative(row.started_at || row.created_at),
      },
    ],
    [evidenceMap, caseMap, progressMap]
  );

  const renderActions = (row) => {
    const status = String(row.status || "").toLowerCase();
    const busy = actionBusy === row.job_id;
    return (
      <div className="d-flex justify-content-end flex-wrap gap-1">
        <Button
          as={Link}
          to={Routes.PipelineDetail.path.replace(":jobId", row.job_id)}
          variant="outline-primary"
          size="sm"
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          View
        </Button>
        {canCreate && CANCELABLE.has(status) ? (
          <Button
            variant="outline-danger"
            size="sm"
            disabled={busy}
            onClick={() => handleCancel(row)}
          >
            <FontAwesomeIcon icon={faBan} className="me-1" />
            Cancel
          </Button>
        ) : null}
      </div>
    );
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Pipeline Monitor"
        subtitle="Track forensic analysis jobs and launch new pipeline runs"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Pipeline" },
        ]}
        actions={
          canCreate ? (
            <Button
              variant="primary"
              onClick={() => history.push(Routes.PipelineRun.path)}
            >
              <FontAwesomeIcon icon={faPlus} className="me-2" />
              Run Pipeline
            </Button>
          ) : null
        }
      />

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3 align-items-end">
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Status</Form.Label>
                <Form.Select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value || "all"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Case</Form.Label>
                <Form.Select
                  value={caseFilter}
                  onChange={(e) => setCaseFilter(e.target.value)}
                >
                  <option value="">All cases</option>
                  {cases.map((c) => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_name}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={6} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">From</Form.Label>
                <Datetime
                  value={dateFrom}
                  onChange={(value) => setDateFrom(toMoment(value))}
                  timeFormat={false}
                  inputProps={{
                    placeholder: "Start date",
                    className: "form-control",
                  }}
                />
              </Form.Group>
            </Col>
            <Col xs={6} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">To</Form.Label>
                <Datetime
                  value={dateTo}
                  onChange={(value) => setDateTo(toMoment(value))}
                  timeFormat={false}
                  inputProps={{
                    placeholder: "End date",
                    className: "form-control",
                  }}
                />
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Button
                variant="outline-secondary"
                className="w-100"
                onClick={() => {
                  setStatusFilter("");
                  setCaseFilter("");
                  setDateFrom(null);
                  setDateTo(null);
                }}
              >
                Reset
              </Button>
            </Col>
          </Row>
          {hasRunning ? (
            <p className="small text-muted mb-0 mt-3">
              Auto-refreshing every 5 seconds while jobs are running.
            </p>
          ) : null}
        </Card.Body>
      </Card>

      {error ? (
        <ApiErrorDisplay
          error={error}
          onRetry={() => loadJobs().catch(() => {})}
          className="mb-3"
        />
      ) : null}

      <Card border="light" className="shadow-sm">
        <Card.Body className="p-0">
          <DataTable
            columns={columns}
            data={pagedJobs}
            loading={loading}
            sortable
            emptyMessage="No pipeline jobs found. Run a pipeline against validated evidence to begin."
            pagination={{ page, pageSize, total: jobs.length }}
            onPageChange={(next) => setPage(next)}
            actions={renderActions}
          />
        </Card.Body>
        {!loading && canCreate && jobs.length === 0 && !error ? (
          <Card.Footer className="bg-white text-center border-0 pb-4">
            <Button
              variant="primary"
              onClick={() => history.push(Routes.PipelineRun.path)}
            >
              <FontAwesomeIcon icon={faPlay} className="me-2" />
              Run first pipeline
            </Button>
          </Card.Footer>
        ) : null}
      </Card>

      <ConfirmDialog {...dialogProps} />
    </Container>
  );
}

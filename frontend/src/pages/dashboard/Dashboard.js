import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Container,
  ListGroup,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faClock,
  faDatabase,
  faFileAlt,
  faFolderOpen,
  faPlayCircle,
  faPlus,
  faShieldAlt,
  faUserShield,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatCard from "components/forensic/StatCard";
import HealthBar from "components/forensic/HealthBar";
import { Routes } from "routes";
import { SUSPICION_COLOURS, SUSPICION_LEVEL } from "utils/constants";
import { formatDate, formatDateRelative } from "utils/formatters";
import usePermission from "hooks/usePermission";
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import healthService from "services/health.service";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip
);

const CATEGORY_COLOURS = [
  "#0d6efd",
  "#198754",
  "#fd7e14",
  "#0dcaf0",
  "#6f42c1",
  "#dc3545",
  "#20c997",
  "#6c757d",
];

const SUSPICION_ORDER = [
  SUSPICION_LEVEL.CRITICAL,
  SUSPICION_LEVEL.HIGH,
  SUSPICION_LEVEL.MEDIUM,
  SUSPICION_LEVEL.LOW,
  SUSPICION_LEVEL.INFORMATIONAL,
];

function humaniseKey(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function activityIcon(action) {
  const text = String(action || "").toLowerCase();
  if (text.includes("login") || text.includes("user")) return faUserShield;
  if (text.includes("pipeline") || text.includes("run")) return faPlayCircle;
  if (text.includes("evidence") || text.includes("hash")) return faDatabase;
  if (text.includes("report")) return faFileAlt;
  if (text.includes("case")) return faFolderOpen;
  return faShieldAlt;
}

function jobToActivity(job) {
  return {
    id: job.job_id,
    timestamp: job.completed_at || job.started_at || job.created_at,
    action: `Pipeline ${job.status || "updated"}`,
    user: job.user_id || "system",
    icon: faPlayCircle,
  };
}

function auditToActivity(entry, index) {
  const user =
    entry?.details?.user_id ||
    entry?.details?.actor ||
    entry?.details?.username ||
    "system";
  // entry_number alone is not always unique in report audit trails.
  const stable =
    entry?.id ||
    `${entry?.entry_number ?? "n"}-${entry?.timestamp ?? ""}-${index}`;
  return {
    id: `audit-${stable}`,
    timestamp: entry.timestamp,
    action: entry.action || "Audit event",
    user,
    icon: activityIcon(entry.action),
  };
}

/**
 * Main DFAT dashboard — stats, charts, activity, quick actions, health.
 */
export default function Dashboard() {
  const casesPerm = usePermission("cases");
  const evidencePerm = usePermission("evidence");
  const analysisPerm = usePermission("analysis");
  const reportsPerm = usePermission("reports");

  const [loading, setLoading] = useState(true);
  const [activeCases, setActiveCases] = useState(0);
  const [evidenceTotal, setEvidenceTotal] = useState(0);
  const [evidenceByType, setEvidenceByType] = useState({});
  const [runningPipelines, setRunningPipelines] = useState(0);
  const [reportsTotal, setReportsTotal] = useState(0);
  const [suspicionByLevel, setSuspicionByLevel] = useState(null);
  const [activity, setActivity] = useState([]);
  const [healthChecks, setHealthChecks] = useState({});
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setHealthLoading(true);
    setHealthError(false);

    const settled = await Promise.allSettled([
      casesService.list({ status: "active" }),
      evidenceService.getStatistics(),
      pipelineService.listJobs({ status: "running" }),
      pipelineService.listJobs(),
      reportsService.getTotal(),
      healthService.ready(),
    ]);

    const [
      casesResult,
      evidenceResult,
      runningResult,
      allJobsResult,
      reportsResult,
      healthResult,
    ] = settled;

    if (casesResult.status === "fulfilled") {
      const payload = casesResult.value;
      setActiveCases(
        typeof payload?.total === "number"
          ? payload.total
          : Array.isArray(payload?.cases)
            ? payload.cases.length
            : Array.isArray(payload)
              ? payload.length
              : 0
      );
    }

    if (evidenceResult.status === "fulfilled") {
      const stats = evidenceResult.value || {};
      setEvidenceTotal(Number(stats.total) || 0);
      setEvidenceByType(stats.by_type || {});
    }

    if (runningResult.status === "fulfilled") {
      const jobs = runningResult.value || [];
      setRunningPipelines(Array.isArray(jobs) ? jobs.length : 0);
    }

    if (reportsResult.status === "fulfilled") {
      setReportsTotal(Number(reportsResult.value) || 0);
    }

    const allJobs =
      allJobsResult.status === "fulfilled" && Array.isArray(allJobsResult.value)
        ? [...allJobsResult.value]
        : [];

    allJobs.sort((a, b) => {
      const ta = new Date(a.completed_at || a.created_at || 0).getTime();
      const tb = new Date(b.completed_at || b.created_at || 0).getTime();
      return tb - ta;
    });

    const candidates = allJobs.filter((job) => job.report_id);
    let nextActivity = allJobs.slice(0, 10).map(jobToActivity);
    let nextSuspicion = null;

    for (const candidate of candidates) {
      try {
        const [jsonReport, audit] = await Promise.all([
          reportsService.getJson(candidate.report_id),
          reportsService.getAuditTrail(candidate.report_id),
        ]);
        nextSuspicion =
          jsonReport?.summary_statistics?.by_suspicion_level || null;
        const entries = Array.isArray(audit?.entries)
          ? audit.entries
          : Array.isArray(audit)
            ? audit
            : [];
        if (entries.length) {
          const sorted = [...entries].sort((a, b) => {
            const ta = new Date(a.timestamp || 0).getTime();
            const tb = new Date(b.timestamp || 0).getTime();
            return tb - ta;
          });
          nextActivity = sorted.slice(0, 10).map(auditToActivity);
        }
        break;
      } catch (err) {
        // Skip orphaned job.report_id pointers (common after DB cleanup).
        if (err?.response?.status === 404) {
          continue;
        }
        break;
      }
    }

    setSuspicionByLevel(nextSuspicion);
    setActivity(nextActivity);

    if (healthResult.status === "fulfilled") {
      setHealthChecks(healthResult.value?.checks || {});
      setHealthError(false);
    } else {
      setHealthChecks({});
      setHealthError(true);
    }

    setHealthLoading(false);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const doughnutData = useMemo(() => {
    const entries = Object.entries(evidenceByType || {});
    if (!entries.length) {
      return {
        labels: ["No data"],
        datasets: [
          {
            data: [1],
            backgroundColor: ["#e9ecef"],
            borderWidth: 0,
          },
        ],
      };
    }
    return {
      labels: entries.map(([key]) => humaniseKey(key)),
      datasets: [
        {
          data: entries.map(([, value]) => Number(value) || 0),
          backgroundColor: entries.map(
            (_, index) => CATEGORY_COLOURS[index % CATEGORY_COLOURS.length]
          ),
          borderWidth: 1,
          borderColor: "#fff",
        },
      ],
    };
  }, [evidenceByType]);

  const suspicionData = useMemo(() => {
    const source = suspicionByLevel || {};
    const labels = SUSPICION_ORDER.map(humaniseKey);
    const values = SUSPICION_ORDER.map((level) => Number(source[level]) || 0);
    const hasData = values.some((v) => v > 0);
    return {
      hasData,
      chart: {
        labels,
        datasets: [
          {
            label: "Artefacts",
            data: hasData ? values : SUSPICION_ORDER.map(() => 0),
            backgroundColor: SUSPICION_ORDER.map(
              (level) => SUSPICION_COLOURS[level]
            ),
            borderWidth: 0,
          },
        ],
      },
    };
  }, [suspicionByLevel]);

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Dashboard"
        subtitle="Operational overview of cases, evidence, pipelines, and system health"
      />

      {/* TOP — Statistics */}
      <Row className="mb-4" data-testid="dashboard-stats">
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Active Cases"
            value={activeCases}
            icon={faFolderOpen}
            colour="primary"
            linkTo={Routes.Cases.path}
            loading={loading}
          />
        </Col>
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Evidence Items"
            value={evidenceTotal}
            icon={faDatabase}
            colour="success"
            linkTo={Routes.Evidence.path}
            loading={loading}
          />
        </Col>
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Running Pipelines"
            value={runningPipelines}
            icon={faPlayCircle}
            colour="warning"
            linkTo={Routes.Pipeline.path}
            loading={loading}
          />
        </Col>
        <Col xs={12} sm={6} xl={3}>
          <StatCard
            title="Reports Generated"
            value={reportsTotal}
            icon={faFileAlt}
            colour="info"
            linkTo={Routes.Reports.path}
            loading={loading}
          />
        </Col>
      </Row>

      {/* MIDDLE — Charts */}
      <Row className="mb-4">
        <Col xs={12} lg={6} className="mb-4 mb-lg-0">
          <Card border="light" className="shadow-sm h-100">
            <Card.Header className="border-bottom border-light">
              <h5 className="mb-0">Evidence by Category</h5>
            </Card.Header>
            <Card.Body className="overflow-hidden">
              {loading ? (
                <SkeletonLoader type="card" rows={1} />
              ) : (
                <div
                  className="mx-auto"
                  style={{ position: "relative", height: 260, maxWidth: 360 }}
                >
                  <Doughnut
                    data={doughnutData}
                    aria-label="Evidence items by category"
                    role="img"
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      layout: {
                        padding: 8,
                      },
                      plugins: {
                        legend: {
                          position: "bottom",
                          labels: { boxWidth: 12, padding: 12 },
                        },
                      },
                    }}
                  />
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header className="border-bottom border-light">
              <h5 className="mb-0">Artefacts by Suspicion Level</h5>
            </Card.Header>
            <Card.Body>
              {loading ? (
                <SkeletonLoader type="card" rows={1} />
              ) : !suspicionData.hasData ? (
                <EmptyState
                  title="No triage data yet"
                  description="Suspicion distribution appears after a completed pipeline run with a report."
                />
              ) : (
                <div style={{ minHeight: 240 }}>
                  <Bar
                    data={suspicionData.chart}
                    aria-label="Artefacts by suspicion level"
                    role="img"
                    options={{
                      indexAxis: "y",
                      responsive: true,
                      maintainAspectRatio: true,
                      plugins: {
                        legend: { display: false },
                      },
                      scales: {
                        x: {
                          beginAtZero: true,
                          ticks: { precision: 0 },
                        },
                      },
                    }}
                  />
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* BOTTOM — Activity + Quick Actions */}
      <Row className="mb-4">
        <Col xs={12} lg={7} className="mb-4 mb-lg-0">
          <Card border="light" className="shadow-sm h-100">
            <Card.Header className="border-bottom border-light d-flex align-items-center">
              <FontAwesomeIcon icon={faClock} className="me-2 text-muted" />
              <h5 className="mb-0">Recent Activity</h5>
            </Card.Header>
            <Card.Body className="p-0">
              {loading ? (
                <div className="p-3">
                  <SkeletonLoader type="text" rows={5} />
                </div>
              ) : activity.length === 0 ? (
                <EmptyState
                  title="No recent activity"
                  description="Audit events and pipeline jobs will appear here."
                />
              ) : (
                <ListGroup
                  variant="flush"
                  style={{ maxHeight: 360, overflowY: "auto" }}
                >
                  {activity.map((item) => (
                    <ListGroup.Item
                      key={item.id}
                      className="d-flex align-items-start border-bottom border-light"
                    >
                      <div className="icon-shape icon-shape-sm rounded bg-soft-primary text-primary me-3 mt-1">
                        <FontAwesomeIcon icon={item.icon || faShieldAlt} />
                      </div>
                      <div className="flex-grow-1">
                        <div className="fw-bold">{item.action}</div>
                        <div className="small text-muted">
                          {item.user} · {formatDateRelative(item.timestamp)}
                          <span className="mx-1">·</span>
                          {formatDate(item.timestamp)}
                        </div>
                      </div>
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={5}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header className="border-bottom border-light">
              <h5 className="mb-0">Quick Actions</h5>
            </Card.Header>
            <Card.Body className="d-grid gap-2">
              {casesPerm.canCreate ? (
                <Button
                  as={Link}
                  to={Routes.CasesNew.path}
                  variant="primary"
                  className="d-flex align-items-center justify-content-center"
                >
                  <FontAwesomeIcon icon={faPlus} className="me-2" />
                  New Case
                </Button>
              ) : null}
              {evidencePerm.canCreate ? (
                <Button
                  as={Link}
                  to={Routes.EvidenceRegister.path}
                  variant="success"
                  className="d-flex align-items-center justify-content-center"
                >
                  <FontAwesomeIcon icon={faDatabase} className="me-2" />
                  Register Evidence
                </Button>
              ) : null}
              {analysisPerm.canCreate ? (
                <Button
                  as={Link}
                  to={Routes.PipelineRun.path}
                  variant="warning"
                  className="d-flex align-items-center justify-content-center"
                >
                  <FontAwesomeIcon icon={faPlayCircle} className="me-2" />
                  Run Pipeline
                </Button>
              ) : null}
              {reportsPerm.canRead ? (
                <Button
                  as={Link}
                  to={Routes.Reports.path}
                  variant="info"
                  className="d-flex align-items-center justify-content-center"
                >
                  <FontAwesomeIcon icon={faFileAlt} className="me-2" />
                  View Reports
                </Button>
              ) : null}
              {!casesPerm.canCreate &&
              !evidencePerm.canCreate &&
              !analysisPerm.canCreate &&
              !reportsPerm.canRead ? (
                <EmptyState
                  title="No actions available"
                  description="Your role does not include dashboard quick actions."
                />
              ) : null}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* SYSTEM HEALTH */}
      <Row>
        <Col xs={12}>
          <HealthBar
            checks={healthChecks}
            loading={healthLoading}
            error={healthError}
          />
        </Col>
      </Row>
    </Container>
  );
}

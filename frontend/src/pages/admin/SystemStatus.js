import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Card,
  Col,
  Container,
  ListGroup,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faExclamationTriangle,
  faTimes,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import SkeletonLoader from "components/common/SkeletonLoader";
import MetricGauge from "components/forensic/MetricGauge";
import usePolling from "hooks/usePolling";
import systemService from "services/system.service";
import { formatDate, formatDateRelative, formatPercentage } from "utils/formatters";

const READINESS_COLOURS = {
  ready: "success",
  degraded: "warning",
  unavailable: "danger",
  initializing: "secondary",
  shutting_down: "dark",
};

const SERVICE_LABELS = {
  database: "Database",
  ollama: "Ollama / LLM",
  vector_store: "Vector Store",
  filesystem: "Filesystem",
  audit_logger: "Audit Logger",
};

const PHASE_LABELS = {
  configuration: "Configuration",
  directories: "Directories",
  database: "Database",
  authentication: "Authentication",
  audit_logging: "Audit Logging",
  dataset_discovery: "Dataset Discovery",
  knowledge_base: "Knowledge Base",
  ioc_database: "IOC Database",
  threat_intelligence: "Threat Intelligence",
  ml_models: "ML Models",
  llm_service: "LLM Service",
  rag_pipeline: "RAG Pipeline",
  forensic_parsers: "Forensic Parsers",
  reporting: "Reporting",
  evaluation: "Evaluation",
  background_workers: "Background Workers",
};

function formatPhaseLabel(phase) {
  return PHASE_LABELS[phase] || String(phase || "").replace(/_/g, " ");
}

function phaseIcon(status) {
  const key = String(status || "").toLowerCase();
  if (key === "completed") {
    return { icon: faCheck, colour: "#198754", label: "Completed" };
  }
  if (key === "degraded" || key === "skipped") {
    return { icon: faExclamationTriangle, colour: "#ffc107", label: "Degraded" };
  }
  if (key === "failed") {
    return { icon: faTimes, colour: "#dc3545", label: "Failed" };
  }
  return { icon: faExclamationTriangle, colour: "#6c757d", label: status || "Unknown" };
}

function formatStorageGb(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${num.toFixed(2)} GB`;
}

function formatStorageMb(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${num.toFixed(1)} MB`;
}

function ServiceHealthCard({ name, health }) {
  const healthy = Boolean(health?.is_healthy);
  return (
    <Col xs={12} md={6} lg={4} className="mb-3">
      <Card className="border-0 shadow-sm h-100">
        <Card.Body>
          <div className="d-flex justify-content-between align-items-start mb-2">
            <Card.Title className="h6 mb-0">
              {SERVICE_LABELS[name] || name}
            </Card.Title>
            <Badge bg={healthy ? "success" : "danger"}>
              {healthy ? "Healthy" : "Unhealthy"}
            </Badge>
          </div>
          <div className="small text-muted">
            <div>
              Last checked:{" "}
              {health?.last_checked
                ? formatDateRelative(health.last_checked)
                : "—"}
            </div>
            <div>
              Response:{" "}
              {health?.response_time_ms != null
                ? `${Number(health.response_time_ms).toFixed(1)} ms`
                : "—"}
            </div>
            {health?.consecutive_failures > 0 ? (
              <div className="text-warning">
                Failures: {health.consecutive_failures}
              </div>
            ) : null}
          </div>
        </Card.Body>
      </Card>
    </Col>
  );
}

/**
 * Admin system status page: startup report, live service health, and resources.
 */
export default function SystemStatus() {
  const [startupLoading, setStartupLoading] = useState(true);
  const [startupError, setStartupError] = useState(null);
  const [startupReport, setStartupReport] = useState(null);

  const fetchMonitoring = useCallback(async () => {
    const [status, resources, alerts] = await Promise.all([
      systemService.getStatus(),
      systemService.getResources(),
      systemService.getAlerts(),
    ]);
    return { status, resources, alerts };
  }, []);

  const {
    data: monitoring,
    loading: monitoringLoading,
    error: monitoringError,
  } = usePolling(fetchMonitoring, 30000, true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStartupLoading(true);
      setStartupError(null);
      try {
        const report = await systemService.getStartupReport();
        if (!cancelled) setStartupReport(report);
      } catch (err) {
        if (!cancelled) setStartupError(err);
      } finally {
        if (!cancelled) setStartupLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const readiness = monitoring?.status?.system_readiness || startupReport?.system_status;
  const readinessVariant =
    READINESS_COLOURS[String(readiness || "").toLowerCase()] || "secondary";

  const degradedCapabilities = useMemo(() => {
    const fromReport = startupReport?.degraded_services || [];
    const fromPhases = (startupReport?.phases || []).flatMap(
      (phase) => phase.degraded_capabilities || []
    );
    return [...new Set([...fromReport, ...fromPhases])];
  }, [startupReport]);

  const serviceEntries = Object.entries(monitoring?.status?.services || {});

  return (
    <Container fluid className="px-4 py-4">
      <PageHeader
        title="System Status"
        subtitle="Bootstrap report, runtime health, and resource utilization"
      />

      {startupError ? <ApiErrorDisplay error={startupError} className="mb-3" /> : null}
      {monitoringError ? <ApiErrorDisplay error={monitoringError} className="mb-3" /> : null}

      <Card className="border-0 shadow-sm mb-4">
        <Card.Body>
          {startupLoading ? (
            <SkeletonLoader lines={4} />
          ) : (
            <>
              <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
                <Badge bg={readinessVariant} className="fs-6 px-3 py-2">
                  {String(readiness || "unknown").toUpperCase()}
                </Badge>
                {monitoring?.status?.degraded_mode ? (
                  <Badge bg="warning" text="dark">
                    Runtime degraded mode
                  </Badge>
                ) : null}
                {startupReport?.completed_at ? (
                  <span className="text-muted small">
                    Boot completed {formatDate(startupReport.completed_at)}
                    {startupReport.total_duration_ms != null
                      ? ` (${(startupReport.total_duration_ms / 1000).toFixed(1)}s)`
                      : ""}
                  </span>
                ) : null}
              </div>

              <Row>
                <Col lg={7}>
                  <h6 className="text-uppercase text-muted mb-3">Boot Phases</h6>
                  <ListGroup variant="flush" className="mb-3">
                    {(startupReport?.phases || []).map((phase) => {
                      const iconMeta = phaseIcon(phase.status);
                      const isDegraded =
                        phase.status === "degraded" ||
                        (phase.degraded_capabilities || []).length > 0;
                      return (
                        <ListGroup.Item
                          key={phase.phase}
                          className={`px-0 ${isDegraded ? "bg-warning bg-opacity-10" : ""}`}
                        >
                          <div className="d-flex align-items-start gap-2">
                            <FontAwesomeIcon
                              icon={iconMeta.icon}
                              style={{ color: iconMeta.colour, marginTop: 4 }}
                              aria-hidden="true"
                            />
                            <div className="flex-grow-1">
                              <div className="fw-semibold">
                                {formatPhaseLabel(phase.phase)}
                              </div>
                              <div className="small text-muted">{phase.message}</div>
                              {(phase.degraded_capabilities || []).length > 0 ? (
                                <div className="small text-warning mt-1">
                                  Degraded: {(phase.degraded_capabilities || []).join(", ")}
                                </div>
                              ) : null}
                            </div>
                            <div className="small text-muted text-end">
                              {Number(phase.duration_ms || 0).toFixed(0)} ms
                            </div>
                          </div>
                        </ListGroup.Item>
                      );
                    })}
                  </ListGroup>
                </Col>
                <Col lg={5}>
                  <h6 className="text-uppercase text-muted mb-3">Capabilities</h6>
                  {degradedCapabilities.length > 0 ? (
                    <Alert variant="warning" className="small">
                      <strong>Degraded:</strong> {degradedCapabilities.join(", ")}
                    </Alert>
                  ) : null}
                  <div className="d-flex flex-wrap gap-2">
                    {(startupReport?.available_capabilities || []).map((cap) => (
                      <Badge
                        key={cap}
                        bg={
                          degradedCapabilities.includes(cap) ? "warning" : "success"
                        }
                        text={degradedCapabilities.includes(cap) ? "dark" : undefined}
                      >
                        {cap.replace(/_/g, " ")}
                      </Badge>
                    ))}
                    {!startupReport?.available_capabilities?.length ? (
                      <span className="text-muted small">No capabilities reported</span>
                    ) : null}
                  </div>
                </Col>
              </Row>
            </>
          )}
        </Card.Body>
      </Card>

      <h5 className="mb-3">Service Health</h5>
      {monitoringLoading && !monitoring ? (
        <SkeletonLoader lines={3} />
      ) : (
        <Row className="mb-4">
          {serviceEntries.length ? (
            serviceEntries.map(([name, health]) => (
              <ServiceHealthCard key={name} name={name} health={health} />
            ))
          ) : (
            <Col>
              <span className="text-muted">No service health data yet.</span>
            </Col>
          )}
        </Row>
      )}

      <h5 className="mb-3">Resource Monitoring</h5>
      {monitoringLoading && !monitoring ? (
        <SkeletonLoader lines={2} />
      ) : (
        <>
          <Row className="mb-3">
            <Col xs={6} md={3} className="mb-3 text-center">
              <MetricGauge
                value={monitoring?.resources?.cpu_percent || 0}
                label="CPU"
                invert
              />
            </Col>
            <Col xs={6} md={3} className="mb-3 text-center">
              <MetricGauge
                value={monitoring?.resources?.memory_percent || 0}
                label="Memory"
                invert
              />
            </Col>
            <Col xs={6} md={3} className="mb-3 text-center">
              <MetricGauge
                value={monitoring?.resources?.disk_percent || 0}
                label="Disk"
                invert
              />
            </Col>
            <Col xs={6} md={3} className="mb-3 text-center">
              <div className="small text-muted text-uppercase fw-bold mb-2">
                Storage
              </div>
              <div>Evidence: {formatStorageGb(monitoring?.resources?.evidence_size_gb)}</div>
              <div>Knowledge: {formatStorageMb(monitoring?.resources?.knowledge_base_size_mb)}</div>
              <div>Database: {formatStorageMb(monitoring?.resources?.database_size_mb)}</div>
            </Col>
          </Row>

          {(monitoring?.alerts || []).length > 0 ? (
            <Alert variant="warning">
              <strong>Resource alerts</strong>
              <ul className="mb-0 mt-2">
                {(monitoring?.alerts || []).map((alert) => (
                  <li key={`${alert.resource}-${alert.message}`}>
                    {alert.message} ({formatPercentage(alert.current_value)} / threshold{" "}
                    {formatPercentage(alert.threshold)})
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}
        </>
      )}
    </Container>
  );
}

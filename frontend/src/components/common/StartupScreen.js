import React, { useEffect, useState } from "react";
import { Alert, ListGroup, Spinner } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faExclamationTriangle,
  faShieldAlt,
  faTimes,
} from "@fortawesome/free-solid-svg-icons";

import config from "config";
import systemService from "services/system.service";
import logo from "assets/img/favicon/android-chrome-192x192.png";

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

function phaseMeta(status) {
  const key = String(status || "").toLowerCase();
  if (key === "completed") {
    return { icon: faCheck, colour: "#198754", label: "Completed" };
  }
  if (key === "running") {
    return { icon: faShieldAlt, colour: "#0d6efd", label: "Running" };
  }
  if (key === "degraded" || key === "skipped") {
    return { icon: faExclamationTriangle, colour: "#ffc107", label: "Degraded" };
  }
  if (key === "failed") {
    return { icon: faTimes, colour: "#dc3545", label: "Failed" };
  }
  return { icon: faExclamationTriangle, colour: "#6c757d", label: "Pending" };
}

/**
 * Full-page startup, offline, or boot-failure screen.
 *
 * @param {{
 *   mode?: "initializing"|"unavailable"|"offline",
 *   startupReport?: object|null,
 *   errorDetail?: string,
 * }} props
 */
export default function StartupScreen({
  mode = "initializing",
  startupReport: externalReport = null,
  errorDetail = "",
}) {
  const [report, setReport] = useState(externalReport);

  useEffect(() => {
    setReport(externalReport);
  }, [externalReport]);

  useEffect(() => {
    if (mode !== "initializing") {
      return undefined;
    }

    let cancelled = false;

    async function loadReport() {
      try {
        const data = await systemService.getStartupReport();
        if (!cancelled) {
          setReport(data);
        }
      } catch {
        /* Startup report may not be available until boot completes */
      }
    }

    loadReport();
    const intervalId = window.setInterval(loadReport, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [mode]);

  const phases = report?.phases || [];
  const isFailure = mode === "unavailable" || mode === "offline";

  return (
    <div
      className="dfat-startup-screen bg-soft d-flex flex-column justify-content-center align-items-center min-vh-100 px-3"
      aria-live="polite"
      aria-busy={mode === "initializing"}
    >
      <div className="text-center mb-4" style={{ maxWidth: 520 }}>
        <img
          src={logo}
          alt={`${config.appName} logo`}
          width={96}
          height={96}
          className="mb-3"
        />
        <h1 className="h3 fw-bold text-primary mb-1">{config.appName}</h1>
        <p className="text-muted mb-0">
          Initializing Digital Forensics Automation Tool…
        </p>
      </div>

      {mode === "offline" ? (
        <Alert variant="danger" className="w-100" style={{ maxWidth: 640 }}>
          <Alert.Heading>Backend not running</Alert.Heading>
          <p className="mb-0">
            {errorDetail ||
              "Could not connect to the DFAT API. Start the backend server and refresh this page."}
          </p>
        </Alert>
      ) : null}

      {mode === "unavailable" ? (
        <Alert variant="danger" className="w-100" style={{ maxWidth: 640 }}>
          <Alert.Heading>System unavailable</Alert.Heading>
          <p>
            DFAT could not complete startup. Review the diagnostic details below
            and check server logs.
          </p>
          {(report?.critical_failures || []).length > 0 ? (
            <ul className="mb-0">
              {report.critical_failures.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </Alert>
      ) : null}

      {mode === "initializing" ? (
        <div className="w-100" style={{ maxWidth: 640 }}>
          <div className="d-flex align-items-center gap-2 mb-3 text-muted">
            <Spinner animation="border" size="sm" role="status">
              <span className="visually-hidden">Loading…</span>
            </Spinner>
            <span>Running bootstrap phases…</span>
          </div>
          <ListGroup variant="flush" className="bg-white shadow-sm rounded">
            {phases.length ? (
              phases.map((phase) => {
                const meta = phaseMeta(phase.status);
                return (
                  <ListGroup.Item
                    key={phase.phase}
                    className="d-flex align-items-start gap-2 py-3"
                  >
                    <FontAwesomeIcon
                      icon={meta.icon}
                      style={{ color: meta.colour, marginTop: 4 }}
                      aria-hidden="true"
                    />
                    <div className="flex-grow-1">
                      <div className="fw-semibold">
                        {formatPhaseLabel(phase.phase)}
                      </div>
                      <div className="small text-muted">{phase.message}</div>
                      {phase.error ? (
                        <div className="small text-danger mt-1">{phase.error}</div>
                      ) : null}
                    </div>
                    <div className="small text-muted text-end">
                      {meta.label}
                    </div>
                  </ListGroup.Item>
                );
              })
            ) : (
              <ListGroup.Item className="py-3 text-muted">
                Waiting for startup report from the backend…
              </ListGroup.Item>
            )}
          </ListGroup>
        </div>
      ) : null}

      {isFailure && phases.length > 0 ? (
        <div className="w-100 mt-4" style={{ maxWidth: 640 }}>
          <h2 className="h6 text-uppercase text-muted mb-2">Boot phases</h2>
          <ListGroup variant="flush" className="bg-white shadow-sm rounded">
            {phases.map((phase) => {
              const meta = phaseMeta(phase.status);
              return (
                <ListGroup.Item
                  key={phase.phase}
                  className="d-flex align-items-start gap-2 py-3"
                >
                  <FontAwesomeIcon
                    icon={meta.icon}
                    style={{ color: meta.colour, marginTop: 4 }}
                    aria-hidden="true"
                  />
                  <div className="flex-grow-1">
                    <div className="fw-semibold">
                      {formatPhaseLabel(phase.phase)}
                    </div>
                    <div className="small text-muted">{phase.message}</div>
                    {phase.error ? (
                      <div className="small text-danger mt-1">{phase.error}</div>
                    ) : null}
                  </div>
                </ListGroup.Item>
              );
            })}
          </ListGroup>
        </div>
      ) : null}
    </div>
  );
}

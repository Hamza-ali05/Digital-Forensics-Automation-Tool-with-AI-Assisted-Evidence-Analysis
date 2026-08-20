import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Button } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faExclamationTriangle, faTimes } from "@fortawesome/free-solid-svg-icons";
import { Link } from "react-router-dom";

import usePolling from "hooks/usePolling";
import systemService from "services/system.service";
import { Routes } from "routes";

const DISMISS_STORAGE_KEY = "dfat_degraded_banner_dismissed";

const SERVICE_LABELS = {
  database: "Database",
  ollama: "Ollama / LLM",
  vector_store: "Vector Store",
  filesystem: "Filesystem",
  audit_logger: "Audit Logger",
};

function formatServiceName(name) {
  return SERVICE_LABELS[name] || String(name || "").replace(/_/g, " ");
}

function buildDegradedList(status) {
  if (!status) return [];

  const unhealthy = Object.entries(status.services || {})
    .filter(([, health]) => health && health.is_healthy === false)
    .map(([name]) => formatServiceName(name));

  if (status.degraded_mode && !unhealthy.includes("Runtime recovery")) {
    unhealthy.push("Runtime recovery");
  }

  return unhealthy;
}

function degradedSignature(services) {
  return services.slice().sort().join("|");
}

function readDismissedSignature() {
  try {
    const raw = localStorage.getItem(DISMISS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.signature || null;
  } catch {
    return null;
  }
}

function writeDismissedSignature(signature) {
  localStorage.setItem(
    DISMISS_STORAGE_KEY,
    JSON.stringify({ signature, dismissedAt: new Date().toISOString() })
  );
}

function clearDismissedSignature() {
  localStorage.removeItem(DISMISS_STORAGE_KEY);
}

/**
 * Dismissible banner when the platform is in degraded readiness.
 */
export default function DegradedBanner() {
  const [dismissedSignature, setDismissedSignature] = useState(
    () => readDismissedSignature()
  );

  const fetchStatus = useCallback(() => systemService.getStatus(), []);

  const { data: status } = usePolling(fetchStatus, 30000, true);

  const readiness = String(status?.system_readiness || "").toLowerCase();
  const degradedServices = useMemo(() => buildDegradedList(status), [status]);
  const signature = useMemo(
    () => degradedSignature(degradedServices),
    [degradedServices]
  );

  useEffect(() => {
    if (readiness === "ready") {
      clearDismissedSignature();
      setDismissedSignature(null);
    }
  }, [readiness]);

  if (readiness !== "degraded" || !degradedServices.length) {
    return null;
  }

  if (dismissedSignature && dismissedSignature === signature) {
    return null;
  }

  const handleDismiss = () => {
    writeDismissedSignature(signature);
    setDismissedSignature(signature);
  };

  return (
    <Alert
      variant="warning"
      className="rounded-0 border-0 border-bottom mb-0 d-flex align-items-start gap-2"
      role="status"
    >
      <FontAwesomeIcon
        icon={faExclamationTriangle}
        className="mt-1"
        aria-hidden="true"
      />
      <div className="flex-grow-1">
        <strong>Degraded mode.</strong> Some services are running in degraded
        mode: {degradedServices.join(", ")}.{" "}
        <Link to={Routes.AdminSystem.path}>Click for details</Link>.
      </div>
      <Button
        variant="link"
        className="text-dark p-0 ms-2"
        aria-label="Dismiss degraded mode banner"
        onClick={handleDismiss}
      >
        <FontAwesomeIcon icon={faTimes} aria-hidden="true" />
      </Button>
    </Alert>
  );
}

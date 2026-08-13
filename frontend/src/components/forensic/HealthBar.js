import React from "react";
import { Card } from "@themesberg/react-bootstrap";

function Dot({ state }) {
  // state: "ok" | "bad" | "unknown"
  const colour =
    state === "ok" ? "#198754" : state === "bad" ? "#dc3545" : "#adb5bd";
  return (
    <span
      aria-hidden="true"
      className="d-inline-block rounded-circle me-2"
      style={{
        width: 10,
        height: 10,
        backgroundColor: colour,
        boxShadow: `0 0 0 3px ${colour}22`,
      }}
    />
  );
}

function Indicator({ label, state, detail }) {
  const statusLabel =
    state === "ok" ? "Healthy" : state === "bad" ? "Unavailable" : "Unknown";
  return (
    <div className="d-flex align-items-center me-4 mb-2 mb-md-0">
      <Dot state={state} />
      <div>
        <div className="fw-bold small text-uppercase text-muted">{label}</div>
        <div className="small">
          {statusLabel}
          {detail ? <span className="text-muted"> — {detail}</span> : null}
        </div>
      </div>
    </div>
  );
}

/**
 * Horizontal system-health indicators.
 *
 * @param {{
 *   checks?: { database?: boolean, llm?: boolean|null, storage?: boolean },
 *   loading?: boolean,
 *   error?: boolean,
 * }} props
 */
export default function HealthBar({ checks = {}, loading = false, error = false }) {
  const backendState = error
    ? "bad"
    : loading
      ? "unknown"
      : checks.storage === true
        ? "ok"
        : checks.storage === false
          ? "bad"
          : "unknown";

  // LLM is optional — false/unavailable renders grey rather than hard red.
  let aiState = "unknown";
  if (!loading && !error) {
    if (checks.llm === true) aiState = "ok";
    else if (checks.llm === false) aiState = "unknown";
  } else if (error) {
    aiState = "unknown";
  }

  const dbState = error
    ? "bad"
    : loading
      ? "unknown"
      : checks.database === true
        ? "ok"
        : checks.database === false
          ? "bad"
          : "unknown";

  return (
    <Card border="light" className="shadow-sm">
      <Card.Body className="d-flex flex-wrap align-items-center justify-content-between py-3">
        <div className="fw-bold me-3 mb-2 mb-md-0">System Health</div>
        <div className="d-flex flex-wrap align-items-center flex-grow-1">
          <Indicator
            label="Backend"
            state={backendState}
            detail={loading ? "Checking…" : null}
          />
          <Indicator label="AI Engine" state={aiState} />
          <Indicator label="Database" state={dbState} />
        </div>
      </Card.Body>
    </Card>
  );
}

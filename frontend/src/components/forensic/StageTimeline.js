import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faCircle,
  faClock,
  faTimes,
} from "@fortawesome/free-solid-svg-icons";
import { Spinner } from "@themesberg/react-bootstrap";

import { PIPELINE_STAGE } from "utils/constants";
import { formatDuration } from "utils/formatters";

const DEFAULT_STAGES = [
  PIPELINE_STAGE.ACQUISITION,
  PIPELINE_STAGE.PARSING,
  PIPELINE_STAGE.AI_TRIAGE,
  PIPELINE_STAGE.REPORTING,
  PIPELINE_STAGE.EVALUATION,
];

function stageLabel(stage) {
  return String(stage || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function normaliseStages(stages) {
  if (Array.isArray(stages) && stages.length) {
    return stages.map((item) => {
      if (typeof item === "string") {
        return { stage: item, status: "pending" };
      }
      return {
        stage: item.stage || item.name || item.key,
        status: String(item.status || "pending").toLowerCase(),
        duration_seconds: item.duration_seconds,
        artefact_count:
          item.artefact_count ??
          item.output_summary?.artefact_count ??
          item.artefacts_found,
        errors: item.errors,
      };
    });
  }

  if (stages && typeof stages === "object") {
    return DEFAULT_STAGES.map((key) => {
      const item = stages[key] || {};
      return {
        stage: key,
        status: String(item.status || "pending").toLowerCase(),
        duration_seconds: item.duration_seconds,
        artefact_count:
          item.artefact_count ??
          item.output_summary?.artefact_count ??
          null,
        errors: item.errors,
      };
    });
  }

  return DEFAULT_STAGES.map((key) => ({
    stage: key,
    status: "pending",
  }));
}

/**
 * Horizontal stepper for pipeline stage execution.
 *
 * @param {{
 *   stages?: Array|Object,
 *   currentStage?: string,
 *   className?: string,
 * }} props
 */
export default function StageTimeline({
  stages,
  currentStage,
  className = "",
}) {
  const items = normaliseStages(stages);
  const current = String(currentStage || "").toLowerCase();

  return (
    <div className={`dfat-stage-timeline ${className}`.trim()}>
      <div className="d-flex align-items-start justify-content-between flex-wrap">
        {items.map((item, index) => {
          const status = String(item.status || "pending").toLowerCase();
          const isCurrent =
            status === "running" ||
            (current && current === String(item.stage).toLowerCase() && status !== "completed" && status !== "failed" && status !== "skipped");
          const completed = status === "completed" || status === "skipped";
          const failed = status === "failed";
          const running = status === "running" || isCurrent;

          let circleStyle = {
            width: 36,
            height: 36,
            borderRadius: "50%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            border: "2px solid #adb5bd",
            backgroundColor: "#fff",
            color: "#6c757d",
          };

          if (completed) {
            circleStyle = {
              ...circleStyle,
              borderColor: "#198754",
              backgroundColor: "#198754",
              color: "#fff",
            };
          } else if (failed) {
            circleStyle = {
              ...circleStyle,
              borderColor: "#dc3545",
              backgroundColor: "#dc3545",
              color: "#fff",
            };
          } else if (running) {
            circleStyle = {
              ...circleStyle,
              borderColor: "#0d6efd",
              backgroundColor: "#0d6efd",
              color: "#fff",
              boxShadow: "0 0 0 4px rgba(13,110,253,0.2)",
            };
          }

          const artefacts =
            item.stage === PIPELINE_STAGE.PARSING &&
            item.artefact_count != null
              ? Number(item.artefact_count)
              : null;

          return (
            <React.Fragment key={item.stage || index}>
              <div className="text-center px-1 mb-2" style={{ minWidth: 88 }}>
                <div className="mx-auto mb-1" style={circleStyle}>
                  {completed ? (
                    <FontAwesomeIcon icon={faCheck} />
                  ) : failed ? (
                    <FontAwesomeIcon icon={faTimes} />
                  ) : running ? (
                    <Spinner
                      animation="border"
                      size="sm"
                      style={{ width: 16, height: 16, borderWidth: 2 }}
                    />
                  ) : status === "pending" ? (
                    <FontAwesomeIcon icon={faClock} />
                  ) : (
                    <FontAwesomeIcon icon={faCircle} style={{ fontSize: 8 }} />
                  )}
                </div>
                <div
                  className={`small ${
                    running
                      ? "fw-bold text-primary"
                      : completed
                        ? "text-success"
                        : failed
                          ? "text-danger"
                          : "text-muted"
                  }`}
                >
                  {stageLabel(item.stage)}
                </div>
                <div className="small text-muted">
                  {item.duration_seconds != null
                    ? formatDuration(item.duration_seconds)
                    : running
                      ? "…"
                      : "—"}
                </div>
                {artefacts != null ? (
                  <div className="small text-muted">{artefacts} artefacts</div>
                ) : null}
              </div>
              {index < items.length - 1 ? (
                <div
                  className="flex-grow-1 mb-4 d-none d-md-block align-self-center"
                  style={{
                    height: 3,
                    minWidth: 12,
                    marginTop: 16,
                    backgroundColor:
                      completed || (running && index < items.length - 1)
                        ? completed
                          ? "#198754"
                          : "#0d6efd"
                        : "#dee2e6",
                    borderRadius: 2,
                  }}
                  aria-hidden="true"
                />
              ) : null}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

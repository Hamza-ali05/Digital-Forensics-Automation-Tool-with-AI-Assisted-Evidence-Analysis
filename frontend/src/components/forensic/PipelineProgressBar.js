import React from "react";
import { ProgressBar } from "@themesberg/react-bootstrap";

import { formatDuration } from "utils/formatters";

function stageLabel(stage) {
  if (!stage) return null;
  return String(stage)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function progressVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "completed" || s === "succeeded") return "success";
  if (s === "failed" || s === "timed_out") return "danger";
  if (s === "cancelled" || s === "canceled") return "secondary";
  return "primary";
}

function isActiveStatus(status) {
  const s = String(status || "").toLowerCase();
  return (
    s === "running" ||
    s === "queued" ||
    s === "initialising" ||
    s === "initializing" ||
    s === "stage_complete" ||
    s === "in_progress"
  );
}

/**
 * Compact pipeline progress bar for job lists and detail views.
 *
 * @param {{
 *   progress?: {
 *     status?: string,
 *     percent_complete?: number,
 *     stages_completed?: number,
 *     stages_total?: number,
 *     current_stage?: string,
 *     current_parser?: string,
 *     elapsed_seconds?: number,
 *     estimated_remaining_seconds?: number|null,
 *     artefacts_found_so_far?: number,
 *   },
 *   compact?: boolean,
 *   className?: string,
 * }} props
 */
export default function PipelineProgressBar({
  progress = {},
  compact = false,
  className = "",
}) {
  const status = progress.status;
  const stagesCompleted = Number(progress.stages_completed) || 0;
  const stagesTotal = Number(progress.stages_total) || 5;
  let percent = Number(progress.percent_complete);
  if (!Number.isFinite(percent)) {
    percent =
      stagesTotal > 0
        ? Math.round((stagesCompleted / stagesTotal) * 1000) / 10
        : 0;
  }
  percent = Math.max(0, Math.min(100, percent));

  const variant = progressVariant(status);
  const animated = isActiveStatus(status);
  const stage = stageLabel(progress.current_stage);
  const parser = progress.current_parser;

  return (
    <div className={`dfat-pipeline-progress ${className}`.trim()}>
      <div className="d-flex justify-content-between align-items-center mb-1 small">
        <span className="text-muted text-truncate me-2">
          {stage || "—"}
          {parser ? ` · ${parser}` : ""}
        </span>
        <span className="fw-bold text-nowrap">{percent}%</span>
      </div>
      <ProgressBar
        now={percent}
        variant={variant}
        animated={animated}
        striped={animated}
        style={{ height: compact ? 8 : 12 }}
      />
      {!compact ? (
        <div className="d-flex flex-wrap justify-content-between small text-muted mt-1 gap-2">
          <span>
            Stage {stagesCompleted}/{stagesTotal}
          </span>
          <span>
            Elapsed {formatDuration(progress.elapsed_seconds)}
            {progress.estimated_remaining_seconds != null ? (
              <>
                {" "}
                · ETA {formatDuration(progress.estimated_remaining_seconds)}
              </>
            ) : null}
          </span>
        </div>
      ) : null}
    </div>
  );
}

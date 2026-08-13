import React from "react";
import { Badge } from "@themesberg/react-bootstrap";

import {
  CASE_STATUS_COLOURS,
  EVIDENCE_STATUS_COLOURS,
  PIPELINE_STATUS_COLOURS,
  SUSPICION_COLOURS,
} from "utils/constants";

const COLOUR_MAPS = {
  case: CASE_STATUS_COLOURS,
  evidence: EVIDENCE_STATUS_COLOURS,
  pipeline: PIPELINE_STATUS_COLOURS,
  suspicion: SUSPICION_COLOURS,
};

function formatLabel(status) {
  if (!status) return "unknown";
  return String(status)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Colour-coded status badge for case / evidence / pipeline / suspicion values.
 *
 * @param {{ status: string, type?: "case"|"evidence"|"pipeline"|"suspicion", className?: string }} props
 */
export default function StatusBadge({
  status,
  type = "case",
  className = "",
}) {
  const key = String(status || "").toLowerCase();
  const map = COLOUR_MAPS[type] || CASE_STATUS_COLOURS;
  const colour = map[key] || "#6c757d";

  return (
    <Badge
      className={`status-badge ${className}`.trim()}
      style={{
        backgroundColor: colour,
        color: "#fff",
      }}
    >
      {formatLabel(status)}
    </Badge>
  );
}

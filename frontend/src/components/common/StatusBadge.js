import React from "react";
import { Badge } from "@themesberg/react-bootstrap";

import {
  CASE_STATUS_COLOURS,
  DATASET_STATUS_COLOURS,
  EVIDENCE_STATUS_COLOURS,
  INDEXING_STATUS_COLOURS,
  ML_EXPERIMENT_STATUS_COLOURS,
  PIPELINE_STATUS_COLOURS,
  SUSPICION_COLOURS,
} from "utils/constants";

const COLOUR_MAPS = {
  case: CASE_STATUS_COLOURS,
  evidence: EVIDENCE_STATUS_COLOURS,
  pipeline: PIPELINE_STATUS_COLOURS,
  suspicion: SUSPICION_COLOURS,
  dataset: DATASET_STATUS_COLOURS,
  indexing: INDEXING_STATUS_COLOURS,
  ml_experiment: ML_EXPERIMENT_STATUS_COLOURS,
};

function hexToRgb(hex) {
  const raw = String(hex || "").replace("#", "");
  const normalized =
    raw.length === 3
      ? raw
          .split("")
          .map((ch) => ch + ch)
          .join("")
      : raw;
  const n = parseInt(normalized, 16);
  if (Number.isNaN(n)) return { r: 108, g: 117, b: 125 };
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function relativeLuminance({ r, g, b }) {
  const lin = (channel) => {
    const s = channel / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrastText(background) {
  const bgLum = relativeLuminance(hexToRgb(background));
  const whiteContrast = 1.05 / (bgLum + 0.05);
  const darkLum = relativeLuminance({ r: 38, g: 43, b: 64 });
  const darkContrast = (bgLum + 0.05) / (darkLum + 0.05);
  return whiteContrast >= 4.5 || whiteContrast >= darkContrast ? "#fff" : "#262B40";
}

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
        color: contrastText(colour),
      }}
    >
      {formatLabel(status)}
    </Badge>
  );
}

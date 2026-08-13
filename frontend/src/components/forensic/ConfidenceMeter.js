import React from "react";
import { ProgressBar } from "@themesberg/react-bootstrap";

function clampScore(score) {
  const num = Number(score);
  if (!Number.isFinite(num)) return 0;
  if (num < 0) return 0;
  if (num > 1) return Math.min(1, num > 100 ? num / 100 : num);
  return num;
}

function barVariant(score) {
  if (score < 0.3) return "danger";
  if (score < 0.6) return "warning";
  return "success";
}

/**
 * Visual confidence indicator for AI outputs (0–1).
 *
 * @param {{ score?: number, className?: string, showLabel?: boolean }} props
 */
export default function ConfidenceMeter({
  score = 0,
  className = "",
  showLabel = true,
}) {
  const value = clampScore(score);
  const percent = Math.round(value * 100);
  const variant = barVariant(value);

  return (
    <div className={className}>
      {showLabel ? (
        <div className="d-flex justify-content-between small mb-1">
          <span className="text-muted">Confidence</span>
          <span className="fw-bold">{percent}%</span>
        </div>
      ) : (
        <span className="visually-hidden">{percent}% confidence</span>
      )}
      <ProgressBar now={percent} variant={variant} />
    </div>
  );
}

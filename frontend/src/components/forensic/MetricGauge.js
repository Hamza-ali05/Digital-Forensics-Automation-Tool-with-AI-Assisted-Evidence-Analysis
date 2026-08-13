import React from "react";

const DEFAULT_THRESHOLDS = { warning: 50, success: 80 };

/**
 * Convert a 0–1 or 0–100 score into a 0–100 percentage.
 */
export function scoreToPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  if (num < 0) return 0;
  if (num <= 1) return Math.round(num * 1000) / 10;
  return Math.min(100, Math.round(num * 10) / 10);
}

/**
 * Colour for a 0–100 gauge value.
 *
 * @param {number} percent
 * @param {{ warning?: number, success?: number }} thresholds
 * @param {boolean} invert When true, higher values are worse.
 */
export function gaugeColour(percent, thresholds = DEFAULT_THRESHOLDS, invert = false) {
  const warning = thresholds.warning ?? 50;
  const success = thresholds.success ?? 80;
  const value = invert ? 100 - percent : percent;
  if (value >= success) return "#198754";
  if (value >= warning) return "#ffc107";
  return "#dc3545";
}

/**
 * Circular percentage gauge with threshold colour coding.
 *
 * @param {{
 *   value?: number,
 *   label?: string,
 *   size?: number,
 *   thresholds?: { warning?: number, success?: number },
 *   invert?: boolean,
 *   display?: string,
 *   className?: string,
 * }} props
 */
export default function MetricGauge({
  value = 0,
  label = "",
  size = 120,
  thresholds = DEFAULT_THRESHOLDS,
  invert = false,
  display,
  className = "",
}) {
  const numeric = Number(value);
  const percent = Math.max(
    0,
    Math.min(100, Number.isFinite(numeric) ? numeric : 0)
  );
  const colour = gaugeColour(percent, thresholds, invert);
  const stroke = Math.max(8, Math.round(size * 0.1));
  const radius = size / 2 - stroke;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - percent / 100);
  const centre = display != null ? display : `${Math.round(percent)}%`;

  return (
    <div
      className={`d-flex flex-column align-items-center ${className}`.trim()}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={
          label
            ? `${label}: ${centre}`
            : `Metric ${centre}`
        }
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e9ecef"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colour}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          fill={colour}
          fontSize={size * 0.18}
          fontWeight="700"
        >
          {centre}
        </text>
      </svg>
      {label ? (
        <div className="small text-muted text-uppercase fw-bold mt-2 text-center">
          {label}
        </div>
      ) : null}
    </div>
  );
}

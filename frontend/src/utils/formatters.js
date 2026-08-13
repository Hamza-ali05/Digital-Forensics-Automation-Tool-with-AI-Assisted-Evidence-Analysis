import { SUSPICION_COLOURS } from "./constants";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function toDate(value) {
  if (value == null || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/**
 * Format an ISO timestamp as ``25 Jun 2026, 14:30``.
 */
export function formatDate(isoString) {
  const date = toDate(isoString);
  if (!date) return "—";
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${pad2(
    date.getHours()
  )}:${pad2(date.getMinutes())}`;
}

/**
 * Relative time such as ``2 hours ago`` / ``3 days ago``.
 */
export function formatDateRelative(isoString, now = Date.now()) {
  const date = toDate(isoString);
  if (!date) return "—";

  const nowMs = typeof now === "number" ? now : Date.now();
  const diffMs = Math.max(0, nowMs - date.getTime());
  const seconds = Math.floor(diffMs / 1000);

  if (seconds < 45) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return days === 1 ? "1 day ago" : `${days} days ago`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return months === 1 ? "1 month ago" : `${months} months ago`;
  }
  const years = Math.floor(days / 365);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}

/**
 * Human-readable byte size (``1.0 GB``, ``256 KB``).
 */
export function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "0 B";
  if (value === 0) return "0 B";

  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  const exponent = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1
  );
  const scaled = value / 1024 ** exponent;
  const decimals = exponent === 0 ? 0 : 1;
  return `${scaled.toFixed(decimals)} ${units[exponent]}`;
}

/**
 * Duration from seconds: ``2m 34s``, ``1h 15m``.
 */
export function formatDuration(seconds) {
  let remaining = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(remaining / 3600);
  remaining %= 3600;
  const minutes = Math.floor(remaining / 60);
  const secs = remaining % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

/**
 * Truncate a hash/digest with ellipsis.
 */
export function formatHash(hash, length = 8) {
  if (!hash) return "—";
  const text = String(hash);
  if (text.length <= length) return text;
  return `${text.slice(0, length)}...`;
}

/**
 * Percentage string with configurable decimals.
 */
export function formatPercentage(value, decimals = 1) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${num.toFixed(decimals)}%`;
}

/**
 * Artefact ID display — first 8 characters.
 */
export function formatArtefactId(uuid) {
  if (!uuid) return "—";
  return String(uuid).slice(0, 8);
}

/**
 * Case ID display — ``CASE-{first 6 chars}``.
 */
export function formatCaseId(uuid) {
  if (!uuid) return "—";
  return `CASE-${String(uuid).slice(0, 6)}`;
}

/**
 * Suspicion level as title case with associated colour.
 * @returns {{ label: string, colour: string }}
 */
export function formatSuspicionLevel(level) {
  const key = String(level || "").toLowerCase();
  const label = key
    ? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "Unknown";
  const colour = SUSPICION_COLOURS[key] || "#6c757d";
  return { label, colour };
}

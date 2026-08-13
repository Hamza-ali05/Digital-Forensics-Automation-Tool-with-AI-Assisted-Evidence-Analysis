import { ARTEFACT_CATEGORY } from "utils/constants";

const TIMESTAMP_FIELDS = new Set([
  "timestamp",
  "create_time",
  "created_time",
  "created",
  "exit_time",
  "modified_time",
  "accessed_time",
  "changed_time",
  "last_modified",
  "last_write_time",
  "last_visit_time",
]);

const ZOOM_MS = {
  "1h": 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  all: null,
};

export const TIMELINE_ZOOM_OPTIONS = [
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "all", label: "All" },
];

function parseTimestamp(value) {
  if (value == null || value === "") return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === "number") {
    const ms = value < 1e12 ? value * 1000 : value;
    const date = new Date(ms);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isTimestampField(field) {
  if (TIMESTAMP_FIELDS.has(field)) return true;
  return field.endsWith("_time") || field.endsWith("_timestamp");
}

function primaryLabel(category, raw) {
  const data = raw || {};
  if (category === ARTEFACT_CATEGORY.RUNNING_PROCESS) {
    const name = data.name || data.process_name;
    const pid = data.pid;
    if (name && pid != null) return `${name} (pid=${pid})`;
    return String(name || pid || "");
  }
  if (category === ARTEFACT_CATEGORY.NETWORK_CONNECTION) {
    const remote = data.remote_address;
    const port = data.remote_port;
    if (remote != null) {
      return port != null ? `${remote}:${port}` : String(remote);
    }
  }
  if (category === ARTEFACT_CATEGORY.FILESYSTEM_METADATA) {
    return data.path || data.filename || "";
  }
  if (category === ARTEFACT_CATEGORY.REGISTRY_KEY) {
    return data.key_path || data.value_name || "";
  }
  if (category === ARTEFACT_CATEGORY.BROWSER_HISTORY) {
    return data.url || data.title || "";
  }
  if (category === ARTEFACT_CATEGORY.EVENT_LOG) {
    return data.event_id != null ? `Event ${data.event_id}` : data.source || "";
  }
  if (category === ARTEFACT_CATEGORY.INJECTED_CODE) {
    const name = data.process_name;
    const start = data.vad_start;
    if (name && start) return `${name} @ ${start}`;
    return String(name || start || "");
  }
  return "";
}

function describe(artefact, field, timestamp) {
  const category = artefact.category || "unknown";
  const detail = primaryLabel(category, artefact.raw_data);
  const stamp = timestamp.toISOString();
  if (detail) return `${category}: ${detail} (${field}=${stamp})`;
  return `${category}: ${field}=${stamp}`;
}

/**
 * Build chronological timeline entries from ranked artefacts (mirrors backend).
 */
export function buildTimelineEntries(artefacts = []) {
  const entries = [];
  (artefacts || []).forEach((artefact) => {
    const raw =
      artefact?.raw_data && typeof artefact.raw_data === "object"
        ? artefact.raw_data
        : {};
    Object.entries(raw).forEach(([field, value]) => {
      if (!isTimestampField(field)) return;
      const timestamp = parseTimestamp(value);
      if (!timestamp) return;
      entries.push({
        id: `${artefact.artefact_id}:${field}:${timestamp.getTime()}`,
        timestamp,
        timestampMs: timestamp.getTime(),
        artefact_id: artefact.artefact_id,
        category: artefact.category,
        suspicion_level: artefact.suspicion_level,
        relevance_score: artefact.relevance_score,
        description: describe(artefact, field, timestamp),
        source_field: field,
        artefact,
      });
    });
  });

  entries.sort((a, b) => {
    if (a.timestampMs !== b.timestampMs) return a.timestampMs - b.timestampMs;
    return String(a.artefact_id).localeCompare(String(b.artefact_id));
  });
  return entries;
}

/**
 * Restrict entries to the zoom window relative to the latest event.
 */
export function applyTimelineZoom(entries, zoomKey = "all") {
  if (!entries.length) return [];
  const windowMs = ZOOM_MS[zoomKey];
  if (windowMs == null) return entries;
  const latest = entries[entries.length - 1].timestampMs;
  const cutoff = latest - windowMs;
  return entries.filter((entry) => entry.timestampMs >= cutoff);
}

/**
 * Group sorted entries into fixed-width hour windows (default 1h).
 */
export function groupTimelineWindows(entries, windowSeconds = 3600) {
  if (!entries.length) return [];
  const widthMs = Math.max(1, windowSeconds) * 1000;
  const windows = [];
  let currentStart = entries[0].timestampMs;
  let currentEnd = currentStart + widthMs;
  let bucket = [];

  entries.forEach((entry) => {
    while (entry.timestampMs >= currentEnd) {
      if (bucket.length) {
        windows.push({
          window_start: new Date(currentStart),
          window_end: new Date(currentEnd),
          entries: bucket,
        });
        bucket = [];
      }
      currentStart = currentEnd;
      currentEnd = currentStart + widthMs;
    }
    bucket.push(entry);
  });

  if (bucket.length) {
    windows.push({
      window_start: new Date(currentStart),
      window_end: new Date(currentEnd),
      entries: bucket,
    });
  }
  return windows;
}

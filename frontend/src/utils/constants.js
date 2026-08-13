/**
 * Frontend enum mirrors matching DFAT backend enums exactly.
 * Sources: dfat.core.enums, dfat.case_management.enums, dfat.auth.rbac
 */

export const CASE_STATUS = Object.freeze({
  CREATED: "created",
  OPEN: "open",
  ACTIVE: "active",
  UNDER_REVIEW: "under_review",
  CLOSED: "closed",
  ARCHIVED: "archived",
});

export const EVIDENCE_STATUS = Object.freeze({
  REGISTERED: "registered",
  VALIDATING: "validating",
  VALIDATED: "validated",
  PROCESSING: "processing",
  PROCESSED: "processed",
  QUARANTINED: "quarantined",
  ARCHIVED: "archived",
});

export const EVIDENCE_TYPE = Object.freeze({
  DISK_IMAGE: "disk_image",
  MEMORY_DUMP: "memory_dump",
});

export const ARTEFACT_CATEGORY = Object.freeze({
  FILESYSTEM_METADATA: "filesystem_metadata",
  REGISTRY_KEY: "registry_key",
  BROWSER_HISTORY: "browser_history",
  EVENT_LOG: "event_log",
  RUNNING_PROCESS: "running_process",
  NETWORK_CONNECTION: "network_connection",
  INJECTED_CODE: "injected_code",
});

export const SUSPICION_LEVEL = Object.freeze({
  CRITICAL: "critical",
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
  INFORMATIONAL: "informational",
});

export const PIPELINE_STAGE = Object.freeze({
  ACQUISITION: "acquisition",
  PARSING: "parsing",
  AI_TRIAGE: "ai_triage",
  REPORTING: "reporting",
  EVALUATION: "evaluation",
});

export const USER_ROLES = Object.freeze({
  ADMIN: "admin",
  INVESTIGATOR: "investigator",
  ANALYST: "analyst",
  VIEWER: "viewer",
});

export const SUSPICION_COLOURS = Object.freeze({
  critical: "#dc3545",
  high: "#fd7e14",
  medium: "#ffc107",
  low: "#0d6efd",
  informational: "#6c757d",
});

export const CASE_STATUS_COLOURS = Object.freeze({
  created: "#6c757d",
  open: "#0d6efd",
  active: "#198754",
  under_review: "#ffc107",
  closed: "#212529",
  archived: "#adb5bd",
});

export const EVIDENCE_STATUS_COLOURS = Object.freeze({
  registered: "#6c757d",
  validating: "#0dcaf0",
  validated: "#0d6efd",
  processing: "#fd7e14",
  processed: "#198754",
  quarantined: "#dc3545",
  archived: "#adb5bd",
});

export const JOB_STATUS = Object.freeze({
  QUEUED: "queued",
  INITIALISING: "initialising",
  RUNNING: "running",
  STAGE_COMPLETE: "stage_complete",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
  TIMED_OUT: "timed_out",
});

export const PIPELINE_MODE = Object.freeze({
  FULL: "full",
  PARSE_ONLY: "parse-only",
  TRIAGE_ONLY: "triage-only",
});

export const PIPELINE_STATUS_COLOURS = Object.freeze({
  queued: "#6c757d",
  pending: "#6c757d",
  initialising: "#0dcaf0",
  initializing: "#0dcaf0",
  running: "#0d6efd",
  in_progress: "#0d6efd",
  stage_complete: "#0d6efd",
  completed: "#198754",
  succeeded: "#198754",
  failed: "#dc3545",
  cancelled: "#adb5bd",
  canceled: "#adb5bd",
  timed_out: "#dc3545",
});

import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";

/**
 * Prefer persisted report IDs; fall back to job pointers that still exist.
 */
async function collectReportIds(maxReports) {
  const seen = new Set();
  const reportIds = [];

  const push = (id) => {
    const key = String(id || "");
    if (!key || seen.has(key)) return;
    seen.add(key);
    reportIds.push(key);
  };

  try {
    const reports = await reportsService.list();
    (reports || []).forEach((report) => push(report.report_id || report.id));
    return reportIds.slice(0, maxReports);
  } catch {
    // Fall through to pipeline jobs when the reports list API is unavailable.
  }

  try {
    const jobs = await pipelineService.listJobs();
    (jobs || []).forEach((job) => push(job?.report_id));
  } catch {
    // Ignore — return whatever we collected.
  }

  return reportIds.slice(0, maxReports);
}

/**
 * Aggregate forensic audit entries from completed pipeline reports.
 * There is no global audit-list endpoint — trails are per report/evidence.
 */
export async function listAggregated(options = {}) {
  const { maxReports = 40 } = options;
  const limited = await collectReportIds(maxReports);
  const batches = await Promise.all(
    limited.map(async (reportId) => {
      try {
        const trail = await reportsService.getAuditTrail(reportId);
        const entries = Array.isArray(trail?.entries)
          ? trail.entries
          : Array.isArray(trail)
            ? trail
            : [];
        return entries.map((entry, index) =>
          normaliseEntry(entry, reportId, index)
        );
      } catch (err) {
        // Skip deleted/orphan report pointers without failing the page.
        if (err?.response?.status === 404) return [];
        return [];
      }
    })
  );

  const flat = batches.flat();
  // Audit trails are evidence-scoped; multiple reports for the same evidence
  // return overlapping entries. Prefer the first occurrence of each entry_number.
  const deduped = [];
  const seenEntries = new Set();
  for (const entry of flat) {
    const key =
      entry.entry_number != null
        ? `n:${entry.entry_number}`
        : `f:${entry.report_id}:${entry.timestamp}:${entry.action}`;
    if (seenEntries.has(key)) continue;
    seenEntries.add(key);
    deduped.push(entry);
  }
  deduped.sort((a, b) => {
    const ta = new Date(a.timestamp || 0).getTime();
    const tb = new Date(b.timestamp || 0).getTime();
    return tb - ta;
  });
  return deduped;
}

function normaliseEntry(entry, reportId, index) {
  const details = entry?.details || {};
  const userId =
    details.user_id ||
    details.performed_by_user_id ||
    details.actor_user_id ||
    details.username ||
    entry.user_id ||
    "";
  // Include index + timestamp so duplicate entry_number values stay unique.
  return {
    id: `${reportId}-${entry.entry_number ?? "x"}-${index}-${entry.timestamp || ""}`,
    entry_number: entry.entry_number,
    timestamp: entry.timestamp,
    stage: entry.stage,
    action: entry.action,
    evidence_id: entry.evidence_id,
    user_id: userId,
    report_id: reportId,
    hash_before: entry.hash_before,
    hash_after: entry.hash_after,
    details,
  };
}

/**
 * Optional direct trail for one report (admin drill-down).
 */
export async function getReportTrail(reportId) {
  const trail = await reportsService.getAuditTrail(reportId);
  const entries = Array.isArray(trail?.entries)
    ? trail.entries
    : Array.isArray(trail)
      ? trail
      : [];
  return entries.map((entry, index) => normaliseEntry(entry, reportId, index));
}

const auditService = {
  listAggregated,
  getReportTrail,
};

export default auditService;

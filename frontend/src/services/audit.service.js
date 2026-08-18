import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";

/**
 * Aggregate forensic audit entries from completed pipeline reports.
 * There is no global audit-list endpoint — trails are per report/evidence.
 */
export async function listAggregated(options = {}) {
  const { maxReports = 40 } = options;
  const jobs = await pipelineService.listJobs();
  const reportIds = [];
  const seen = new Set();
  (jobs || []).forEach((job) => {
    const id = job?.report_id;
    if (!id || seen.has(id)) return;
    seen.add(id);
    reportIds.push(id);
  });

  const limited = reportIds.slice(0, maxReports);
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
      } catch {
        return [];
      }
    })
  );

  const flat = batches.flat();
  flat.sort((a, b) => {
    const ta = new Date(a.timestamp || 0).getTime();
    const tb = new Date(b.timestamp || 0).getTime();
    return tb - ta;
  });
  return flat;
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
  return {
    id: `${reportId}-${entry.entry_number ?? index}`,
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

import { JOB_STATUS } from "utils/constants";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";

const COMPLETED = new Set([JOB_STATUS.COMPLETED, "completed"]);

/**
 * Normalise inventory payloads to a flat evidence array.
 */
export function normaliseEvidenceList(inventory) {
  if (Array.isArray(inventory)) return inventory;
  return inventory?.items || inventory?.evidence || [];
}

export function evidenceOptionId(item) {
  return item?.id || item?.evidence_id || "";
}

export function evidenceOptionLabel(item) {
  if (!item) return "—";
  const id = evidenceOptionId(item);
  const short = id ? String(id).slice(0, 8) : "—";
  const name = item.filename || item.name || item.label;
  return name ? `${name} (${short})` : short;
}

function findReportJobs(jobs, evidenceId) {
  const matches = (jobs || []).filter(
    (job) =>
      String(job.evidence_id) === String(evidenceId) &&
      job.report_id &&
      COMPLETED.has(String(job.status || "").toLowerCase())
  );
  return matches.sort((a, b) => {
    const aTime = new Date(a.completed_at || a.created_at || 0).getTime();
    const bTime = new Date(b.completed_at || b.created_at || 0).getTime();
    return bTime - aTime;
  });
}

/**
 * Load ranked artefacts for evidence via the latest completed pipeline report.
 */
export async function loadArtefactsForEvidence(evidenceId) {
  if (!evidenceId) {
    return { artefacts: [], reportMeta: null };
  }
  const jobs = await pipelineService.listJobs();
  const candidates = findReportJobs(jobs, evidenceId);
  for (const job of candidates) {
    try {
      const json = await reportsService.getJson(job.report_id);
      const artefacts = extractArtefacts(json);
      return {
        artefacts,
        reportMeta: {
          reportId: job.report_id,
          jobId: job.job_id || job.id,
          summaryStatistics: json?.summary_statistics || null,
          evidenceId,
        },
      };
    } catch (err) {
      if (err?.response?.status === 404) {
        continue;
      }
      throw err;
    }
  }
  return { artefacts: [], reportMeta: null };
}

/**
 * Artefact array from either the exporter document or JSONReport dump.
 */
export function extractArtefacts(json) {
  if (Array.isArray(json?.artefacts)) return json.artefacts;
  if (Array.isArray(json?.artefact_data)) return json.artefact_data;
  return [];
}

/**
 * Completed pipeline jobs that produced a report that still exists.
 */
export async function listCompletedReports() {
  const [jobs, reports] = await Promise.all([
    pipelineService.listJobs(),
    reportsService.list().catch(() => null),
  ]);
  const existingIds = reports
    ? new Set(
        reports
          .map((report) => report.report_id || report.id)
          .filter(Boolean)
          .map(String)
      )
    : null;

  return (jobs || [])
    .filter((job) => {
      if (!job.report_id) return false;
      if (!existingIds) return true;
      return existingIds.has(String(job.report_id));
    })
    .map((job) => ({
      reportId: job.report_id,
      evidenceId: job.evidence_id,
      jobId: job.job_id || job.id,
      completedAt: job.completed_at || job.created_at,
      status: job.status,
    }));
}

/**
 * Load evidence inventory options for selector dropdowns.
 */
export async function loadEvidenceOptions() {
  const inventory = await evidenceService.getInventory();
  return normaliseEvidenceList(inventory);
}

import { apiGet, apiPost, apiDownload } from "services/api";
import { API_ENDPOINTS } from "config/api.config";
import pipelineService from "services/pipeline.service";

/**
 * Report fetch, export, verify, and audit helpers.
 * There is no backend report-list endpoint — totals are derived from jobs.
 */
export async function getById(id) {
  const { data } = await apiGet(API_ENDPOINTS.REPORTS.BY_ID(id));
  return data;
}

export async function getJson(id) {
  const { data } = await apiGet(API_ENDPOINTS.REPORTS.JSON(id));
  return data;
}

export async function getNarrative(id) {
  const { data } = await apiGet(API_ENDPOINTS.REPORTS.NARRATIVE(id));
  return data;
}

export async function verify(id) {
  const { data } = await apiPost(API_ENDPOINTS.REPORTS.VERIFY(id));
  return data;
}

export async function getCustody(id) {
  const { data } = await apiGet(API_ENDPOINTS.REPORTS.CUSTODY(id));
  return data;
}

/** Alias used by Prompt 8.16. */
export const getCustodyReport = getCustody;

export async function getAuditTrail(id) {
  const { data } = await apiGet(API_ENDPOINTS.REPORTS.AUDIT_TRAIL(id));
  return data;
}

export async function compare(payload) {
  const { data } = await apiPost(API_ENDPOINTS.REPORTS.COMPARE, payload);
  return data;
}

function filenameFromResponse(response, fallback) {
  const header =
    response?.headers?.["content-disposition"] ||
    response?.headers?.["Content-Disposition"] ||
    "";
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf) {
    try {
      return decodeURIComponent(utf[1]);
    } catch {
      return utf[1];
    }
  }
  const simple = /filename="?([^";]+)"?/i.exec(header);
  return simple ? simple[1] : fallback;
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function downloadExport(url, fallbackName) {
  const response = await apiDownload(url);
  const blob = response.data;
  triggerBlobDownload(blob, filenameFromResponse(response, fallbackName));
  return response;
}

export async function exportPdf(id) {
  return downloadExport(API_ENDPOINTS.REPORTS.PDF(id), `report-${id}.pdf`);
}

export async function exportHtml(id) {
  return downloadExport(API_ENDPOINTS.REPORTS.HTML(id), `report-${id}.html`);
}

export async function exportJson(id) {
  return downloadExport(
    API_ENDPOINTS.REPORTS.JSON_FILE(id),
    `report-${id}.json`
  );
}

/**
 * Count generated reports via completed pipeline jobs that expose report_id.
 */
export async function getTotal() {
  const jobs = await pipelineService.listJobs();
  const ids = new Set(
    (jobs || [])
      .map((job) => job.report_id)
      .filter(Boolean)
  );
  return ids.size;
}

const reportsService = {
  getById,
  getJson,
  getNarrative,
  verify,
  getCustody,
  getCustodyReport,
  getAuditTrail,
  compare,
  exportPdf,
  exportHtml,
  exportJson,
  getTotal,
};

export default reportsService;


import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Pipeline run, progress, cancel, and job-list helpers.
 */
export async function run(payload) {
  const { data } = await apiPost(API_ENDPOINTS.PIPELINE.RUN, payload);
  return data;
}

export async function getById(id) {
  const { data } = await apiGet(API_ENDPOINTS.PIPELINE.BY_ID(id));
  return data;
}

/** Alias for Prompt 8.9 naming. */
export const getJob = getById;

export async function getProgress(id) {
  const { data } = await apiGet(API_ENDPOINTS.PIPELINE.PROGRESS(id));
  return data;
}

export async function cancel(id) {
  const { data } = await apiPost(API_ENDPOINTS.PIPELINE.CANCEL(id));
  return data;
}

export async function listJobs(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.PIPELINE.JOBS, params);
  return Array.isArray(data) ? data : data?.jobs || [];
}

export async function listParsers() {
  const { data } = await apiGet(API_ENDPOINTS.PIPELINE.PARSERS);
  return data;
}

const pipelineService = {
  run,
  getById,
  getJob,
  getProgress,
  cancel,
  listJobs,
  listParsers,
};

export default pipelineService;

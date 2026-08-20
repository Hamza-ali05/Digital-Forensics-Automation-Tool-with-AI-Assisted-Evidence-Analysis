import { apiDelete, apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Dataset intelligence registry API helpers.
 */
export async function list(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.DATASETS.LIST, params);
  return Array.isArray(data) ? data : [];
}

export async function getStatistics() {
  const { data } = await apiGet(API_ENDPOINTS.DATASETS.STATISTICS);
  return data?.statistics || data || {};
}

export async function getById(id) {
  const { data } = await apiGet(API_ENDPOINTS.DATASETS.BY_ID(id));
  return data;
}

export async function scan(payload = {}) {
  const { data } = await apiPost(API_ENDPOINTS.DATASETS.SCAN, payload);
  return data;
}

export async function reindex(id) {
  const { data } = await apiPost(API_ENDPOINTS.DATASETS.REINDEX(id));
  return data;
}

export async function refresh(id) {
  const { data } = await apiPost(API_ENDPOINTS.DATASETS.REFRESH(id));
  return data;
}

export async function remove(id) {
  const { data } = await apiDelete(API_ENDPOINTS.DATASETS.DELETE(id));
  return data;
}

const datasetsService = {
  list,
  getStatistics,
  getById,
  scan,
  reindex,
  refresh,
  remove,
};

export default datasetsService;

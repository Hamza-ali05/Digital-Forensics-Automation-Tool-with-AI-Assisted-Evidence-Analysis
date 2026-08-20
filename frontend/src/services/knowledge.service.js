import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Knowledge base, vector store, and IOC API helpers.
 */
export async function getStats() {
  const { data } = await apiGet(API_ENDPOINTS.KNOWLEDGE.STATS);
  return data;
}

export async function query(payload) {
  const { data } = await apiPost(API_ENDPOINTS.KNOWLEDGE.QUERY, payload);
  return data;
}

export async function getGraphStats() {
  const { data } = await apiGet(API_ENDPOINTS.KNOWLEDGE.GRAPH_STATS);
  return data;
}

export async function searchIocs(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.KNOWLEDGE.IOCS, params);
  return data;
}

export async function getIocStats() {
  const { data } = await apiGet(API_ENDPOINTS.KNOWLEDGE.IOC_STATS);
  return data;
}

const knowledgeService = {
  getStats,
  query,
  getGraphStats,
  searchIocs,
  getIocStats,
};

export default knowledgeService;

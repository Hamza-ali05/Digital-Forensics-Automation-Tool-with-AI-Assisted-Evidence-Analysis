import { apiDelete, apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * AI engine health and analysis helpers.
 */
export async function getHealth() {
  const { data } = await apiGet(API_ENDPOINTS.AI.HEALTH);
  return data;
}

export async function getStats() {
  const { data } = await apiGet(API_ENDPOINTS.AI.STATS);
  return data;
}

export async function classify(payload) {
  const { data } = await apiPost(API_ENDPOINTS.AI.CLASSIFY, payload);
  return data;
}

export async function summarize(payload) {
  const { data } = await apiPost(API_ENDPOINTS.AI.SUMMARIZE, payload);
  return data;
}

export async function explain(artefactId, payload = {}) {
  const { data } = await apiPost(API_ENDPOINTS.AI.EXPLAIN(artefactId), payload);
  return data;
}

export async function ask(payload) {
  const { data } = await apiPost(API_ENDPOINTS.AI.ASK, payload);
  return data;
}

export async function getCacheStats() {
  const { data } = await apiGet(API_ENDPOINTS.AI.CACHE_STATS);
  return data;
}

export async function clearCache() {
  const { data } = await apiDelete(API_ENDPOINTS.AI.CACHE_CLEAR);
  return data;
}

/**
 * Normalise AI health payload into a boolean availability flag.
 */
export function isAiHealthy(health) {
  if (!health) return false;
  if (health.is_healthy === true) return true;
  if (health.healthy === true || health.available === true) return true;
  const status = String(health.status || "").toLowerCase();
  return status === "healthy" || status === "ok";
}

const aiService = {
  getHealth,
  getStats,
  classify,
  summarize,
  explain,
  ask,
  getCacheStats,
  clearCache,
  isAiHealthy,
};

export default aiService;

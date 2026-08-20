import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Threat intelligence summary, scanning, and rule inventory API helpers.
 */
export async function getSummary() {
  const { data } = await apiGet(API_ENDPOINTS.THREAT_INTEL.SUMMARY);
  return data?.summary || data || {};
}

export async function scan(payload) {
  const { data } = await apiPost(API_ENDPOINTS.THREAT_INTEL.SCAN, payload);
  return data;
}

export async function getMitreCoverage() {
  const { data } = await apiGet(API_ENDPOINTS.THREAT_INTEL.MITRE);
  return data;
}

export async function listYaraRules() {
  const { data } = await apiGet(API_ENDPOINTS.THREAT_INTEL.YARA_RULES);
  return data;
}

export async function listSigmaRules() {
  const { data } = await apiGet(API_ENDPOINTS.THREAT_INTEL.SIGMA_RULES);
  return data;
}

const threatIntelService = {
  getSummary,
  scan,
  getMitreCoverage,
  listYaraRules,
  listSigmaRules,
};

export default threatIntelService;

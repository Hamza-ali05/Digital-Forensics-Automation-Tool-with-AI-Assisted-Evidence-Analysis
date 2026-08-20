import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * System startup, health, resource, and capability monitoring API helpers.
 */
export async function getStartupReport() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.STARTUP);
  return data;
}

export async function getStatus() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.STATUS);
  return data;
}

export async function getResources() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.RESOURCES);
  return data;
}

export async function getAlerts() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.RESOURCE_ALERTS);
  return data?.alerts || [];
}

export async function getTasks() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.TASKS);
  return data?.tasks || {};
}

export async function restartTask(name) {
  const { data } = await apiPost(API_ENDPOINTS.SYSTEM.RESTART_TASK(name));
  return data;
}

export async function getCapabilities() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.CAPABILITIES);
  return data;
}

export async function getDiagnostics() {
  const { data } = await apiGet(API_ENDPOINTS.SYSTEM.DIAGNOSTICS);
  return data;
}

const systemService = {
  getStartupReport,
  getStatus,
  getResources,
  getAlerts,
  getTasks,
  restartTask,
  getCapabilities,
  getDiagnostics,
};

export default systemService;

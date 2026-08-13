import { apiDelete, apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Case listing and lifecycle API helpers.
 */
export async function list(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.CASES.LIST, params);
  return data;
}

export async function getMine() {
  const { data } = await apiGet(API_ENDPOINTS.CASES.MINE);
  return data;
}

export async function getById(id) {
  const { data } = await apiGet(API_ENDPOINTS.CASES.BY_ID(id));
  return data;
}

export async function getSummary(id) {
  const { data } = await apiGet(API_ENDPOINTS.CASES.SUMMARY(id));
  return data;
}

export async function create(payload) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.CREATE, payload);
  return data;
}

export async function open(id) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.OPEN(id));
  return data;
}

export async function activate(id) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.ACTIVATE(id));
  return data;
}

export async function close(id, payload = {}) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.CLOSE(id), payload);
  return data;
}

export async function archive(id) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.ARCHIVE(id));
  return data;
}

export async function submitReview(id) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.SUBMIT_REVIEW(id));
  return data;
}

export async function reopen(id, payload = {}) {
  const { data } = await apiPost(API_ENDPOINTS.CASES.REOPEN(id), payload);
  return data;
}

export async function assignInvestigator(caseId, payload) {
  const { data } = await apiPost(
    API_ENDPOINTS.CASES.INVESTIGATORS(caseId),
    payload
  );
  return data;
}

export async function removeInvestigator(caseId, userId) {
  const { data } = await apiDelete(
    API_ENDPOINTS.CASES.REMOVE_INVESTIGATOR(caseId, userId)
  );
  return data;
}

export async function addEvidence(caseId, payload) {
  const { data } = await apiPost(
    API_ENDPOINTS.CASES.ADD_EVIDENCE(caseId),
    payload
  );
  return data;
}

const casesService = {
  list,
  getMine,
  getById,
  getSummary,
  create,
  open,
  activate,
  close,
  archive,
  submitReview,
  reopen,
  assignInvestigator,
  removeInvestigator,
  addEvidence,
};

export default casesService;

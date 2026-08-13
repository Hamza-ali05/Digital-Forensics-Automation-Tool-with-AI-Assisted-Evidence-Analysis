import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Benchmark evaluation and usability API helpers.
 */
export async function getDatasets() {
  const { data } = await apiGet(API_ENDPOINTS.EVALUATION.BENCHMARK_DATASETS);
  return data || { dfrws: [], cfreds: [] };
}

export async function runBenchmark(payload) {
  const { data } = await apiPost(
    API_ENDPOINTS.EVALUATION.BENCHMARK_RUN,
    payload
  );
  return data;
}

export async function getResults() {
  const { data } = await apiGet(API_ENDPOINTS.EVALUATION.BENCHMARK_RESULTS);
  return Array.isArray(data) ? data : data?.results || [];
}

export async function getResult(id) {
  const { data } = await apiGet(API_ENDPOINTS.EVALUATION.BENCHMARK_RESULT(id));
  return data;
}

export async function getPerformance(params = {}) {
  const { data } = await apiGet(
    API_ENDPOINTS.EVALUATION.BENCHMARK_PERFORMANCE,
    params
  );
  return data;
}

export async function getQuestionnaire() {
  const { data } = await apiGet(
    API_ENDPOINTS.EVALUATION.USABILITY_QUESTIONNAIRE
  );
  return data;
}

export async function submitQuestionnaire(payload) {
  const { data } = await apiPost(
    API_ENDPOINTS.EVALUATION.USABILITY_RESPOND,
    payload
  );
  return data;
}

const evaluationService = {
  getDatasets,
  runBenchmark,
  getResults,
  getResult,
  getPerformance,
  getQuestionnaire,
  submitQuestionnaire,
};

export default evaluationService;

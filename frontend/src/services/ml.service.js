import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * ML lifecycle, training, and inference API helpers.
 */
export async function listModels() {
  const { data } = await apiGet(API_ENDPOINTS.ML.MODELS);
  return Array.isArray(data) ? data : [];
}

export async function getLatestModel(name) {
  const { data } = await apiGet(API_ENDPOINTS.ML.MODEL_LATEST(name));
  return data;
}

export async function listExperiments(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.ML.EXPERIMENTS, params);
  return Array.isArray(data) ? data : [];
}

export async function getExperiment(id) {
  const { data } = await apiGet(API_ENDPOINTS.ML.EXPERIMENT(id));
  return data;
}

export async function train(payload) {
  const { data } = await apiPost(API_ENDPOINTS.ML.TRAIN, payload);
  return data;
}

export async function retrain() {
  const { data } = await apiPost(API_ENDPOINTS.ML.RETRAIN);
  return data;
}

export async function predict(payload) {
  const { data } = await apiPost(API_ENDPOINTS.ML.PREDICT, payload);
  return data;
}

const mlService = {
  listModels,
  getLatestModel,
  listExperiments,
  getExperiment,
  train,
  retrain,
  predict,
};

export default mlService;

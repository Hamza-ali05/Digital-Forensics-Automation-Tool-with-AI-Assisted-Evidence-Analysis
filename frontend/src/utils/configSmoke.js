/**
 * Smoke import for absolute path resolution (jsconfig baseUrl=src).
 * Not executed in production UI — kept for Prompt 7.4 verification.
 */
import config from "config";
import { API_ENDPOINTS } from "config/api.config";
import { AUTH_CONFIG } from "config/auth.config";
import { APP_CONFIG } from "config/app.config";

export function getConfigSmokeSnapshot() {
  return {
    apiBaseUrl: config.apiBaseUrl,
    appName: config.appName,
    authTokenKey: AUTH_CONFIG.tokenKey,
    appVersion: APP_CONFIG.version,
    authLogin: API_ENDPOINTS.AUTH.LOGIN,
    casesList: API_ENDPOINTS.CASES.LIST,
    evidenceRegister: API_ENDPOINTS.EVIDENCE.REGISTER,
    pipelineRun: API_ENDPOINTS.PIPELINE.RUN,
    aiClassify: API_ENDPOINTS.AI.CLASSIFY,
    reportsPdf: API_ENDPOINTS.REPORTS.PDF("sample"),
    evalBenchmark: API_ENDPOINTS.EVALUATION.BENCHMARK_RUN,
  };
}

export default getConfigSmokeSnapshot;

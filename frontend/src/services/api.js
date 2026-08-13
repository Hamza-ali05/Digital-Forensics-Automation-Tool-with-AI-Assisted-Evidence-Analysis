import axiosModule from "axios";

import config from "config";
import { API_ENDPOINTS } from "config/api.config";
import { AUTH_CONFIG } from "config/auth.config";

// Support both ESM default export and CJS (Jest shim) shapes.
const axios =
  axiosModule && typeof axiosModule.create === "function"
    ? axiosModule
    : axiosModule &&
      axiosModule.default &&
      typeof axiosModule.default.create === "function"
      ? axiosModule.default
      : axiosModule;

/**
 * Generate a request correlation ID for audit trails.
 * Prefer crypto.randomUUID when available.
 */
function createRequestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `dfat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Clear stored auth credentials after a failed refresh.
 */
function clearAuthStorage() {
  localStorage.removeItem(AUTH_CONFIG.tokenKey);
  localStorage.removeItem(AUTH_CONFIG.refreshTokenKey);
  localStorage.removeItem(AUTH_CONFIG.userKey);
  localStorage.removeItem(AUTH_CONFIG.tokenExpiryKey);
  localStorage.removeItem(AUTH_CONFIG.sessionStartKey);
}

/**
 * Normalise Axios/network errors into a stable client shape.
 */
export function normaliseApiError(error) {
  const data = error.response?.data;
  let message =
    data?.message ||
    (typeof data?.detail === "string" ? data.detail : null) ||
    error.message ||
    "Network error";

  if (Array.isArray(data?.detail)) {
    message = data.detail
      .map((item) => item.msg || JSON.stringify(item))
      .join("; ");
  }

  return {
    status: error.response?.status || 0,
    message,
    details: data?.details || {},
    requestId:
      error.response?.headers?.["x-request-id"] ||
      data?.request_id ||
      null,
  };
}

const apiClient = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// Single in-flight refresh so concurrent 401s share one refresh call.
let refreshPromise = null;

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = localStorage.getItem(AUTH_CONFIG.refreshTokenKey);
      if (!refreshToken) {
        throw new Error("No refresh token available");
      }
      const { data } = await axios.post(
        `${config.apiBaseUrl}${API_ENDPOINTS.AUTH.REFRESH}`,
        { refresh_token: refreshToken },
        { headers: { "Content-Type": "application/json" } }
      );
      localStorage.setItem(AUTH_CONFIG.tokenKey, data.access_token);
      localStorage.setItem(AUTH_CONFIG.refreshTokenKey, data.refresh_token);
      if (typeof data.expires_in === "number") {
        const expiry = Date.now() + data.expires_in * 1000;
        localStorage.setItem(AUTH_CONFIG.tokenExpiryKey, String(expiry));
      }
      return data.access_token;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

// Request interceptor: attach JWT + audit correlation id
apiClient.interceptors.request.use((req) => {
  const token = localStorage.getItem(AUTH_CONFIG.tokenKey);
  if (token) {
    req.headers.Authorization = `Bearer ${token}`;
  }
  req.headers["X-Request-ID"] = createRequestId();

  if (config.debug) {
    // eslint-disable-next-line no-console
    console.debug("[DFAT API]", req.method?.toUpperCase(), req.url, {
      requestId: req.headers["X-Request-ID"],
    });
  }

  return req;
});

// Response interceptor: 401 → refresh once, then retry; else normalise error
apiClient.interceptors.response.use(
  (response) => {
    if (config.debug) {
      // eslint-disable-next-line no-console
      console.debug(
        "[DFAT API]",
        response.status,
        response.config?.method?.toUpperCase(),
        response.config?.url
      );
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry
    ) {
      // Do not attempt refresh for auth endpoints themselves.
      const url = originalRequest.url || "";
      const isAuthEndpoint =
        url.includes(API_ENDPOINTS.AUTH.LOGIN) ||
        url.includes(API_ENDPOINTS.AUTH.REFRESH) ||
        url.includes(API_ENDPOINTS.AUTH.LOGOUT);

      if (!isAuthEndpoint) {
        originalRequest._retry = true;
        try {
          const accessToken = await refreshAccessToken();
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
          return apiClient(originalRequest);
        } catch (refreshError) {
          clearAuthStorage();
          if (!window.location.pathname.startsWith("/auth/login")) {
            window.location.href = "/auth/login";
          }
          return Promise.reject(normaliseApiError(refreshError));
        }
      }
    }

    return Promise.reject(normaliseApiError(error));
  }
);

export default apiClient;

export const apiGet = (url, params) => apiClient.get(url, { params });
export const apiPost = (url, data, options) =>
  apiClient.post(url, data, options);
export const apiPut = (url, data, options) => apiClient.put(url, data, options);
export const apiDelete = (url, options) => apiClient.delete(url, options);
export const apiDownload = (url, params) =>
  apiClient.get(url, { params, responseType: "blob" });

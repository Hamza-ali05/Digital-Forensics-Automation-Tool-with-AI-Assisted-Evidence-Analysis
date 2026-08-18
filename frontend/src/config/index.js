/**
 * Application-wide configuration loaded from CRA environment variables.
 * Prefix REACT_APP_ is required for client-side exposure.
 */
const config = {
  // Prefer relative /api/v1 so CRA setupProxy.js can forward to :8000 in dev.
  apiBaseUrl: process.env.REACT_APP_API_BASE_URL || "/api/v1",
  appName: process.env.REACT_APP_APP_NAME || "DFAT",
  appVersion: process.env.REACT_APP_APP_VERSION || "0.1.0",
  tokenRefreshInterval: parseInt(
    process.env.REACT_APP_TOKEN_REFRESH_INTERVAL_MS || "300000",
    10
  ),
  pollingInterval: parseInt(
    process.env.REACT_APP_POLLING_INTERVAL_MS || "5000",
    10
  ),
  maxFileSizeMB: parseInt(process.env.REACT_APP_MAX_FILE_SIZE_MB || "500", 10),
  debug: process.env.REACT_APP_DEBUG === "true",
};

export default config;

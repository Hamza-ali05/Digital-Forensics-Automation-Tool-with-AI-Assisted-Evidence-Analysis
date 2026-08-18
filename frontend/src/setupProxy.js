/**
 * CRA development proxy — forwards /api to the DFAT backend.
 * Avoids CORS during local development (frontend :3000 → backend :8000).
 * In Docker Compose, set DFAT_BACKEND_PROXY_TARGET=http://backend:8000.
 */
const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function setupProxy(app) {
  const target =
    process.env.DFAT_BACKEND_PROXY_TARGET || "http://127.0.0.1:8000";

  app.use(
    "/api",
    createProxyMiddleware({
      target,
      changeOrigin: true,
      logLevel: "warn",
      timeout: 120000,
      proxyTimeout: 120000,
    })
  );
};

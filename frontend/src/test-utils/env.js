/**
 * Must run before any module that reads REACT_APP_API_BASE_URL (via Jest setupFiles).
 * Node axios cannot resolve relative `/api/v1` bases.
 */
if (!process.env.REACT_APP_API_BASE_URL) {
  process.env.REACT_APP_API_BASE_URL = "http://localhost/api/v1";
}

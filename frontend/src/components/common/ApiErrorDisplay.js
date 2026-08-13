import React from "react";
import { Alert, Button } from "@themesberg/react-bootstrap";

function formatValidationDetails(details) {
  if (!details) return "";
  if (typeof details === "string") return details;
  if (Array.isArray(details)) {
    return details
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join("; ");
  }
  if (typeof details === "object") {
    return Object.entries(details)
      .map(([key, value]) => `${key}: ${value}`)
      .join("; ");
  }
  return String(details);
}

function messageForStatus(error) {
  const status = error?.status ?? 0;
  const details = formatValidationDetails(error?.details);
  const fallback = error?.message;

  switch (status) {
    case 401:
      return "Session expired. Please log in again.";
    case 403:
      return "You don't have permission to perform this action.";
    case 404:
      return "The requested resource was not found.";
    case 422:
      return details
        ? `Validation error: ${details}`
        : fallback || "Validation error.";
    case 429:
      return "Too many requests. Please wait and try again.";
    case 500:
    case 502:
    case 503:
      return "Server error. Please try again later.";
    case 0:
      return "Network error. Check your connection.";
    default:
      return fallback || `Request failed (status ${status}).`;
  }
}

function alertVariant(status) {
  if (status === 401 || status === 403) return "warning";
  if (status === 0 || status >= 500) return "danger";
  if (status === 404 || status === 422) return "warning";
  return "danger";
}

/**
 * Friendly display for normalised API errors from ``services/api``.
 *
 * @param {{ error: object, onRetry?: () => void, className?: string }} props
 */
export default function ApiErrorDisplay({ error, onRetry, className = "" }) {
  if (!error) {
    return null;
  }

  const status = error.status ?? 0;
  const message = messageForStatus(error);

  return (
    <Alert
      variant={alertVariant(status)}
      className={`dfat-api-error ${className}`.trim()}
    >
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-2">
        <div>
          <p className="mb-1 fw-bold">{message}</p>
          {error.requestId ? (
            <p className="mb-0 small text-muted">
              Support reference: <code>{error.requestId}</code>
            </p>
          ) : null}
        </div>
        {typeof onRetry === "function" ? (
          <Button variant="outline-dark" size="sm" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </div>
    </Alert>
  );
}

import React from "react";
import { Alert, Card } from "@themesberg/react-bootstrap";

/**
 * Inline insufficient-permissions message (no redirect).
 *
 * @param {{ role?: string|null, allowedRoles?: string[], message?: string }} props
 */
export default function AccessDenied({
  role = null,
  allowedRoles = [],
  message = "Insufficient permissions",
}) {
  const required =
    Array.isArray(allowedRoles) && allowedRoles.length > 0
      ? allowedRoles.join(", ")
      : "—";

  return (
    <Card border="light" className="shadow-sm">
      <Card.Body>
        <h4 className="mb-3">Access denied</h4>
        <Alert variant="warning" className="mb-0">
          <p className="mb-2 fw-bold">{message}</p>
          <p className="mb-1">
            Your role: <code>{role || "unknown"}</code>
          </p>
          <p className="mb-0">
            Required role(s): <code>{required}</code>
          </p>
        </Alert>
      </Card.Body>
    </Card>
  );
}

/**
 * Frontend RBAC mirror of `dfat.auth.rbac.ROLE_PERMISSIONS` (Prompt 2.6).
 * Keep in sync with backend — admin wildcard via synthetic ``all`` resource.
 */

export const ROLE_PERMISSIONS = Object.freeze({
  admin: { all: ["create", "read", "update", "delete"] },
  investigator: {
    evidence: ["create", "read", "update", "delete"],
    analysis: ["create", "read"],
    reports: ["create", "read"],
    evaluation: ["create", "read"],
    cases: ["create", "read", "update"],
  },
  analyst: {
    evidence: ["read"],
    analysis: ["create", "read"],
    reports: ["read"],
    evaluation: ["read"],
    cases: ["read"],
  },
  viewer: {
    reports: ["read"],
    evaluation: ["read"],
  },
});

/**
 * Route → required permission pair for client-side navigation checks.
 */
export const ROUTE_PERMISSIONS = Object.freeze({
  "/cases": { resource: "cases", action: "read" },
  "/cases/new": { resource: "cases", action: "create" },
  "/evidence": { resource: "evidence", action: "read" },
  "/evidence/new": { resource: "evidence", action: "create" },
  "/evidence/register": { resource: "evidence", action: "create" },
  "/evidence/integrity": { resource: "evidence", action: "read" },
  "/pipeline": { resource: "analysis", action: "read" },
  "/pipeline/run": { resource: "analysis", action: "create" },
  "/reports": { resource: "reports", action: "read" },
  "/evaluation": { resource: "evaluation", action: "read" },
  "/settings": { resource: "users", action: "read" },
  "/settings/users": { resource: "users", action: "read" },
  "/settings/audit": { resource: "users", action: "read" },
});

/**
 * Whether ``role`` may perform ``action`` on ``resource``.
 * Matches ``PermissionChecker.has_permission`` on the backend.
 */
export function hasPermission(role, resource, action) {
  if (!role) {
    return false;
  }
  const permissions = ROLE_PERMISSIONS[role];
  if (!permissions) {
    return false;
  }
  if (permissions.all && permissions.all.includes(action)) {
    return true;
  }
  const allowed = permissions[resource] || [];
  return allowed.includes(action);
}

/**
 * Whether ``role`` may access a registered route path.
 */
export function canAccess(role, route) {
  const requirement = ROUTE_PERMISSIONS[route];
  if (!requirement) {
    return false;
  }
  return hasPermission(role, requirement.resource, requirement.action);
}

/**
 * Route paths from ``ROUTE_PERMISSIONS`` that ``role`` may access.
 */
export function getAccessibleRoutes(role) {
  return Object.keys(ROUTE_PERMISSIONS).filter((path) => canAccess(role, path));
}

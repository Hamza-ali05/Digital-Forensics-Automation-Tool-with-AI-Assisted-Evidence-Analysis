import useAuth from "hooks/useAuth";
import { hasPermission as checkPermission } from "utils/permissions";

/**
 * Permission helpers bound to the current user's role and a resource.
 *
 * @example
 * const { hasPermission, canCreate, canRead } = usePermission("evidence");
 *
 * @param {string} resource Resource name (e.g. ``evidence``, ``cases``).
 */
export default function usePermission(resource) {
  const { role } = useAuth();

  const hasPermission = (action) => checkPermission(role, resource, action);

  return {
    hasPermission,
    canCreate: checkPermission(role, resource, "create"),
    canRead: checkPermission(role, resource, "read"),
    canUpdate: checkPermission(role, resource, "update"),
    canDelete: checkPermission(role, resource, "delete"),
  };
}

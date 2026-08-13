import React from "react";

import AccessDenied from "components/common/AccessDenied";
import LoadingSpinner from "components/common/LoadingSpinner";
import useAuth from "hooks/useAuth";

/**
 * Restricts children to users whose role is in ``allowedRoles``.
 * Does not redirect — renders an inline AccessDenied message.
 *
 * @param {{ allowedRoles: string[], children: React.ReactNode }} props
 */
export default function RoleGuard({ allowedRoles = [], children }) {
  const { role, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner show />;
  }

  const allowed = Array.isArray(allowedRoles) ? allowedRoles : [];
  if (!role || !allowed.includes(role)) {
    return (
      <AccessDenied
        role={role}
        allowedRoles={allowed}
        message="Insufficient permissions"
      />
    );
  }

  return children;
}

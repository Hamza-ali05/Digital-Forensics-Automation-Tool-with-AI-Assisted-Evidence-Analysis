import React from "react";
import { Redirect, useLocation } from "react-router-dom";

import LoadingSpinner from "components/common/LoadingSpinner";
import { Routes } from "routes";
import useAuth from "hooks/useAuth";

/**
 * Protects routes that require an authenticated session.
 * Redirects guests to login; shows a spinner while auth bootstraps.
 */
export default function AuthGuard({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingSpinner show />;
  }

  if (!isAuthenticated) {
    return (
      <Redirect
        to={{
          pathname: Routes.Login.path,
          state: { from: location },
        }}
      />
    );
  }

  return children;
}

import React from "react";
import { Redirect } from "react-router-dom";

import LoadingSpinner from "components/common/LoadingSpinner";
import { Routes } from "routes";
import useAuth from "hooks/useAuth";

/**
 * For login/register: redirects authenticated users to the dashboard.
 */
export default function GuestGuard({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingSpinner show />;
  }

  if (isAuthenticated) {
    return <Redirect to={Routes.Dashboard.path} />;
  }

  return children;
}

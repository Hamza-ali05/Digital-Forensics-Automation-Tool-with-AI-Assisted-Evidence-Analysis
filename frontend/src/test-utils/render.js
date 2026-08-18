import React from "react";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";

import { AuthProvider } from "contexts/AuthContext";
import { NotificationProvider } from "contexts/NotificationContext";
import { ThemeProvider } from "contexts/ThemeContext";
import { AUTH_CONFIG } from "config/auth.config";

/**
 * Render a page with router + auth/notification providers.
 */
export function renderWithProviders(
  ui,
  {
    route = "/",
    role = "admin",
    user = null,
    ...options
  } = {}
) {
  const profile =
    user ||
    (role
      ? {
          id: "u-test",
          username: "tester",
          role_name: role,
          email: "tester@example.com",
          full_name: "Test User",
          is_active: true,
        }
      : null);

  if (profile) {
    localStorage.setItem(AUTH_CONFIG.tokenKey, "test-token");
    localStorage.setItem(AUTH_CONFIG.refreshTokenKey, "test-refresh");
    localStorage.setItem(AUTH_CONFIG.userKey, JSON.stringify(profile));
  }

  function Wrapper({ children }) {
    return (
      <ThemeProvider>
        <AuthProvider>
          <NotificationProvider>
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </NotificationProvider>
        </AuthProvider>
      </ThemeProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}

export function mockAuthServiceAs(role) {
  // eslint-disable-next-line global-require
  const authService = require("services/auth.service").default;
  const profile = {
    id: "u-test",
    username: "tester",
    role_name: role,
    email: "tester@example.com",
    full_name: "Test User",
    is_active: true,
  };
  authService.getStoredUser.mockReturnValue(profile);
  authService.isAuthenticated.mockReturnValue(true);
  authService.hasRefreshToken.mockReturnValue(true);
  authService.getCurrentUser.mockResolvedValue(profile);
  return profile;
}

import React from "react";
import { act, render, wait } from "@testing-library/react";

import { AuthProvider } from "contexts/AuthContext";
import useAuth from "hooks/useAuth";
import { AUTH_CONFIG } from "config/auth.config";
import authService from "services/auth.service";

jest.mock("services/auth.service", () => {
  const service = {
    getCurrentUser: jest.fn(),
    login: jest.fn(),
    logout: jest.fn(),
    refreshToken: jest.fn(),
    hasRefreshToken: jest.fn(() => false),
    isAuthenticated: jest.fn(() => false),
    getStoredUser: jest.fn(() => null),
    clearAuthStorage: jest.fn(),
    register: jest.fn(),
  };
  return {
    __esModule: true,
    default: service,
    ...service,
  };
});

function AuthProbe({ onReady }) {
  const auth = useAuth();
  React.useEffect(() => {
    onReady(auth);
  }, [auth, onReady]);
  return (
    <div>
      <span data-testid="user">{auth.user ? auth.user.username : "null"}</span>
      <span data-testid="loading">{String(auth.isLoading)}</span>
    </div>
  );
}

describe("useAuth", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    authService.getStoredUser.mockReturnValue(null);
    authService.isAuthenticated.mockReturnValue(false);
    authService.hasRefreshToken.mockReturnValue(false);
    authService.getCurrentUser.mockResolvedValue(null);
    authService.clearAuthStorage.mockImplementation(() => {
      localStorage.removeItem(AUTH_CONFIG.tokenKey);
      localStorage.removeItem(AUTH_CONFIG.refreshTokenKey);
      localStorage.removeItem(AUTH_CONFIG.userKey);
      localStorage.removeItem(AUTH_CONFIG.tokenExpiryKey);
    });
  });

  test("test_provides_null_when_unauthenticated", async () => {
    const { getByTestId } = render(
      <AuthProvider>
        <AuthProbe onReady={() => {}} />
      </AuthProvider>
    );

    await wait(() => {
      expect(getByTestId("loading")).toHaveTextContent("false");
    });
    expect(getByTestId("user")).toHaveTextContent("null");
  });

  test("test_provides_user_when_authenticated", async () => {
    const profile = {
      id: "u1",
      username: "alice",
      role_name: "admin",
    };
    authService.getStoredUser.mockReturnValue(profile);
    authService.isAuthenticated.mockReturnValue(true);
    authService.hasRefreshToken.mockReturnValue(true);
    authService.getCurrentUser.mockResolvedValue(profile);

    localStorage.setItem(AUTH_CONFIG.tokenKey, "access");
    localStorage.setItem(AUTH_CONFIG.refreshTokenKey, "refresh");
    localStorage.setItem(AUTH_CONFIG.userKey, JSON.stringify(profile));

    const { getByTestId } = render(
      <AuthProvider>
        <AuthProbe onReady={() => {}} />
      </AuthProvider>
    );

    await wait(() => {
      expect(getByTestId("loading")).toHaveTextContent("false");
    });
    expect(getByTestId("user")).toHaveTextContent("alice");
  });

  test("test_login_updates_state", async () => {
    const profile = {
      id: "u2",
      username: "bob",
      role_name: "investigator",
    };
    authService.login.mockResolvedValue(profile);
    authService.isAuthenticated.mockReturnValue(true);
    authService.hasRefreshToken.mockReturnValue(true);

    let latest = null;
    const { getByTestId } = render(
      <AuthProvider>
        <AuthProbe
          onReady={(auth) => {
            latest = auth;
          }}
        />
      </AuthProvider>
    );

    await wait(() => {
      expect(getByTestId("loading")).toHaveTextContent("false");
    });

    await act(async () => {
      await latest.login("bob", "LifeCyclePass1!");
    });

    expect(authService.login).toHaveBeenCalledWith("bob", "LifeCyclePass1!");
    expect(getByTestId("user")).toHaveTextContent("bob");
  });
});

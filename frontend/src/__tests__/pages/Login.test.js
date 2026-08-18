import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import Login from "pages/auth/Login";
import { renderWithProviders } from "test-utils/render";
import useAuth from "hooks/useAuth";
import authService from "services/auth.service";

const mockReplace = jest.fn();

jest.mock("hooks/useAuth", () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useHistory: () => ({
      replace: mockReplace,
      push: jest.fn(),
      listen: jest.fn(),
      location: { pathname: "/login" },
    }),
  };
});

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
  return { __esModule: true, default: service, ...service };
});

jest.mock("../../assets/img/illustrations/signin.svg", () => "signin.svg");

describe("Login", () => {
  const loginMock = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({ login: loginMock });
    authService.getStoredUser.mockReturnValue(null);
    authService.isAuthenticated.mockReturnValue(false);
    authService.hasRefreshToken.mockReturnValue(false);
  });

  test("test_renders_login_form", () => {
    renderWithProviders(<Login />, { role: null, user: null });
    expect(screen.getByText("Sign in to DFAT")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("investigator")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Password")).toBeInTheDocument();
  });

  test("test_shows_error_on_invalid_credentials", async () => {
    loginMock.mockRejectedValue({ status: 401, message: "Unauthorized" });
    renderWithProviders(<Login />, { role: null, user: null });

    fireEvent.change(screen.getByPlaceholderText("investigator"), {
      target: { value: "alice" },
    });
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "wrong-pass" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Sign in$/i }));

    await wait(() => {
      expect(
        screen.getByText(/Invalid username or password/i)
      ).toBeInTheDocument();
    });
  });

  test("test_redirects_on_success", async () => {
    loginMock.mockResolvedValue({
      id: "1",
      username: "alice",
      role_name: "investigator",
    });
    renderWithProviders(<Login />, { role: null, user: null });

    fireEvent.change(screen.getByPlaceholderText("investigator"), {
      target: { value: "alice" },
    });
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "LifeCyclePass1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Sign in$/i }));

    await wait(() => {
      expect(mockReplace).toHaveBeenCalledWith("/dashboard");
    });
  });

  test("test_shows_lockout_message_on_423", async () => {
    const lockedUntil = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    loginMock.mockRejectedValue({
      status: 423,
      details: { locked_until: lockedUntil },
    });
    renderWithProviders(<Login />, { role: null, user: null });

    fireEvent.change(screen.getByPlaceholderText("investigator"), {
      target: { value: "alice" },
    });
    fireEvent.change(screen.getByPlaceholderText("Password"), {
      target: { value: "LifeCyclePass1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Sign in$/i }));

    await wait(() => {
      expect(screen.getByText(/Account locked/i)).toBeInTheDocument();
    });
  });
});

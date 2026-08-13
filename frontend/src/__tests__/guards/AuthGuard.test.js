import React from "react";
import { MemoryRouter, Route, Switch } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import AuthGuard from "guards/AuthGuard";

jest.mock("hooks/useAuth", () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock("components/common/LoadingSpinner", () => ({
  __esModule: true,
  default: function MockSpinner() {
    return <div data-testid="loading-spinner">Loading</div>;
  },
}));

jest.mock("routes", () => ({
  Routes: {
    Login: { path: "/auth/login" },
    Dashboard: { path: "/dashboard" },
  },
  AppRoutes: () => null,
}));

import useAuth from "hooks/useAuth";

describe("AuthGuard", () => {
  test("test_renders_children_when_authenticated", () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    render(
      <MemoryRouter>
        <AuthGuard>
          <div>Protected Content</div>
        </AuthGuard>
      </MemoryRouter>
    );
    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });

  test("test_redirects_when_unauthenticated", () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isLoading: false });
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Switch>
          <Route exact path="/auth/login">
            <div>Login Page</div>
          </Route>
          <Route>
            <AuthGuard>
              <div>Protected Content</div>
            </AuthGuard>
          </Route>
        </Switch>
      </MemoryRouter>
    );
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });

  test("test_shows_loading_while_checking", () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isLoading: true });
    render(
      <MemoryRouter>
        <AuthGuard>
          <div>Protected Content</div>
        </AuthGuard>
      </MemoryRouter>
    );
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });
});

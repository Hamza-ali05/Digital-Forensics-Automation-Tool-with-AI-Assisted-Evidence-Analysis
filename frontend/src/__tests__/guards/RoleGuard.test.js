import React from "react";
import { render, screen } from "@testing-library/react";

import RoleGuard from "guards/RoleGuard";

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

import useAuth from "hooks/useAuth";

describe("RoleGuard", () => {
  test("test_renders_when_role_allowed", () => {
    useAuth.mockReturnValue({ role: "admin", isLoading: false });
    render(
      <RoleGuard allowedRoles={["admin"]}>
        <div>Admin Panel</div>
      </RoleGuard>
    );
    expect(screen.getByText("Admin Panel")).toBeInTheDocument();
  });

  test("test_shows_denied_when_role_not_allowed", () => {
    useAuth.mockReturnValue({ role: "viewer", isLoading: false });
    render(
      <RoleGuard allowedRoles={["admin", "investigator"]}>
        <div>Create Case</div>
      </RoleGuard>
    );
    expect(screen.queryByText("Create Case")).not.toBeInTheDocument();
    expect(screen.getByText(/Insufficient permissions/i)).toBeInTheDocument();
    expect(screen.getByText(/viewer/i)).toBeInTheDocument();
  });

  test("test_handles_multiple_allowed_roles", () => {
    useAuth.mockReturnValue({ role: "investigator", isLoading: false });
    render(
      <RoleGuard allowedRoles={["admin", "investigator"]}>
        <div>Shared Area</div>
      </RoleGuard>
    );
    expect(screen.getByText("Shared Area")).toBeInTheDocument();
  });
});

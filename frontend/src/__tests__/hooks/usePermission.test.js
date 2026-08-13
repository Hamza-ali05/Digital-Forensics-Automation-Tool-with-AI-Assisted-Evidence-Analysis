import React from "react";
import { render } from "@testing-library/react";

import usePermission from "hooks/usePermission";
import { hasPermission } from "utils/permissions";

jest.mock("hooks/useAuth", () => ({
  __esModule: true,
  default: jest.fn(),
}));

import useAuth from "hooks/useAuth";

function PermissionProbe({ resource, onReady }) {
  const perms = usePermission(resource);
  React.useEffect(() => {
    onReady(perms);
  }, [perms, onReady]);
  return null;
}

describe("usePermission", () => {
  test("test_admin_has_all_permissions", () => {
    useAuth.mockReturnValue({ role: "admin" });
    let perms = null;
    render(
      <PermissionProbe
        resource="evidence"
        onReady={(value) => {
          perms = value;
        }}
      />
    );
    expect(perms.canCreate).toBe(true);
    expect(perms.canRead).toBe(true);
    expect(perms.canUpdate).toBe(true);
    expect(perms.canDelete).toBe(true);
    expect(perms.hasPermission("delete")).toBe(true);
  });

  test("test_viewer_cannot_create_evidence", () => {
    useAuth.mockReturnValue({ role: "viewer" });
    let perms = null;
    render(
      <PermissionProbe
        resource="evidence"
        onReady={(value) => {
          perms = value;
        }}
      />
    );
    expect(perms.canCreate).toBe(false);
    expect(perms.canRead).toBe(false);
  });

  test("test_analyst_can_read_reports", () => {
    useAuth.mockReturnValue({ role: "analyst" });
    let perms = null;
    render(
      <PermissionProbe
        resource="reports"
        onReady={(value) => {
          perms = value;
        }}
      />
    );
    expect(perms.canRead).toBe(true);
    expect(perms.canCreate).toBe(false);
  });

  test("test_hasPermission_matches_backend", () => {
    expect(hasPermission("admin", "users", "read")).toBe(true);
    expect(hasPermission("investigator", "cases", "create")).toBe(true);
    expect(hasPermission("viewer", "cases", "create")).toBe(false);
    expect(hasPermission("analyst", "evidence", "read")).toBe(true);
    expect(hasPermission("analyst", "evidence", "delete")).toBe(false);
  });
});

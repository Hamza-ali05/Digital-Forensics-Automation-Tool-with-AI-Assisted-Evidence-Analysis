import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import CaseList from "pages/cases/CaseList";
import { renderWithProviders } from "test-utils/render";
import casesService from "services/cases.service";
import authService from "services/auth.service";

jest.mock("services/cases.service", () => ({
  __esModule: true,
  default: {
    list: jest.fn(),
    close: jest.fn(),
  },
}));

jest.mock("services/auth.service", () => {
  const service = {
    getCurrentUser: jest.fn(),
    login: jest.fn(),
    logout: jest.fn(),
    refreshToken: jest.fn(),
    hasRefreshToken: jest.fn(() => true),
    isAuthenticated: jest.fn(() => true),
    getStoredUser: jest.fn(),
    clearAuthStorage: jest.fn(),
    register: jest.fn(),
  };
  return { __esModule: true, default: service, ...service };
});

jest.mock("react-datetime", () => {
  const React = require("react");
  return function DatetimeMock() {
    return React.createElement("div", { "data-testid": "datetime" });
  };
});

const CASES = [
  {
    case_id: "c1",
    case_name: "Alpha Case",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    investigators: [],
  },
  {
    case_id: "c2",
    case_name: "Beta Case",
    status: "open",
    created_at: "2026-01-02T00:00:00Z",
    investigators: [],
  },
];

describe("CaseList", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    casesService.list.mockResolvedValue({ cases: CASES, total: 2 });
  });

  test("test_renders_case_table", async () => {
    renderWithProviders(<CaseList />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText("Alpha Case")).toBeInTheDocument();
    });
    expect(screen.getByText("Beta Case")).toBeInTheDocument();
  });

  test("test_filters_by_status", async () => {
    renderWithProviders(<CaseList />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText("Alpha Case")).toBeInTheDocument();
    });
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "active" } });
    await wait(() => {
      expect(casesService.list).toHaveBeenCalled();
    });
    const lastCall = casesService.list.mock.calls[
      casesService.list.mock.calls.length - 1
    ][0];
    expect(lastCall).toEqual(expect.objectContaining({ status: "active" }));
  });

  test("test_new_case_button_hidden_for_viewer", async () => {
    const viewer = { id: "2", username: "view", role_name: "viewer" };
    authService.getStoredUser.mockReturnValue(viewer);
    authService.getCurrentUser.mockResolvedValue(viewer);
    casesService.list.mockResolvedValue({ cases: [], total: 0 });

    renderWithProviders(<CaseList />, { role: "viewer", user: viewer });
    await wait(() => {
      expect(screen.getAllByText(/^Cases$/i).length).toBeGreaterThan(0);
    });
    expect(screen.queryByRole("button", { name: /New Case/i })).toBeNull();
    expect(screen.queryByText(/^New Case$/i)).not.toBeInTheDocument();
  });
});

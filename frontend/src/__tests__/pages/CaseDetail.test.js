import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import CaseDetail from "pages/cases/CaseDetail";
import { renderWithProviders } from "test-utils/render";
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import usersService from "services/users.service";
import authService from "services/auth.service";

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "c1" }),
  };
});

jest.mock("services/cases.service", () => ({
  __esModule: true,
  default: {
    getById: jest.fn(),
    getSummary: jest.fn(),
    open: jest.fn(),
    activate: jest.fn(),
    close: jest.fn(),
    archive: jest.fn(),
    submitReview: jest.fn(),
    reopen: jest.fn(),
    assignInvestigator: jest.fn(),
    removeInvestigator: jest.fn(),
    addEvidence: jest.fn(),
  },
}));

jest.mock("services/evidence.service", () => ({
  __esModule: true,
  default: { getInventory: jest.fn() },
}));

jest.mock("services/pipeline.service", () => ({
  __esModule: true,
  default: { listJobs: jest.fn() },
}));

jest.mock("services/users.service", () => ({
  __esModule: true,
  default: { list: jest.fn() },
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

const INVESTIGATORS = [
  {
    user_id: "u1",
    username: "alice",
    full_name: "Alice Lead",
    role: "lead",
    assigned_at: "2026-01-01T00:00:00Z",
  },
  {
    user_id: "u2",
    username: "bob",
    full_name: "Bob Member",
    role: "member",
    assigned_at: "2026-01-02T00:00:00Z",
  },
];

function mockCase(overrides = {}) {
  return {
    case_id: "c1",
    case_name: "Alpha Case",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    lead_investigator_id: "u1",
    investigators: INVESTIGATORS,
    evidence_count: 0,
    ...overrides,
  };
}

describe("CaseDetail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    casesService.getSummary.mockResolvedValue({
      case_id: "c1",
      investigators: INVESTIGATORS,
    });
    evidenceService.getInventory.mockResolvedValue({ items: [] });
    pipelineService.listJobs.mockResolvedValue([]);
    usersService.list.mockResolvedValue({ users: [] });
  });

  test("test_renders_case_info", async () => {
    casesService.getById.mockResolvedValue(mockCase({ status: "active" }));
    renderWithProviders(<CaseDetail />, { role: "investigator" });

    await wait(() => {
      expect(screen.getAllByText("Alpha Case").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByRole("button", { name: /Submit for Review/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Close$/i })).toBeInTheDocument();
  });

  test("test_hides_invalid_transitions", async () => {
    casesService.getById.mockResolvedValue(mockCase({ status: "created" }));
    renderWithProviders(<CaseDetail />, { role: "investigator" });

    await wait(() => {
      expect(
        screen.getByRole("button", { name: /Open Case/i })
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Activate$/i })).toBeNull();
  });

  test("test_investigator_tab_shows_team", async () => {
    casesService.getById.mockResolvedValue(mockCase({ status: "active" }));
    const { container } = renderWithProviders(<CaseDetail />, {
      role: "investigator",
    });

    await wait(() => {
      expect(screen.getAllByText("Alpha Case").length).toBeGreaterThan(0);
    });

    const invLink = Array.from(container.querySelectorAll("a.nav-link")).find(
      (el) => el.textContent.trim() === "Investigators"
    );
    expect(invLink).toBeTruthy();
    fireEvent.click(invLink);

    await wait(() => {
      expect(screen.getByText("Alice Lead")).toBeInTheDocument();
    });
    expect(screen.getByText("Bob Member")).toBeInTheDocument();
  });

  test("test_shows_lifecycle_buttons_for_current_status", async () => {
    casesService.getById.mockResolvedValue(mockCase({ status: "open" }));
    renderWithProviders(<CaseDetail />, { role: "investigator" });

    await wait(() => {
      expect(
        screen.getByRole("button", { name: /^Activate$/i })
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /Open Case/i })).toBeNull();
  });
});

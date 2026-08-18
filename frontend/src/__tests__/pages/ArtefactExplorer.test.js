import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import ArtefactExplorer from "pages/artefacts/ArtefactExplorer";
import { renderWithProviders } from "test-utils/render";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import authService from "services/auth.service";

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "ev-1" }),
  };
});

jest.mock("services/evidence.service", () => ({
  __esModule: true,
  default: { getInventory: jest.fn() },
}));
jest.mock("services/pipeline.service", () => ({
  __esModule: true,
  default: { listJobs: jest.fn() },
}));
jest.mock("services/reports.service", () => ({
  __esModule: true,
  default: { getJson: jest.fn() },
}));
jest.mock("services/ai.service", () => ({
  __esModule: true,
  default: { classify: jest.fn(), explain: jest.fn() },
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

const ARTEFACTS = [
  {
    artefact_id: "art-1",
    category: "event_log",
    suspicion_level: "high",
    relevance_score: 0.9,
    raw_data: { event_id: "Suspicious Event", source: "Security" },
    metadata: {},
  },
  {
    artefact_id: "art-2",
    category: "browser_history",
    suspicion_level: "low",
    relevance_score: 0.2,
    raw_data: { url: "https://example.com/visit" },
    metadata: {},
  },
];

describe("ArtefactExplorer", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    evidenceService.getInventory.mockResolvedValue([
      { evidence_id: "ev-1", file_name: "disk.E01", status: "processed" },
    ]);
    pipelineService.listJobs.mockResolvedValue([
      {
        job_id: "j1",
        evidence_id: "ev-1",
        report_id: "r1",
        status: "completed",
        completed_at: "2026-01-01T00:00:00Z",
      },
    ]);
    reportsService.getJson.mockResolvedValue({ artefacts: ARTEFACTS });
  });

  test("test_category_tabs_render_correct_tables", async () => {
    renderWithProviders(<ArtefactExplorer />, {
      role: "investigator",
      route: "/artefacts/ev-1",
    });
    await wait(() => {
      expect(screen.getAllByText("File System").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("Registry").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Event Logs").length).toBeGreaterThan(0);
    await wait(() => {
      expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
    });
  });

  test("test_suspicion_filter_updates_table", async () => {
    renderWithProviders(<ArtefactExplorer />, {
      role: "investigator",
      route: "/artefacts/ev-1",
    });
    await wait(() => {
      expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/example\.com\/visit/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText(/^High$/i));

    await wait(() => {
      expect(screen.queryAllByText(/example\.com\/visit/i).length).toBe(0);
    });
    expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
  });

  test("test_search_filters_artefacts", async () => {
    renderWithProviders(<ArtefactExplorer />, {
      role: "investigator",
      route: "/artefacts/ev-1",
    });
    await wait(() => {
      expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
    });

    const search = screen.getByPlaceholderText(/Search raw_data fields/i);
    fireEvent.change(search, { target: { value: "example.com" } });

    await wait(() => {
      expect(screen.queryAllByText(/Suspicious Event/i).length).toBe(0);
    });
    expect(screen.getAllByText(/example\.com\/visit/i).length).toBeGreaterThan(0);
  });

  test("test_detail_modal_shows_raw_data", async () => {
    renderWithProviders(<ArtefactExplorer />, {
      role: "investigator",
      route: "/artefacts/ev-1",
    });
    await wait(() => {
      expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByRole("button", { name: /Details/i })[0]);

    await wait(() => {
      expect(
        screen.getByText(/Artefact Details|Artefact art/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/Raw data/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Suspicious Event/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Security/i).length).toBeGreaterThan(0);
  });
});

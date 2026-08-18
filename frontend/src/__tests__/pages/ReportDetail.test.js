import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import ReportDetail from "pages/reports/ReportDetail";
import { renderWithProviders } from "test-utils/render";
import reportsService from "services/reports.service";
import pipelineService from "services/pipeline.service";
import authService from "services/auth.service";

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "rep-1" }),
  };
});

jest.mock("services/reports.service", () => {
  const getCustody = jest.fn();
  return {
    __esModule: true,
    default: {
      getById: jest.fn(),
      getJson: jest.fn(),
      getNarrative: jest.fn(),
      exportPdf: jest.fn(),
      exportHtml: jest.fn(),
      exportJson: jest.fn(),
      verify: jest.fn(),
      getCustody,
      getCustodyReport: (...args) => getCustody(...args),
      getAuditTrail: jest.fn(),
      compare: jest.fn(),
    },
  };
});

jest.mock("services/pipeline.service", () => ({
  __esModule: true,
  default: { listJobs: jest.fn() },
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

jest.mock("react-chartjs-2", () => ({
  Bar: () => <div data-testid="bar-chart" />,
}));

describe("ReportDetail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);

    reportsService.getById.mockResolvedValue({
      report_id: "rep-1",
      case_id: "c1",
      case_name: "Alpha Case",
      evidence_id: "ev-1",
      generated_at: "2026-01-01T00:00:00Z",
    });
    reportsService.getJson.mockResolvedValue({
      report_id: "rep-1",
      case_id: "c1",
      evidence_id: "ev-1",
      schema_version: "1.0",
      artefacts: [
        {
          artefact_id: "art-1",
          category: "event_log",
          suspicion_level: "high",
          relevance_score: 0.9,
        },
      ],
      summary_statistics: {
        by_category: { event_log: 1 },
        by_suspicion: { high: 1 },
      },
    });
    reportsService.getNarrative.mockResolvedValue(
      "Narrative summary of the investigation findings."
    );
    reportsService.getCustody.mockResolvedValue({ entries: [] });
    reportsService.getAuditTrail.mockResolvedValue({ entries: [] });
    pipelineService.listJobs.mockResolvedValue([
      {
        job_id: "j1",
        report_id: "rep-1",
        evidence_id: "ev-1",
        case_id: "c1",
        status: "completed",
        completed_at: "2026-01-01T00:00:00Z",
      },
    ]);
    reportsService.exportPdf.mockResolvedValue({});
    reportsService.verify.mockResolvedValue({
      is_valid: true,
      integrity_hash_match: true,
      schema_version_valid: true,
      verified_at: "2026-01-02T00:00:00Z",
      issues: [],
    });
  });

  test("test_renders_all_tabs", async () => {
    renderWithProviders(<ReportDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText(/^Overview$/)).toBeInTheDocument();
    });
    expect(screen.getByText(/^Narrative Summary$/)).toBeInTheDocument();
    expect(screen.getByText(/^JSON Data$/)).toBeInTheDocument();
    expect(screen.getByText(/^Export$/)).toBeInTheDocument();
  });

  test("test_export_buttons_trigger_download", async () => {
    renderWithProviders(<ReportDetail />, { role: "investigator" });
    await wait(() => {
      expect(
        screen.getAllByRole("button", { name: /Export PDF/i }).length
      ).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByRole("button", { name: /Export PDF/i })[0]);

    await wait(() => {
      expect(reportsService.exportPdf).toHaveBeenCalledWith("rep-1");
    });
  });

  test("test_integrity_verification_works", async () => {
    renderWithProviders(<ReportDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText(/^Export$/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/^Export$/));

    await wait(() => {
      expect(
        screen.getByRole("button", { name: /Verify Integrity/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Verify Integrity/i }));

    await wait(() => {
      expect(reportsService.verify).toHaveBeenCalledWith("rep-1");
    });
    await wait(() => {
      expect(screen.getByText(/Integrity hash match/i)).toBeInTheDocument();
    });
  });
});

import React from "react";
import { screen, wait } from "@testing-library/react";

import PipelineDetail from "pages/pipeline/PipelineDetail";
import { renderWithProviders } from "test-utils/render";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import authService from "services/auth.service";

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ jobId: "job-1" }),
  };
});

jest.mock("services/pipeline.service", () => {
  const getById = jest.fn();
  return {
    __esModule: true,
    default: {
      getById,
      getJob: (...args) => getById(...args),
      getProgress: jest.fn(),
      cancel: jest.fn(),
    },
  };
});

jest.mock("services/reports.service", () => ({
  __esModule: true,
  default: { getJson: jest.fn() },
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

describe("PipelineDetail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
  });

  test("test_progress_bar_animates_when_running", async () => {
    pipelineService.getById.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      current_stage: "parsing",
      stage_executions: {
        acquisition: { status: "completed", duration_seconds: 2 },
        parsing: { status: "running", duration_seconds: 1 },
      },
      evidence_id: "ev-1",
      case_id: "c-1",
    });
    pipelineService.getProgress.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      percent_complete: 40,
      stages_completed: 1,
      stages_total: 5,
      current_stage: "parsing",
    });

    const { container } = renderWithProviders(<PipelineDetail />, {
      role: "investigator",
    });
    await wait(() => {
      expect(screen.getByText("40%")).toBeInTheDocument();
    });
    expect(container.querySelector(".progress-bar-animated")).toBeTruthy();
  });

  test("test_stage_timeline_shows_correct_states", async () => {
    pipelineService.getById.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      current_stage: "parsing",
      stage_executions: {
        acquisition: { status: "completed", duration_seconds: 2 },
        parsing: { status: "running", duration_seconds: 1 },
        ai_triage: { status: "pending" },
        reporting: { status: "pending" },
        evaluation: { status: "pending" },
      },
      evidence_id: "ev-1",
      case_id: "c-1",
    });
    pipelineService.getProgress.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      percent_complete: 40,
      current_stage: "parsing",
    });

    renderWithProviders(<PipelineDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText(/Stage Timeline/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Acquisition/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Parsing/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Ai Triage|AI Triage/i).length).toBeGreaterThan(0);
  });

  test("test_parser_results_table_shows_per_parser", async () => {
    pipelineService.getById.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      current_stage: "parsing",
      stage_executions: {
        acquisition: { status: "completed", duration_seconds: 2 },
        parsing: {
          status: "running",
          duration_seconds: 1,
          parser_results: {
            filesystem: {
              parser_name: "FilesystemParser",
              status: "completed",
              artefacts_found: 5,
              duration_seconds: 1.2,
            },
            registry: {
              parser_name: "RegistryParser",
              status: "running",
              artefacts_found: 2,
              duration_seconds: 0.5,
            },
          },
        },
      },
      evidence_id: "ev-1",
      case_id: "c-1",
    });
    pipelineService.getProgress.mockResolvedValue({
      job_id: "job-1",
      status: "running",
      percent_complete: 45,
      current_stage: "parsing",
    });

    renderWithProviders(<PipelineDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText("FilesystemParser")).toBeInTheDocument();
    });
    expect(screen.getByText("RegistryParser")).toBeInTheDocument();
    expect(screen.getByText("Parser Results")).toBeInTheDocument();
  });

  test("test_completed_job_shows_results_summary", async () => {
    pipelineService.getById.mockResolvedValue({
      job_id: "job-1",
      status: "completed",
      report_id: "rep-1",
      evidence_id: "ev-1",
      case_id: "c-1",
      artefact_count: 12,
      stage_executions: {
        acquisition: { status: "completed", duration_seconds: 2 },
        parsing: { status: "completed", duration_seconds: 5 },
        ai_triage: { status: "completed", duration_seconds: 3 },
        reporting: { status: "completed", duration_seconds: 2 },
        evaluation: { status: "completed", duration_seconds: 1 },
      },
    });
    pipelineService.getProgress.mockResolvedValue({
      job_id: "job-1",
      status: "completed",
      percent_complete: 100,
    });
    reportsService.getJson.mockResolvedValue({
      summary_statistics: { by_category: { event_log: 4 } },
    });

    renderWithProviders(<PipelineDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText(/View Report/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Results Summary/i)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});

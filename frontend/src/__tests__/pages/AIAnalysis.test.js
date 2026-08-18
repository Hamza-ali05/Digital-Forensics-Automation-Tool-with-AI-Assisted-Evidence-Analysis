import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import AIAnalysis from "pages/ai/AIAnalysis";
import { renderWithProviders } from "test-utils/render";
import aiService from "services/ai.service";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import authService from "services/auth.service";

jest.mock("services/ai.service", () => ({
  __esModule: true,
  default: {
    getHealth: jest.fn(),
    getCacheStats: jest.fn(),
    clearCache: jest.fn(),
    classify: jest.fn(),
    summarize: jest.fn(),
    ask: jest.fn(),
    explain: jest.fn(),
  },
  isAiHealthy: (health) =>
    Boolean(health && (health.is_healthy || health.healthy || health.available)),
}));

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

describe("AIAnalysis", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    aiService.getHealth.mockResolvedValue({
      is_healthy: true,
      model_name: "llama-3",
      model_loaded: true,
      response_time_ms: 12,
    });
    evidenceService.getInventory.mockResolvedValue([
      {
        evidence_id: "ev-1",
        file_name: "disk.E01",
        status: "processed",
      },
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
    reportsService.getJson.mockResolvedValue({
      artefacts: [
        {
          artefact_id: "art-1",
          category: "event_log",
          suspicion_level: "high",
          relevance_score: 0.9,
          raw_data: { event_id: 4624 },
        },
      ],
    });
    aiService.ask.mockResolvedValue({
      answer: "No critical findings beyond the high-suspicion event log.",
      confidence: 0.8,
      referenced_artefact_ids: ["art-1"],
      hallucination_check: { risk_level: "low" },
    });
  });

  test("test_health_indicator_shows_status", async () => {
    renderWithProviders(<AIAnalysis />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByText(/AI engine available/i)).toBeInTheDocument();
    });
  });

  test("test_disclaimer_always_visible", async () => {
    renderWithProviders(<AIAnalysis />, { role: "investigator" });
    await wait(() => {
      expect(
        screen.getByText(/should be verified against/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/Confidence scores indicate/i)).toBeInTheDocument();
  });

  test("test_qa_interface_sends_question", async () => {
    renderWithProviders(<AIAnalysis />, {
      role: "investigator",
      route: "/ai?evidence_id=ev-1",
    });

    await wait(() => {
      expect(
        screen.getByLabelText(/Ask a question about the evidence/i)
      ).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/Ask a question about the evidence/i);
    fireEvent.change(input, {
      target: { value: "What are the key findings?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    await wait(() => {
      expect(aiService.ask).toHaveBeenCalled();
    });
    await wait(() => {
      expect(
        screen.getByText(/No critical findings beyond the high-suspicion/i)
      ).toBeInTheDocument();
    });
  });
});

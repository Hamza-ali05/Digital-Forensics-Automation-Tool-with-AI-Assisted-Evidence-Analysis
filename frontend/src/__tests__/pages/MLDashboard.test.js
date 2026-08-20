import React from "react";
import { screen, wait } from "@testing-library/react";

import MLDashboard from "pages/ml/MLDashboard";
import { mockAuthServiceAs, renderWithProviders } from "test-utils/render";
import mlService from "services/ml.service";
import datasetsService from "services/datasets.service";

jest.mock("services/ml.service", () => ({
  __esModule: true,
  default: {
    listModels: jest.fn(),
    listExperiments: jest.fn(),
    train: jest.fn(),
  },
}));
jest.mock("services/datasets.service", () => ({
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
jest.mock("hooks/usePolling", () => () => ({
  data: null,
  loading: false,
  error: null,
  isPolling: false,
  stopPolling: jest.fn(),
  startPolling: jest.fn(),
}));

describe("MLDashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthServiceAs("analyst");
    mlService.listModels.mockResolvedValue([
      {
        model_id: "m-1",
        model_name: "MalwareClassifier",
        version: "1",
        metrics: { accuracy: 0.91, f1_score: 0.88 },
        trained_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mlService.listExperiments.mockResolvedValue([
      {
        experiment_id: "exp-1",
        model_name: "MalwareClassifier",
        dataset_name: "malware_samples",
        status: "completed",
        metrics: { f1_score: 0.88 },
        started_at: "2026-01-01T00:00:00Z",
        duration_seconds: 12,
      },
    ]);
    datasetsService.list.mockResolvedValue([]);
  });

  test("renders trained models section", async () => {
    renderWithProviders(<MLDashboard />, { role: "analyst" });
    await wait(() => {
      expect(
        screen.getByRole("link", { name: "MalwareClassifier" })
      ).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Trained Models/i).length).toBeGreaterThan(0);
  });

  test("renders experiment history", async () => {
    renderWithProviders(<MLDashboard />, { role: "analyst" });
    await wait(() => {
      expect(screen.getByText(/Experiment History/i)).toBeInTheDocument();
    });
    expect(screen.getByText("malware_samples")).toBeInTheDocument();
  });

  test("shows train button for admin users", async () => {
    mockAuthServiceAs("admin");
    renderWithProviders(<MLDashboard />, { role: "admin" });
    await wait(() => {
      expect(
        screen.getByRole("button", { name: /Train Model/i })
      ).toBeInTheDocument();
    });
  });
});

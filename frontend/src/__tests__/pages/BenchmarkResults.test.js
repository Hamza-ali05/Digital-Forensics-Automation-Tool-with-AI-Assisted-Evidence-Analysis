import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import BenchmarkResults from "pages/evaluation/BenchmarkResults";
import { renderWithProviders } from "test-utils/render";
import evaluationService from "services/evaluation.service";
import authService from "services/auth.service";

jest.mock("services/evaluation.service", () => ({
  __esModule: true,
  default: {
    getResults: jest.fn(),
    getResult: jest.fn(),
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

jest.mock("react-chartjs-2", () => ({
  Line: () => <div data-testid="trend-chart" />,
}));

const RESULTS = [
  {
    benchmark_id: "b1",
    dataset_name: "dfrws-2009",
    precision: 0.9,
    recall: 0.8,
    f1_score: 0.85,
    time_to_triage_seconds: 42,
    artefacts_expected: 10,
    artefacts_recovered: 9,
    false_positives: 1,
    false_negatives: 2,
    false_positive_ids: ["fp-a"],
    false_negative_ids: ["fn-b"],
    evaluated_at: "2026-01-02T00:00:00Z",
    per_category: {
      event_log: { precision: 0.9, recall: 0.8, f1_score: 0.85 },
    },
  },
];

describe("BenchmarkResults", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    evaluationService.getResults.mockResolvedValue(RESULTS);
    evaluationService.getResult.mockResolvedValue(RESULTS[0]);
  });

  test("test_renders_metrics_cards", async () => {
    renderWithProviders(<BenchmarkResults />, {
      role: "investigator",
      route: "/evaluation/benchmark/history?id=b1",
    });
    await wait(() => {
      expect(screen.getByLabelText(/Precision:/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Recall:/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^F1:/i)).toBeInTheDocument();
  });

  test("test_renders_trend_chart", async () => {
    renderWithProviders(<BenchmarkResults />, { role: "investigator" });
    await wait(() => {
      expect(screen.getByTestId("trend-chart")).toBeInTheDocument();
    });
  });

  test("test_renders_fp_fn_details", async () => {
    renderWithProviders(<BenchmarkResults />, {
      role: "investigator",
      route: "/evaluation/benchmark/history?id=b1",
    });
    await wait(() => {
      expect(
        screen.getByText(/False positives \/ false negatives/i)
      ).toBeInTheDocument();
    });
    const fpHeading = screen.getByText((content, element) => {
      if (!element || element.tagName !== "H6") return false;
      return (
        content.includes("False positives") &&
        !content.includes("negatives") &&
        !content.includes("/")
      );
    });
    fireEvent.click(fpHeading.closest("[aria-expanded]") || fpHeading);
    await wait(() => {
      expect(screen.getByText("fp-a")).toBeInTheDocument();
    });
  });
});

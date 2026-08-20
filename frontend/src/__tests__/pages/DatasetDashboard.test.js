import React from "react";
import { screen, wait } from "@testing-library/react";

import DatasetDashboard from "pages/datasets/DatasetDashboard";
import { mockAuthServiceAs, renderWithProviders } from "test-utils/render";
import datasetsService from "services/datasets.service";

jest.mock("services/datasets.service", () => ({
  __esModule: true,
  default: {
    list: jest.fn(),
    getStatistics: jest.fn(),
    scan: jest.fn(),
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
  Bar: () => <div data-testid="bar-chart" />,
  Doughnut: () => <div data-testid="doughnut-chart" />,
}));

describe("DatasetDashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthServiceAs("analyst");
    datasetsService.getStatistics.mockResolvedValue({
      total_count: 2,
      category_counts: { benchmark: 1, threat_intelligence: 1 },
      format_counts: { csv: 2 },
      status_counts: { ready: 2 },
      total_size_bytes: 2048,
    });
    datasetsService.list.mockResolvedValue([
      {
        dataset_id: "ds-1",
        name: "ioc_feed.csv",
        category: "threat_intelligence",
        format: "csv",
        status: "ready",
        file_size_bytes: 1024,
        indexing_status: "complete",
      },
    ]);
  });

  test("renders dataset overview statistics", async () => {
    renderWithProviders(<DatasetDashboard />, { role: "analyst" });
    await wait(() => {
      expect(screen.getByText(/Total Datasets/i)).toBeInTheDocument();
    });
    const totalLabel = screen.getByText(/Total Datasets/i);
    expect(totalLabel.parentElement).toHaveTextContent("2");
  });

  test("lists registered datasets in table", async () => {
    renderWithProviders(<DatasetDashboard />, { role: "analyst" });
    await wait(() => {
      expect(screen.getByText("ioc_feed.csv")).toBeInTheDocument();
    });
  });

  test("shows scan button for admin users only", async () => {
    mockAuthServiceAs("admin");
    renderWithProviders(<DatasetDashboard />, { role: "admin" });
    await wait(() => {
      expect(
        screen.getByRole("button", { name: /Scan for Datasets/i })
      ).toBeInTheDocument();
    });
  });
});

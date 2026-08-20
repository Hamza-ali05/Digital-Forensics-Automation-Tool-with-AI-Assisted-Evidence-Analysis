import React from "react";
import { screen, wait } from "@testing-library/react";

import SystemStatus from "pages/admin/SystemStatus";
import { renderWithProviders } from "test-utils/render";
import systemService from "services/system.service";

jest.mock("services/system.service", () => ({
  __esModule: true,
  default: {
    getStartupReport: jest.fn(),
    getStatus: jest.fn(),
    getResources: jest.fn(),
    getAlerts: jest.fn(),
  },
}));

jest.mock("hooks/usePolling", () => () => ({
  data: {
    status: {
      system_readiness: "ready",
      degraded_mode: false,
      services: {
        database: {
          is_healthy: true,
          last_checked: "2026-01-01T00:00:00Z",
          response_time_ms: 2.5,
        },
        ollama: {
          is_healthy: true,
          last_checked: "2026-01-01T00:00:00Z",
          response_time_ms: 12.0,
        },
      },
    },
    resources: {
      cpu_percent: 12,
      memory_percent: 45,
      disk_percent: 60,
      evidence_size_gb: 1.2,
      knowledge_base_size_mb: 50,
      database_size_mb: 20,
    },
    alerts: [],
  },
  loading: false,
  error: null,
  isPolling: true,
  stopPolling: jest.fn(),
  startPolling: jest.fn(),
}));

describe("SystemStatus", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    systemService.getStartupReport.mockResolvedValue({
      system_status: "ready",
      completed_at: "2026-01-01T00:00:00Z",
      total_duration_ms: 1200,
      phases: [
        {
          phase: "database",
          status: "completed",
          duration_ms: 100,
          message: "Database ready",
          degraded_capabilities: [],
        },
        {
          phase: "llm_service",
          status: "completed",
          duration_ms: 50,
          message: "LLM ready",
          degraded_capabilities: [],
        },
      ],
      degraded_services: [],
      available_capabilities: ["database", "llm_service"],
    });
  });

  test("renders startup report and monitoring sections", async () => {
    renderWithProviders(<SystemStatus />, { role: "admin" });

    await wait(() => {
      expect(screen.getByText(/System Status/i)).toBeInTheDocument();
    });
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText(/Database ready/i)).toBeInTheDocument();
    expect(screen.getByText(/Service Health/i)).toBeInTheDocument();
    expect(screen.getByText(/Resource Monitoring/i)).toBeInTheDocument();
  });

  test("shows boot phase labels and capability badges", async () => {
    renderWithProviders(<SystemStatus />, { role: "admin" });

    await wait(() => {
      expect(screen.getByText(/Boot Phases/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText("Database").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("LLM Service")).toBeInTheDocument();
    expect(screen.getByText(/Capabilities/i)).toBeInTheDocument();
    expect(screen.getAllByText(/llm service/i).length).toBeGreaterThanOrEqual(1);
  });

  test("renders service health cards for monitored services", async () => {
    renderWithProviders(<SystemStatus />, { role: "admin" });

    await wait(() => {
      expect(screen.getByText(/Ollama \/ LLM/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText("Healthy").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/CPU/i)).toBeInTheDocument();
    expect(screen.getByText(/Memory/i)).toBeInTheDocument();
  });
});

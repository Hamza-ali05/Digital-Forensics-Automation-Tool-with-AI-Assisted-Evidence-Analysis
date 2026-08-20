import React from "react";
import { screen, wait } from "@testing-library/react";

import TaskMonitor from "pages/admin/TaskMonitor";
import { renderWithProviders } from "test-utils/render";
import systemService from "services/system.service";

jest.mock("services/system.service", () => ({
  __esModule: true,
  default: {
    getTasks: jest.fn(),
    restartTask: jest.fn(),
  },
}));

jest.mock("hooks/usePolling", () => () => ({
  data: {
    HealthMonitor: {
      name: "HealthMonitor",
      is_running: true,
      run_count: 3,
      error_count: 0,
    },
  },
  loading: false,
  error: null,
  isPolling: true,
  stopPolling: jest.fn(),
  startPolling: jest.fn(),
}));

describe("TaskMonitor", () => {
  test("lists background tasks with restart action", async () => {
    renderWithProviders(<TaskMonitor />, { role: "admin" });

    await wait(() => {
      expect(screen.getByText("HealthMonitor")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Restart/i })).toBeInTheDocument();
  });
});

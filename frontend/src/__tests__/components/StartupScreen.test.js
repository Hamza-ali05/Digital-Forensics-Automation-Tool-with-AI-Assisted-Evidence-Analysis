import React from "react";
import { screen } from "@testing-library/react";

import StartupScreen from "components/common/StartupScreen";
import { renderWithProviders } from "test-utils/render";
import systemService from "services/system.service";

jest.mock("services/system.service", () => ({
  __esModule: true,
  default: {
    getStartupReport: jest.fn(),
    getStatus: jest.fn(),
  },
}));

describe("StartupScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    systemService.getStartupReport.mockResolvedValue({
      phases: [
        {
          phase: "database",
          status: "completed",
          message: "Database ready",
        },
      ],
      critical_failures: [],
    });
  });

  test("shows initialization message and boot phases", () => {
    renderWithProviders(
      <StartupScreen
        mode="initializing"
        startupReport={{
          phases: [
            {
              phase: "database",
              status: "running",
              message: "Connecting to database",
            },
          ],
        }}
      />
    );

    expect(
      screen.getByText(/Initializing Digital Forensics Automation Tool/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Connecting to database/i)).toBeInTheDocument();
    expect(screen.getByText(/Running bootstrap phases/i)).toBeInTheDocument();
  });

  test("shows backend offline message", () => {
    renderWithProviders(
      <StartupScreen mode="offline" errorDetail="Connection refused" />
    );

    expect(screen.getByText(/Backend not running/i)).toBeInTheDocument();
    expect(screen.getByText(/Connection refused/i)).toBeInTheDocument();
  });

  test("shows unavailable diagnostics", () => {
    renderWithProviders(
      <StartupScreen
        mode="unavailable"
        startupReport={{
          critical_failures: ["database: connection refused"],
          phases: [
            {
              phase: "database",
              status: "failed",
              message: "Database failed",
              error: "connection refused",
            },
          ],
        }}
      />
    );

    expect(screen.getByText(/System unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/database: connection refused/i)).toBeInTheDocument();
    expect(screen.getByText(/Database failed/i)).toBeInTheDocument();
  });
});

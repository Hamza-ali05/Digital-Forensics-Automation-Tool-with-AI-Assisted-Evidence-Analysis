import React from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DegradedBanner from "components/common/DegradedBanner";
import { renderWithProviders } from "test-utils/render";
import systemService from "services/system.service";

jest.mock("services/system.service", () => ({
  __esModule: true,
  default: {
    getStartupReport: jest.fn(),
    getStatus: jest.fn(),
  },
}));

jest.mock("hooks/usePolling", () => (fetchFn) => {
  const payload = fetchFn();
  return {
    data: payload,
    loading: false,
    error: null,
    isPolling: true,
    stopPolling: jest.fn(),
    startPolling: jest.fn(),
  };
});

describe("DegradedBanner", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    systemService.getStatus.mockReturnValue({
      system_readiness: "degraded",
      degraded_mode: false,
      services: {
        ollama: { is_healthy: false },
        database: { is_healthy: true },
      },
    });
  });

  test("shows degraded services with details link", () => {
    renderWithProviders(<DegradedBanner />, { route: "/dashboard", role: "admin" });

    expect(screen.getByRole("status")).toHaveTextContent(/Degraded mode/i);
    expect(screen.getByText(/Ollama \/ LLM/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Click for details/i })).toHaveAttribute(
      "href",
      "/admin/system"
    );
  });

  test("annotates chromadb vector store failures", () => {
    systemService.getStatus.mockReturnValue({
      system_readiness: "degraded",
      degraded_mode: false,
      services: {
        vector_store: {
          is_healthy: false,
          details: { error: "chromadb is not installed — vector search is unavailable" },
        },
      },
    });

    renderWithProviders(<DegradedBanner />, { route: "/dashboard", role: "admin" });

    expect(screen.getByRole("status")).toHaveTextContent(/Vector Store \(ChromaDB missing\)/i);
  });
});

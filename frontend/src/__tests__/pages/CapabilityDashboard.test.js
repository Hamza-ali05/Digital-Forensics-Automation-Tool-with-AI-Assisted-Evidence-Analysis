import React from "react";
import { screen, wait } from "@testing-library/react";

import CapabilityDashboard from "pages/admin/CapabilityDashboard";
import { renderWithProviders } from "test-utils/render";
import systemService from "services/system.service";
import knowledgeService from "services/knowledge.service";
import threatIntelService from "services/threat-intel.service";

jest.mock("services/system.service", () => ({
  __esModule: true,
  default: { getCapabilities: jest.fn() },
}));

jest.mock("services/knowledge.service", () => ({
  __esModule: true,
  default: { getStats: jest.fn() },
}));

jest.mock("services/threat-intel.service", () => ({
  __esModule: true,
  default: { getSummary: jest.fn() },
}));

describe("CapabilityDashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    systemService.getCapabilities.mockResolvedValue({
      parsers: { RegistryParser: true },
      ai: { llm: true, rag: false, ml: true },
      threat_intel: { yara: true, sigma: false, mitre: true },
      knowledge: { vector_store: true, graph: true, ioc_db: false },
      benchmarks: { dfrws: true, cfreds: false },
    });
    knowledgeService.getStats.mockResolvedValue({
      collections: { knowledge: { count: 12 } },
      graph: { node_count: 40 },
      ioc_count: 8,
    });
    threatIntelService.getSummary.mockResolvedValue({
      yara_rules: 5,
      sigma_rules: 0,
    });
  });

  test("renders capability sections and install hints", async () => {
    renderWithProviders(<CapabilityDashboard />, { role: "admin" });

    await wait(() => {
      expect(screen.getByText(/System Capabilities/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Forensic Parsers/i)).toBeInTheDocument();
    expect(screen.getByText(/RegistryParser/i)).toBeInTheDocument();
    expect(screen.getByText(/Enable RAG in config/i)).toBeInTheDocument();
  });
});

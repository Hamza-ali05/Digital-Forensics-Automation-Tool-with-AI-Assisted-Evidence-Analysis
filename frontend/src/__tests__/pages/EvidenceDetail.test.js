import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";

import EvidenceDetail from "pages/evidence/EvidenceDetail";
import { renderWithProviders } from "test-utils/render";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import authService from "services/auth.service";

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: "ev-1" }),
  };
});

jest.mock("services/evidence.service", () => ({
  __esModule: true,
  default: {
    getDetail: jest.fn(),
    getStatus: jest.fn(),
    getCustody: jest.fn(),
    verifyIntegrity: jest.fn(),
    verifyCustody: jest.fn(),
    validate: jest.fn(),
    quarantine: jest.fn(),
  },
}));

jest.mock("services/pipeline.service", () => ({
  __esModule: true,
  default: { listJobs: jest.fn() },
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

const DETAIL = {
  evidence_id: "ev-1",
  file_path: "/data/disk.E01",
  evidence_type: "disk_image",
  status: "processed",
  case_id: "c1",
  original_hash: "aa".repeat(32),
  metadata: {
    mime_type: "application/octet-stream",
    hash_set: {
      sha256: "bb".repeat(32),
      md5: "d41d8cd98f00b204e9800998ecf8427e",
      sha1: "da39a3ee5e6b4b0d3255bfef95601890afd80709",
    },
    is_valid_format: true,
  },
};

describe("EvidenceDetail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
    evidenceService.getDetail.mockResolvedValue(DETAIL);
    evidenceService.getStatus.mockResolvedValue({
      history: [
        {
          new_status: "processed",
          previous_status: "processing",
          changed_at: "2026-01-02T00:00:00Z",
          changed_by_user_id: "u1",
        },
        {
          new_status: "processing",
          previous_status: "validated",
          changed_at: "2026-01-01T12:00:00Z",
          changed_by_user_id: "u1",
        },
      ],
    });
    evidenceService.getCustody.mockResolvedValue({
      entries: [
        {
          entry_number: 1,
          action: "acquired",
          timestamp: "2026-01-01T00:00:00Z",
          performed_by_name: "Alice",
          hash_at_action: "bb".repeat(32),
        },
        {
          entry_number: 2,
          action: "accessed",
          timestamp: "2026-01-02T00:00:00Z",
          performed_by_name: "Bob",
          hash_at_action: "bb".repeat(32),
        },
      ],
    });
    pipelineService.listJobs.mockResolvedValue([]);
    evidenceService.verifyIntegrity.mockResolvedValue({
      integrity_verified: true,
      hash_set: { sha256: "bb".repeat(32) },
      timestamp: "2026-01-03T00:00:00Z",
    });
  });

  test("test_renders_hash_set_with_copy_buttons", async () => {
    renderWithProviders(<EvidenceDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getAllByText("disk.E01").length).toBeGreaterThan(0);
    });
    expect(
      screen.getAllByRole("button", { name: /Copy SHA/i }).length
    ).toBeGreaterThan(0);
  });

  test("test_custody_chain_shows_entries", async () => {
    renderWithProviders(<EvidenceDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getAllByText("disk.E01").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText(/^Chain of Custody$/));

    await wait(() => {
      expect(screen.getAllByText(/Acquired/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/Alice/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Accessed/i).length).toBeGreaterThan(0);
  });

  test("test_status_timeline_shows_transitions", async () => {
    renderWithProviders(<EvidenceDetail />, { role: "investigator" });
    await wait(() => {
      expect(screen.getAllByText("disk.E01").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText(/^Status History$/));

    await wait(() => {
      expect(screen.getAllByText(/Current/i).length).toBeGreaterThan(0);
    });
  });

  test("test_verify_integrity_shows_result", async () => {
    renderWithProviders(<EvidenceDetail />, { role: "investigator" });
    await wait(() => {
      expect(
        screen.getByRole("button", { name: /Verify Integrity/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Verify Integrity/i }));

    await wait(() => {
      expect(evidenceService.verifyIntegrity).toHaveBeenCalledWith("ev-1");
    });
    await wait(() => {
      expect(
        screen.getByText(/Integrity verification passed/i)
      ).toBeInTheDocument();
    });
  });
});

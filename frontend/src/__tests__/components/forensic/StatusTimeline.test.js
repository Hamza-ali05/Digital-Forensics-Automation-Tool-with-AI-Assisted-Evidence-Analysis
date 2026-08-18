import React from "react";
import { screen } from "@testing-library/react";

import StatusTimeline from "components/forensic/StatusTimeline";
import { renderWithProviders } from "test-utils/render";
import authService from "services/auth.service";

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

describe("StatusTimeline", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
  });

  test("test_renders_entries_in_order", () => {
    const entries = [
      { id: "e1", label: "First current" },
      { id: "e2", label: "Second older" },
      { id: "e3", label: "Third oldest" },
    ];
    renderWithProviders(
      <StatusTimeline
        entries={entries}
        renderEntry={(entry) => <div>{entry.label}</div>}
      />
    );
    const texts = screen.getAllByText(/current|older|oldest/i).map((n) => n.textContent);
    expect(texts[0]).toBe("First current");
    expect(texts[1]).toBe("Second older");
    expect(texts[2]).toBe("Third oldest");
  });

  test("test_current_status_highlighted", () => {
    const entries = [
      { id: "e1", label: "Current item" },
      { id: "e2", label: "Past item" },
    ];
    const { container } = renderWithProviders(
      <StatusTimeline
        entries={entries}
        renderEntry={(entry, _i, isCurrent) => (
          <div data-current={isCurrent ? "yes" : "no"}>{entry.label}</div>
        )}
      />
    );
    expect(screen.getByText("Current item").getAttribute("data-current")).toBe(
      "yes"
    );
    expect(screen.getByText("Past item").getAttribute("data-current")).toBe("no");
    const dots = container.querySelectorAll(".rounded-circle");
    expect(dots[0].style.backgroundColor).toBe("rgb(13, 110, 253)");
  });

  test("test_handles_empty_entries", () => {
    renderWithProviders(
      <StatusTimeline
        entries={[]}
        renderEntry={() => null}
        emptyTitle="No history yet"
        emptyDescription="Timeline entries will appear here."
      />
    );
    expect(screen.getByText("No history yet")).toBeInTheDocument();
    expect(
      screen.getByText(/Timeline entries will appear here/i)
    ).toBeInTheDocument();
  });
});

import React from "react";
import { fireEvent, screen } from "@testing-library/react";

import ChatInterface from "components/forensic/ChatInterface";
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

describe("ChatInterface", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const profile = { id: "1", username: "inv", role_name: "investigator" };
    authService.getStoredUser.mockReturnValue(profile);
    authService.getCurrentUser.mockResolvedValue(profile);
  });

  test("test_renders_message_history", () => {
    renderWithProviders(
      <ChatInterface
        messages={[
          { role: "user", content: "What happened?" },
          { role: "assistant", content: "Suspicious login detected.", confidence: 0.9 },
        ]}
        onSend={jest.fn()}
      />
    );
    expect(screen.getByText("What happened?")).toBeInTheDocument();
    expect(screen.getByText("Suspicious login detected.")).toBeInTheDocument();
  });

  test("test_send_triggers_callback", () => {
    const onSend = jest.fn();
    renderWithProviders(<ChatInterface messages={[]} onSend={onSend} />);

    fireEvent.change(screen.getByLabelText(/Ask a question about the evidence/i), {
      target: { value: "List critical artefacts" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Send/i }));

    expect(onSend).toHaveBeenCalledWith("List critical artefacts");
  });

  test("test_shows_suggestions", () => {
    renderWithProviders(
      <ChatInterface
        messages={[]}
        onSend={jest.fn()}
        suggestions={[
          "What artefacts were recovered?",
          "Are there CRITICAL findings?",
        ]}
      />
    );
    expect(screen.getByText(/Suggested questions/i)).toBeInTheDocument();
    expect(screen.getByText("What artefacts were recovered?")).toBeInTheDocument();
    expect(screen.getByText("Are there CRITICAL findings?")).toBeInTheDocument();
  });
});

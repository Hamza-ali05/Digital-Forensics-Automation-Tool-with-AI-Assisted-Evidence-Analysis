import React from "react";
import { fireEvent, screen, wait } from "@testing-library/react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Questionnaire from "pages/evaluation/Questionnaire";
import evaluationService from "services/evaluation.service";

jest.mock("services/evaluation.service", () => ({
  __esModule: true,
  default: {
    getQuestionnaire: jest.fn(),
    submitQuestionnaire: jest.fn(),
  },
}));

describe("Questionnaire", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    evaluationService.getQuestionnaire.mockResolvedValue({
      instrument_version: "1.0.0",
      questions: [
        { id: "Q1", text: "Useful?", type: "likert" },
        { id: "Q2", text: "Accurate?", type: "likert" },
        { id: "Q3", text: "Clear?", type: "likert" },
        { id: "Q4", text: "Would use?", type: "likert" },
        { id: "Q5", text: "Compare?", type: "likert" },
        { id: "Q6", text: "Feedback", type: "open", scale: "free_text" },
      ],
    });
  });

  test("test_renders_without_auth", async () => {
    render(
      <MemoryRouter>
        <Questionnaire />
      </MemoryRouter>
    );
    await wait(() => {
      expect(screen.getByText(/DFAT Usability Assessment/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Sign in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Logout/i)).not.toBeInTheDocument();
  });

  test("test_all_questions_displayed", async () => {
    render(
      <MemoryRouter>
        <Questionnaire />
      </MemoryRouter>
    );
    await wait(() => {
      expect(screen.getByText("Useful?")).toBeInTheDocument();
    });
    expect(screen.getByText("Accurate?")).toBeInTheDocument();
    expect(screen.getByText("Clear?")).toBeInTheDocument();
    expect(screen.getByText("Would use?")).toBeInTheDocument();
    expect(screen.getByText("Compare?")).toBeInTheDocument();
    expect(screen.getByText("Feedback")).toBeInTheDocument();
  });

  test("test_validation_requires_all_likert", async () => {
    render(
      <MemoryRouter>
        <Questionnaire />
      </MemoryRouter>
    );
    await wait(() => {
      expect(screen.getByText(/Submit anonymous response/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Submit anonymous response/i));
    await wait(() => {
      expect(
        screen.getAllByText(/Please select a rating from 1 to 5/i).length
      ).toBeGreaterThan(0);
    });
    expect(evaluationService.submitQuestionnaire).not.toHaveBeenCalled();
  });

  test("test_submission_shows_thank_you", async () => {
    evaluationService.submitQuestionnaire.mockResolvedValue({
      participant_id: "part-123",
    });
    render(
      <MemoryRouter>
        <Questionnaire />
      </MemoryRouter>
    );
    await wait(() => {
      expect(screen.getByText("Useful?")).toBeInTheDocument();
    });

    ["Q1", "Q2", "Q3", "Q4", "Q5"].forEach((id) => {
      fireEvent.click(
        screen.getByLabelText(new RegExp(`${id}: 3 Neutral`, "i"))
      );
    });

    fireEvent.click(screen.getByText(/Submit anonymous response/i));
    await wait(() => {
      expect(screen.getByText(/Thank you/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/part-123/)).toBeInTheDocument();
  });
});

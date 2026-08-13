import React from "react";
import { render, screen } from "@testing-library/react";

import StatusBadge from "components/common/StatusBadge";
import { CASE_STATUS_COLOURS, SUSPICION_COLOURS } from "utils/constants";

describe("StatusBadge", () => {
  test("test_renders_correct_colour_for_suspicion", () => {
    render(<StatusBadge status="critical" type="suspicion" />);
    const badge = screen.getByText("Critical");
    expect(badge).toHaveStyle(`background-color: ${SUSPICION_COLOURS.critical}`);
  });

  test("test_renders_correct_colour_for_case_status", () => {
    render(<StatusBadge status="active" type="case" />);
    const badge = screen.getByText("Active");
    expect(badge).toHaveStyle(`background-color: ${CASE_STATUS_COLOURS.active}`);
  });

  test("test_renders_correct_text", () => {
    render(<StatusBadge status="under_review" type="case" />);
    expect(screen.getByText("Under Review")).toBeInTheDocument();
  });
});

import React from "react";
import { render, screen } from "@testing-library/react";

import StatusBadge from "components/common/StatusBadge";
import {
  CASE_STATUS_COLOURS,
  EVIDENCE_STATUS_COLOURS,
  PIPELINE_STATUS_COLOURS,
  SUSPICION_COLOURS,
} from "utils/constants";

describe("StatusBadge", () => {
  test("test_case_status_colours", () => {
    render(<StatusBadge status="active" type="case" />);
    expect(screen.getByText("Active")).toHaveStyle(
      `background-color: ${CASE_STATUS_COLOURS.active}`
    );
  });

  test("test_evidence_status_colours", () => {
    render(<StatusBadge status="validated" type="evidence" />);
    expect(screen.getByText("Validated")).toHaveStyle(
      `background-color: ${EVIDENCE_STATUS_COLOURS.validated}`
    );
  });

  test("test_suspicion_level_colours", () => {
    render(<StatusBadge status="critical" type="suspicion" />);
    expect(screen.getByText("Critical")).toHaveStyle(
      `background-color: ${SUSPICION_COLOURS.critical}`
    );
  });

  test("test_pipeline_status_colours", () => {
    render(<StatusBadge status="running" type="pipeline" />);
    expect(screen.getByText("Running")).toHaveStyle(
      `background-color: ${PIPELINE_STATUS_COLOURS.running}`
    );
  });

  test("test_unknown_status_default", () => {
    render(<StatusBadge status="mystery" type="case" />);
    expect(screen.getByText("Mystery")).toHaveStyle(
      "background-color: #6c757d"
    );
  });
});

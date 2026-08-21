import {
  formatBytes,
  formatCaseId,
  formatDate,
  formatDuration,
  formatEvidenceId,
  formatHash,
  formatJobId,
  formatPercentage,
  humanizeFileName,
  humanizeLabel,
} from "utils/formatters";

describe("formatters", () => {
  test("test_formatBytes_various_sizes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1073741824)).toBe("1.0 GB");
  });

  test("test_formatDuration_various_durations", () => {
    expect(formatDuration(154)).toBe("2m 34s");
    expect(formatDuration(4500)).toBe("1h 15m");
    expect(formatDuration(12)).toBe("12s");
  });

  test("test_formatHash_truncation", () => {
    expect(formatHash("a1b2c3d4e5f67890", 8)).toBe("a1b2c3d4...");
    expect(formatHash("abc", 8)).toBe("abc");
  });

  test("test_formatDate_valid_iso", () => {
    const formatted = formatDate("2026-06-25T14:30:00");
    expect(formatted).toMatch(/25 Jun 2026/);
    expect(formatted).toMatch(/14:30/);
  });

  test("test_formatPercentage", () => {
    expect(formatPercentage(87.5)).toBe("87.5%");
    expect(formatPercentage(100, 0)).toBe("100%");
  });

  test("test_formatEvidenceId_and_caseId", () => {
    expect(formatEvidenceId("ab415eeb-1234-5678")).toBe("EVD-ab415e");
    expect(formatCaseId("cafebabe-0001")).toBe("CASE-cafeba");
    expect(formatJobId("deadbeef-9999")).toBe("JOB-deadbe");
  });

  test("test_humanizeFileName_strips_timestamp_suffix", () => {
    expect(humanizeFileName("inventory-1786663537723.dd")).toBe("inventory.dd");
    expect(humanizeFileName("disk.E01")).toBe("disk.E01");
  });

  test("test_humanizeLabel_strips_numeric_and_status_suffixes", () => {
    expect(humanizeLabel("E2E Case 1786661719092")).toBe("E2E Case");
    expect(humanizeLabel("Dev Sample — Active")).toBe("Dev Sample");
  });
});

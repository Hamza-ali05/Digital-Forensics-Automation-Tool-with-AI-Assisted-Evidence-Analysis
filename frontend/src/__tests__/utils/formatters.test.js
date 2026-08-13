import {
  formatBytes,
  formatDate,
  formatDuration,
  formatHash,
  formatPercentage,
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
});

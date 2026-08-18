const fs = require("fs");
const path = require("path");
const AxeBuilder = require("@axe-core/playwright").default;

function formatViolations(violations) {
  return violations
    .map((v) => {
      const nodes = (v.nodes || [])
        .map((n) => `    - ${n.target.join(" ")} ${n.failureSummary || ""}`)
        .join("\n");
      return `[${v.impact}] ${v.id}: ${v.help} (${(v.nodes || []).length} nodes)\n${nodes}`;
    })
    .join("\n");
}

function logViolations(violations, pageName) {
  if (!violations.length) {
    // eslint-disable-next-line no-console
    console.log(`[axe:${pageName}] no violations`);
    return;
  }
  // eslint-disable-next-line no-console
  console.log(`[axe:${pageName}] ${violations.length} violation(s):\n${formatViolations(violations)}`);
}

/**
 * Run axe and fail the test on critical/serious impacts.
 */
async function expectNoCriticalAxeViolations(page, pageName) {
  await page.locator(".preloader").waitFor({ state: "hidden", timeout: 20_000 }).catch(() => {});
  const results = await new AxeBuilder({ page })
    .exclude("#webpack-dev-server-client-overlay")
    .exclude(".webpack-dev-server-client-overlay")
    .analyze();
  logViolations(results.violations, pageName);
  try {
    const outDir = path.join(__dirname, "..", "test-results");
    fs.mkdirSync(outDir, { recursive: true });
    const summary = results.violations.length
      ? formatViolations(results.violations)
      : "no violations";
    fs.writeFileSync(path.join(outDir, `axe-${pageName}.txt`), summary);
  } catch {
    // Ignore dump failures — assertions still use `results`.
  }
  const blocking = results.violations.filter((v) =>
    ["critical", "serious"].includes(v.impact)
  );
  if (blocking.length) {
    throw new Error(
      `Axe critical/serious violations on ${pageName}:\n${formatViolations(blocking)}`
    );
  }
}

module.exports = {
  expectNoCriticalAxeViolations,
  logViolations,
  formatViolations,
};

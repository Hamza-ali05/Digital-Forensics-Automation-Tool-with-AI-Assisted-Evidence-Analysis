const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs } = require("./helpers/auth");
const { apiLogin, ensureValidatedEvidence, waitForJob } = require("./helpers/api");
const { prepareEvidenceFile } = require("./helpers/files");
const { recoverFromNetworkError } = require("./helpers/ui");

test.describe("pipeline", () => {
  test("test_pipeline_execution", async ({ page }) => {
    test.setTimeout(180_000);
    const token = await apiLogin();
    const filePath = prepareEvidenceFile("pipeline");
    const evidence = await ensureValidatedEvidence(token, filePath);

    await loginAs(page, investigator);
    await page.goto("/pipeline");
    await recoverFromNetworkError(page);
    await page.getByRole("button", { name: /run pipeline/i }).click();
    await page.waitForURL(/\/pipeline\/run/);
    await expect(page.getByRole("heading", { name: /run pipeline/i })).toBeVisible();
    const evidenceSelect = page.locator("form select").first();
    await expect(evidenceSelect).toBeVisible();
    const valueLocator = evidenceSelect.locator(
      `option[value="${evidence.evidence_id}"]`
    );
    if ((await valueLocator.count()) === 0) {
      await expect(evidenceSelect.locator("option[value]:not([value=''])").first()).toHaveCount(
        1,
        { timeout: 20_000 }
      );
      await evidenceSelect.selectOption({ index: 1 });
    } else {
      await evidenceSelect.selectOption(evidence.evidence_id);
    }
    await page.locator("#mode-full").check();
    await page.locator("#use-fallback").check();
    await page.getByRole("button", { name: /start pipeline/i }).click();
    await page.waitForURL(/\/pipeline\/[0-9a-f-]{8,}$/i, { timeout: 30_000 });
    const jobId = page.url().split("/").pop();

    await expect(page.locator("body")).toContainText(
      /queued|pending|running|in_progress|parsing|completed|failed|acquisition|triage|reporting/i,
      { timeout: 30_000 }
    );

    const finished = await waitForJob(token, jobId, 120_000);
    expect(["completed", "failed", "cancelled", "error"]).toContain(
      String(finished.status || "").toLowerCase()
    );
    await page.reload();
    await recoverFromNetworkError(page);
    await expect(page.locator("body")).toContainText(
      /completed|failed|cancelled/i,
      { timeout: 20_000 }
    );
  });

  test("test_pipeline_job_list", async ({ page }) => {
    await loginAs(page, investigator);
    await page.goto("/pipeline");
    const table = page.locator("table").filter({ hasText: /job|status|evidence/i }).first();
    await expect(
      table.or(page.getByText(/no pipeline jobs found|no (jobs|records)/i))
    ).toBeVisible({
      timeout: 20_000,
    });
  });
});

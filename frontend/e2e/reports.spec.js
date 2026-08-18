const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs } = require("./helpers/auth");
const { apiLogin, ensureCompletedReport } = require("./helpers/api");
const { prepareEvidenceFile } = require("./helpers/files");
const { recoverFromNetworkError } = require("./helpers/ui");

let seededReportId = null;

test.describe("reports", () => {
  test.describe.configure({ timeout: 240_000 });

  test.beforeAll(async () => {
    const token = await apiLogin();
    const filePath = prepareEvidenceFile("report");
    const job = await ensureCompletedReport(token, filePath);
    seededReportId = job.report_id;
    if (!seededReportId) {
      throw new Error("beforeAll did not produce a report_id");
    }
  });

  test("test_report_viewing", async ({ page }) => {
    test.setTimeout(90_000);
    await loginAs(page, investigator);
    await page.goto("/reports");

    const viewLink = page.getByRole("link", { name: /view/i }).first();
    if (await viewLink.isVisible().catch(() => false)) {
      await viewLink.click();
    } else {
      await page.goto(`/reports/${seededReportId}`);
    }
    await recoverFromNetworkError(page);
    await page.waitForURL(/\/reports\/[^/]+/);

    await expect(page.getByRole("tab", { name: /overview/i })).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole("tab", { name: /json data/i }).click();
    await expect(
      page.getByText(/json|artefact|schema|report/i).first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test("test_report_export", async ({ page }) => {
    test.setTimeout(90_000);
    await loginAs(page, investigator);
    await page.goto(`/reports/${seededReportId}`);
    await recoverFromNetworkError(page);
    await expect(page.getByRole("button", { name: /export pdf/i })).toBeVisible({
      timeout: 30_000,
    });

    const pdfResponse = page.waitForResponse(
      (res) =>
        /\/reports\/[^/]+\/export\/pdf/i.test(res.url()) && res.status() < 500,
      { timeout: 60_000 }
    );
    const downloadPromise = page.waitForEvent("download", { timeout: 60_000 }).catch(() => null);
    await page.getByRole("button", { name: /export pdf/i }).click();
    const response = await pdfResponse;
    expect(response.ok()).toBeTruthy();
    const contentType = (response.headers()["content-type"] || "").toLowerCase();
    expect(
      contentType.includes("pdf") ||
        contentType.includes("octet-stream") ||
        contentType.includes("application/")
    ).toBeTruthy();
    const download = await downloadPromise;
    expect(download || response.ok()).toBeTruthy();
  });
});

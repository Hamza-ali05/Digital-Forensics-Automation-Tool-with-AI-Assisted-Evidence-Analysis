const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs } = require("./helpers/auth");
const { apiLogin, ensureValidatedEvidence, ensureCompletedReport } = require("./helpers/api");
const { prepareEvidenceFile } = require("./helpers/files");
const { recoverFromNetworkError } = require("./helpers/ui");
const { expectNoCriticalAxeViolations } = require("./helpers/accessibility");

async function seedEvidence() {
  const token = await apiLogin();
  const evidence = await ensureValidatedEvidence(token, prepareEvidenceFile("a11y"));
  return evidence.evidence_id;
}

async function seedReport() {
  const token = await apiLogin();
  const job = await ensureCompletedReport(token, prepareEvidenceFile("a11y-report"));
  return job.report_id;
}

test.describe("accessibility", () => {
  test.describe.configure({ timeout: 180_000 });

  test("test_login_page_accessible", async ({ page }) => {
    await page.goto("/auth/login");
    await expect(page.getByRole("heading", { name: /sign in to dfat/i })).toBeVisible();
    await expectNoCriticalAxeViolations(page, "login");
  });

  test("test_dashboard_accessible", async ({ page }) => {
    await loginAs(page, investigator);
    await page.goto("/dashboard");
    await recoverFromNetworkError(page);
    await expect(page.getByRole("heading", { name: /^dashboard$/i })).toBeVisible();
    await expectNoCriticalAxeViolations(page, "dashboard");
  });

  test("test_case_list_accessible", async ({ page }) => {
    await loginAs(page, investigator);
    await page.goto("/cases");
    await recoverFromNetworkError(page);
    await expect(page.getByRole("heading", { name: /^cases$/i })).toBeVisible();
    await expectNoCriticalAxeViolations(page, "case-list");
  });

  test("test_evidence_detail_accessible", async ({ page }) => {
    const evidenceId = await seedEvidence();
    expect(evidenceId).toBeTruthy();
    await loginAs(page, investigator);
    await page.goto(`/evidence/${evidenceId}`);
    await recoverFromNetworkError(page);
    await expect(page.locator("h1, h4").first()).toBeVisible({ timeout: 30_000 });
    await expectNoCriticalAxeViolations(page, "evidence-detail");
  });

  test("test_questionnaire_accessible", async ({ page }) => {
    await page.goto("/questionnaire");
    await expect(
      page.getByRole("heading", { name: /usability assessment/i })
    ).toBeVisible();
    await expectNoCriticalAxeViolations(page, "questionnaire");
  });

  test("test_report_detail_accessible", async ({ page }) => {
    const reportId = await seedReport();
    expect(reportId).toBeTruthy();
    await loginAs(page, investigator);
    await page.goto(`/reports/${reportId}`);
    await recoverFromNetworkError(page);
    await expect(page.locator("h1, h4").first()).toBeVisible({ timeout: 30_000 });
    await expectNoCriticalAxeViolations(page, "report-detail");
  });
});

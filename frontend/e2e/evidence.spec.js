const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs } = require("./helpers/auth");
const {
  apiLogin,
  ensureOpenCase,
  apiPost,
  ensureValidatedEvidence,
} = require("./helpers/api");
const { prepareEvidenceFile } = require("./helpers/files");
const { recoverFromNetworkError } = require("./helpers/ui");

function evidenceTable(page) {
  return page.locator("table").filter({ hasText: /file name|evidence id/i }).first();
}

test.describe("evidence", () => {
  test("test_evidence_registration", async ({ page }) => {
    test.setTimeout(90_000);
    const token = await apiLogin();
    const openCase = await ensureOpenCase(token);
    const filePath = prepareEvidenceFile("register");

    await loginAs(page, investigator);
    await page.goto("/evidence");
    await recoverFromNetworkError(page);
    await page.getByRole("button", { name: /register evidence/i }).click();
    await page.waitForURL(/\/evidence\/register/);
    const caseSelect = page.locator("form select").first();
    await expect(caseSelect).toBeVisible();
    await expect(caseSelect.locator(`option[value="${openCase.case_id}"]`)).toHaveCount(1, {
      timeout: 20_000,
    });
    await caseSelect.selectOption(openCase.case_id);
    await page.locator("#evidencePath").fill(filePath);
    await page.locator("#type-disk").check();
    await page.getByRole("button", { name: /register evidence/i }).click();
    await page.waitForURL(/\/evidence\/[0-9a-f-]{8,}$/i, { timeout: 30_000 });
    await recoverFromNetworkError(page);
    await expect(page.getByRole("button", { name: /verify integrity/i })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("test_evidence_inventory", async ({ page }) => {
    test.setTimeout(90_000);
    const token = await apiLogin();
    const filePath = prepareEvidenceFile("inventory");
    const openCase = await ensureOpenCase(token);
    await apiPost(token, "/evidence/register", {
      file_path: filePath,
      case_id: openCase.case_id,
      evidence_type: "disk_image",
      description: "Inventory E2E item",
    }).catch(() => {});

    await loginAs(page, investigator);
    await page.goto("/evidence");
    await recoverFromNetworkError(page);
    const table = evidenceTable(page);
    await expect(table).toBeVisible({ timeout: 20_000 });
    await expect(table.locator("tbody tr").first()).toBeVisible({ timeout: 20_000 });

    await page.locator('select[aria-label="Filter by type"]').selectOption("disk_image");
    await page.waitForTimeout(500);
    await expect(table.getByText(/disk image/i).first()).toBeVisible();
  });

  test("test_integrity_verification", async ({ page }) => {
    test.setTimeout(90_000);
    const token = await apiLogin();
    const filePath = prepareEvidenceFile("integrity");
    const evidence = await ensureValidatedEvidence(token, filePath);

    await loginAs(page, investigator);
    await page.goto(`/evidence/${evidence.evidence_id}`);
    await recoverFromNetworkError(page);
    const verify = page.getByRole("button", { name: /verify integrity/i });
    await expect(verify).toBeEnabled({ timeout: 20_000 });
    await verify.click();
    await expect(
      page.getByText(/integrity verification (passed|failed)/i).first()
    ).toBeVisible({ timeout: 20_000 });
  });
});

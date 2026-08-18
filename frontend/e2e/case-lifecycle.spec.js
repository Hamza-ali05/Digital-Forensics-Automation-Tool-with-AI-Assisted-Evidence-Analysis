const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs, getStoredUser } = require("./helpers/auth");
const { recoverFromNetworkError } = require("./helpers/ui");

/** Prefer the main content data table (sidebar may include hidden tables). */
function mainTable(page, headerHint) {
  return page.locator("table").filter({ hasText: headerHint }).first();
}

test.describe("case lifecycle", () => {
  test("test_create_and_open_case", async ({ page }) => {
    test.setTimeout(90_000);
    await loginAs(page, investigator);
    const user = await getStoredUser(page);
    const userId = user?.id || user?.user_id;
    expect(userId).toBeTruthy();

    const caseName = `E2E Case ${Date.now()}`;
    await page.goto("/cases/new");
    await page.locator("#caseName").fill(caseName);
    await page.locator("#caseDescription").fill("Created by Playwright E2E");
    await page.getByRole("button", { name: /create case/i }).click();
    await page.waitForURL(/\/cases\/([^/]+)$/);
    await recoverFromNetworkError(page);
    await expect(page.getByText(caseName).first()).toBeVisible({ timeout: 20_000 });

    await page.getByRole("tab", { name: /investigators/i }).click();
    await page.getByRole("button", { name: /assign investigator/i }).click();

    const modal = page.getByRole("dialog").filter({ hasText: /assign investigator/i });
    await expect(modal).toBeVisible();

    const userSelect = modal.getByRole("combobox").filter({ hasText: /select user/i });
    const userInput = modal.getByPlaceholder("User UUID");
    if (await userSelect.count()) {
      const option = userSelect.locator(`option[value="${userId}"]`);
      if ((await option.count()) > 0) {
        await userSelect.selectOption(userId);
      } else {
        await userSelect.selectOption({ index: 1 });
      }
    } else {
      await userInput.fill(userId);
    }
    await modal
      .locator("select")
      .filter({ has: page.locator('option[value="lead"]') })
      .selectOption("lead");
    await modal.getByRole("button", { name: /^assign$/i }).click();
    await expect(modal).toBeHidden({ timeout: 15_000 });
    await expect(page.getByText(/^lead$/i).first()).toBeVisible();

    const openCase = page.getByRole("button", { name: /open case/i }).first();
    await expect(openCase).toBeEnabled({ timeout: 15_000 });
    await openCase.click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /open case/i })
      .click();

    await expect(
      page.locator(".status-badge").filter({ hasText: /^open$/i }).first()
    ).toBeVisible({ timeout: 20_000 });
  });

  test("test_case_list_and_filter", async ({ page }) => {
    await loginAs(page, investigator);
    await page.goto("/cases");
    await recoverFromNetworkError(page);
    await expect(page.getByRole("heading", { name: /^cases$/i })).toBeVisible();
    const table = mainTable(page, /case name/i);
    await expect(table).toBeVisible({ timeout: 20_000 });

    const statusFilter = page.locator('select[aria-label="Filter by status"]');
    await statusFilter.selectOption({ label: "Active" });
    await expect(statusFilter).toHaveValue("active");
    await page.waitForTimeout(1000);
    await recoverFromNetworkError(page);
    await expect(table).toBeVisible();
    const badges = table.locator(".status-badge");
    if ((await badges.count()) > 0) {
      await expect(badges.first()).toBeVisible();
      const labels = await badges.allTextContents();
      for (const label of labels) {
        expect(label.trim().toLowerCase()).toBe("active");
      }
    }
  });

  test("test_case_detail_tabs", async ({ page }) => {
    await loginAs(page, investigator);
    await page.goto("/cases");
    await recoverFromNetworkError(page);
    const table = mainTable(page, /case name/i);
    await expect(table).toBeVisible({ timeout: 20_000 });
    await table.getByRole("link", { name: /^view$/i }).first().click();
    await page.waitForURL(/\/cases\/[^/]+/);
    await recoverFromNetworkError(page);

    await page.getByRole("tab", { name: /investigators/i }).click();
    await expect(page.getByRole("heading", { name: /^investigators$/i })).toBeVisible();

    await page.getByRole("tab", { name: /^evidence$/i }).click();
    await expect(page.getByRole("heading", { name: /^evidence$/i })).toBeVisible();

    await page.getByRole("tab", { name: /activity/i }).click();
    await expect(page.getByRole("heading", { name: /^activity$/i })).toBeVisible();
  });
});

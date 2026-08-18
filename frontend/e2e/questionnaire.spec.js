const { test, expect } = require("@playwright/test");

test.describe("questionnaire", () => {
  test("test_questionnaire_no_auth", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/questionnaire");
    await expect(
      page.getByRole("heading", { name: /usability assessment/i })
    ).toBeVisible({ timeout: 20_000 });

    // Answer each Likert question (Q1–Q5) with rating 4
    for (const qid of ["Q1", "Q2", "Q3", "Q4", "Q5"]) {
      await page.getByRole("radio", { name: new RegExp(`^${qid}: 4`) }).check();
    }

    await page.getByRole("button", { name: /submit anonymous response/i }).click();
    await expect(page.getByRole("heading", { name: /thank you/i })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/participant id/i)).toBeVisible();
    await expect(page.locator("code").first()).not.toHaveText("—");
  });

  test("test_questionnaire_validation", async ({ page }) => {
    await page.goto("/questionnaire");
    await expect(
      page.getByRole("heading", { name: /usability assessment/i })
    ).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: /submit anonymous response/i }).click();
    await expect(page.locator(".invalid-feedback").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /thank you/i })).toHaveCount(0);
  });
});

const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs, getStoredUser, logoutViaMenu } = require("./helpers/auth");

test.describe("auth", () => {
  test("test_login_flow", async ({ page }) => {
    await page.goto("/auth/login");
    await expect(page.getByRole("heading", { name: /sign in to dfat/i })).toBeVisible();
    await page.locator('input[autocomplete="username"]').fill(investigator.username);
    await page.locator('input[autocomplete="current-password"]').fill(investigator.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/dashboard/);
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("nav .media-body .fw-bold")).toHaveText(
      investigator.username
    );
  });

  test("test_login_invalid_credentials", async ({ page }) => {
    await page.goto("/auth/login");
    await page.locator('input[autocomplete="username"]').fill(investigator.username);
    await page.locator('input[autocomplete="current-password"]').fill("WrongPassword!999");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/invalid username or password/i)).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test("test_logout_flow", async ({ page }) => {
    await loginAs(page, investigator);
    await logoutViaMenu(page);
    await expect(page).toHaveURL(/\/auth\/login/);
    await expect(page.getByRole("heading", { name: /sign in to dfat/i })).toBeVisible();
  });

  test("test_session_persistence", async ({ page }) => {
    await loginAs(page, investigator);
    const before = await getStoredUser(page);
    expect(before?.username || before?.user?.username).toBeTruthy();
    await page.reload();
    await expect(page).not.toHaveURL(/\/auth\/login/);
    await expect(page.locator("nav .media-body .fw-bold")).toHaveText(
      investigator.username,
      { timeout: 15_000 }
    );
    const after = await getStoredUser(page);
    expect(after).toBeTruthy();
  });
});

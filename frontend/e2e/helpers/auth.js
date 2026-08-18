const { investigator } = require("./credentials");

/**
 * Sign in through the UI and land on the dashboard.
 * Login labels are not htmlFor-associated; use autocomplete attributes.
 */
async function loginAs(page, user = investigator) {
  await page.goto("/auth/login");
  await page.locator('input[autocomplete="username"]').fill(user.username);
  await page.locator('input[autocomplete="current-password"]').fill(user.password);

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.getByRole("button", { name: /sign in/i }).click();
    try {
      await page.waitForURL(/\/dashboard/, { timeout: 12_000 });
      return;
    } catch (err) {
      const network = page.getByText(/network error/i);
      if (attempt < 2 && (await network.isVisible().catch(() => false))) {
        await page.waitForTimeout(2000);
        continue;
      }
      throw err;
    }
  }
}

/**
 * Read the cached user profile from localStorage.
 */
async function getStoredUser(page) {
  return page.evaluate(() => {
    try {
      return JSON.parse(localStorage.getItem("dfat_user") || "null");
    } catch {
      return null;
    }
  });
}

/**
 * Open the topbar user menu and click Logout.
 */
async function logoutViaMenu(page) {
  await page.locator("nav .dropdown").last().locator("a.nav-link").first().click();
  await page.locator(".user-dropdown").getByText("Logout", { exact: true }).click();
  await page.waitForURL(/\/auth\/login/);
}

module.exports = {
  loginAs,
  getStoredUser,
  logoutViaMenu,
};

const { test, expect } = require("@playwright/test");
const { investigator } = require("./helpers/credentials");
const { loginAs } = require("./helpers/auth");
const { recoverFromNetworkError } = require("./helpers/ui");

const VIEWPORTS = {
  mobile: { width: 375, height: 667 },
  tablet: { width: 768, height: 1024 },
  desktop: { width: 1920, height: 1080 },
};

async function loginOnViewport(page, viewport) {
  await page.setViewportSize(viewport);
  await loginAs(page, investigator);
  await recoverFromNetworkError(page);
}

test.describe("responsive", () => {
  test("test_sidebar_collapses_on_mobile", async ({ page }) => {
    await loginOnViewport(page, VIEWPORTS.mobile);
    await page.goto("/dashboard");
    await recoverFromNetworkError(page);

    const hamburger = page.getByRole("button", { name: /toggle navigation|open navigation/i });
    await expect(hamburger.first()).toBeVisible();

    const sidebar = page.locator(".sidebar");
    await expect(sidebar).toBeHidden();

    const content = page.locator("#main-content, main.content").first();
    const box = await content.boundingBox();
    expect(box).toBeTruthy();
    expect(box.width).toBeGreaterThanOrEqual(VIEWPORTS.mobile.width - 24);

    await page.setViewportSize(VIEWPORTS.tablet);
    await expect(page.locator(".sidebar")).toBeVisible();

    await page.setViewportSize(VIEWPORTS.desktop);
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(hamburger.first()).toBeHidden();
  });

  test("test_data_tables_scroll_on_mobile", async ({ page }) => {
    await loginOnViewport(page, VIEWPORTS.mobile);
    await page.goto("/cases");
    await recoverFromNetworkError(page);
    await expect(page.getByRole("heading", { name: /^cases$/i })).toBeVisible();

    const wrapper = page.locator(".table-responsive").first();
    await expect(wrapper).toBeVisible();
    const overflowX = await wrapper.evaluate((el) => getComputedStyle(el).overflowX);
    expect(["auto", "scroll"]).toContain(overflowX);

    const table = wrapper.locator("table").first();
    const tableBox = await table.boundingBox();
    const wrapBox = await wrapper.boundingBox();
    expect(tableBox).toBeTruthy();
    expect(wrapBox).toBeTruthy();
    expect(tableBox.width).toBeGreaterThanOrEqual(wrapBox.width - 2);
  });

  test("test_dashboard_cards_stack_on_mobile", async ({ page }) => {
    await loginOnViewport(page, VIEWPORTS.mobile);
    await page.goto("/dashboard");
    await recoverFromNetworkError(page);

    const cards = page.locator("[data-testid='dashboard-stats'] .card");
    await expect(cards.first()).toBeVisible();
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);

    const first = await cards.nth(0).boundingBox();
    const second = await cards.nth(1).boundingBox();
    expect(first && second).toBeTruthy();
    expect(second.y).toBeGreaterThan(first.y + first.height / 2);
    expect(Math.abs(second.x - first.x)).toBeLessThan(24);

    await page.setViewportSize(VIEWPORTS.desktop);
    const desktopFirst = await cards.nth(0).boundingBox();
    const desktopSecond = await cards.nth(1).boundingBox();
    expect(desktopSecond.x).toBeGreaterThan(desktopFirst.x + 40);
  });

  test("test_forms_fill_width_on_mobile", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto("/auth/login");
    await expect(page.getByRole("heading", { name: /sign in to dfat/i })).toBeVisible();

    const loginGroup = page.locator("form .input-group").first();
    const loginGroupBox = await loginGroup.boundingBox();
    expect(loginGroupBox).toBeTruthy();
    expect(loginGroupBox.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.65);

    await loginOnViewport(page, VIEWPORTS.mobile);
    await page.goto("/cases");
    await recoverFromNetworkError(page);
    const searchGroup = page.locator(".search-bar, #case-search").first();
    const searchBox = await searchGroup.boundingBox();
    expect(searchBox).toBeTruthy();
    expect(searchBox.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.65);
  });
});

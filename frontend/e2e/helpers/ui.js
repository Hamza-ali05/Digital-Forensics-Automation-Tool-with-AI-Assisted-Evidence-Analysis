/**
 * Retry through ApiErrorDisplay network banners that appear under SQLite load.
 */
async function recoverFromNetworkError(page, attempts = 5) {
  for (let i = 0; i < attempts; i += 1) {
    const banner = page.getByText(/network error/i);
    if (!(await banner.isVisible().catch(() => false))) {
      return;
    }
    const retry = page.getByRole("button", { name: /retry/i });
    if (await retry.count()) {
      await retry.first().click();
    } else {
      await page.reload();
    }
    await page.waitForTimeout(1500);
  }
}

module.exports = {
  recoverFromNetworkError,
};

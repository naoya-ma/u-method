import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {

  // Go to https://www.google.com/
  await page.goto('https://www.google.com/');
  await expect(page).toHaveScreenshot();

  // Click text=ログインせずに使う
  await page.frameLocator('iframe[role="presentation"]').locator('text=ログインせずに使う').click();

  // Click [aria-label="検索"]
  await page.locator('[aria-label="検索"]').click();
  await page.type('input[name=q]', '大谷翔平');
  await page.click('input[name=btnK]:visible');
  await expect(page).toHaveScreenshot();

  // Click [aria-label="検索"]
  await page.locator('[aria-label="検索"]').click();
  // Fill [aria-label="検索"]
  await page.locator('[aria-label="検索"]').fill('KDDI 通信障害');
  // Press Enter
  await page.locator('[aria-label="検索"]').press('Enter');

  await expect(page).toHaveScreenshot();


});

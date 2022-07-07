// npx playwright test textcompare.spec.ts --headed -u

import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {

  // Go to https://www.google.com/
  await page.goto('https://www.google.com/');

  await page.type('input[name=q]', '7zip 未修正 脆弱性');
  await page.click('input[name=btnK]:visible');
  await expect(page).toHaveScreenshot();

  await expect(page.locator('#cnt')).toContainText('約 53,200 件');
  
});

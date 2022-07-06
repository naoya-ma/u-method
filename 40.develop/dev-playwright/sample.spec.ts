import { test, expect } from '@playwright/test';
test('test', async ({ page }) => {
  // Go to https://www.google.com/
  await page.goto('https://www.google.com/');
  // Click text=ログインせずに使う
  await page.frameLocator('iframe[role="presentation"]').locator('text=ログインせずに使う').click();
  // Click [aria-label="検索"]
  await page.locator('[aria-label="検索"]').click();
  // Fill [aria-label="検索"]
  await page.locator('[aria-label="検索"]').fill('KDDI t');
  // Click text=kddi 通信障害 >> nth=0
  await page.locator('text=kddi 通信障害').first().click();
  //await expect(page).toHaveURL('https://www.google.com/search?q=kddi+%E9%80%9A%E4%BF%A1%E9%9A%9C%E5%AE%B3&source=hp&ei=AMzEYrzABoKl-Qbb6aHoAQ&iflsig=AJiK0e8AAAAAYsTaEFh19DSEYCBPHYk20cqkZWfWJ9JR&oq=KDDI+t&gs_lcp=Cgdnd3Mtd2l6EAEYADINCAAQgAQQsQMQgwEQBDIGCAAQBBADMg0IABCABBCxAxCDARAEMg0IABCABBCxAxCDARAEMgYIABAEEAMyBggAEAQQAzIGCAAQBBADMgYIABAEEANQvjVYvjVgg2JoAXAAeACAAVGIAVGSAQExmAEAoAEBsAEA&sclient=gws-wiz');
  await page.screenshot({ path: 'shotaniNews.png'});
});

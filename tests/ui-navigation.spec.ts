import {expect, test} from '@playwright/test';

test('user can move through primary navigation tabs', async ({page}) => {
  await page.goto('/');

  await expect(page.getByText(/Good morning\./i)).toBeVisible();

  await page.getByRole('button', {name: /Family/i}).click();
  await expect(page.getByText(/Household/i)).toBeVisible();

  await page.getByRole('button', {name: /Alerts/i}).click();
  await expect(page.getByText(/Schedule Conflict/i)).toBeVisible();

  await page.getByRole('button', {name: /Alfred/i}).click();
  await expect(page.getByText(/Always at your service/i)).toBeVisible();
});

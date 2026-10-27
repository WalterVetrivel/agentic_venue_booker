import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';
import { login } from './helpers';

const MOCK = path.resolve(import.meta.dirname, '../../../data/mock');

async function logout(page: Page) {
	await page.context().clearCookies();
}

test('search past events, fix one that needs checking, and re-upload a report', async ({
	page
}) => {
	await login(page, 'cseoa@kiot.ac.in');
	await page.goto('/documents');
	await expect(page.getByText(/155 events from 276 documents/)).toBeVisible();

	await page.getByLabel('Search circulars and reports').fill('hackathon in the COE labs');
	await page.getByRole('button', { name: 'Search' }).click();
	const first = page.getByRole('listitem').filter({ hasText: 'KIOT In-house Hackathon' }).first();
	await expect(first).toContainText('COE1, COE2, COE3');
	await expect(first.locator('mark').first()).toBeVisible();

	// Events with an impossible time range are flagged; the OA corrects one.
	await page.getByRole('tab', { name: 'Past events' }).click();
	await page.getByLabel('Only events that need checking').check();
	await page
		.getByRole('link', { name: /Needs checking/ })
		.first()
		.click();
	await expect(page.getByText('This event needs checking')).toBeVisible();
	await page.getByRole('button', { name: 'Correct the details' }).click();
	await page.getByLabel('Ends').fill('15:55');
	await page.getByRole('button', { name: 'Save' }).click();
	await expect(page.getByText('corrected by hand')).toBeVisible();
	await expect(page.getByText('This event needs checking')).toBeHidden();

	// Uploading a report that is already there replaces it.
	await page.goto('/documents?tab=documents');
	await page
		.getByLabel('Upload circulars or event reports (PDF)')
		.setInputFiles(
			path.join(
				MOCK,
				'reports',
				'REPORT EV0081 - HANDS_ON_WORKSHOP_ON_GENERATIVE_AI_FOR_DEVELOPERS.pdf'
			)
		);
	await expect(page.locator('li').filter({ hasText: 'Replaced EV0081/2024-25' })).toBeVisible();
});

test('the booking form warns about a yearly event in that venue', async ({ page }) => {
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto('/book?venue=CC1&date=2027-11-15&start=10:00&end=12:00');
	await page.getByLabel('Expected attendance').fill('40');
	await expect(
		page.getByText(/Model Practical Examinations - Odd Semester” is usually held in CC1/)
	).toBeVisible();
	await page.getByRole('link', { name: 'Past events in CC1' }).click();
	await expect(
		page.getByRole('link', { name: /Model Practical Examinations/ }).first()
	).toBeVisible();

	// Staff without upload rights can search but not upload.
	await expect(page.getByRole('tab', { name: 'Upload & manage' })).toHaveCount(0);
	await logout(page);
});

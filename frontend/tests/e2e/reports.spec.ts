import { expect, test } from '@playwright/test';
import { login } from './helpers';

test('the HOD sees CSE venue utilisation and can download CSV', async ({ page }) => {
	await login(page, 'hod.cse@kiot.ac.in');
	await page.goto('/reports');
	await expect(page.getByText(/^CSE venues ·/)).toBeVisible();
	const use = page.getByRole('region', { name: 'Venue utilisation' });
	await expect(use.getByRole('link', { name: 'CC5', exact: true })).toBeVisible();
	await expect(use.getByRole('link', { name: 'DSH', exact: true })).toHaveCount(0);

	await use.getByRole('button', { name: 'Table' }).click();
	await expect(use.getByRole('table', { name: 'Utilisation by venue' })).toBeVisible();

	const download = page.waitForEvent('download');
	await use.getByRole('link', { name: 'CSV' }).click();
	expect((await download).suggestedFilename()).toMatch(/^utilisation-.*\.csv$/);
});

test('an in-charge picks a period and sees only their hall', async ({ page }) => {
	await login(page, 'sh.dblock@kiot.ac.in');
	await page.goto('/reports');
	await expect(page.getByText(/^Your venues \(DSH\) ·/)).toBeVisible();
	await page.getByRole('button', { name: 'Choose dates' }).click();
	await page.getByLabel('From', { exact: true }).fill('2025-01-01');
	await page.getByLabel('To', { exact: true }).fill('2025-12-31');
	await page.getByRole('button', { name: 'Show' }).click();
	await expect(page.getByText(/1 Jan 2025 to 31 Dec 2025/)).toBeVisible();
	await expect(page).toHaveURL(/start=2025-01-01&end=2025-12-31/);
	const events = page.getByRole('region', { name: 'Events' });
	await expect(events.getByText(/List all \d+ events/)).toBeVisible();
});

test('people without a reporting role are told so', async ({ page }) => {
	await login(page, 'prcse@kiot.ac.in');
	await page.goto('/reports');
	await expect(page.getByRole('alert')).toContainText("don't have access");
});

test('an event type called "Other" folds into the Other row', async ({ page }) => {
	await page.route('**/api/reports/summary*', async (route) => {
		const res = await route.fetch();
		const data = await res.json();
		const names = ['Workshop', 'Seminar', 'Hackathon', 'Meeting', 'Other', 'Coding contest'];
		data.events.by_type = [...names, 'Conference', 'Guest lecture', 'Inauguration', 'Quiz'].map(
			(name, i) => ({ name, count: 20 - i })
		);
		data.equipment.out_of_service = [
			{ venue: 'CC5', item: 'Projector', status: 'faulty', since: null },
			{ venue: 'CC5', item: 'Projector', status: 'under_repair', since: null }
		];
		await route.fulfill({ response: res, json: data });
	});
	await login(page, 'hod.cse@kiot.ac.in');
	await page.goto('/reports');
	const events = page.getByRole('region', { name: 'Events' });
	await expect(events.getByText('Other', { exact: true })).toHaveCount(1);
	await expect(page.getByText('Equipment out')).toBeVisible();
});

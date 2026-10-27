import { expect, test } from '@playwright/test';
import { login, navLabels } from './helpers';

test('students can browse venues without logging in', async ({ page }) => {
	await page.goto('/venues');
	await expect(page.getByText('Computer Centre 1', { exact: true })).toBeVisible();
	await page.getByText('Computer Centre 5', { exact: true }).click();
	await expect(page.getByText('Power BI Desktop')).toBeVisible();
	expect(await navLabels(page)).toEqual(['Home', 'Availability', 'Venues']);
});

const MENUS: Record<string, string[]> = {
	'swvcse@kiot.ac.in': [
		'Home',
		'Availability',
		'Venues',
		'Book a venue',
		'My bookings',
		'Approvals',
		'Past events',
		'Reports'
	],
	'prcse@kiot.ac.in': [
		'Home',
		'Availability',
		'Venues',
		'Book a venue',
		'My bookings',
		'Past events'
	],
	'cseoa@kiot.ac.in': ['Home', 'Availability', 'Venues', 'Timetables', 'Past events'],
	'hod.cse@kiot.ac.in': [
		'Home',
		'Availability',
		'Venues',
		'Book a venue',
		'My bookings',
		'Approvals',
		'Timetables',
		'Past events',
		'Reports'
	],
	'dirim@kiot.ac.in': [
		'Home',
		'Availability',
		'Venues',
		'Book a venue',
		'My bookings',
		'Approvals',
		'Timetables',
		'Past events',
		'Reports',
		'Settings'
	]
};

for (const [email, menu] of Object.entries(MENUS)) {
	test(`menu for ${email}`, async ({ page }) => {
		await login(page, email);
		expect(await navLabels(page)).toEqual(menu);
	});
}

test('wrong password shows an error', async ({ page }) => {
	await page.goto('/login');
	await page.getByLabel('Email').fill('swvcse@kiot.ac.in');
	await page.getByLabel('Password').fill('wrong');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page.getByRole('alert')).toHaveText('Wrong email or password');
});

test('theme toggle switches and persists', async ({ page }) => {
	await page.goto('/');
	const html = page.locator('html');
	const before = await html.getAttribute('data-theme');
	await page.getByRole('button', { name: /Switch to (dark|light) mode/ }).click();
	const after = await html.getAttribute('data-theme');
	expect(after).not.toBe(before);
	await page.reload();
	await expect(html).toHaveAttribute('data-theme', after!);
});

test('chat panel can be closed and reopened', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	const panel = page.getByRole('complementary', { name: 'AI assistant' });
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	if (await opener.isVisible()) await opener.click();
	await expect(panel).toBeVisible();
	await panel.getByRole('button', { name: 'Close assistant' }).click();
	await expect(panel).toBeHidden();
	await opener.click();
	await expect(panel).toBeVisible();
});

test('no horizontal scrolling', async ({ page }) => {
	await page.goto('/venues/CC1');
	await expect(page.getByRole('heading', { name: 'Software', exact: true })).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

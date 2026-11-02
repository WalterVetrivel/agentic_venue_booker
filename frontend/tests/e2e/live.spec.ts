import { expect, test, type Page } from '@playwright/test';
import { login } from './helpers';

async function openChat(page: Page) {
	const input = page.getByLabel('Message');
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	await expect(input.or(opener)).toBeVisible();
	if (await opener.isVisible()) await opener.click();
	return page.getByRole('complementary', { name: 'AI assistant' });
}

test('approving in the chat updates the dashboard without a reload', async ({ page }, info) => {
	const day = info.project.name === 'desktop' ? '2027-04-06' : '2027-04-07';
	const title = `Live update ${info.project.name}`;
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto(`/book?venue=CSEPGSH&date=${day}&start=10:00&end=12:00`);
	await page.getByLabel('Title').fill(title);
	await page.getByLabel('Event type').selectOption('Seminar');
	await page.getByLabel('Expected attendance').fill('50');
	await expect(page.getByText(/CSEPGSH is free on/)).toBeVisible();
	await page.getByRole('button', { name: 'Submit request' }).click();
	await expect(page.getByRole('heading', { name: title })).toBeVisible();
	const ref = (await page.getByText(/^BK-\d{4}-\d+/).innerText()).split(' ')[0];

	await page.context().clearCookies();
	await login(page, 'pvcse@kiot.ac.in');
	const pending = page.locator(`[data-approval="${ref}"]`);
	await expect(pending).toHaveCount(1);

	const chat = await openChat(page);
	await chat.getByLabel('Message').fill(`approve ${ref}`);
	await chat.getByLabel('Message').press('Enter');
	const card = chat.locator('[data-card="confirm"]');
	await expect(card.getByText(`Approve ${ref}?`)).toBeVisible();
	await card.getByRole('button', { name: 'Approve' }).click();
	await expect(card.getByRole('button', { name: 'Approved' })).toBeDisabled();
	await expect(pending).toHaveCount(0);
});

test('the app loads nothing from the internet', async ({ page }) => {
	const external: string[] = [];
	await page.route(
		(url) => !['127.0.0.1', 'localhost'].includes(url.hostname),
		(route) => {
			external.push(route.request().url());
			return route.abort();
		}
	);
	await login(page, 'pvcse@kiot.ac.in');
	for (const path of ['/', '/approvals', '/availability', '/venues', '/settings', '/docs']) {
		await page.goto(path);
		await page.waitForLoadState('networkidle');
	}
	await openChat(page);
	expect(external).toEqual([]);
	// The bundled font is the one in use.
	expect(await page.evaluate(() => document.fonts.check('16px "Inter Variable"'))).toBe(true);
});

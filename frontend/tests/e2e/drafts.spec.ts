import { expect, test } from '@playwright/test';
import { login } from './helpers.ts';

test('a saved draft whose slot is booked meanwhile can only join the waitlist', async ({
	page,
	playwright
}, info) => {
	const day = info.project.name === 'desktop' ? '2027-05-04' : '2027-05-05';
	const title = `Alumni talk (${info.project.name})`;
	await login(page, 'tkcse@kiot.ac.in');

	// Save a half-filled form, then finish it later.
	await page.goto('/book');
	await page.getByLabel('Title').fill(title);
	await page.getByRole('button', { name: 'Save as draft' }).click();
	await expect(page.getByRole('status')).toContainText('Draft saved');
	await expect(page).toHaveURL(/\/book\?draft=\d+$/);
	await page.getByLabel('Event type').selectOption('Guest lecture');
	await page.getByLabel('Expected attendance').fill('80');
	await page.getByLabel('Venue', { exact: true }).selectOption('ESH');
	await page.getByLabel('Date').fill(day);
	await page.getByLabel('Starts').fill('10:00');
	await page.getByLabel('Ends').fill('12:00');
	await expect(page.getByText('ESH is free')).toBeVisible();
	await page.getByRole('button', { name: 'Save draft' }).click();
	await expect(page.getByRole('status')).toContainText('Draft saved');

	await page.goto('/bookings');
	const draft = page.getByTestId('draft').filter({ hasText: title });
	await expect(draft).toContainText('Free: ready to submit');

	// Someone else books the same hall and time.
	const other = await playwright.request.newContext({ baseURL: info.project.use.baseURL });
	await other.post('/api/auth/login', {
		data: { email: 'gbcse@kiot.ac.in', password: 'password' }
	});
	const res = await other.post('/api/bookings', {
		data: {
			venue: 'ESH',
			title: 'Placement briefing',
			event_type: 'Placement training',
			expected_count: 60,
			date_from: day,
			start_time: '11:00',
			end_time: '13:00'
		}
	});
	expect(res.status()).toBe(201);
	await other.dispose();

	await page.reload();
	await expect(draft).toContainText('since you saved it');
	await draft.getByRole('link', { name: 'Open' }).click();
	await expect(page.getByTestId('taken-since-saved')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Submit request' })).toHaveCount(0);
	await page.getByRole('button', { name: 'Join the waitlist' }).click();
	await expect(page.getByText('You are number 1 on the waitlist')).toBeVisible();

	await page.goto('/bookings');
	await expect(page.getByTestId('draft').filter({ hasText: title })).toHaveCount(0);
});

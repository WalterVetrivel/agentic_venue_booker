import { expect, test, type Page } from '@playwright/test';
import { login } from './helpers';

async function logout(page: Page) {
	await page.context().clearCookies();
}

test('book, approve twice, cancel, and the waitlisted request gets the offer', async ({
	page
}, info) => {
	// Desktop and mobile share one database, so each uses its own date.
	const day = info.project.name === 'desktop' ? '2027-03-02' : '2027-03-03';
	const title = `Robotics expo ${info.project.name}`;
	const book = `/book?venue=CSEPGSH&date=${day}&start=10:00&end=12:00`;

	// Faculty books the CSE PG seminar hall.
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto(book);
	await page.getByLabel('Title').fill(title);
	await page.getByLabel('Event type').selectOption('Seminar');
	await page.getByLabel('Expected attendance').fill('70');
	await expect(page.getByText(/CSEPGSH is free on/)).toBeVisible();
	await page.getByRole('button', { name: 'Submit request' }).click();
	await expect(page.getByRole('heading', { name: title })).toBeVisible();
	await expect(page.getByText('Waiting for in-charge').first()).toBeVisible();
	const firstUrl = page.url();

	// Someone else wants the same slot and joins the waitlist.
	await logout(page);
	await login(page, 'swvcse@kiot.ac.in');
	await page.goto(book);
	await page.getByLabel('Title').fill(`Cloud meetup ${info.project.name}`);
	await page.getByLabel('Event type').selectOption('Meeting');
	await page.getByLabel('Expected attendance').fill('40');
	await expect(page.getByText(`Already booked: ${title} (awaiting approval)`)).toBeVisible();
	await page.getByRole('button', { name: 'Join the waitlist' }).click();
	await expect(page.getByText('You are number 1 on the waitlist.')).toBeVisible();
	const waitUrl = page.url();

	// The hall's in-charge, then the HOD, approve.
	for (const approver of ['pvcse@kiot.ac.in', 'hod.cse@kiot.ac.in']) {
		await logout(page);
		await login(page, approver);
		await page.goto('/approvals');
		const item = page.getByRole('listitem').filter({ hasText: title });
		await expect(item.getByText('Capacity fits: 70 expected, 80 seats.')).toBeVisible();
		await item.getByRole('button', { name: /^Approve/ }).click();
		await expect(page.getByText(new RegExp(`“${title}”: approved`))).toBeVisible();
	}

	// The requester sees it confirmed, then cancels.
	await logout(page);
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto(firstUrl);
	await expect(page.getByText('Confirmed').first()).toBeVisible();
	await page.getByRole('button', { name: 'Cancel booking…' }).click();
	await page.getByLabel('Reason (optional)').fill('Speaker unavailable');
	await page.getByRole('button', { name: 'Cancel booking', exact: true }).click();
	await expect(page.getByText('Reason: Speaker unavailable')).toBeVisible();

	// The waitlisted request is offered the slot and confirms it.
	await logout(page);
	await login(page, 'swvcse@kiot.ac.in');
	await expect(page.getByRole('button', { name: /Notifications, \d+ unread/ })).toBeVisible();
	await page.goto(waitUrl);
	await expect(page.getByText('The slot you were waiting for is free.')).toBeVisible();
	await page.getByRole('button', { name: 'Confirm the slot' }).click();
	await expect(page.getByText('Waiting for in-charge').first()).toBeVisible();
});

test('a booking shows on the public availability grid', async ({ page }, info) => {
	const day = info.project.name === 'desktop' ? '2027-03-09' : '2027-03-10';
	await login(page, 'dirim@kiot.ac.in'); // the Director's bookings are confirmed at once
	await page.goto(`/book?venue=DSH&date=${day}&start=14:00&end=16:00`);
	await page.getByLabel('Title').fill(`Alumni talk ${info.project.name}`);
	await page.getByLabel('Event type').selectOption('Guest lecture');
	await page.getByLabel('Expected attendance').fill('200');
	await expect(page.getByText(/DSH is free on/)).toBeVisible();
	await page.getByRole('button', { name: 'Submit request' }).click();
	await expect(page.getByText('Confirmed').first()).toBeVisible();

	await logout(page);
	await page.goto(`/availability?date=${day}&type=seminar_hall`);
	const label = `Alumni talk ${info.project.name}`;
	const shown =
		info.project.name === 'desktop'
			? page.locator(`[title*="${label}"]`)
			: page.getByText(label).locator('visible=true');
	await expect(shown.first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Book', exact: true })).toHaveCount(0);
});

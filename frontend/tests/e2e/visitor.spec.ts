import { expect, test, type Page } from '@playwright/test';

async function ask(page: Page, text: string) {
	const input = page.getByLabel('Message');
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	await expect(input.or(opener)).toBeVisible();
	if (await opener.isVisible()) await opener.click();
	const chat = page.getByRole('complementary', { name: 'AI assistant' });
	await chat.getByLabel('Message').fill(text);
	await chat.getByLabel('Message').press('Enter');
	return chat;
}

test('a visitor books a lab and tracks a request from the home page', async ({ page }) => {
	await page.goto('/');
	const hero = page.locator('section').first();
	await expect(hero.getByRole('link', { name: 'Book a lab' })).toHaveAttribute(
		'href',
		'/book/student'
	);
	const tracker = page.getByRole('search', { name: 'Track a request' });
	await tracker.getByLabel('Tracking number').fill('st-2345-6789');
	await tracker.getByRole('button', { name: 'Track' }).click();
	await expect(page).toHaveURL(/\/track\?code=st-2345-6789/);
	await expect(page.getByText('No request has that tracking number')).toBeVisible();
});

test('faculty on the student form log in and land on the booking form', async ({ page }) => {
	await page.goto('/book/student');
	const note = page.getByRole('complementary', { name: 'For faculty and staff' });
	await expect(note).toContainText('Faculty member?');
	await note.getByRole('link', { name: 'Log in to book' }).click();
	await page.getByLabel('Email').fill('tkcse@kiot.ac.in');
	await page.getByLabel('Password').fill('password');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page).toHaveURL(/\/book$/);
	await expect(page.getByRole('heading', { name: 'Book a venue', level: 1 })).toBeVisible();
});

test('the assistant sends a signed-out faculty member to log in', async ({ page }) => {
	await page.goto('/');
	const chat = await ask(page, "I'm faculty. Book DSH tomorrow 10 to 12 for a guest lecture.");
	const link = chat.getByRole('link', { name: 'Log in' });
	await expect(link).toHaveAttribute('href', '/login?next=/book');
});

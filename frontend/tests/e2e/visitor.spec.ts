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
	await expect(page.getByRole('heading', { name: 'Staff login' })).toBeVisible();
	await expect(page).toHaveURL(/\/login\?next=%2Fbook$|\/login\?next=\/book$/);
	await page.getByLabel('Email').fill('tkcse@kiot.ac.in');
	await page.getByLabel('Password').fill('password');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page).toHaveURL((url) => url.pathname === '/book');
	await expect(page.getByRole('heading', { name: 'Book a venue', level: 1 })).toBeVisible();
});

test('the assistant sends a signed-out faculty member to log in', async ({ page }) => {
	await page.goto('/');
	const chat = await ask(page, "I'm faculty. Book DSH tomorrow 10 to 12 for a guest lecture.");
	const link = chat.getByRole('link', { name: 'Log in' });
	await expect(link).toHaveAttribute('href', '/login?next=/book');
});

test('a draft from the chat fills in the open form and keeps what was typed', async ({ page }) => {
	await page.goto('/book/student');
	await page.locator('#sname-0').fill('Arun K');
	await page.locator('#reason').fill('Smart parking app');
	const chat = await ask(page, 'Book CC7 tomorrow 14:00 to 16:00');
	await expect(chat.getByText('Draft student request')).toBeVisible();
	await expect(page.locator('#venue')).toHaveValue('CC7');
	await expect(page.locator('#start')).toHaveValue('14:00');
	// The assistant's reason replaces the typed one; the student it didn't mention stays.
	await expect(page.locator('#reason')).toHaveValue('Mini project work');
	await expect(page.locator('#sname-0')).toHaveValue('Arun K');
});

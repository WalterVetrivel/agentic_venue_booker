import { expect, test, type Page } from '@playwright/test';
import { login } from './helpers';

// The backend runs with LLM_FAKE=1: a scripted demo model that calls the real tools.

async function openChat(page: Page) {
	const input = page.getByLabel('Message');
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	await expect(input.or(opener)).toBeVisible();
	if (await opener.isVisible()) await opener.click();
	return page.getByRole('complementary', { name: 'AI assistant' });
}

async function ask(page: Page, text: string) {
	const chat = await openChat(page);
	await chat.getByLabel('Message').fill(text);
	await chat.getByLabel('Message').press('Enter');
	return chat;
}

test('a visitor asks whether a lab is free', async ({ page }) => {
	await page.goto('/');
	const chat = await ask(page, 'Is CC5 free on 2027-02-09 16:30 to 17:30?');
	await expect(chat.getByText('✓ Checking availability')).toBeVisible();
	await expect(chat.getByText('CC5 is free on Tuesday 09 Feb 2027, 16:30–17:30.')).toBeVisible();
	await expect(chat.getByRole('button', { name: 'Attach a PDF' })).toHaveCount(0);
});

test('faculty drafts a booking in chat, submits it, then cancels it from a card', async ({
	page
}, info) => {
	const day = info.project.name === 'desktop' ? '2027-03-09' : '2027-03-10';
	await login(page, 'tkcse@kiot.ac.in');
	let chat = await ask(page, `Please book COE2 on ${day} 14:00 to 16:00`);
	const draft = chat.locator('[data-card="draft"]');
	await expect(draft.getByText('Draft booking: Python workshop')).toBeVisible();
	await draft.getByRole('link', { name: 'Review & submit' }).click();

	await expect(page.getByLabel('Title')).toHaveValue('Python workshop');
	await expect(page.getByLabel('Expected attendance')).toHaveValue('30');
	await expect(page.getByText(/COE2 is free on/)).toBeVisible();
	await page.getByRole('button', { name: 'Submit request' }).click();
	await expect(page.getByRole('heading', { name: 'Python workshop' })).toBeVisible();
	const ref = (await page.getByText(/^BK-\d{4}-\d+/).innerText()).split(' ')[0];

	chat = await ask(page, `cancel ${ref}`);
	const confirm = chat.locator('[data-card="confirm"]');
	await expect(confirm.getByText(`Cancel ${ref}?`)).toBeVisible();
	await confirm.getByRole('button', { name: 'Cancel booking' }).click();
	await expect(confirm.getByText(`✓ ${ref} cancelled.`)).toBeVisible();
	await page.reload();
	await expect(page.getByText('Cancelled').first()).toBeVisible();

	// The chat was saved and can be reopened from the history menu.
	chat = await openChat(page);
	await chat.getByRole('button', { name: /New chat/ }).click();
	await chat.getByLabel('Search chats').fill(ref);
	await chat
		.getByRole('button', { name: `Please book COE2 on ${day} 14:00 to 16:00`, exact: true })
		.click();
	await expect(chat.getByText(`✓ ${ref} cancelled.`)).toBeVisible();
});

test('the director sets the Groq key without seeing it again', async ({ page }) => {
	await login(page, 'dirim@kiot.ac.in');
	await page.goto('/settings');
	await page.getByLabel('API key').fill('gsk_e2e_test_key_123456');
	await page.getByRole('button', { name: 'Save settings' }).click();
	await expect(page.getByText('Saved.')).toBeVisible();
	await expect(page.getByLabel('API key')).toHaveAttribute('placeholder', /gsk_…3456/);
	await page.getByRole('button', { name: 'Remove saved key' }).click();
	await expect(page.getByText('Saved key removed.')).toBeVisible();

	await page.getByRole('button', { name: 'Create a token' }).click();
	await expect(page.getByText('"mcp-remote"')).toBeVisible();
});

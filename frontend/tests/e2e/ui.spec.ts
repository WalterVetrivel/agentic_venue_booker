import { expect, test, type Page, type Route } from '@playwright/test';
import { login } from './helpers';

async function openChat(page: Page) {
	const input = page.getByLabel('Message');
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	await expect(input.or(opener)).toBeVisible();
	if (await opener.isVisible()) await opener.click();
	return page.getByRole('complementary', { name: 'AI assistant' });
}

/** Answer /api/chat with the given scripted streams, one per request, recording each body. */
function scriptChat(page: Page, replies: string[][]) {
	const bodies: Record<string, unknown>[] = [];
	page.route('/api/chat', async (route: Route) => {
		bodies.push(route.request().postDataJSON());
		const events = replies.shift() ?? ['Out of script.'];
		const body = events
			.map((text, i) =>
				i === events.length - 1 && text.startsWith('!')
					? { type: 'error', message: text.slice(1) }
					: { type: 'done', content: text, provider: 'fake', model: 'e2e' }
			)
			.map((e) => `data: ${JSON.stringify(e)}\n\n`)
			.join('');
		await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
	});
	return bodies;
}

test('a failed reply can be rerun with the same prompt', async ({ page }) => {
	const bodies = scriptChat(page, [['!Groq rate limit reached'], ['CC5 is free all day.']]);
	await page.goto('/');
	const chat = await openChat(page);
	await chat.getByLabel('Message').fill('Is CC5 free tomorrow?');
	await chat.getByLabel('Message').press('Enter');
	await expect(chat.getByText('Groq rate limit reached')).toBeVisible();

	await chat.getByRole('button', { name: 'Rerun' }).click();
	await expect(chat.getByText('CC5 is free all day.')).toBeVisible();
	await expect(chat.getByText('Groq rate limit reached')).toHaveCount(0);
	await expect(chat.locator('[data-role="user"]')).toHaveCount(1);
	expect(bodies.map((b) => b.message)).toEqual(['Is CC5 free tomorrow?', 'Is CC5 free tomorrow?']);
	expect(bodies[1].regenerate).toBe(false); // a visitor's chat isn't saved, so nothing to replace
	expect(bodies[1].history).toEqual([]);
});

test('yes/no questions get quick replies that send at once', async ({ page }) => {
	const bodies = scriptChat(page, [
		['CC5 is free then. Would you like me to draft a booking?'],
		['Here is the draft.']
	]);
	await page.goto('/');
	const chat = await openChat(page);
	await chat.getByLabel('Message').fill('Is CC5 free tomorrow 10:00 to 12:00?');
	await chat.getByLabel('Message').press('Enter');
	const replies = chat.getByRole('group', { name: 'Quick replies' });
	await expect(replies.getByRole('button')).toHaveText(['Yes, please', 'No, thanks']);
	await replies.getByRole('button', { name: 'Yes, please' }).click();
	await expect(chat.getByText('Here is the draft.')).toBeVisible();
	await expect(replies).toHaveCount(0);
	expect(bodies[1].message).toBe('Yes, please');
});

test('choices are not offered as yes/no', async ({ page }) => {
	scriptChat(page, [['Both are free. Do you prefer CC5 or CC6?']]);
	await page.goto('/');
	const chat = await openChat(page);
	await chat.getByLabel('Message').fill('Which lab?');
	await chat.getByLabel('Message').press('Enter');
	await expect(chat.getByText('Do you prefer CC5 or CC6?')).toBeVisible();
	await expect(chat.getByRole('group', { name: 'Quick replies' })).toHaveCount(0);
});

test('the dashboard shows current bookings and pending approvals', async ({ page }) => {
	await login(page, 'hod.cse@kiot.ac.in');
	await expect(page.getByRole('heading', { name: /Your current bookings/ })).toBeVisible();
	await expect(page.getByRole('heading', { name: /Pending approvals/ })).toBeVisible();
	await expect(page.getByRole('link', { name: /All approvals/ })).toHaveAttribute(
		'href',
		'/approvals'
	);
	await expect(page.getByRole('img', { name: 'KIOT logo' })).toBeVisible();
});

test('plain faculty see their bookings but no approvals panel', async ({ page }) => {
	await login(page, 'tkcse@kiot.ac.in');
	await expect(page.getByRole('heading', { name: /Your current bookings/ })).toBeVisible();
	await expect(page.getByRole('heading', { name: /Pending approvals/ })).toHaveCount(0);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('breadcrumbs and the back button lead home', async ({ page }) => {
	await page.goto('/venues/CC1');
	const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' });
	await expect(crumbs.getByRole('link')).toHaveText(['Home', 'Venues']);
	await expect(crumbs.locator('[aria-current="page"]')).toHaveText('CC1');
	await crumbs.getByRole('link', { name: 'Venues' }).click();
	await expect(page).toHaveURL(/\/venues$/);
	await page.getByRole('link', { name: 'Dashboard' }).click();
	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toHaveCount(0);
});

test('buttons and links show a pointer', async ({ page }) => {
	await page.goto('/');
	const cursor = (sel: string) =>
		page
			.locator(sel)
			.first()
			.evaluate((el) => getComputedStyle(el).cursor);
	expect(await cursor('button')).toBe('pointer');
	expect(await cursor('a[href]')).toBe('pointer');
});

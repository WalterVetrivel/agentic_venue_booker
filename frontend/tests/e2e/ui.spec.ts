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

test('the availability calendar shows a venue by day, week and month', async ({ page }) => {
	await page.goto('/availability?view=calendar&venue=CC1&date=2027-02-10');
	await expect(page.getByRole('combobox', { name: 'Venue' })).toHaveValue('CC1');
	await page.getByRole('button', { name: 'Week', exact: true }).click();
	await expect(page.getByRole('region', { name: /8 Feb – 13 Feb 2027 at CC1/ })).toBeVisible();
	await page.getByRole('button', { name: 'Month', exact: true }).click();
	await expect(page.getByRole('heading', { name: 'February 2027' })).toBeVisible();
	await page.getByRole('button', { name: /^Wednesday, 10 February/ }).click();
	await expect(page.getByRole('heading', { name: 'Wednesday, 10 February 2027' })).toBeVisible();
	await page.getByRole('button', { name: 'Next day' }).click();
	await expect(page).toHaveURL(/date=2027-02-11/);
});

test('the venue page shows its calendar', async ({ page }) => {
	await page.goto('/venues/CC1');
	await expect(page.getByRole('heading', { name: 'Schedule' })).toBeVisible();
	await expect(page.getByRole('region', { name: /at CC1$/ })).toBeVisible();
	await page.getByRole('button', { name: 'Class timetable' }).click();
	await expect(page.getByRole('heading', { name: 'Weekly class schedule' })).toBeVisible();
});

test('availability alerts start collapsed with a count', async ({ page }) => {
	// Early January brings warnings about yearly events held in these venues.
	await page.goto('/availability?date=2027-01-04');
	const alerts = page.locator('details', { hasText: 'Alerts' });
	await expect(alerts).toBeVisible();
	await expect(alerts).not.toHaveAttribute('open');
	await alerts.locator('summary').click();
	await expect(alerts).toHaveAttribute('open');
});

test('bookings switch between cards and a table', async ({ page }) => {
	await login(page, 'swvcse@kiot.ac.in');
	await expect(page.getByRole('link', { name: 'Book a venue' }).first()).toBeVisible();
	await page.goto('/bookings');
	await page.getByRole('button', { name: 'Table' }).click();
	const table = page.getByRole('table').first();
	await expect(table.getByRole('columnheader')).toHaveText([
		'Title',
		'Venue',
		'Date and time',
		'Status'
	]);
	await page.reload();
	await expect(page.getByRole('button', { name: 'Table' })).toHaveAttribute('aria-pressed', 'true');
	await page.getByRole('button', { name: 'Cards' }).click();
});

test('an in-charge approves straight from the dashboard', async ({ page }, info) => {
	const day = info.project.name === 'desktop' ? '2027-05-11' : '2027-05-12';
	await login(page, 'tkcse@kiot.ac.in');
	const res = await page.request.post('/api/bookings', {
		data: {
			venue: 'DSH',
			title: 'Dashboard approval check',
			event_type: 'Workshop',
			expected_count: 60,
			date_from: day,
			start_time: '10:00',
			end_time: '12:00'
		}
	});
	expect(res.status()).toBe(201);
	const { ref } = await res.json();

	await page.getByRole('button', { name: /Account menu/ }).click();
	await page.getByRole('menuitem', { name: 'Log out' }).click();
	await login(page, 'sh.dblock@kiot.ac.in');
	const row = page.locator(`[data-approval="${ref}"]`);
	await row.getByRole('button', { name: `Approve ${ref}` }).click();
	await expect(page.getByRole('status')).toHaveText(`${ref} approved and confirmed.`);
	await expect(row).toHaveCount(0);
});

test('a draft from the chat fills a booking form that is already open', async ({ page }, info) => {
	const day = info.project.name === 'desktop' ? '2027-03-16' : '2027-03-17';
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto('/book');
	await expect(page.getByLabel('Title')).toHaveValue('');
	const chat = await openChat(page);
	await chat.getByLabel('Message').fill(`Please book COE2 on ${day} 14:00 to 16:00`);
	await chat.getByLabel('Message').press('Enter');
	await chat.locator('[data-card="draft"]').getByRole('link', { name: 'Review & submit' }).click();
	await expect(page.getByLabel('Title')).toHaveValue('Python workshop');
	await expect(page.getByLabel('Expected attendance')).toHaveValue('30');
});

test('the account menu links to the dashboard and bookings', async ({ page }) => {
	await login(page, 'tkcse@kiot.ac.in');
	await page.goto('/venues');
	await page.getByRole('button', { name: /Account menu/ }).click();
	const menu = page.getByRole('menu', { name: 'Account' });
	await expect(menu.getByRole('menuitem')).toHaveText(['Dashboard', 'My bookings', 'Log out']);
	await menu.getByRole('menuitem', { name: 'My bookings' }).click();
	await expect(page).toHaveURL(/\/bookings$/);
	await expect(menu).toHaveCount(0);
});

test('the side menu collapses to icons and opens on hover', async ({ page }, info) => {
	test.skip(info.project.name === 'mobile', 'The side menu is a drawer on phones');
	await page.goto('/venues');
	const nav = page.getByRole('navigation', { name: 'Main' });
	await page.getByRole('button', { name: 'Collapse the menu' }).click();
	await page.mouse.move(900, 500);
	await expect.poll(async () => (await nav.boundingBox())!.width).toBeLessThan(100);
	await nav.hover();
	await expect.poll(async () => (await nav.boundingBox())!.width).toBeGreaterThan(200);
	await page.mouse.move(900, 500);
	await expect.poll(async () => (await nav.boundingBox())!.width).toBeLessThan(100);
	await page.reload();
	await page.mouse.move(900, 500);
	await expect.poll(async () => (await nav.boundingBox())!.width).toBeLessThan(100);
	await page.getByRole('button', { name: 'Keep the menu open' }).click();
	await page.mouse.move(900, 500);
	await expect.poll(async () => (await nav.boundingBox())!.width).toBeGreaterThan(200);
});

test('a submitted draft shows as submitted, also when the chat is reopened', async ({
	page
}, info) => {
	const day = info.project.name === 'desktop' ? '2027-03-23' : '2027-03-24';
	const prompt = `Please book COE2 on ${day} 14:00 to 16:00`;
	await login(page, 'tkcse@kiot.ac.in');
	let chat = await openChat(page);
	await chat.getByLabel('Message').fill(prompt);
	await chat.getByLabel('Message').press('Enter');
	await chat.locator('[data-card="draft"]').getByRole('link', { name: 'Review & submit' }).click();
	await page.getByRole('button', { name: 'Submit request' }).click();
	await expect(page.getByRole('heading', { name: 'Python workshop' })).toBeVisible();

	chat = await openChat(page);
	const draft = chat.locator('[data-card="draft"]');
	await expect(draft.getByRole('button', { name: 'Submitted' })).toBeDisabled();
	await expect(draft.getByRole('link', { name: 'Review & submit' })).toHaveCount(0);

	// The saved chat remembers it too.
	await page.reload();
	chat = await openChat(page);
	await chat.getByRole('button', { name: /New chat/ }).click();
	await chat.getByRole('button', { name: prompt, exact: true }).click();
	await expect(
		chat.locator('[data-card="draft"]').getByRole('button', { name: 'Submitted' })
	).toBeDisabled();
});

test('the chat history menu closes when clicking outside it', async ({ page }) => {
	await page.goto('/');
	const chat = await openChat(page);
	const history = chat.locator('button[aria-haspopup="menu"]').first();
	await history.click();
	await expect(history).toHaveAttribute('aria-expanded', 'true');
	await expect(chat.getByRole('button', { name: 'New chat', exact: true })).toHaveCount(2);
	await chat.getByLabel('Message').click();
	await expect(history).toHaveAttribute('aria-expanded', 'false');
	await expect(chat.getByRole('button', { name: 'New chat', exact: true })).toHaveCount(1);
});

test('the assistant starts closed', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('button', { name: 'Ask the assistant' })).toBeVisible();
	await expect(page.getByRole('complementary', { name: 'AI assistant' })).toHaveCount(0);
});

test('signed-in people can sign out from the bottom of the menu', async ({ page }) => {
	await page.goto('/login');
	await expect(page.getByText('Demo accounts')).toHaveCount(0);
	await expect(page.getByLabel('Email')).toHaveAttribute('placeholder', 'name@kiot.ac.in');
	await login(page, 'tkcse@kiot.ac.in');
	const opener = page.getByRole('button', { name: 'Open menu' });
	if (await opener.isVisible()) await opener.click();
	const nav = page.getByRole('navigation', { name: 'Main' });
	await nav.getByRole('button', { name: 'Sign out' }).click();
	await expect(page).toHaveURL((url) => url.pathname === '/');
	await expect(page.getByRole('link', { name: 'Log in' }).first()).toBeVisible();
});

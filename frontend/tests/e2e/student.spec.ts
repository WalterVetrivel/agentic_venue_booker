import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { login } from './helpers';

// Student requests need classes to choose from: commit CSE III-B's timetable as the OA.
test.beforeAll(async ({ request }) => {
	const res = await request.post('/api/auth/login', {
		data: { email: 'cseoa@kiot.ac.in', password: 'password' }
	});
	expect(res.ok()).toBeTruthy();
	const sections = await (await request.get('/api/timetables/sections')).json();
	if (sections.some((s: { label: string }) => s.label === 'CSE III-B')) return;
	const pdf = '../data/mock/timetables/TT_CSE_III_YR_B.pdf';
	const upload = await request.post('/api/timetables/uploads', {
		multipart: {
			file: { name: 'TT_CSE_III_YR_B.pdf', mimeType: 'application/pdf', buffer: readFileSync(pdf) }
		}
	});
	expect(upload.ok()).toBeTruthy();
	const { id } = await upload.json();
	expect((await request.post(`/api/timetables/uploads/${id}/commit`)).ok()).toBeTruthy();
});

async function logout(page: Page) {
	await page.context().clearCookies();
}

test('a student group requests a lab, the guide approves one student, then the in-charge and HOD', async ({
	page
}, info) => {
	const day = info.project.name === 'desktop' ? '2027-03-16' : '2027-03-17';
	const reason = `Smart parking app ${info.project.name}`;

	// A visitor (no login) finds the student form in the menu.
	await page.goto('/');
	await page.goto(`/book/student?venue=CC5&date=${day}&start=14:00&end=16:00`);
	await expect(page.getByRole('heading', { name: 'Request a lab for group work' })).toBeVisible();
	await expect(page.getByRole('option', { name: /CSEPGSH/ })).toHaveCount(0);
	await page.getByLabel('What will the group work on?').fill(reason);
	await page.getByLabel('Faculty guide').selectOption({ label: 'Mrs. B. Ashwini · Asst. Prof.' });
	await page.locator('#sname-0').fill('Arun K');
	await page.locator('#sclass-0').selectOption({ label: 'CSE III-B' });
	await page.getByRole('button', { name: 'Add a student' }).click();
	await page.locator('#sname-1').fill('Bala S');
	await expect(page.locator('#sclass-1')).toHaveValue(await page.locator('#sclass-0').inputValue());
	await page.getByLabel('One email for the group').fill('team@example.com');
	await expect(page.getByText(/CC5 is free on/)).toBeVisible();
	await page.getByRole('button', { name: 'Send the request' }).click();

	const code = (await page.getByTestId('tracking-code').innerText()).trim();
	expect(code).toMatch(/^ST-[A-Z0-9]{4}-[A-Z0-9]{4}$/);
	await page.getByRole('link', { name: 'Track this request' }).click();
	await expect(page.getByText('Waiting for faculty guide').first()).toBeVisible();

	// The guide approves Arun and rejects Bala.
	await login(page, 'bacse@kiot.ac.in');
	await page.goto('/approvals');
	const item = page.getByRole('listitem').filter({ hasText: reason });
	await item.getByRole('radiogroup', { name: 'Decision for Arun K' }).getByLabel('Approve').check();
	await item.getByRole('radiogroup', { name: 'Decision for Bala S' }).getByLabel('Reject').check();
	await item.getByPlaceholder(/Why/).fill('Working with another team');
	await item.getByRole('button', { name: 'Save: approve 1 of 2' }).click();
	await expect(page.getByText(/approved, now waiting for in-charge/)).toBeVisible();

	// The lab's in-charge and the HOD approve as usual.
	for (const approver of ['mkscse@kiot.ac.in', 'hod.cse@kiot.ac.in']) {
		await logout(page);
		await login(page, approver);
		await page.goto('/approvals');
		const req = page.getByRole('listitem').filter({ hasText: reason });
		await expect(req.getByText('Approved by the guide: Arun K (CSE III-B)')).toBeVisible();
		await req.getByRole('button', { name: /^Approve/ }).click();
		await expect(page.getByText(/approved/).first()).toBeVisible();
	}

	// The group tracks it to the end.
	await logout(page);
	await page.goto('/track');
	await page.getByLabel('Tracking number').fill(code.toLowerCase());
	await page.getByRole('button', { name: 'Look it up' }).click();
	await expect(page.getByText('Confirmed').first()).toBeVisible();
	await expect(page.getByText('“Working with another team”')).toBeVisible();
});

test('a visitor asks the assistant to draft a student request', async ({ page }) => {
	await page.goto('/');
	const input = page.getByLabel('Message');
	const opener = page.getByRole('button', { name: 'Ask the assistant' });
	await expect(input.or(opener)).toBeVisible();
	if (await opener.isVisible()) await opener.click();
	const chat = page.getByRole('complementary', { name: 'AI assistant' });
	await chat.getByLabel('Message').fill('Please book CC6 on 2027-03-18 14:00 to 16:00');
	await chat.getByLabel('Message').press('Enter');
	const draft = chat.locator('[data-card="draft"]');
	await expect(draft.getByText('Draft student request')).toBeVisible();
	await draft.getByRole('link', { name: 'Finish on the form' }).click();
	await expect(page.getByLabel('What will the group work on?')).toHaveValue('Mini project work');
	await expect(page.getByLabel('Lab')).toHaveValue('CC6');
});

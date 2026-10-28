import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { login } from './helpers';

// Automated WCAG 2.1 AA checks on the main pages, in both themes.
const PUBLIC = ['/', '/availability', '/venues', '/venues/CC5', '/login'];
const STAFF = ['/', '/book', '/bookings', '/approvals', '/documents', '/reports', '/timetables'];

async function check(page: import('@playwright/test').Page, path: string) {
	await page.goto(path);
	await page.waitForLoadState('networkidle');
	// Let entrance fades finish so colours are checked as people see them.
	await page.waitForFunction(() =>
		document
			.getAnimations()
			.every((a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity)
	);
	const { violations } = await new AxeBuilder({ page })
		.withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
		.analyze();
	const summary = violations.map(
		(v) => `${path}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')}`
	);
	expect(summary).toEqual([]);
}

for (const theme of ['light', 'dark'] as const) {
	test.describe(`${theme} theme`, () => {
		test.use({ colorScheme: theme });

		test('public pages', async ({ page }) => {
			for (const path of PUBLIC) await check(page, path);
		});

		test('staff pages', async ({ page }) => {
			await login(page, 'hod.cse@kiot.ac.in');
			for (const path of STAFF) await check(page, path);
		});
	});
}

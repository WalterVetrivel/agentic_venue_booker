import { expect, test } from '@playwright/test';
import path from 'node:path';
import { login } from './helpers';

const MOCK = path.resolve(import.meta.dirname, '../../../data/mock/timetables');

test('OA uploads a timetable, fixes a slot, commits it and the labs show the class', async ({
	page
}, info) => {
	// Desktop and mobile runs share one database, so each commits a different class
	// and checks a weekday on which that class has labs (Mon for II-A, Tue for II-B).
	const [file, label, date] =
		info.project.name === 'desktop'
			? ['TT_CSE_II_YR_A.pdf', 'CSE II-A', '2026-11-02']
			: ['TT_CSE_II_YR_B.pdf', 'CSE II-B', '2026-11-03'];

	await login(page, 'cseoa@kiot.ac.in');
	await page.goto('/timetables');
	await page.getByLabel('Upload timetable PDFs').setInputFiles(path.join(MOCK, file));
	await expect(page.getByText(/Ready: \d+ lab slots found/)).toBeVisible();

	await page.getByRole('link', { name: new RegExp(label) }).click();
	await expect(page.getByRole('heading', { name: `Review ${label}` })).toBeVisible();

	// A typo in a venue is flagged and blocks the commit until it is fixed.
	const venue = page.getByLabel('Venue').first();
	const original = await venue.inputValue();
	await venue.fill('Lab 999');
	await page.getByRole('button', { name: 'Save and re-check' }).click();
	await expect(page.getByText('Unknown venue “Lab 999”.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Commit timetable' })).toBeDisabled();
	await venue.fill(original);
	await page.getByRole('button', { name: 'Save and re-check' }).click();
	await expect(page.getByText(/Unknown venue/)).toHaveCount(0);

	await page.getByRole('button', { name: 'Commit timetable' }).click();
	await expect(page).toHaveURL(/\/timetables$/);
	await page.getByRole('link', { name: new RegExp(`${label}.*lab slots a week`) }).click();
	await expect(page.getByRole('heading', { name: `${label} lab schedule` })).toBeVisible();

	// The committed lab sessions now appear on the availability grid for that weekday.
	await page.goto(`/availability?date=${date}&type=lab`);
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	// Desktop shows the class in each grid cell's tooltip; mobile lists it as text.
	const cls = new RegExp(`${label} · (DS|DBMS)`);
	const visible =
		info.project.name === 'desktop'
			? page.locator(`[title*="${label} · D"]`)
			: page.getByText(cls).locator('visible=true');
	await expect(visible.first()).toBeVisible();
});

test('faculty cannot upload timetables', async ({ page }) => {
	await login(page, 'swvcse@kiot.ac.in');
	await page.goto('/timetables');
	await expect(page.getByText('Only the office assistant, HOD and Director')).toBeVisible();
	await expect(page.getByLabel('Upload timetable PDFs')).toHaveCount(0);
});

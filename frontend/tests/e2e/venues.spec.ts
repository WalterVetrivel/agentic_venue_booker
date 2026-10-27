import { expect, test } from '@playwright/test';
import { login } from './helpers';

// April falls in the A Block Seminar Hall's admissions season (March to July).
const APRIL_DAY = '2027-04-05';

test('availability shows the A Block admissions block and filters by software', async ({
	page
}) => {
	await page.goto(`/availability?date=${APRIL_DAY}`);
	await expect(page.getByRole('heading', { name: 'Monday, 5 April 2027' })).toBeVisible();
	await expect(page.getByText(/Reserved for admission counselling/).locator('visible=true')).toHaveCount(1);

	await page.getByLabel('Needs software or equipment').fill('Power BI');
	await page.getByRole('button', { name: 'Apply filters' }).click();
	await expect(page.getByText('4 venues')).toBeVisible();
});

test('Sunday shows the college as closed', async ({ page }) => {
	await page.goto('/availability?date=2027-04-04');
	await expect(page.getByText('The college is closed on Sundays.')).toBeVisible();
});

test('in-charge puts their lab under maintenance and it shows as unavailable', async ({
	page
}, info) => {
	// Desktop and mobile runs share one database, so each uses its own date.
	const day = info.project.name === 'desktop' ? '2027-08-02' : '2027-08-03';
	await login(page, 'swvcse@kiot.ac.in');
	await page.goto('/venues/CC10');
	await page.getByLabel('Status', { exact: true }).selectOption('maintenance');
	await page.getByLabel('From').fill(day);
	await page.getByLabel('To (optional)').fill(day);
	await page.getByLabel('Reason').fill(`AC repair ${info.project.name}`);
	await page.getByRole('button', { name: 'Add period' }).click();
	await expect(page.getByText(`AC repair ${info.project.name}`)).toBeVisible();

	await page.goto(`/availability?date=${day}&type=lab`);
	await page.getByLabel('Free from').fill('10:00');
	await page.getByLabel('Free until').fill('11:00');
	await expect(page.getByRole('link', { name: 'CC9', exact: true }).or(page.getByRole('link', { name: 'Computer Centre 9' }))).toBeVisible();
	await expect(page.getByRole('link', { name: 'CC10', exact: true }).or(page.getByRole('link', { name: 'Computer Centre 10' }))).toHaveCount(0);
});

test('in-charge cannot edit a venue they do not own', async ({ page }) => {
	await login(page, 'swvcse@kiot.ac.in');
	await page.goto('/venues/CC9');
	await expect(page.getByRole('heading', { name: /Computer Centre 9/ })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Edit details' })).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Add period' })).toHaveCount(0);
});

test('director adds a venue', async ({ page }, info) => {
	const code = info.project.name === 'desktop' ? 'CC13' : 'CC14';
	await login(page, 'dirim@kiot.ac.in');
	await page.goto('/venues');
	await page.getByRole('link', { name: 'Add venue' }).click();
	await page.getByLabel('Code').fill(code);
	await page.getByLabel('Name').fill(`Computer Centre ${code.slice(2)}`);
	await page.getByLabel('Capacity').fill('40');
	await page.getByLabel('In-charge').selectOption('tkcse@kiot.ac.in');
	await page.getByRole('button', { name: 'Add venue' }).click();
	await expect(page).toHaveURL(new RegExp(`/venues/${code}$`));
	await expect(page.getByText('Mr. T. Karthikeyan')).toBeVisible();
});

test('faculty member does not see the add venue button', async ({ page }) => {
	await login(page, 'prcse@kiot.ac.in');
	await page.goto('/venues');
	await expect(page.getByRole('heading', { name: 'Venues' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Add venue' })).toHaveCount(0);
});

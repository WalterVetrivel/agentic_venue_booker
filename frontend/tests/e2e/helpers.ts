import { expect, type Page } from '@playwright/test';

export async function login(page: Page, email: string) {
	await page.goto('/login');
	await page.getByLabel('Email').fill(email);
	await page.getByLabel('Password').fill('password');
	await page.getByRole('button', { name: 'Log in' }).click();
	await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome');
}

export async function navLabels(page: Page) {
	const nav = page.getByRole('navigation', { name: 'Main' });
	if (!(await nav.isVisible())) await page.getByRole('button', { name: 'Open menu' }).click();
	return nav.getByRole('link').allInnerTexts();
}

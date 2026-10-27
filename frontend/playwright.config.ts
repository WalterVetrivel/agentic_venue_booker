import { defineConfig, devices } from '@playwright/test';

// Runs the real backend (serving the built SPA) against a freshly seeded e2e database.
// Requires `npm run build` first. Set PYTHON to the backend interpreter (e.g. ../backend/.venv/bin/python).
const python = process.env.PYTHON ?? 'python';
const db = 'sqlite:///./storage/e2e.db';

export default defineConfig({
	testDir: 'tests/e2e',
	use: {
		baseURL: 'http://127.0.0.1:8010',
		launchOptions: process.env.PW_CHROMIUM_PATH
			? { executablePath: process.env.PW_CHROMIUM_PATH }
			: {}
	},
	projects: [
		{
			name: 'desktop',
			use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
		},
		{ name: 'mobile', use: { ...devices['Pixel 7'] } }
	],
	webServer: {
		command: `${python} -c "import pathlib; pathlib.Path('storage/e2e.db').unlink(missing_ok=True)" && ${python} -m alembic upgrade head && ${python} -m app.seed && ${python} -m uvicorn app.main:app --port 8010`,
		cwd: '../backend',
		env: { DATABASE_URL: db },
		url: 'http://127.0.0.1:8010/api/health',
		reuseExistingServer: false,
		timeout: 120_000
	}
});

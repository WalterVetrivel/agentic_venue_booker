/** Local-date helpers. The backend works in naive local time (college time zone). */

export function isoDate(d: Date): string {
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(iso: string, days: number): string {
	const [y, m, d] = iso.split('-').map(Number);
	return isoDate(new Date(y, m - 1, d + days));
}

export function minutesOf(hhmm: string): number {
	const [h, m] = hhmm.split(':').map(Number);
	return h * 60 + m;
}

export function hhmm(minutes: number): string {
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** Minutes since midnight of `day` for an ISO datetime, clamped to [0, 1440]. */
export function minutesOnDay(isoDateTime: string, day: string): number {
	const [d, t] = isoDateTime.split('T');
	if (d < day) return 0;
	if (d > day) return 1440;
	return minutesOf(t.slice(0, 5));
}

export function prettyDate(iso: string): string {
	const [y, m, d] = iso.split('-').map(Number);
	return new Date(y, m - 1, d).toLocaleDateString('en-IN', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric'
	});
}

/** "Tue 3 Nov, 10:00–12:00" for one occurrence. */
export function whenText(start: string, end: string): string {
	const [d, t] = start.split('T');
	const [y, m, day] = d.split('-').map(Number);
	const date = new Date(y, m - 1, day).toLocaleDateString('en-IN', {
		weekday: 'short',
		day: 'numeric',
		month: 'short'
	});
	return `${date}, ${t.slice(0, 5)}–${end.split('T')[1].slice(0, 5)}`;
}

export function dateTimeText(iso: string): string {
	return new Date(iso).toLocaleString('en-IN', {
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

/** The current local time as a naive ISO string, comparable with the backend's datetimes. */
export function nowLocal(): string {
	const d = new Date();
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${isoDate(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;
}

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
	const res = await fetch(`/api${path}`, {
		credentials: 'same-origin',
		...init,
		headers: { 'Content-Type': 'application/json', ...init.headers }
	});
	if (!res.ok) {
		let message = res.statusText;
		try {
			message = (await res.json()).detail ?? message;
		} catch {
			/* not JSON */
		}
		throw new ApiError(res.status, message);
	}
	return res.status === 204 ? (undefined as T) : res.json();
}

export async function uploadFile<T>(path: string, file: File): Promise<T> {
	const body = new FormData();
	body.append('file', file);
	const res = await fetch(`/api${path}`, { method: 'POST', body, credentials: 'same-origin' });
	if (!res.ok) {
		let message = res.statusText;
		try {
			message = (await res.json()).detail ?? message;
		} catch {
			/* not JSON */
		}
		throw new ApiError(res.status, message);
	}
	return res.json();
}

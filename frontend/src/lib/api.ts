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

import { api } from '#lib/api.ts';
import type { User } from '#lib/types.ts';

type Me = { user: User | null; capabilities: string[] };

class Session {
	user = $state<User | null>(null);
	capabilities = $state<string[]>([]);
	loaded = $state(false);

	can(capability: string): boolean {
		return this.capabilities.includes(capability);
	}

	async load() {
		try {
			const me = await api<Me>('/auth/me');
			this.user = me.user;
			this.capabilities = me.capabilities;
		} finally {
			this.loaded = true;
		}
	}

	async login(email: string, password: string) {
		const user = await api<User>('/auth/login', {
			method: 'POST',
			body: JSON.stringify({ email, password })
		});
		this.user = user;
		this.capabilities = user.capabilities;
	}

	async logout() {
		await api('/auth/logout', { method: 'POST' });
		await this.load();
	}
}

export const session = new Session();

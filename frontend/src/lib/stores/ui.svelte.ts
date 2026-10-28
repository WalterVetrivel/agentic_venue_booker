function read(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

function write(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		/* storage unavailable */
	}
}

class Ui {
	theme = $state<'light' | 'dark'>(
		(document.documentElement.dataset.theme as 'light' | 'dark') ?? 'light'
	);
	// Docked chat on large screens remembers whether it was closed.
	chatOpen = $state(read('chatOpen') !== 'false' && window.innerWidth >= 1280);
	navOpen = $state(false);
	/** A detail page's own name for the last breadcrumb (cleared on every navigation). */
	crumb = $state('');

	toggleTheme() {
		this.theme = this.theme === 'dark' ? 'light' : 'dark';
		document.documentElement.dataset.theme = this.theme;
		write('theme', this.theme);
	}

	setChat(open: boolean) {
		this.chatOpen = open;
		write('chatOpen', String(open));
	}
}

export const ui = new Ui();

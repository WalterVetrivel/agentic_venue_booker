import { goto } from '$app/navigation';
import { api, uploadFile } from '#lib/api.ts';
import { session } from '#lib/stores/session.svelte.ts';
import type {
	Attachment,
	ChatCard,
	ChatMessage,
	Conversation,
	ConversationBrief,
	Providers
} from '#lib/types.ts';

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

type ChatEvent =
	| { type: 'conversation'; id: number; title: string }
	| { type: 'step'; id: string; tool: string; label: string }
	| { type: 'step_done'; id: string; ok: boolean; error?: string }
	| { type: 'card'; card: ChatCard }
	| { type: 'text'; text: string }
	| { type: 'done'; content: string; message_id?: number; provider: string; model: string }
	| { type: 'error'; message: string; message_id?: number };

class Chat {
	messages = $state<ChatMessage[]>([]);
	conversationId = $state<number | null>(null);
	title = $state('New chat');
	busy = $state(false);
	conversations = $state<ConversationBrief[]>([]);
	providers = $state<Providers | null>(null);
	provider = $state<string>(read('chatProvider') ?? '');
	model = $state<string>(read('chatModel') ?? '');
	attachment = $state<Attachment | null>(null);
	attaching = $state(false);
	attachError = $state('');
	private controller: AbortController | null = null;

	async loadProviders() {
		try {
			this.providers = await api<Providers>('/chat/providers');
		} catch {
			return;
		}
		const known = this.providers.providers.find((p) => p.key === this.provider);
		if (!known) this.choose(this.providers.default, '');
		else if (this.model && !known.models.includes(this.model)) this.choose(known.key, '');
	}

	choose(provider: string, model: string) {
		this.provider = provider;
		this.model = model;
		write('chatProvider', provider);
		write('chatModel', model);
	}

	get modelLabel(): string {
		if (this.providers?.demo) return 'Demo';
		const p = this.providers?.providers.find((x) => x.key === this.provider);
		return p ? `${p.key === 'groq' ? 'Groq' : 'Ollama'} · ${this.model || p.model}` : 'Assistant';
	}

	reset() {
		this.controller?.abort();
		this.messages = [];
		this.conversationId = null;
		this.title = 'New chat';
		this.attachment = null;
		this.attachError = '';
		this.busy = false;
	}

	async loadConversations(q = '') {
		if (!session.user) {
			this.conversations = [];
			return;
		}
		const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : '';
		this.conversations = await api<ConversationBrief[]>(`/chat/conversations${query}`);
	}

	async open(id: number) {
		this.reset();
		const c = await api<Conversation>(`/chat/conversations/${id}`);
		this.conversationId = c.id;
		this.title = c.title;
		this.messages = c.messages;
	}

	async rename(id: number, title: string) {
		await api(`/chat/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) });
		if (this.conversationId === id) this.title = title;
		await this.loadConversations();
	}

	async remove(id: number) {
		await api(`/chat/conversations/${id}`, { method: 'DELETE' });
		if (this.conversationId === id) this.reset();
		await this.loadConversations();
	}

	async attach(file: File) {
		this.attaching = true;
		this.attachError = '';
		try {
			this.attachment = await uploadFile<Attachment>('/chat/attachments', file);
		} catch (e) {
			this.attachError = e instanceof Error ? e.message : 'Could not read the file';
		} finally {
			this.attaching = false;
		}
	}

	stop() {
		this.controller?.abort();
	}

	/** Ask the last question again, replacing its reply (after a timeout or rate limit, say). */
	async rerun() {
		if (this.busy) return;
		const at = this.messages.findLastIndex((m) => m.role === 'user');
		if (at < 0) return;
		const question = this.messages[at];
		this.messages.splice(at);
		await this.send(question.content, { regenerate: true, attachment: question.attachment });
	}

	async send(text: string, opts: { regenerate?: boolean; attachment?: Attachment | null } = {}) {
		text = text.trim();
		if (!text || this.busy) return;
		const history = session.user
			? []
			: this.messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
		let attachment: Attachment | null | undefined = opts.attachment;
		if (!opts.regenerate) {
			attachment = this.attachment;
			this.attachment = null;
		}
		this.messages.push({
			role: 'user',
			content: text,
			attachment,
			steps: [],
			cards: attachment ? [{ kind: 'file', title: attachment.title, href: attachment.link }] : []
		});
		this.messages.push({ role: 'assistant', content: '', steps: [], cards: [], streaming: true });
		const reply = this.messages[this.messages.length - 1];
		this.busy = true;
		this.controller = new AbortController();
		try {
			const res = await fetch('/api/chat', {
				method: 'POST',
				credentials: 'same-origin',
				headers: { 'Content-Type': 'application/json' },
				signal: this.controller.signal,
				body: JSON.stringify({
					message: text,
					conversation_id: this.conversationId,
					provider: this.provider || null,
					model: this.model || null,
					history,
					attachment,
					regenerate: !!opts.regenerate && this.conversationId !== null
				})
			});
			if (!res.ok || !res.body) {
				let message = res.statusText;
				try {
					message = (await res.json()).detail ?? message;
				} catch {
					/* not JSON */
				}
				throw new Error(message);
			}
			const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
			let buffer = '';
			for (;;) {
				const { value, done } = await reader.read();
				if (done) break;
				buffer += value;
				let cut;
				while ((cut = buffer.indexOf('\n\n')) >= 0) {
					const chunk = buffer.slice(0, cut);
					buffer = buffer.slice(cut + 2);
					if (chunk.startsWith('data: ')) this.apply(reply, JSON.parse(chunk.slice(6)));
				}
			}
		} catch (e) {
			if ((e as Error).name !== 'AbortError')
				reply.error = e instanceof Error ? e.message : 'Something went wrong';
		} finally {
			reply.streaming = false;
			reply.content = reply.content.trim();
			this.busy = false;
			this.controller = null;
			this.refillOpenForm(reply);
			if (session.user) this.loadConversations();
		}
	}

	/** A draft's form link, tagged so the form can mark the card once it's submitted. */
	draftHref(message: ChatMessage, index: number, href: string) {
		if (!message.id) return href;
		const url = new URL(href, window.location.origin);
		url.searchParams.set('from_msg', String(message.id));
		url.searchParams.set('from_card', String(index));
		return url.pathname + url.search;
	}

	/** If the person is already on the form a new draft is for, fill it in straight away. */
	private refillOpenForm(reply: ChatMessage) {
		const index = reply.cards.findLastIndex((c) => c.kind === 'draft' && c.href);
		if (index < 0) return;
		const href = this.draftHref(reply, index, reply.cards[index].href!);
		if (href.split('?')[0] === window.location.pathname)
			goto(href, { replace: true, reset: false });
	}

	private apply(reply: ChatMessage, e: ChatEvent) {
		switch (e.type) {
			case 'conversation':
				this.conversationId = e.id;
				this.title = e.title;
				break;
			case 'step':
				reply.steps.push({ id: e.id, tool: e.tool, label: e.label });
				break;
			case 'step_done': {
				const step = reply.steps.find((s) => s.id === e.id);
				if (step) Object.assign(step, { ok: e.ok, error: e.error });
				break;
			}
			case 'card':
				reply.cards.push(e.card);
				break;
			case 'text':
				reply.content += e.text;
				break;
			case 'done':
				reply.id = e.message_id;
				reply.content = e.content;
				break;
			case 'error':
				reply.id = e.message_id;
				reply.error = e.message;
				break;
		}
	}

	/** Run a proposal card's action through the normal API, marked as coming from the assistant. */
	async confirm(message: ChatMessage, index: number) {
		const card = message.cards[index];
		const action = card.action;
		if (!action || !action.url.startsWith('/api/') || action.url.includes('..')) return;
		card.note = null;
		try {
			await api(action.url.slice(4), {
				method: action.method,
				headers: { 'X-Via': 'agent' },
				body: action.body === undefined ? undefined : JSON.stringify(action.body)
			});
		} catch (e) {
			card.note = e instanceof Error ? e.message : 'That did not work';
			return;
		}
		await this.mark(message, index, 'done', card.done ?? 'Done.');
	}

	/** The booking form submitted a draft from this chat: show its card as submitted. */
	async draftSubmitted(messageId: number, index: number, note: string) {
		const message = this.messages.find((m) => m.id === messageId);
		if (message?.cards[index]) {
			await this.mark(message, index, 'done', note);
			return;
		}
		// The chat isn't on screen (or was reset): still record it in the saved history.
		try {
			await api(`/chat/messages/${messageId}/cards/${index}`, {
				method: 'POST',
				body: JSON.stringify({ state: 'done', note })
			});
		} catch {
			/* the booking itself went through; only the history note failed */
		}
	}

	async mark(message: ChatMessage, index: number, state: 'done' | 'dismissed', note?: string) {
		const card = message.cards[index];
		card.state = state;
		card.note = note ?? null;
		if (message.id && session.user) {
			try {
				await api(`/chat/messages/${message.id}/cards/${index}`, {
					method: 'POST',
					body: JSON.stringify({ state, note: card.note })
				});
			} catch {
				/* the change itself went through; only the history note failed */
			}
		}
	}
}

export const chat = new Chat();

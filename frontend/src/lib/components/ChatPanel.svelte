<script lang="ts">
	import { tick, untrack } from 'svelte';
	import Icon from './Icon.svelte';
	import { renderMarkdown } from '#lib/markdown.ts';
	import { yesNoReplies } from '#lib/replies.ts';
	import { chat } from '#lib/stores/chat.svelte.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import type { ChatMessage } from '#lib/types.ts';

	let historyOpen = $state(false);
	let modelOpen = $state(false);
	let historyMenu = $state<HTMLDivElement>();
	let modelMenu = $state<HTMLDivElement>();

	// Clicking anywhere outside an open menu closes it.
	function onWindowClick(e: MouseEvent) {
		const target = e.target as Node;
		if (historyOpen && historyMenu && !historyMenu.contains(target)) historyOpen = false;
		if (modelOpen && modelMenu && !modelMenu.contains(target)) modelOpen = false;
	}

	function onWindowKey(e: KeyboardEvent) {
		if (e.key === 'Escape') historyOpen = modelOpen = false;
	}

	let draft = $state('');
	let search = $state('');
	let renaming = $state<number | null>(null);
	let newTitle = $state('');
	let scroller = $state<HTMLDivElement>();
	let fileInput = $state<HTMLInputElement>();

	const suggestions = $derived.by(() => {
		const caps = session.capabilities;
		if (caps.includes('approve_cse_venues') || caps.includes('approve_all'))
			return ['What is waiting for my approval?', 'Which labs are free tomorrow afternoon?'];
		if (caps.includes('upload_timetables') && !caps.includes('book'))
			return ['Which labs does CSE III-B use?', 'Is CC5 free on Monday 10:00 to 12:00?'];
		if (caps.includes('book'))
			return [
				'Find a lab for 35 students with Power BI next Friday 14:00 to 16:00',
				'Where were Gen-AI workshops held before?'
			];
		return ['Which labs are free tomorrow afternoon?', 'Which lab has Docker installed?'];
	});

	// A new person (login or logout) starts with a fresh chat.
	$effect(() => {
		session.user?.id;
		untrack(() => {
			chat.reset();
			chat.loadConversations().catch(() => {});
		});
	});

	$effect(() => {
		if (ui.chatOpen && !chat.providers) untrack(() => chat.loadProviders());
	});

	// Keep the newest message in view while a reply streams in.
	$effect(() => {
		const last = chat.messages.at(-1);
		void last?.content;
		void last?.steps.length;
		void last?.cards.length;
		void chat.messages.length;
		tick().then(() => scroller?.scrollTo({ top: scroller.scrollHeight }));
	});

	function submit(e?: Event) {
		e?.preventDefault();
		const text = draft;
		draft = '';
		chat.send(text);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) submit(e);
	}

	function closeOnSmallScreens() {
		if (window.innerWidth < 1280) ui.setChat(false);
	}

	async function openHistory() {
		historyOpen = !historyOpen;
		modelOpen = false;
		if (historyOpen) await chat.loadConversations(search);
	}

	async function pick(id: number) {
		historyOpen = false;
		await chat.open(id);
	}

	async function saveTitle(id: number) {
		if (newTitle.trim()) await chat.rename(id, newTitle.trim());
		renaming = null;
	}

	function stepIcon(ok: boolean | undefined) {
		return ok === undefined ? '…' : ok ? '✓' : '✗';
	}

	const isEmpty = $derived(chat.messages.length === 0);
	const canAttach = $derived(!!session.user);

	function attachFile(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (file) chat.attach(file);
		input.value = '';
	}

	function cardDone(m: ChatMessage, i: number) {
		return m.cards[i].state === 'done' || m.cards[i].state === 'dismissed';
	}

	const lastIndex = $derived(chat.messages.length - 1);
	// Yes/no chips under the last reply, unless a card is already asking for a decision.
	const quickReplies = $derived.by(() => {
		const m = chat.messages.at(-1);
		if (!m || m.role !== 'assistant' || m.streaming || m.error || chat.busy) return [];
		if (m.cards.some((c, i) => c.kind === 'confirm' && !cardDone(m, i))) return [];
		return yesNoReplies(m.content);
	});
</script>

<svelte:window onclick={onWindowClick} onkeydown={onWindowKey} />

{#if ui.chatOpen}
	<!-- Backdrop only when the chat overlays content (below xl). -->
	<button
		class="fixed inset-0 z-40 bg-black/40 xl:hidden"
		aria-label="Close assistant"
		onclick={() => ui.setChat(false)}
	></button>

	<aside
		class="glass-strong fixed inset-0 z-50 flex flex-col border-l md:left-auto md:w-[26rem] xl:top-16 xl:z-20"
		aria-label="AI assistant"
	>
		<div class="flex h-16 shrink-0 items-center gap-1 border-b border-border px-3">
			<div class="relative min-w-0" bind:this={historyMenu}>
				<button
					class="flex max-w-56 items-center gap-2 rounded-lg px-2 py-1.5 font-semibold hover:bg-surface-2"
					aria-expanded={historyOpen}
					aria-haspopup="menu"
					onclick={openHistory}
				>
					<Icon name="history" size={18} class="shrink-0" />
					<span class="truncate">{chat.title}</span>
					<Icon name="chevron" size={16} class="shrink-0" />
				</button>
				{#if historyOpen}
					<div
						class="pop absolute top-full left-0 z-10 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-surface p-3 shadow-lg"
					>
						<button
							class="mb-2 flex w-full items-center gap-2 rounded-lg bg-accent-soft px-3 py-2 font-medium text-accent hover:bg-accent/15"
							onclick={() => {
								chat.reset();
								historyOpen = false;
							}}
						>
							<Icon name="plus" size={18} /> New chat
						</button>
						{#if session.user}
							<label class="sr-only" for="chat-search">Search chats</label>
							<input
								id="chat-search"
								type="search"
								placeholder="Search your chats"
								bind:value={search}
								oninput={() => chat.loadConversations(search)}
								class="mb-2 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm"
							/>
							<ul class="max-h-80 overflow-y-auto">
								{#each chat.conversations as c (c.id)}
									<li class="group flex items-center gap-1 rounded-lg hover:bg-surface-2">
										{#if renaming === c.id}
											<form
												class="flex flex-1 gap-1 p-1"
												onsubmit={(e) => {
													e.preventDefault();
													saveTitle(c.id);
												}}
											>
												<input
													aria-label="Chat title"
													bind:value={newTitle}
													class="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1 text-sm"
												/>
												<button class="rounded px-2 text-sm text-accent">Save</button>
											</form>
										{:else}
											<button
												class="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm {c.id ===
												chat.conversationId
													? 'font-semibold'
													: ''}"
												onclick={() => pick(c.id)}>{c.title}</button
											>
											<button
												class="rounded px-1.5 py-1 text-xs text-muted hover:text-fg"
												aria-label="Rename {c.title}"
												onclick={() => {
													renaming = c.id;
													newTitle = c.title;
												}}>Rename</button
											>
											<button
												class="rounded px-1.5 py-1 text-xs text-danger"
												aria-label="Delete {c.title}"
												onclick={() => chat.remove(c.id)}>Delete</button
											>
										{/if}
									</li>
								{:else}
									<li class="px-3 py-2 text-sm text-muted">
										{search ? 'No chats match.' : 'No saved chats yet.'}
									</li>
								{/each}
							</ul>
						{:else}
							<p class="px-3 text-sm text-muted">Chats aren't saved for visitors.</p>
						{/if}
					</div>
				{/if}
			</div>

			<div class="relative ml-auto" bind:this={modelMenu}>
				<button
					class="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium text-muted hover:text-fg"
					aria-haspopup="menu"
					aria-expanded={modelOpen}
					title="Choose the model"
					onclick={() => {
						modelOpen = !modelOpen;
						historyOpen = false;
					}}>{chat.modelLabel}</button
				>
				{#if modelOpen && chat.providers}
					<div
						class="pop absolute top-full right-0 z-10 mt-2 w-72 rounded-xl border border-border bg-surface p-3 shadow-lg"
					>
						{#if chat.providers.demo}
							<p class="text-sm text-muted">
								The demo assistant is on (LLM_FAKE): answers are scripted.
							</p>
						{/if}
						{#each chat.providers.providers as p (p.key)}
							<fieldset class="mb-3 last:mb-0">
								<legend class="text-sm font-semibold">{p.label}</legend>
								{#if p.note}<p class="text-xs text-muted">{p.note}</p>{/if}
								{#each p.models as m (m)}
									<label class="flex items-center gap-2 py-1 text-sm">
										<input
											type="radio"
											name="chat-model"
											checked={chat.provider === p.key && (chat.model || p.model) === m}
											onchange={() => {
												chat.choose(p.key, m === p.model ? '' : m);
												modelOpen = false;
											}}
										/>
										{m}
									</label>
								{/each}
							</fieldset>
						{/each}
					</div>
				{/if}
			</div>
			<button
				class="rounded-lg p-2 hover:bg-surface-2"
				aria-label="Close assistant"
				onclick={() => ui.setChat(false)}
			>
				<Icon name="close" />
			</button>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto p-5" bind:this={scroller} aria-live="polite">
			{#if isEmpty}
				<div class="rounded-2xl bg-gradient-to-br from-accent-soft to-surface-2 p-4">
					<p class="font-medium">
						Hi{session.user ? `, ${session.user.name}` : ''}! I can check availability, recommend
						venues and help with bookings.
					</p>
					<p class="mt-2 text-sm text-muted">
						{session.user
							? 'I fill in forms and prepare changes; you confirm them.'
							: 'Log in as staff to book. Visitors can check venues and availability.'}
					</p>
				</div>
				<div class="space-y-2">
					<p class="text-sm font-medium text-muted">Try asking</p>
					{#each suggestions as s (s)}
						<button
							class="press lift glass block w-full rounded-xl border px-4 py-2.5 text-left hover:border-accent/50"
							onclick={() => (draft = s)}>{s}</button
						>
					{/each}
				</div>
			{/if}

			{#each chat.messages as m, mi (mi)}
				{#if m.role === 'user'}
					<div
						class="pop ml-8 rounded-2xl rounded-br-md bg-gradient-to-br from-accent to-accent/85 px-4 py-2.5 text-accent-fg shadow-sm"
						data-role="user"
					>
						{#each m.cards as f, i (i)}
							<p class="mb-1 text-sm opacity-90">📎 {f.title}</p>
						{/each}
						<p class="whitespace-pre-wrap">{m.content}</p>
					</div>
				{:else}
					<div class="group/msg space-y-2" data-role="assistant">
						{#if m.steps.length}
							<ul class="space-y-0.5 text-sm text-muted">
								{#each m.steps as s (s.id)}
									<li class={s.ok === false ? 'text-danger' : ''}>
										<span aria-hidden="true">{stepIcon(s.ok)}</span>
										{s.label}{s.error ? `: ${s.error}` : ''}
									</li>
								{/each}
							</ul>
						{/if}
						{#if m.content}
							<div class="chat-md space-y-2">{@html renderMarkdown(m.content)}</div>
						{:else if m.streaming}
							<p class="typing flex items-center py-1 text-muted" aria-label="Thinking">
								<span></span><span></span><span></span>
							</p>
						{/if}
						{#each m.cards as c, ci (ci)}
							<div
								class="rounded-xl border p-4 {c.danger ? 'border-danger/40' : 'border-accent/40'}"
								data-card={c.kind}
							>
								<p class="font-semibold">{c.title}</p>
								<ul class="mt-1 text-sm text-muted">
									{#each c.lines ?? [] as line, li (li)}<li>{line}</li>{/each}
								</ul>
								{#if c.kind === 'draft' && c.href}
									{#if c.state === 'done'}
										<button
											class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-success/10 px-4 py-2 font-medium text-success"
											disabled
											title={c.note ?? undefined}
										>
											<Icon name="check" size={16} /> Submitted
										</button>
										{#if c.note}<p class="mt-1 text-sm text-muted">{c.note}</p>{/if}
									{:else}
										<a
											href={chat.draftHref(m, ci, c.href)}
											class="btn-cta mt-3 inline-block rounded-lg px-4 py-2 font-medium"
											onclick={closeOnSmallScreens}>{c.button ?? 'Open'}</a
										>
									{/if}
								{:else if c.kind === 'confirm'}
									{#if c.state === 'done' && c.booking_id && c.outcome}
										<button
											class="mt-3 inline-flex items-center gap-1.5 rounded-lg px-4 py-2 font-medium {c.outcome ===
											'Approved'
												? 'bg-success/10 text-success'
												: c.outcome === 'Rejected'
													? 'bg-danger/10 text-danger'
													: 'bg-surface-2 text-muted'}"
											disabled
										>
											<Icon name={c.outcome === 'Approved' ? 'check' : 'close'} size={16} />
											{c.outcome}
										</button>
										{#if c.note}<p class="mt-1 text-sm text-muted">{c.note}</p>{/if}
									{:else if cardDone(m, ci)}
										<p
											class="mt-3 text-sm font-medium {c.state === 'done'
												? 'text-success'
												: 'text-muted'}"
										>
											{c.state === 'done' ? `✓ ${c.note ?? 'Done.'}` : 'Dismissed.'}
										</p>
									{:else}
										<div class="mt-3 flex gap-2">
											<button
												class="rounded-lg px-4 py-2 font-medium {c.danger
													? 'bg-danger text-white'
													: 'btn-cta'}"
												onclick={() => chat.confirm(m, ci)}>{c.button ?? 'Confirm'}</button
											>
											<button
												class="rounded-lg border border-border px-4 py-2 font-medium hover:bg-surface-2"
												onclick={() => chat.mark(m, ci, 'dismissed')}>Not now</button
											>
										</div>
										{#if c.note}<p class="mt-2 text-sm text-danger" role="alert">{c.note}</p>{/if}
									{/if}
								{/if}
							</div>
						{/each}
						{#if m.error}
							<div
								class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger"
								role="alert"
							>
								<span>{m.error}</span>
								{#if mi === lastIndex && !chat.busy}
									<button
										class="press inline-flex items-center gap-1.5 rounded-md bg-danger/10 px-2.5 py-1 font-medium hover:bg-danger/20"
										onclick={() => chat.rerun()}
									>
										<Icon name="retry" size={14} /> Try again
									</button>
								{/if}
							</div>
						{/if}
						{#if mi === lastIndex && !m.streaming && !chat.busy}
							<div class="flex items-center gap-1 text-muted">
								<button
									class="press group/rerun rounded-md p-1.5 hover:bg-surface-2 hover:text-fg"
									aria-label="Rerun"
									title="Run the same prompt again"
									onclick={() => chat.rerun()}
								>
									<Icon
										name="retry"
										size={16}
										class="transition-transform duration-500 group-hover/rerun:rotate-180"
									/>
								</button>
							</div>
						{/if}
					</div>
				{/if}
			{/each}

			{#if quickReplies.length}
				<div class="flex flex-wrap gap-2" aria-label="Quick replies" role="group">
					{#each quickReplies as q, i (q)}
						<button
							class="press pop rounded-full border border-accent/40 bg-accent-soft px-4 py-1.5 text-sm font-medium text-accent hover:bg-accent hover:text-accent-fg"
							style="animation-delay: {i * 60}ms"
							onclick={() => chat.send(q)}>{q}</button
						>
					{/each}
				</div>
			{/if}
		</div>

		<form class="border-t border-border p-4" onsubmit={submit}>
			{#if chat.attachment || chat.attaching || chat.attachError}
				<div class="mb-2 flex items-center gap-2 text-sm">
					{#if chat.attaching}
						<span class="text-muted">Reading the PDF…</span>
					{:else if chat.attachment}
						<span class="truncate rounded-full bg-surface-2 px-3 py-1"
							>📎 {chat.attachment.title}{chat.attachment.kind === 'timetable'
								? ' (timetable, ready to review)'
								: chat.attachment.kind === 'document'
									? ' (added to past events)'
									: ''}</span
						>
						<button
							type="button"
							class="text-muted hover:text-fg"
							aria-label="Remove attachment"
							onclick={() => (chat.attachment = null)}>✕</button
						>
					{:else}
						<span class="text-danger" role="alert">{chat.attachError}</span>
					{/if}
				</div>
			{/if}
			<div class="flex items-end gap-2">
				{#if canAttach}
					<input
						bind:this={fileInput}
						type="file"
						accept="application/pdf"
						class="hidden"
						aria-label="Attach a PDF"
						onchange={attachFile}
					/>
					<button
						type="button"
						class="rounded-lg border border-border p-3 hover:bg-surface-2"
						aria-label="Attach a PDF"
						title="Attach a timetable, circular or report (PDF)"
						disabled={chat.attaching}
						onclick={() => fileInput?.click()}
					>
						<Icon name="clip" />
					</button>
				{/if}
				<label class="sr-only" for="chat-input">Message</label>
				<textarea
					id="chat-input"
					rows="2"
					bind:value={draft}
					onkeydown={onKey}
					placeholder="Ask about venues, availability or bookings…"
					class="min-h-12 flex-1 resize-none rounded-lg border border-border bg-glass px-3 py-2.5 transition focus:border-accent focus:ring-3 focus:ring-accent/15 focus:outline-none"
				></textarea>
				{#if chat.busy}
					<button
						type="button"
						class="press rounded-lg bg-surface-2 p-3"
						aria-label="Stop"
						onclick={() => chat.stop()}
					>
						<Icon name="stop" />
					</button>
				{:else}
					<button
						type="submit"
						disabled={!draft.trim()}
						class="btn-cta rounded-lg p-3 disabled:opacity-50"
						aria-label="Send"
					>
						<Icon name="send" />
					</button>
				{/if}
			</div>
		</form>
	</aside>
{:else}
	<button
		class="press pop fixed right-5 bottom-5 z-30 flex items-center gap-2 rounded-full bg-gradient-to-br from-accent to-accent/80 px-5 py-3.5 font-medium text-accent-fg shadow-lg transition-shadow hover:shadow-xl hover:shadow-accent/30"
		onclick={() => ui.setChat(true)}
	>
		<Icon name="chat" /> Ask the assistant
	</button>
{/if}

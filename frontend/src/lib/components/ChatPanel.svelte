<script lang="ts">
	import Icon from './Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';

	let historyOpen = $state(false);
	let draft = $state('');

	const suggestions = $derived.by(() => {
		const caps = session.capabilities;
		if (caps.includes('approve_cse_venues') || caps.includes('approve_all'))
			return ['Summarise pending approvals', 'Which labs were used most last month?'];
		if (caps.includes('upload_timetables') && !caps.includes('book'))
			return ['Read this timetable PDF', 'Which labs does CSE III-B use?'];
		if (caps.includes('book'))
			return [
				'Find a lab for 55 students with Power BI next Friday afternoon',
				'Where were Gen-AI workshops held before?'
			];
		return ['Which labs are free tomorrow afternoon?', 'Which lab has Docker installed?'];
	});
</script>

{#if ui.chatOpen}
	<!-- Backdrop only when the chat overlays content (below xl). -->
	<button
		class="fixed inset-0 z-40 bg-black/40 xl:hidden"
		aria-label="Close assistant"
		onclick={() => ui.setChat(false)}
	></button>

	<aside
		class="fixed inset-0 z-50 flex flex-col border-l border-border bg-surface md:left-auto md:w-[26rem] xl:top-16 xl:z-20"
		aria-label="AI assistant"
	>
		<div class="flex h-16 shrink-0 items-center gap-2 border-b border-border px-4">
			<div class="relative">
				<button
					class="flex items-center gap-2 rounded-lg px-2 py-1.5 font-semibold hover:bg-surface-2"
					aria-expanded={historyOpen}
					aria-haspopup="menu"
					onclick={() => (historyOpen = !historyOpen)}
				>
					<Icon name="history" size={18} /> New chat <Icon name="chevron" size={16} />
				</button>
				{#if historyOpen}
					<div
						class="absolute top-full left-0 z-10 mt-2 w-72 rounded-xl border border-border bg-surface p-3 shadow-lg"
						role="menu"
					>
						<p class="text-sm text-muted">
							{session.user
								? 'Your saved chats will be listed here.'
								: "Chats aren't saved for visitors."}
						</p>
					</div>
				{/if}
			</div>
			<span
				class="ml-auto rounded-full bg-surface-2 px-2.5 py-1 text-xs font-medium text-muted"
				title="LLM provider">Groq</span
			>
			<button
				class="rounded-lg p-2 hover:bg-surface-2"
				aria-label="Close assistant"
				onclick={() => ui.setChat(false)}
			>
				<Icon name="close" />
			</button>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto p-5">
			<div class="rounded-xl bg-surface-2 p-4">
				<p class="font-medium">
					Hi{session.user ? `, ${session.user.name}` : ''}! I can check availability, recommend
					venues and help with bookings.
				</p>
				<p class="mt-2 text-sm text-muted">The assistant is switched on in Phase 5.</p>
			</div>
			<div class="space-y-2">
				<p class="text-sm font-medium text-muted">Try asking</p>
				{#each suggestions as s (s)}
					<button
						class="block w-full rounded-lg border border-border px-4 py-2.5 text-left hover:bg-surface-2"
						onclick={() => (draft = s)}>{s}</button
					>
				{/each}
			</div>
		</div>

		<form class="border-t border-border p-4" onsubmit={(e) => e.preventDefault()}>
			<div class="flex items-end gap-2">
				<label class="sr-only" for="chat-input">Message</label>
				<textarea
					id="chat-input"
					rows="2"
					bind:value={draft}
					placeholder="Ask about venues, availability or bookings…"
					class="min-h-12 flex-1 resize-none rounded-lg border border-border bg-bg px-3 py-2.5 focus:border-accent focus:outline-none"
				></textarea>
				<button
					type="submit"
					disabled
					class="rounded-lg bg-accent p-3 text-accent-fg disabled:opacity-50"
					aria-label="Send"
				>
					<Icon name="send" />
				</button>
			</div>
		</form>
	</aside>
{:else}
	<button
		class="fixed right-5 bottom-5 z-30 flex items-center gap-2 rounded-full bg-accent px-5 py-3.5 font-medium text-accent-fg shadow-lg hover:opacity-90"
		onclick={() => ui.setChat(true)}
	>
		<Icon name="chat" /> Ask the assistant
	</button>
{/if}

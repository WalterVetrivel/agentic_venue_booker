<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { visibleNav } from '#lib/nav.ts';

	const cards = $derived(visibleNav(session.capabilities).filter((n) => n.href !== '/'));
</script>

<h1 class="text-3xl font-semibold">
	{session.user ? `Welcome, ${session.user.name}` : 'Find a lab or venue'}
</h1>
<p class="mt-2 text-lg text-muted">
	{session.user
		? 'Book venues, track approvals and ask the assistant for recommendations.'
		: 'Check which labs are free and what hardware and software they have.'}
</p>

<div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
	{#each cards as c (c.href)}
		<a
			href={c.href}
			class="flex items-start gap-4 rounded-xl border border-border bg-surface p-5 transition hover:border-accent"
		>
			<span class="rounded-lg bg-accent-soft p-2.5 text-accent"><Icon name={c.icon} /></span>
			<span>
				<span class="block font-semibold">{c.label}</span>
				{#if c.phase}<span class="text-sm text-muted">Phase {c.phase}</span>{/if}
			</span>
		</a>
	{/each}
</div>

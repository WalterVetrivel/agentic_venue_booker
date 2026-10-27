<script lang="ts">
	import { NAV } from '#lib/nav.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { page } from '$app/state';

	let { children }: { children?: any } = $props();

	const item = $derived(NAV.find((n) => n.href === page.url.pathname));
	const allowed = $derived(
		!item || item.anyOf.length === 0 || item.anyOf.some((c) => session.can(c))
	);
</script>

{#if item}
	<h1 class="text-2xl font-semibold">{item.label}</h1>
	{#if !allowed}
		<div class="mt-6 rounded-xl border border-border bg-surface p-8">
			{#if session.user}
				<p>You don't have access to this page.</p>
			{:else}
				<p>Please <a class="text-accent underline" href="/login">log in</a> to use this page.</p>
			{/if}
		</div>
	{:else}
		<div class="mt-6 rounded-xl border border-dashed border-border bg-surface p-8">
			<p class="text-sm font-medium tracking-wide text-accent uppercase">
				Coming in Phase {item.phase}
			</p>
			<div class="mt-2 text-muted">{@render children?.()}</div>
		</div>
	{/if}
{/if}

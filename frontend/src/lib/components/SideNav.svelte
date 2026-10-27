<script lang="ts">
	import Icon from './Icon.svelte';
	import { page } from '$app/state';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { visibleNav } from '#lib/nav.ts';

	const items = $derived(visibleNav(session.capabilities));

	function active(href: string) {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path.startsWith(href);
	}
</script>

{#if ui.navOpen}
	<button
		class="fixed inset-0 z-30 bg-black/40 lg:hidden"
		aria-label="Close menu"
		onclick={() => (ui.navOpen = false)}
	></button>
{/if}

<nav
	class="fixed top-16 bottom-0 left-0 z-40 w-64 overflow-y-auto border-r border-border bg-surface p-4 transition-transform lg:sticky lg:z-0 lg:h-[calc(100vh-4rem)] lg:translate-x-0 {ui.navOpen
		? 'translate-x-0'
		: '-translate-x-full'}"
	aria-label="Main"
>
	<ul class="space-y-1">
		{#each items as item (item.href)}
			<li>
				<a
					href={item.href}
					onclick={() => (ui.navOpen = false)}
					class="flex items-center gap-3 rounded-lg px-3 py-2.5 {active(item.href)
						? 'bg-accent-soft font-semibold text-accent'
						: 'hover:bg-surface-2'}"
					aria-current={active(item.href) ? 'page' : undefined}
				>
					<Icon name={item.icon} />
					<span>{item.label}</span>
				</a>
			</li>
		{/each}
	</ul>
	{#if !session.user && session.loaded}
		<p class="mt-6 rounded-lg bg-surface-2 p-3 text-sm text-muted">
			Students can browse venues and availability without logging in. Staff log in to book.
		</p>
	{/if}
</nav>

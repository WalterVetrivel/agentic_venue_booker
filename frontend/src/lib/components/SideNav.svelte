<script lang="ts">
	import Icon from './Icon.svelte';
	import { page } from '$app/state';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { visibleNav } from '#lib/nav.ts';

	const items = $derived(visibleNav(session.capabilities));
	// A collapsed nav opens over the page while the pointer (or focus) is on it.
	let peek = $state(false);
	const slim = $derived(ui.navCollapsed && !peek);

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

<!-- Holds the nav's place in the layout on large screens. -->
<div
	class="shrink-0 transition-[width] duration-200 ease-in-out lg:relative {ui.navCollapsed
		? 'lg:w-[4.5rem]'
		: 'lg:w-64'}"
>
	<nav
		class="fixed top-16 bottom-0 left-0 z-40 w-64 overflow-x-hidden overflow-y-auto glass-bar border-r p-3 transition-[transform,width,box-shadow] duration-200 ease-in-out lg:sticky lg:h-[calc(100vh-4rem)] lg:translate-x-0 {ui.navOpen
			? 'translate-x-0'
			: '-translate-x-full'} {slim ? 'lg:w-[4.5rem]' : 'lg:w-64'} {ui.navCollapsed && peek
			? 'nav-peek lg:z-30'
			: 'lg:z-0'}"
		aria-label="Main"
		onmouseenter={() => (peek = ui.navCollapsed)}
		onmouseleave={() => (peek = false)}
		onfocusin={() => (peek = ui.navCollapsed)}
		onfocusout={(e) => {
			if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) peek = false;
		}}
	>
		<ul class="space-y-1">
			{#each items as item (item.href)}
				<li>
					<a
						href={item.href}
						onclick={() => (ui.navOpen = false)}
						title={slim ? item.label : undefined}
						class="group flex items-center gap-3 rounded-xl px-3 py-2.5 whitespace-nowrap {active(
							item.href
						)
							? 'bg-accent-soft font-semibold text-accent shadow-sm'
							: 'hover:bg-surface-2'}"
						aria-current={active(item.href) ? 'page' : undefined}
					>
						<Icon
							name={item.icon}
							class="shrink-0 transition-transform duration-200 ease-in-out group-hover:scale-110"
						/>
						<span class="transition-opacity duration-200 ease-in-out {slim ? 'lg:opacity-0' : ''}"
							>{item.label}</span
						>
					</a>
				</li>
			{/each}
		</ul>
		{#if !session.user && session.loaded}
			<p class="mt-6 rounded-xl bg-surface-2 p-3 text-sm text-muted {slim ? 'lg:hidden' : ''}">
				Students can browse venues and availability without logging in. Staff log in to book.
			</p>
		{/if}
		<button
			class="mt-4 hidden w-full items-center gap-3 rounded-xl px-3 py-2.5 whitespace-nowrap text-muted hover:bg-surface-2 hover:text-fg lg:flex"
			aria-label={ui.navCollapsed ? 'Keep the menu open' : 'Collapse the menu'}
			title={ui.navCollapsed ? 'Keep the menu open' : 'Collapse the menu'}
			onclick={() => {
				ui.toggleNav();
				peek = false;
			}}
		>
			<Icon name={ui.navCollapsed ? 'expand' : 'collapse'} class="shrink-0" />
			<span class="transition-opacity duration-200 ease-in-out {slim ? 'lg:opacity-0' : ''}"
				>{ui.navCollapsed ? 'Keep open' : 'Collapse'}</span
			>
		</button>
	</nav>
</div>

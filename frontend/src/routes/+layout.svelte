<script lang="ts">
	import './layout.css';
	import type { LayoutProps } from './$types';
	import TopBar from '#lib/components/TopBar.svelte';
	import SideNav from '#lib/components/SideNav.svelte';
	import ChatPanel from '#lib/components/ChatPanel.svelte';
	import Breadcrumbs from '#lib/components/Breadcrumbs.svelte';
	import { beforeNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';

	let { children }: LayoutProps = $props();

	// The booking form reads its fields from the URL once, so a new draft from the
	// assistant (same page, new query) must mount a fresh form.
	const pageKey = $derived(
		page.url.pathname === '/book' ? page.url.pathname + page.url.search : page.url.pathname
	);

	session.load();

	beforeNavigate(({ from, to }) => {
		if (from?.url.pathname !== to?.url.pathname) ui.crumb = '';
	});
</script>

<svelte:head>
	<link rel="icon" type="image/png" href="/favicon.png" />
</svelte:head>

<div class="backdrop" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
<TopBar />
<div class="flex">
	<SideNav />
	<main
		class="min-w-0 flex-1 px-4 pt-8 pb-28 md:px-8 lg:px-10 {ui.chatOpen ? 'xl:mr-[26rem]' : ''}"
	>
		<div class="mx-auto max-w-5xl">
			{#if session.loaded}
				{#if page.url.pathname !== '/'}<Breadcrumbs />{/if}
				{#key pageKey}
					<div class="rise">
						{@render children()}
					</div>
				{/key}
			{/if}
		</div>
	</main>
</div>
<ChatPanel />

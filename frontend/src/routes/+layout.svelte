<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';
	import TopBar from '#lib/components/TopBar.svelte';
	import SideNav from '#lib/components/SideNav.svelte';
	import ChatPanel from '#lib/components/ChatPanel.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';

	let { children }: LayoutProps = $props();

	session.load();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<TopBar />
<div class="flex">
	<SideNav />
	<main
		class="min-w-0 flex-1 px-4 pt-8 pb-28 md:px-8 lg:px-10 {ui.chatOpen ? 'xl:mr-[26rem]' : ''}"
	>
		<div class="mx-auto max-w-5xl">
			{#if session.loaded}
				{@render children()}
			{/if}
		</div>
	</main>
</div>
<ChatPanel />

<script lang="ts">
	import Icon from './Icon.svelte';
	import Notifications from './Notifications.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import UserMenu from './UserMenu.svelte';
</script>

<header
	class="topbar sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border px-4 md:px-6"
>
	<button
		class="press rounded-lg p-2 hover:bg-surface-2 lg:hidden"
		aria-label="Open menu"
		onclick={() => (ui.navOpen = !ui.navOpen)}
	>
		<Icon name="menu" size={24} />
	</button>
	<a href="/" class="group flex items-center gap-2.5 text-lg font-semibold">
		<img
			src="/kiot-logo.png"
			alt="KIOT logo"
			width="40"
			height="40"
			class="h-10 w-10 object-contain drop-shadow-sm transition-transform duration-300 group-hover:scale-105 group-hover:-rotate-3"
		/>
		<span class="hidden leading-tight sm:block">
			<span class="block">KIOT Venue Booker</span>
			<span class="block text-xs font-normal text-muted">Beyond Knowledge</span>
		</span>
	</a>

	<div class="ml-auto flex items-center gap-2">
		{#if session.can('book')}
			<a
				href="/book"
				class="mr-1 inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-2 font-medium hover:border-accent/40 hover:bg-surface-2 hover:text-accent sm:px-4"
				aria-label="Book a venue"
				><Icon name="plus" size={18} /><span class="hidden sm:inline">Book a venue</span></a
			>
		{/if}
		<button
			class="press rounded-lg p-2.5 hover:bg-surface-2"
			aria-label={ui.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
			title={ui.theme === 'dark' ? 'Light mode' : 'Dark mode'}
			onclick={() => ui.toggleTheme()}
		>
			<Icon name={ui.theme === 'dark' ? 'sun' : 'moon'} />
		</button>
		{#if !ui.chatOpen}
			<button
				class="press hidden items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-2 xl:flex"
				onclick={() => ui.setChat(true)}
			>
				<Icon name="chat" /> Assistant
			</button>
		{/if}

		{#if session.user}
			<Notifications />
			<UserMenu />
		{:else if session.loaded}
			<a
				href="/login"
				class="btn-cta inline-flex items-center gap-2 rounded-lg px-4 py-2 font-medium"
				><Icon name="login" size={18} /> Staff login</a
			>
		{/if}
	</div>
</header>

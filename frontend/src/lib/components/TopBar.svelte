<script lang="ts">
	import Icon from './Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { ROLE_LABELS } from '#lib/types.ts';
	import { goto } from '$app/navigation';

	async function logout() {
		await session.logout();
		goto('/');
	}
</script>

<header
	class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-surface px-4 md:px-6"
>
	<button
		class="rounded-lg p-2 hover:bg-surface-2 lg:hidden"
		aria-label="Open menu"
		onclick={() => (ui.navOpen = !ui.navOpen)}
	>
		<Icon name="menu" size={24} />
	</button>
	<a href="/" class="flex items-center gap-2 text-lg font-semibold">
		<span
			class="grid h-9 w-9 place-items-center rounded-lg bg-accent text-sm font-bold text-accent-fg"
			>KV</span
		>
		<span class="hidden sm:inline">KIOT Venue Booker</span>
	</a>

	<div class="ml-auto flex items-center gap-2">
		<button
			class="rounded-lg p-2.5 hover:bg-surface-2"
			aria-label={ui.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
			title={ui.theme === 'dark' ? 'Light mode' : 'Dark mode'}
			onclick={() => ui.toggleTheme()}
		>
			<Icon name={ui.theme === 'dark' ? 'sun' : 'moon'} />
		</button>
		{#if !ui.chatOpen}
			<button
				class="hidden items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-2 xl:flex"
				onclick={() => ui.setChat(true)}
			>
				<Icon name="chat" /> Assistant
			</button>
		{/if}

		{#if session.user}
			<div class="hidden text-right leading-tight md:block">
				<div class="font-medium">{session.user.name}</div>
				<div class="text-sm text-muted">
					{session.user.roles.map((r) => ROLE_LABELS[r] ?? r).join(' · ')}
				</div>
			</div>
			<button
				class="rounded-lg p-2.5 hover:bg-surface-2"
				aria-label="Log out"
				title="Log out"
				onclick={logout}
			>
				<Icon name="logout" />
			</button>
		{:else if session.loaded}
			<a
				href="/login"
				class="rounded-lg bg-accent px-4 py-2 font-medium text-accent-fg hover:opacity-90">Staff login</a
			>
		{/if}
	</div>
</header>

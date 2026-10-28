<script lang="ts">
	import Icon from './Icon.svelte';
	import { goto } from '$app/navigation';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ROLE_LABELS } from '#lib/types.ts';

	let open = $state(false);
	let root = $state<HTMLDivElement>();

	const user = $derived(session.user!);
	const roles = $derived(user.roles.map((r) => ROLE_LABELS[r] ?? r).join(' · '));
	const initials = $derived(
		user.name
			.replace(/^(Dr|Mr|Mrs|Ms|Prof)\.?\s+/i, '')
			.split(/[\s.]+/)
			.filter(Boolean)
			.slice(-2)
			.map((w) => w[0].toUpperCase())
			.join('')
	);

	async function logout() {
		open = false;
		await session.logout();
		goto('/');
	}

	function onWindowClick(e: MouseEvent) {
		if (open && root && !root.contains(e.target as Node)) open = false;
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) {
			open = false;
			root?.querySelector('button')?.focus();
		}
	}

	const item =
		'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-surface-2 hover:text-accent';
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKey} />

<div class="relative" bind:this={root}>
	<button
		class="flex items-center gap-2.5 rounded-xl py-1 pr-2 pl-1 hover:bg-surface-2 md:pl-2"
		aria-haspopup="menu"
		aria-expanded={open}
		onclick={() => (open = !open)}
	>
		<span class="hidden text-right leading-tight md:block">
			<span class="block font-medium">{user.name}</span>
			<span class="block text-sm text-muted">{roles}</span>
		</span>
		<span
			class="grid h-9 w-9 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent"
			aria-hidden="true">{initials}</span
		>
		<span class="sr-only">Account menu</span>
		<Icon
			name="chevron"
			size={16}
			class="text-muted transition-transform duration-200 ease-in-out {open ? 'rotate-180' : ''}"
		/>
	</button>
	{#if open}
		<div
			class="pop absolute top-full right-0 z-50 mt-2 w-64 rounded-xl border border-border bg-surface p-2 shadow-lg"
			role="menu"
			aria-label="Account"
		>
			<div class="border-b border-border px-3 pt-1 pb-2.5 md:hidden">
				<div class="font-medium">{user.name}</div>
				<div class="text-sm text-muted">{roles}</div>
			</div>
			<a href="/" class={item} role="menuitem" onclick={() => (open = false)}>
				<Icon name="home" size={18} /> Dashboard
			</a>
			{#if session.can('book')}
				<a href="/bookings" class={item} role="menuitem" onclick={() => (open = false)}>
					<Icon name="list" size={18} /> My bookings
				</a>
			{/if}
			<div class="my-1 border-t border-border"></div>
			<button class="{item} hover:!text-danger" role="menuitem" onclick={logout}>
				<Icon name="logout" size={18} /> Log out
			</button>
		</div>
	{/if}
</div>

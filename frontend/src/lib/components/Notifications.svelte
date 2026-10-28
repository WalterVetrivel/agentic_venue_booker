<script lang="ts">
	import Icon from './Icon.svelte';
	import { api } from '#lib/api.ts';
	import { dateTimeText } from '#lib/time.ts';
	import type { AppNotification } from '#lib/types.ts';

	let items = $state<AppNotification[]>([]);
	let open = $state(false);
	const unread = $derived(items.filter((n) => !n.read_at).length);

	async function load() {
		try {
			items = await api<AppNotification[]>('/notifications');
		} catch {
			/* logged out or offline; try again on the next tick */
		}
	}

	$effect(() => {
		load();
		const timer = setInterval(load, 60_000);
		return () => clearInterval(timer);
	});

	async function markAllRead() {
		await api('/notifications/read', { method: 'POST', body: '{}' });
		await load();
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') open = false;
	}
</script>

<svelte:window onkeydown={onKey} />

<div class="relative">
	<button
		class="relative rounded-lg p-2.5 hover:bg-surface-2"
		aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
		aria-expanded={open}
		onclick={() => {
			open = !open;
			if (open) load();
		}}
	>
		<Icon name="bell" />
		{#if unread}
			<span
				class="absolute top-1 right-1 grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-xs font-semibold text-white"
				>{unread}</span
			>
		{/if}
	</button>
	{#if open}
		<button
			class="fixed inset-0 z-40 cursor-default"
			aria-label="Close notifications"
			onclick={() => (open = false)}
		></button>
		<div
			class="fixed inset-x-3 top-16 z-50 max-h-[70vh] overflow-y-auto pop glass-strong rounded-xl border sm:absolute sm:inset-x-auto sm:top-12 sm:right-0 sm:w-96"
			role="dialog"
			aria-label="Notifications"
		>
			<div class="flex items-center justify-between border-b border-border px-4 py-3">
				<span class="font-semibold">Notifications</span>
				{#if unread}
					<button class="text-sm text-accent hover:underline" onclick={markAllRead}
						>Mark all as read</button
					>
				{/if}
			</div>
			{#if items.length === 0}
				<p class="px-4 py-6 text-muted">Nothing yet.</p>
			{:else}
				<ul>
					{#each items as n (n.id)}
						<li class="border-b border-border last:border-0 {n.read_at ? '' : 'bg-accent-soft/50'}">
							<a
								href={n.link ?? '#'}
								class="block px-4 py-3 hover:bg-surface-2"
								onclick={() => {
									open = false;
									if (!n.read_at)
										api('/notifications/read', {
											method: 'POST',
											body: JSON.stringify({ ids: [n.id] })
										}).then(load);
								}}
							>
								<span class="block">{n.message}</span>
								<span class="mt-1 block text-sm text-muted">{dateTimeText(n.created_at)}</span>
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</div>

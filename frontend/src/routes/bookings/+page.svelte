<script lang="ts">
	import { api } from '#lib/api.ts';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { nowLocal, whenText } from '#lib/time.ts';
	import { btnPrimary, card } from '#lib/ui.ts';
	import type { Booking } from '#lib/types.ts';

	let bookings = $state<Booking[] | null>(null);
	let error = $state('');

	$effect(() => {
		if (session.user)
			api<Booking[]>('/bookings/mine')
				.then((b) => (bookings = b))
				.catch((e) => (error = e.message));
	});

	const ACTIVE = ['pending_incharge', 'pending_hod', 'confirmed', 'waitlisted', 'offered'];
	const now = nowLocal();
	const upcoming = $derived(
		(bookings ?? []).filter((b) => ACTIVE.includes(b.status) && b.end > now).reverse()
	);
	const past = $derived((bookings ?? []).filter((b) => !upcoming.includes(b)));
</script>

<div class="flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">My bookings</h1>
	{#if session.can('book')}<a href="/book" class={btnPrimary}>Book a venue</a>{/if}
</div>

{#if !session.loaded || (session.user && !bookings && !error)}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.user}
	<p class="mt-6 {card}">Log in to see your bookings.</p>
{:else if error}
	<p class="mt-6 text-danger">{error}</p>
{:else}
	{#each [['Upcoming', upcoming], ['Past and closed', past]] as [heading, list] (heading)}
		{@const items = list as Booking[]}
		<section class="mt-8">
			<h2 class="text-lg font-semibold">{heading} ({items.length})</h2>
			{#if items.length === 0}
				<p class="mt-2 text-muted">
					{heading === 'Upcoming' ? 'Nothing booked yet.' : 'Nothing here yet.'}
				</p>
			{:else}
				<ul class="mt-3 space-y-3">
					{#each items as b (b.id)}
						<li>
							<a
								href="/bookings/{b.id}"
								class="block rounded-xl border bg-surface p-5 hover:border-accent {b.status ===
								'offered'
									? 'border-accent'
									: 'border-border'}"
							>
								<div class="flex flex-wrap items-start justify-between gap-2">
									<span class="text-lg font-semibold">{b.title}</span>
									<StatusBadge status={b.status} />
								</div>
								<p class="mt-1 text-muted">
									{b.venue.code} · {whenText(b.occurrences[0].start, b.occurrences[0].end)}{b
										.occurrences.length > 1
										? ` (+${b.occurrences.length - 1} more days)`
										: ''} · {b.ref}
								</p>
								{#if b.status === 'waitlisted'}
									<p class="mt-1 text-sm">Position {b.waitlist_position} on the waitlist.</p>
								{:else if b.status === 'offered'}
									<p class="mt-1 text-sm font-medium text-accent">
										The slot is free. Open to confirm it.
									</p>
								{/if}
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}
{/if}

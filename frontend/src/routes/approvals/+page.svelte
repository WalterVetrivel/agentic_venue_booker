<script lang="ts">
	import { api } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field } from '#lib/ui.ts';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import type { ApprovalItem, Booking, DecisionHistory } from '#lib/types.ts';

	let items = $state<ApprovalItem[] | null>(null);
	let error = $state('');
	let comments = $state<Record<number, string>>({});
	let busy = $state<number | null>(null);
	let done = $state<{ ref: string; title: string; status: string }[]>([]);
	let history = $state<DecisionHistory[] | null>(null);

	async function load() {
		try {
			[items, history] = await Promise.all([
				api<ApprovalItem[]>('/approvals'),
				api<DecisionHistory[]>('/approvals/history')
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load';
		}
	}
	$effect(() => {
		if (session.user) load();
	});

	async function decide(b: Booking, decision: 'approve' | 'reject') {
		busy = b.id;
		error = '';
		try {
			const res = await api<Booking>(`/bookings/${b.id}/${decision}`, {
				method: 'POST',
				body: JSON.stringify({ comment: comments[b.id] || null })
			});
			done = [{ ref: res.ref, title: res.title, status: res.status }, ...done];
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save';
		} finally {
			busy = null;
		}
	}

	const STEP: Record<string, string> = { incharge: 'as venue in-charge', hod: 'as HOD' };
</script>

<h1 class="text-2xl font-semibold">Approvals</h1>
{#if !session.loaded}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.user}
	<p class="mt-6 {card}">Log in to see requests waiting for you.</p>
{:else}
	<p class="mt-2 text-muted">Requests waiting for your decision, soonest first.</p>
	{#if error}<p class="mt-4 text-danger" role="alert">{error}</p>{/if}
	{#if done.length}
		<ul class="mt-4 space-y-1">
			{#each done as d (d.ref)}
				<li class="rounded-lg bg-success/10 px-4 py-2">
					{d.ref} “{d.title}”: {d.status === 'rejected'
						? 'rejected'
						: d.status === 'confirmed'
							? 'approved and confirmed'
							: 'approved, now waiting for the HOD'}.
				</li>
			{/each}
		</ul>
	{/if}

	{#if !items}
		<p class="mt-6 text-muted">Loading…</p>
	{:else if items.length === 0}
		<p class="mt-6 {card} text-muted">Nothing is waiting for you.</p>
	{:else}
		<ul class="mt-6 space-y-4">
			{#each items as item (item.booking.id)}
				{@const b = item.booking}
				<li class={card}>
					<div class="flex flex-wrap items-start justify-between gap-2">
						<div>
							<a href="/bookings/{b.id}" class="text-lg font-semibold hover:text-accent"
								>{b.title}</a
							>
							<p class="text-muted">
								{b.ref} · {b.event_type} · {b.requester} · you approve {STEP[item.step]}
							</p>
						</div>
						<span class="rounded-full bg-surface-2 px-3 py-1 font-medium">{b.venue.code}</span>
					</div>
					<p class="mt-3">
						{#each b.occurrences as o, i (o.start)}{i ? '; ' : ''}{whenText(o.start, o.end)}{/each}
						· {b.expected_count} people
					</p>
					{#if b.requirements}<p class="mt-1 text-muted">Needs: {b.requirements}</p>{/if}

					<div class="mt-4 rounded-lg bg-surface-2 p-4">
						<p class="font-medium">Things to check</p>
						<ul class="mt-1 list-disc space-y-1 pl-5">
							{#each item.notes as n, i (i)}<li>{n}</li>{/each}
						</ul>
					</div>

					<label class="mt-4 block">
						<span class="mb-1.5 block font-medium">Comment (needed to reject)</span>
						<input bind:value={comments[b.id]} class={field} />
					</label>
					<div class="mt-3 flex flex-wrap gap-3">
						<button class={btnPrimary} disabled={busy === b.id} onclick={() => decide(b, 'approve')}
							>Approve {b.ref}</button
						>
						<button
							class="{btnSecondary} text-danger"
							disabled={busy === b.id || !comments[b.id]?.trim()}
							onclick={() => decide(b, 'reject')}>Reject</button
						>
					</div>
				</li>
			{/each}
		</ul>
	{/if}

	<section class="mt-10">
		<h2 class="text-lg font-semibold">
			Your past decisions{history ? ` (${history.length})` : ''}
		</h2>
		{#if !history}
			<p class="mt-2 text-muted">Loading…</p>
		{:else if history.length === 0}
			<p class="mt-2 text-muted">You haven't approved or rejected anything yet.</p>
		{:else}
			<ul class="mt-3 space-y-2">
				{#each history as h, i (`${h.booking.id}-${h.step}-${i}`)}
					<li>
						<a
							href="/bookings/{h.booking.id}"
							class="lift glass flex flex-wrap items-center justify-between gap-2 rounded-xl border px-4 py-3 hover:border-accent/50"
						>
							<span class="min-w-0">
								<span class="block font-medium">{h.booking.title}</span>
								<span class="block text-sm text-muted">
									{h.booking.ref} · {h.booking.venue.code} · {whenText(
										h.booking.start,
										h.booking.end
									)} · you {h.decision}
									{STEP[h.step]}{h.comment ? `: “${h.comment}”` : ''}
								</span>
							</span>
							<StatusBadge status={h.booking.status} />
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}

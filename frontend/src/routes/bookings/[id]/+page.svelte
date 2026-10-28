<script lang="ts">
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { dateTimeText, whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { Booking } from '#lib/types.ts';

	let booking = $state<Booking | null>(null);
	let error = $state('');
	let actionError = $state('');
	let busy = $state(false);
	let comment = $state('');
	let cancelling = $state(false);
	let reason = $state('');

	const id = $derived((page.params as Record<string, string>).id);

	$effect(() => {
		if (!session.user) return;
		api<Booking>(`/bookings/${id}`)
			.then((b) => {
				booking = b;
				ui.crumb = b.title;
			})
			.catch((e) => (error = e.message));
	});

	async function act(path: string, body: object = {}) {
		busy = true;
		actionError = '';
		try {
			booking = await api<Booking>(`/bookings/${id}/${path}`, {
				method: 'POST',
				body: JSON.stringify(body)
			});
			comment = '';
			cancelling = false;
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Something went wrong';
		} finally {
			busy = false;
		}
	}

	const STEP_NAMES: Record<string, string> = { incharge: 'Venue in-charge', hod: 'HOD' };
</script>

<a href={booking?.can_approve ? '/approvals' : '/bookings'} class="text-accent"
	>← {booking?.can_approve ? 'Approvals' : 'My bookings'}</a
>
{#if !session.loaded}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.user}
	<p class="mt-6 {card}">Log in to see this booking.</p>
{:else if error}
	<p class="mt-6 text-danger">{error}</p>
{:else if !booking}
	<p class="mt-6 text-muted">Loading…</p>
{:else}
	{@const b = booking}
	<div class="mt-4 flex flex-wrap items-start justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold">{b.title}</h1>
			<p class="mt-1 text-muted">{b.ref} · {b.event_type} · requested by {b.requester}</p>
		</div>
		<StatusBadge status={b.status} />
	</div>

	{#if b.status === 'offered' && b.can_cancel}
		<div class="mt-6 rounded-xl border border-accent bg-accent-soft p-5">
			<p class="font-semibold">The slot you were waiting for is free.</p>
			<p class="mt-1">
				Confirm by {dateTimeText(b.offer_expires_at!)} or it goes to the next person waiting. Confirming
				sends it for approval.
			</p>
			<div class="mt-3 flex flex-wrap gap-3">
				<button class={btnPrimary} disabled={busy} onclick={() => act('accept-offer')}
					>Confirm the slot</button
				>
				<button
					class={btnSecondary}
					disabled={busy}
					onclick={() => act('cancel', { reason: 'Offer declined' })}>No longer needed</button
				>
			</div>
		</div>
	{:else if b.status === 'waitlisted'}
		<p class="mt-6 rounded-xl bg-accent-soft p-5">
			You are number {b.waitlist_position} on the waitlist. You'll be notified if the slot frees up.
		</p>
	{:else if b.cancel_reason}
		<p class="mt-6 text-muted">Reason: {b.cancel_reason}</p>
	{/if}

	<div class="mt-6 grid gap-6 lg:grid-cols-2">
		<section class={card}>
			<h2 class="text-lg font-semibold">Details</h2>
			<dl class="mt-3 space-y-3">
				<div>
					<dt class="text-sm text-muted">Venue</dt>
					<dd>
						<a href="/venues/{b.venue.code}" class="text-accent">{b.venue.code}</a> · {b.venue.name} ({b
							.venue.capacity} seats)
					</dd>
				</div>
				<div>
					<dt class="text-sm text-muted">When</dt>
					<dd>
						<ul>
							{#each b.occurrences as o (o.start)}<li>{whenText(o.start, o.end)}</li>{/each}
						</ul>
					</dd>
				</div>
				<div>
					<dt class="text-sm text-muted">Expected attendance</dt>
					<dd>{b.expected_count}</dd>
				</div>
				{#if b.requirements}
					<div>
						<dt class="text-sm text-muted">Requirements</dt>
						<dd>{b.requirements}</dd>
					</div>
				{/if}
				{#if b.description}
					<div>
						<dt class="text-sm text-muted">Description</dt>
						<dd class="whitespace-pre-line">{b.description}</dd>
					</div>
				{/if}
				{#if b.parent_ref}
					<div>
						<dt class="text-sm text-muted">Reschedules</dt>
						<dd>{b.parent_ref}</dd>
					</div>
				{/if}
			</dl>
			{#if b.moves.length}
				<h3 class="mt-5 font-semibold">Classes that move</h3>
				<ul class="mt-2 space-y-1">
					{#each b.moves as m (m.slot_id + m.date)}
						<li>
							{m.label}, {m.date}, {m.time}:
							{m.action === 'relocated' ? `moves to ${m.venue}` : 'BYOD in the classroom'}
							{#if m.faculty_name}<span class="text-muted">({m.faculty_name})</span>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<section class={card}>
			<h2 class="text-lg font-semibold">Approvals</h2>
			<ol class="mt-3 space-y-3">
				{#each b.steps as step (step)}
					{@const a = b.approvals.filter((x) => x.step === step).at(-1)}
					<li class="flex gap-3">
						<span
							class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-sm {a?.decision ===
							'approved'
								? 'bg-success text-white'
								: a?.decision === 'rejected'
									? 'bg-danger text-white'
									: 'bg-surface-2'}">{a?.decision === 'rejected' ? '✕' : a ? '✓' : ''}</span
						>
						<div>
							<p class="font-medium">{STEP_NAMES[step] ?? step}</p>
							{#if a}
								<p class="text-sm text-muted">
									{a.decision === 'approved' ? 'Approved' : 'Rejected'} by {a.approver} · {dateTimeText(
										a.decided_at
									)}
								</p>
								{#if a.comment}<p class="mt-1">“{a.comment}”</p>{/if}
							{:else if b.status === `pending_${step}`}
								<p class="text-sm text-warning">Waiting</p>
							{/if}
						</div>
					</li>
				{/each}
			</ol>

			{#if b.can_approve}
				<div class="mt-6 border-t border-border pt-5">
					<label class={label} for="comment">Comment (needed to reject)</label>
					<textarea id="comment" rows="2" bind:value={comment} class={field}></textarea>
					<div class="mt-3 flex flex-wrap gap-3">
						<button class={btnPrimary} disabled={busy} onclick={() => act('approve', { comment })}
							>Approve</button
						>
						<button
							class="{btnSecondary} text-danger"
							disabled={busy || !comment.trim()}
							onclick={() => act('reject', { comment })}>Reject</button
						>
					</div>
				</div>
			{/if}
		</section>
	</div>

	{#if actionError}<p class="mt-4 text-danger" role="alert">{actionError}</p>{/if}

	{#if (b.can_cancel && b.status !== 'offered') || b.can_reschedule}
		<div class="mt-6 flex flex-wrap gap-3">
			{#if b.can_reschedule}
				<a href="/book?reschedule={b.id}" class={btnSecondary}>Reschedule</a>
			{/if}
			{#if b.can_cancel && b.status !== 'offered'}
				{#if cancelling}
					<form
						class="flex w-full flex-wrap items-end gap-3"
						onsubmit={(e) => {
							e.preventDefault();
							act('cancel', { reason: reason || null });
						}}
					>
						<div class="min-w-64 flex-1">
							<label class={label} for="reason">Reason (optional)</label>
							<input id="reason" bind:value={reason} class={field} />
						</div>
						<button class="{btnPrimary} bg-danger" disabled={busy}>Cancel booking</button>
						<button type="button" class={btnSecondary} onclick={() => (cancelling = false)}
							>Keep it</button
						>
					</form>
				{:else}
					<button class="{btnSecondary} text-danger" onclick={() => (cancelling = true)}
						>Cancel booking…</button
					>
				{/if}
			{/if}
		</div>
	{/if}
{/if}

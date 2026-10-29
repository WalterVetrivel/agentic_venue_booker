<script lang="ts">
	import { chat } from '#lib/stores/chat.svelte.ts';
	import { api } from '#lib/api.ts';
	import { btnPrimary, btnSecondary, field } from '#lib/ui.ts';
	import type { Booking } from '#lib/types.ts';

	// The faculty guide approves or rejects each student in a student request.
	let { booking, ondone }: { booking: Booking; ondone?: (b: Booking) => void } = $props();

	type Choice = { decision: 'approved' | 'rejected' | ''; comment: string };
	let choices = $state<Record<number, Choice>>({});
	let busy = $state(false);
	let error = $state('');

	$effect(() => {
		const next: Record<number, Choice> = {};
		for (const s of booking.students)
			if (s.decision === 'pending') next[s.id] = { decision: '', comment: '' };
		choices = next;
	});

	const pending = $derived(booking.students.filter((s) => s.decision === 'pending'));
	const ready = $derived(
		pending.length > 0 &&
			pending.every(
				(s) =>
					choices[s.id]?.decision === 'approved' ||
					(choices[s.id]?.decision === 'rejected' && choices[s.id].comment.trim())
			)
	);
	const approving = $derived(pending.filter((s) => choices[s.id]?.decision === 'approved').length);

	function setAll(decision: 'approved' | 'rejected') {
		for (const s of pending) choices[s.id].decision = decision;
	}

	async function save() {
		busy = true;
		error = '';
		try {
			const res = await api<Booking>(`/bookings/${booking.id}/students`, {
				method: 'POST',
				body: JSON.stringify({
					decisions: pending.map((s) => ({
						student_id: s.id,
						decision: choices[s.id].decision,
						comment: choices[s.id].comment.trim() || null
					}))
				})
			});
			chat.decided(res.id, res.status === 'rejected' ? 'Rejected' : 'Approved');
			ondone?.(res);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save';
		} finally {
			busy = false;
		}
	}
</script>

<fieldset class="mt-4 rounded-lg border border-border p-4">
	<legend class="px-1 font-medium">Approve or reject each student</legend>
	<p class="text-sm text-muted">
		The request goes on to the venue in-charge with the students you approve. Rejecting someone
		needs a reason; their class advisor is told.
	</p>
	<div class="mt-3 flex flex-wrap gap-2">
		<button type="button" class={btnSecondary} onclick={() => setAll('approved')}
			>Approve all</button
		>
		<button type="button" class="{btnSecondary} text-danger" onclick={() => setAll('rejected')}
			>Reject all</button
		>
	</div>
	<ul class="mt-3 divide-y divide-border">
		{#each pending as s (s.id)}
			{@const c = choices[s.id]}
			{#if c}
				<li class="py-3">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<span>
							<span class="font-medium">{s.name}</span>
							<span class="text-muted"
								>· {s.class_label}{s.register_no ? ` · ${s.register_no}` : ''}</span
							>
						</span>
						<span class="flex gap-4" role="radiogroup" aria-label="Decision for {s.name}">
							<label class="flex items-center gap-2">
								<input
									type="radio"
									name="st-{s.id}"
									value="approved"
									bind:group={c.decision}
									class="h-5 w-5"
								/>
								Approve
							</label>
							<label class="flex items-center gap-2">
								<input
									type="radio"
									name="st-{s.id}"
									value="rejected"
									bind:group={c.decision}
									class="h-5 w-5"
								/>
								Reject
							</label>
						</span>
					</div>
					{#if c.decision === 'rejected'}
						<label class="mt-2 block">
							<span class="sr-only">Why {s.name} is rejected</span>
							<input
								bind:value={c.comment}
								placeholder="Why (the student and their class advisor see this)"
								class={field}
							/>
						</label>
					{/if}
				</li>
			{/if}
		{/each}
	</ul>
	{#if error}<p class="mt-2 text-danger" role="alert">{error}</p>{/if}
	<button type="button" class="{btnPrimary} mt-3" disabled={!ready || busy} onclick={save}>
		{approving === 0 && ready
			? 'Reject the request'
			: `Save: approve ${approving} of ${pending.length}`}
	</button>
</fieldset>

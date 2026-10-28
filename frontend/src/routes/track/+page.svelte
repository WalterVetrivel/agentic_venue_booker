<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, ApiError } from '#lib/api.ts';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import StudentList from '#lib/components/StudentList.svelte';
	import { dateTimeText, whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { StudentTrack } from '#lib/types.ts';

	let code = $state(page.url.searchParams.get('code') ?? '');
	let request = $state<StudentTrack | null>(null);
	let error = $state('');
	let loading = $state(false);
	let cancelling = $state(false);
	let reason = $state('');
	let busy = $state(false);

	async function look(c: string) {
		if (!c.trim()) return;
		loading = true;
		error = '';
		try {
			request = await api<StudentTrack>(`/student/bookings/${encodeURIComponent(c.trim())}`);
		} catch (e) {
			request = null;
			error =
				e instanceof ApiError && e.status === 404
					? 'No request has that tracking number. Check it and try again.'
					: e instanceof Error
						? e.message
						: 'Could not look it up';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		const c = page.url.searchParams.get('code');
		if (c) look(c);
	});

	function find(e: SubmitEvent) {
		e.preventDefault();
		goto(`/track?code=${encodeURIComponent(code.trim())}`);
	}

	async function cancel(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			request = await api<StudentTrack>(`/student/bookings/${request!.tracking_code}/cancel`, {
				method: 'POST',
				body: JSON.stringify({ reason: reason || null })
			});
			cancelling = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not cancel';
		} finally {
			busy = false;
		}
	}

	const DOT: Record<string, string> = {
		done: 'bg-success text-white',
		rejected: 'bg-danger text-white',
		current: 'bg-warning/30 text-warning',
		waiting: 'bg-surface-2',
		skipped: 'bg-surface-2 opacity-50'
	};
</script>

<h1 class="text-2xl font-semibold">Track a student request</h1>
<form class="mt-6 flex flex-wrap items-end gap-3" onsubmit={find}>
	<div class="min-w-64 flex-1">
		<label class={label} for="code">Tracking number</label>
		<input
			id="code"
			required
			bind:value={code}
			placeholder="ST-XXXX-XXXX"
			autocomplete="off"
			class="{field} font-mono uppercase"
		/>
	</div>
	<button class={btnPrimary} disabled={loading}>Look it up</button>
</form>

{#if error}<p class="mt-4 text-danger" role="alert">{error}</p>{/if}

{#if request}
	{@const r = request}
	<section class="mt-6 {card}" aria-live="polite">
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h2 class="text-xl font-semibold">{r.venue.code} · {r.venue.name}</h2>
				<p class="mt-1 text-muted">
					{r.tracking_code} · {r.ref} · sent {dateTimeText(r.created_at)}
				</p>
			</div>
			<StatusBadge status={r.status} />
		</div>
		<ul class="mt-3">
			{#each r.occurrences as o (o.start)}<li>{whenText(o.start, o.end)}</li>{/each}
		</ul>
		<p class="mt-2 whitespace-pre-line">{r.reason}</p>
		<p class="mt-1 text-muted">
			Faculty guide: {r.guide}{r.contact_email ? ` · updates go to ${r.contact_email}` : ''}
		</p>
		{#if r.cancel_reason}<p class="mt-1 text-muted">Cancelled: {r.cancel_reason}</p>{/if}

		<div class="mt-6 grid gap-6 lg:grid-cols-2">
			<div>
				<h3 class="font-semibold">Approvals</h3>
				<ol class="mt-3 space-y-3">
					{#each r.steps as s (s.step)}
						<li class="flex gap-3">
							<span
								class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-sm {DOT[
									s.state
								]}">{s.state === 'done' ? '✓' : s.state === 'rejected' ? '✕' : ''}</span
							>
							<div>
								<p class="font-medium">{s.label}</p>
								{#if s.state === 'done' || s.state === 'rejected'}
									<p class="text-sm text-muted">
										{s.state === 'done' ? 'Approved' : 'Not approved'} by {s.approver} · {dateTimeText(
											s.decided_at!
										)}
									</p>
									{#if s.comment}<p class="mt-1">“{s.comment}”</p>{/if}
								{:else if s.state === 'current'}
									<p class="text-sm text-warning">Waiting for a decision</p>
								{/if}
							</div>
						</li>
					{/each}
				</ol>
			</div>
			<div>
				<h3 class="font-semibold">Students</h3>
				<div class="mt-1"><StudentList students={r.students} /></div>
			</div>
		</div>

		{#if r.can_cancel}
			<div class="mt-6 border-t border-border pt-5">
				{#if cancelling}
					<form class="flex flex-wrap items-end gap-3" onsubmit={cancel}>
						<div class="min-w-64 flex-1">
							<label class={label} for="reason">Reason (optional)</label>
							<input id="reason" bind:value={reason} class={field} />
						</div>
						<button class="{btnPrimary} bg-danger" disabled={busy}>Cancel request</button>
						<button type="button" class={btnSecondary} onclick={() => (cancelling = false)}
							>Keep it</button
						>
					</form>
				{:else}
					<button class="{btnSecondary} text-danger" onclick={() => (cancelling = true)}
						>Cancel this request…</button
					>
				{/if}
			</div>
		{/if}
	</section>
{/if}

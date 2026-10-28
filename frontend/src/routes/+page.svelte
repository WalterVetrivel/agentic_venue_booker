<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { api } from '#lib/api.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { APPROVER_CAPABILITIES, visibleNav } from '#lib/nav.ts';
	import { nowLocal, whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, panel } from '#lib/ui.ts';
	import { STATUS_LABELS } from '#lib/types.ts';
	import type { ApprovalItem, Booking } from '#lib/types.ts';

	const SHOWN = 5;
	const ACTIVE = [
		'pending_guide',
		'pending_incharge',
		'pending_hod',
		'confirmed',
		'waitlisted',
		'offered'
	];
	const STEP: Record<string, string> = {
		guide: 'as faculty guide',
		incharge: 'as venue in-charge',
		hod: 'as HOD'
	};

	const cards = $derived(
		visibleNav(session.capabilities, !!session.user).filter((n) => n.href !== '/')
	);
	const canBook = $derived(session.can('book'));
	const isApprover = $derived(APPROVER_CAPABILITIES.some((c) => session.can(c)));

	let bookings = $state<Booking[] | null>(null);
	let approvals = $state<ApprovalItem[] | null>(null);
	// Other faculty get the panel only while a student group's request waits for them as guide.
	const canApprove = $derived(isApprover || (canBook && !!approvals?.length));
	let bookingsError = $state('');
	let approvalsError = $state('');
	let deciding = $state<number | null>(null);
	let rejecting = $state<number | null>(null);
	let reason = $state('');
	let decided = $state('');

	async function loadApprovals() {
		try {
			approvals = await api<ApprovalItem[]>('/approvals');
		} catch (e) {
			approvalsError = e instanceof Error ? e.message : 'Could not load approvals';
		}
	}

	async function decide(b: Booking, decision: 'approve' | 'reject') {
		deciding = b.id;
		approvalsError = '';
		try {
			const res = await api<Booking>(`/bookings/${b.id}/${decision}`, {
				method: 'POST',
				body: JSON.stringify({ comment: decision === 'reject' ? reason.trim() : null })
			});
			decided =
				res.status === 'rejected'
					? `${res.ref} rejected.`
					: res.status === 'confirmed'
						? `${res.ref} approved and confirmed.`
						: `${res.ref} approved, now ${(STATUS_LABELS[res.status] ?? res.status).toLowerCase()}.`;
			rejecting = null;
			await loadApprovals();
		} catch (e) {
			approvalsError = e instanceof Error ? e.message : 'Could not save';
		} finally {
			deciding = null;
		}
	}

	$effect(() => {
		if (!session.user) return;
		if (canBook)
			api<Booking[]>('/bookings/mine')
				.then((b) => (bookings = b))
				.catch((e) => (bookingsError = e.message));
		if (isApprover || canBook) loadApprovals();
	});

	const now = nowLocal();
	/** The next part of a booking that hasn't ended yet. */
	function nextOccurrence(b: Booking) {
		return b.occurrences.find((o) => o.end > now) ?? b.occurrences[0];
	}
	const current = $derived(
		(bookings ?? [])
			.filter((b) => ACTIVE.includes(b.status) && b.end > now)
			.sort((a, b) => nextOccurrence(a).start.localeCompare(nextOccurrence(b).start))
	);

	function dayTile(iso: string) {
		const [y, m, d] = iso.split('T')[0].split('-').map(Number);
		const date = new Date(y, m - 1, d);
		return {
			day: String(d),
			month: date.toLocaleDateString('en-IN', { month: 'short' })
		};
	}

	const greeting = (() => {
		const h = new Date().getHours();
		return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
	})();
	const today = new Date().toLocaleDateString('en-IN', {
		weekday: 'long',
		day: 'numeric',
		month: 'long'
	});
</script>

<section class="{panel} rise relative overflow-hidden p-6 sm:p-8">
	<img
		src="/kiot-logo.png"
		alt=""
		aria-hidden="true"
		class="pointer-events-none absolute -top-6 -right-6 h-44 w-44 rotate-6 opacity-[0.07] select-none sm:h-56 sm:w-56"
	/>
	<p class="text-sm font-medium tracking-wide text-muted uppercase">
		{session.user ? `${greeting} · ${today}` : today}
	</p>
	<h1 class="mt-1 text-3xl font-semibold sm:text-4xl">
		{session.user ? `Welcome, ${session.user.name}` : 'Find a lab or venue'}
	</h1>
	<p class="mt-2 max-w-2xl text-lg text-muted">
		{session.user
			? 'Book venues, track approvals and ask the assistant for recommendations.'
			: 'Check which labs are free and what hardware and software they have.'}
	</p>
	<div class="mt-6 flex flex-wrap gap-3">
		{#if canBook}
			<a href="/book" class="{btnPrimary} inline-flex items-center gap-2"
				><Icon name="plus" size={18} /> Book a venue</a
			>
		{/if}
		<a href="/availability" class="{btnSecondary} inline-flex items-center gap-2"
			><Icon name="calendar" size={18} /> Check availability</a
		>
	</div>
</section>

{#if session.user && (canBook || canApprove)}
	<div
		class="mt-6 grid gap-6 {canBook && canApprove
			? ui.chatOpen
				? '2xl:grid-cols-2'
				: 'lg:grid-cols-2'
			: ''}"
	>
		{#if canBook}
			<section
				class="{panel} rise flex min-w-0 flex-col p-5"
				style="--i: 1"
				aria-labelledby="current-h"
			>
				<div class="flex items-center justify-between gap-3">
					<h2 id="current-h" class="flex items-center gap-2 text-lg font-semibold">
						<span class="rounded-lg bg-accent-soft p-1.5 text-accent"
							><Icon name="clock" size={18} /></span
						>
						Your current bookings
						{#if bookings}<span class="rounded-full bg-surface-2 px-2 text-sm text-muted"
								>{current.length}</span
							>{/if}
					</h2>
					<a href="/bookings" class="group flex items-center gap-1 text-sm font-medium text-accent"
						>All bookings <Icon
							name="arrow"
							size={16}
							class="transition-transform group-hover:translate-x-0.5"
						/></a
					>
				</div>
				{#if bookingsError}
					<p class="mt-4 text-danger">{bookingsError}</p>
				{:else if !bookings}
					<ul class="mt-4 space-y-2" aria-hidden="true">
						{#each [0, 1, 2] as i (i)}<li
								class="h-16 animate-pulse rounded-xl bg-surface-2"
							></li>{/each}
					</ul>
				{:else if current.length === 0}
					<div
						class="mt-4 flex flex-1 flex-col items-center justify-center rounded-xl bg-surface-2 p-6 text-center"
					>
						<p class="text-muted">No current or upcoming bookings.</p>
						<a
							href="/book"
							class="mt-2 inline-flex items-center gap-1 font-medium text-accent hover:underline"
							><Icon name="plus" size={16} /> Book a venue</a
						>
					</div>
				{:else}
					<ul class="mt-4 space-y-2">
						{#each current.slice(0, SHOWN) as b, i (b.id)}
							{@const o = nextOccurrence(b)}
							{@const tile = dayTile(o.start)}
							<li class="rise" style="--i: {i + 2}">
								<a
									href="/bookings/{b.id}"
									class="lift flex items-center gap-3 rounded-xl border border-transparent p-2.5 hover:border-glass-border hover:bg-glass-strong {b.status ===
									'offered'
										? 'ring-2 ring-accent/40'
										: ''}"
								>
									<span
										class="grid w-12 shrink-0 place-items-center rounded-lg bg-accent-soft py-1 leading-tight text-accent"
									>
										<span class="text-lg font-semibold">{tile.day}</span>
										<span class="text-xs uppercase">{tile.month}</span>
									</span>
									<span class="min-w-0 flex-1">
										<span class="block truncate font-medium">{b.title}</span>
										<span class="block text-sm text-muted">
											{b.venue.code} · {whenText(o.start, o.end)}{o.start <= now
												? ' · happening now'
												: ''}
										</span>
									</span>
									<StatusBadge status={b.status} />
								</a>
							</li>
						{/each}
					</ul>
					{#if current.length > SHOWN}
						<a href="/bookings" class="mt-3 text-sm text-muted hover:text-accent"
							>+{current.length - SHOWN} more upcoming</a
						>
					{/if}
				{/if}
			</section>
		{/if}

		{#if canApprove}
			<section
				class="{panel} rise flex min-w-0 flex-col p-5"
				style="--i: 2"
				aria-labelledby="pending-h"
			>
				<div class="flex items-center justify-between gap-3">
					<h2 id="pending-h" class="flex items-center gap-2 text-lg font-semibold">
						<span class="rounded-lg bg-warning/15 p-1.5 text-warning"
							><Icon name="check" size={18} /></span
						>
						Pending approvals
						{#if approvals}<span
								class="rounded-full px-2 text-sm {approvals.length
									? 'bg-warning/20 font-semibold text-warning'
									: 'bg-surface-2 text-muted'}">{approvals.length}</span
							>{/if}
					</h2>
					<a href="/approvals" class="group flex items-center gap-1 text-sm font-medium text-accent"
						>All approvals <Icon
							name="arrow"
							size={16}
							class="transition-transform group-hover:translate-x-0.5"
						/></a
					>
				</div>
				{#if decided}
					<p class="pop mt-3 rounded-lg bg-success/10 px-3 py-2 text-sm text-success" role="status">
						{decided}
					</p>
				{/if}
				{#if approvalsError}
					<p class="mt-3 text-sm text-danger" role="alert">{approvalsError}</p>
				{/if}
				{#if !approvals}
					<ul class="mt-4 space-y-2" aria-hidden="true">
						{#each [0, 1, 2] as i (i)}<li
								class="h-16 animate-pulse rounded-xl bg-surface-2"
							></li>{/each}
					</ul>
				{:else if approvals.length === 0}
					<div
						class="mt-4 flex flex-1 items-center justify-center rounded-xl bg-surface-2 p-6 text-center"
					>
						<p class="text-muted">You're all caught up. Nothing is waiting for you.</p>
					</div>
				{:else}
					<ul class="mt-4 space-y-2">
						{#each approvals.slice(0, SHOWN) as item, i (item.booking.id)}
							{@const b = item.booking}
							{@const tile = dayTile(b.start)}
							<li class="rise" style="--i: {i + 3}" data-approval={b.ref}>
								<div
									class="lift flex flex-wrap items-center gap-3 rounded-xl border border-transparent p-2.5 hover:border-glass-border hover:bg-glass-strong"
								>
									<span
										class="grid w-12 shrink-0 place-items-center rounded-lg bg-warning/15 py-1 leading-tight text-warning"
									>
										<span class="text-lg font-semibold">{tile.day}</span>
										<span class="text-xs uppercase">{tile.month}</span>
									</span>
									<a href="/bookings/{b.id}" class="min-w-0 flex-1 hover:text-accent">
										<span class="block truncate font-medium">{b.title}</span>
										<span class="block text-sm text-muted">
											{b.requester} · {b.venue.code} · {whenText(b.start, b.end)} · you approve
											{STEP[item.step] ?? ''}
										</span>
									</a>
									{#if item.step === 'guide'}
										<a
											href="/bookings/{b.id}"
											class="press shrink-0 rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
											>Decide per student</a
										>
									{:else if rejecting !== b.id}
										<div class="flex shrink-0 gap-2">
											<button
												class="btn-cta inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium"
												disabled={deciding === b.id}
												onclick={() => decide(b, 'approve')}
												aria-label="Approve {b.ref}"><Icon name="check" size={16} /> Approve</button
											>
											<button
												class="press rounded-lg border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10"
												disabled={deciding === b.id}
												onclick={() => {
													rejecting = b.id;
													reason = '';
												}}
												aria-label="Reject {b.ref}">Reject</button
											>
										</div>
									{/if}
								</div>
								{#if rejecting === b.id}
									<form
										class="pop mt-2 flex flex-wrap items-center gap-2 pl-[3.75rem]"
										onsubmit={(e) => {
											e.preventDefault();
											decide(b, 'reject');
										}}
									>
										<label class="sr-only" for="reason-{b.id}">Reason for rejecting {b.ref}</label>
										<input
											id="reason-{b.id}"
											bind:value={reason}
											placeholder="Reason (the requester sees this)"
											class="min-w-0 flex-1 rounded-lg border border-border bg-glass-strong px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
										/>
										<button
											class="press rounded-lg bg-danger px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
											disabled={!reason.trim() || deciding === b.id}>Reject {b.ref}</button
										>
										<button
											type="button"
											class="press rounded-lg px-2 py-1.5 text-sm text-muted hover:text-fg"
											onclick={() => (rejecting = null)}>Cancel</button
										>
									</form>
								{/if}
							</li>
						{/each}
					</ul>
					{#if approvals.length > SHOWN}
						<a href="/approvals" class="mt-3 text-sm text-muted hover:text-accent"
							>+{approvals.length - SHOWN} more waiting</a
						>
					{/if}
				{/if}
			</section>
		{/if}
	</div>
{/if}

<h2 class="mt-10 text-sm font-semibold tracking-wide text-muted uppercase">Go to</h2>
<div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
	{#each cards as c, i (c.href)}
		<a
			href={c.href}
			class="lift glass group rise flex items-start gap-4 rounded-2xl border p-5 hover:border-accent/50"
			style="--i: {i + 3}"
		>
			<span
				class="rounded-xl bg-accent-soft p-2.5 text-accent transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-6"
				><Icon name={c.icon} /></span
			>
			<span>
				<span class="block font-semibold">{c.label}</span>
				<span class="text-sm text-muted">{c.blurb}</span>
			</span>
		</a>
	{/each}
</div>

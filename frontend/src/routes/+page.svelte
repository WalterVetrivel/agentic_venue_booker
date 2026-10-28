<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { api } from '#lib/api.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { APPROVER_CAPABILITIES, visibleNav } from '#lib/nav.ts';
	import { nowLocal, whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, panel } from '#lib/ui.ts';
	import type { ApprovalItem, Booking } from '#lib/types.ts';

	const SHOWN = 5;
	const ACTIVE = ['pending_incharge', 'pending_hod', 'confirmed', 'waitlisted', 'offered'];
	const STEP: Record<string, string> = { incharge: 'as venue in-charge', hod: 'as HOD' };

	const cards = $derived(visibleNav(session.capabilities).filter((n) => n.href !== '/'));
	const canBook = $derived(session.can('book'));
	const canApprove = $derived(APPROVER_CAPABILITIES.some((c) => session.can(c)));

	let bookings = $state<Booking[] | null>(null);
	let approvals = $state<ApprovalItem[] | null>(null);
	let bookingsError = $state('');
	let approvalsError = $state('');

	$effect(() => {
		if (!session.user) return;
		if (canBook)
			api<Booking[]>('/bookings/mine')
				.then((b) => (bookings = b))
				.catch((e) => (bookingsError = e.message));
		if (canApprove)
			api<ApprovalItem[]>('/approvals')
				.then((a) => (approvals = a))
				.catch((e) => (approvalsError = e.message));
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
						<a href="/book" class="mt-2 font-medium text-accent hover:underline">Book a venue</a>
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
				{#if approvalsError}
					<p class="mt-4 text-danger">{approvalsError}</p>
				{:else if !approvals}
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
							<li class="rise" style="--i: {i + 3}">
								<a
									href="/approvals"
									class="lift flex items-center gap-3 rounded-xl border border-transparent p-2.5 hover:border-glass-border hover:bg-glass-strong"
								>
									<span
										class="grid w-12 shrink-0 place-items-center rounded-lg bg-warning/15 py-1 leading-tight text-warning"
									>
										<span class="text-lg font-semibold">{tile.day}</span>
										<span class="text-xs uppercase">{tile.month}</span>
									</span>
									<span class="min-w-0 flex-1">
										<span class="block truncate font-medium">{b.title}</span>
										<span class="block text-sm text-muted">
											{b.requester} · {b.venue.code} · {whenText(b.start, b.end)}
										</span>
									</span>
									<span class="hidden text-xs text-muted sm:block">{STEP[item.step] ?? ''}</span>
								</a>
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

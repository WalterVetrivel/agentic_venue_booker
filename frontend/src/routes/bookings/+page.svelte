<script lang="ts">
	import { api } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';

	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import RecordTable from '#lib/components/RecordTable.svelte';
	import ViewToggle, { savedView } from '#lib/components/ViewToggle.svelte';

	import { session } from '#lib/stores/session.svelte.ts';
	import { nowLocal, prettyDate, whenText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card } from '#lib/ui.ts';
	import type { Booking, BookingDraft } from '#lib/types.ts';

	let bookings = $state<Booking[] | null>(null);
	let guiding = $state<Booking[]>([]);
	let drafts = $state<BookingDraft[]>([]);
	let error = $state('');
	let layout = $state(savedView('bookings', ['cards', 'table'] as const, 'cards'));

	function when(b: Booking) {
		const o = b.occurrences[0];
		const more = b.occurrences.length - 1;
		return whenText(o.start, o.end) + (more ? ` (+${more} more day${more === 1 ? '' : 's'})` : '');
	}

	$effect(() => {
		if (session.user)
			Promise.all([
				api<Booking[]>('/bookings/mine'),
				api<Booking[]>('/bookings/guiding'),
				session.can('book') ? api<BookingDraft[]>('/booking-drafts') : []
			])
				.then(([mine, guided, saved]) => {
					bookings = mine;
					guiding = guided;
					drafts = saved;
				})
				.catch((e) => (error = e.message));
	});

	function draftWhen(d: BookingDraft) {
		if (!d.date_from) return 'No date yet';
		const day = prettyDate(d.date_from);
		const time =
			d.start_time && d.end_time ? `, ${d.start_time.slice(0, 5)}–${d.end_time.slice(0, 5)}` : '';
		return (
			day + time + (d.date_to && d.date_to !== d.date_from ? ` to ${prettyDate(d.date_to)}` : '')
		);
	}

	function draftState(d: BookingDraft): [string, string] {
		if (d.taken_since_saved)
			return [
				'Booked by someone else since you saved it: it can only join the waitlist',
				'text-warning'
			];
		return (
			(
				{
					free: ['Free: ready to submit', 'text-success'],
					waitlist: ['Already booked: it can only join the waitlist', 'text-warning'],
					displace: ['A class uses the venue then: choose where it moves', 'text-warning'],
					blocked: ["The venue can't be booked then", 'text-danger'],
					invalid: ['Check the dates and times', 'text-danger']
				} as Record<string, [string, string]>
			)[d.outcome] ?? ['Not finished: add the venue, date and time', 'text-muted']
		);
	}

	async function deleteDraft(d: BookingDraft) {
		if (!confirm(`Delete the draft “${d.title || 'Untitled'}”?`)) return;
		await api(`/booking-drafts/${d.id}`, { method: 'DELETE' });
		drafts = drafts.filter((x) => x.id !== d.id);
	}

	const ACTIVE = [
		'pending_guide',
		'pending_incharge',
		'pending_hod',
		'confirmed',
		'waitlisted',
		'offered'
	];
	const now = nowLocal();
	const upcoming = $derived(
		(bookings ?? []).filter((b) => ACTIVE.includes(b.status) && b.end > now).reverse()
	);
	const past = $derived((bookings ?? []).filter((b) => !upcoming.includes(b)));
</script>

<div class="flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">My bookings</h1>
	<div class="flex flex-wrap items-center gap-3">
		<ViewToggle
			bind:value={layout}
			key="bookings"
			label="Layout"
			options={[
				{ value: 'cards', label: 'Cards', icon: 'list' },
				{ value: 'table', label: 'Table', icon: 'table' }
			]}
		/>
		{#if session.can('book')}<a href="/book" class="{btnPrimary} inline-flex items-center gap-2"
				><Icon name="plus" size={18} /> Book a venue</a
			>{/if}
	</div>
</div>

{#if !session.loaded || (session.user && !bookings && !error)}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.user}
	<p class="mt-6 {card}">Log in to see your bookings.</p>
{:else if error}
	<p class="mt-6 text-danger">{error}</p>
{:else}
	{#if drafts.length}
		<section class="mt-8" id="drafts">
			<h2 class="text-lg font-semibold">Drafts ({drafts.length})</h2>
			<p class="mt-1 text-sm text-muted">
				Saved but not submitted. A draft doesn't hold the venue: someone else can book it meanwhile.
			</p>
			<ul class="mt-3 space-y-3">
				{#each drafts as d (d.id)}
					{@const [state, tone] = draftState(d)}
					<li class="glass rounded-2xl border border-border p-5" data-testid="draft">
						<div class="flex flex-wrap items-start justify-between gap-3">
							<div>
								<p class="text-lg font-semibold">{d.title || 'Untitled draft'}</p>
								<p class="mt-1 text-muted">
									{d.venue ?? 'No venue yet'} · {draftWhen(d)}
								</p>
								<p class="mt-1 text-sm font-medium {tone}">{state}</p>
							</div>
							<div class="flex gap-2">
								<a href="/book?draft={d.id}" class={btnPrimary}>Open</a>
								<button
									type="button"
									class={btnSecondary}
									aria-label="Delete draft {d.title || 'Untitled'}"
									onclick={() => deleteDraft(d)}>Delete</button
								>
							</div>
						</div>
					</li>
				{/each}
			</ul>
		</section>
	{/if}
	{#if guiding.length}
		<section class="mt-8">
			<h2 class="text-lg font-semibold">Student requests I'm guiding ({guiding.length})</h2>
			<div class="mt-3">
				<RecordTable
					label="Student requests I'm guiding"
					extraLabel="Students"
					rows={guiding.map((b) => ({
						key: b.id,
						href: `/bookings/${b.id}`,
						title: b.title,
						sub: b.ref,
						venue: b.venue.code,
						when: when(b),
						extra: b.students.map((s) => s.name).join(', '),
						status: b.status
					}))}
				/>
			</div>
		</section>
	{/if}
	{#each [['Upcoming', upcoming], ['Past and closed', past]] as [heading, list] (heading)}
		{@const items = list as Booking[]}
		<section class="mt-8">
			<h2 class="text-lg font-semibold">{heading} ({items.length})</h2>
			{#if items.length === 0}
				<p class="mt-2 text-muted">
					{heading === 'Upcoming' ? 'Nothing booked yet.' : 'Nothing here yet.'}
				</p>
			{:else if layout === 'table'}
				<div class="mt-3">
					<RecordTable
						label="{heading} bookings"
						rows={items.map((b) => ({
							key: b.id,
							href: `/bookings/${b.id}`,
							title: b.title,
							sub: b.ref,
							venue: b.venue.code,
							when: when(b),
							status: b.status
						}))}
					/>
				</div>
			{:else}
				<ul class="mt-3 space-y-3">
					{#each items as b (b.id)}
						<li>
							<a
								href="/bookings/{b.id}"
								class="block lift glass rounded-2xl border p-5 hover:border-accent/50 {b.status ===
								'offered'
									? 'border-accent'
									: 'border-border'}"
							>
								<div class="flex flex-wrap items-start justify-between gap-2">
									<span class="text-lg font-semibold">{b.title}</span>
									<StatusBadge status={b.status} />
								</div>
								<p class="mt-1 text-muted">
									{b.venue.code} · {when(b)} · {b.ref}
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

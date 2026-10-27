<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { untrack } from 'svelte';
	import { api } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { isoDate, prettyDate } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { Booking, BookingCheck, Move, Venue } from '#lib/types.ts';

	const params = page.url.searchParams;
	const rescheduleId = params.get('reschedule');

	let venues = $state<Venue[]>([]);
	let eventTypes = $state<string[]>([]);
	let original = $state<Booking | null>(null);

	let title = $state('');
	let eventType = $state('');
	let expected = $state<number | null>(null);
	let description = $state('');
	let requirements = $state('');
	let venue = $state(params.get('venue') ?? '');
	let dateFrom = $state(params.get('date') ?? isoDate(new Date()));
	let multiDay = $state(false);
	let dateTo = $state('');
	let start = $state(params.get('start') ?? '10:00');
	let end = $state(params.get('end') ?? '12:00');

	let check = $state<BookingCheck | null>(null);
	let checkError = $state('');
	let checking = $state(false);
	let moves = $state<Record<string, Move>>({});
	let submitError = $state('');
	let submitting = $state(false);

	$effect(() => {
		if (!session.user) return;
		untrack(async () => {
			[venues, eventTypes] = await Promise.all([
				api<Venue[]>('/venues'),
				api<string[]>('/bookings/event-types')
			]);
			if (rescheduleId) {
				const b = await api<Booking>(`/bookings/${rescheduleId}`);
				original = b;
				title = b.title;
				eventType = b.event_type;
				expected = b.expected_count;
				description = b.description ?? '';
				requirements = b.requirements ?? '';
				venue = b.venue.code;
				dateFrom = b.occurrences[0].start.slice(0, 10);
				const last = b.occurrences.at(-1)!.start.slice(0, 10);
				multiDay = last !== dateFrom;
				dateTo = multiDay ? last : '';
				start = b.occurrences[0].start.slice(11, 16);
				end = b.occurrences[0].end.slice(11, 16);
			}
		});
	});

	function body() {
		return {
			venue,
			title: title || 'Untitled',
			event_type: eventType || 'Other',
			expected_count: expected || 1,
			date_from: dateFrom,
			date_to: multiDay && dateTo ? dateTo : null,
			start_time: start,
			end_time: end,
			description: description || null,
			requirements: requirements || null,
			moves: Object.values(moves)
		};
	}

	// Re-check whenever the venue, time or size changes (debounced).
	$effect(() => {
		void [venue, dateFrom, dateTo, multiDay, start, end, expected];
		if (!venue || !dateFrom || !start || !end) return;
		const timer = setTimeout(runCheck, 350);
		return () => clearTimeout(timer);
	});

	async function runCheck() {
		checking = true;
		checkError = '';
		try {
			const q = rescheduleId ? `?reschedule_of=${rescheduleId}` : '';
			check = await api<BookingCheck>(`/bookings/check${q}`, {
				method: 'POST',
				body: JSON.stringify({ ...body(), moves: [] })
			});
			// Default each class to its best relocation, or BYOD when no lab is free.
			const next: Record<string, Move> = {};
			for (const c of check.clashes) {
				const key = `${c.slot_id}|${c.date}`;
				next[key] =
					moves[key] ??
					(c.options.length
						? {
								slot_id: c.slot_id,
								date: c.date,
								action: 'relocated',
								venue_code: c.options[0].code
							}
						: { slot_id: c.slot_id, date: c.date, action: 'byod_classroom' });
			}
			moves = next;
		} catch (e) {
			check = null;
			checkError = e instanceof Error ? e.message : 'Could not check';
		} finally {
			checking = false;
		}
	}

	function choose(key: string, value: string) {
		const [slot, date] = key.split('|');
		moves[key] =
			value === 'byod'
				? { slot_id: Number(slot), date, action: 'byod_classroom' }
				: { slot_id: Number(slot), date, action: 'relocated', venue_code: value };
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		submitting = true;
		submitError = '';
		try {
			const b = await api<Booking>('/bookings', {
				method: 'POST',
				body: JSON.stringify({
					...body(),
					join_waitlist: check?.outcome === 'waitlist',
					reschedule_of: rescheduleId ? Number(rescheduleId) : null
				})
			});
			goto(`/bookings/${b.id}`);
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Could not submit';
			await runCheck();
		} finally {
			submitting = false;
		}
	}

	const selected = $derived(venues.find((v) => v.code === venue));
	const pct = (n: number) => `${Math.round(n * 100)}%`;
</script>

<h1 class="text-2xl font-semibold">
	{original ? `Reschedule ${original.ref}` : 'Book a venue'}
</h1>
{#if !session.loaded}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.can('book')}
	<p class="mt-6 {card}">Log in as a faculty member to book a venue.</p>
{:else}
	<p class="mt-2 text-muted">
		{original
			? 'Your current slot stays booked until the new time is approved.'
			: 'Availability is checked as you type. Requests go to the venue in-charge, and to the HOD for CSE venues or when a class has to move.'}
	</p>

	<form class="mt-6 space-y-6" onsubmit={submit}>
		<section class="{card} grid gap-4 sm:grid-cols-2">
			<h2 class="text-lg font-semibold sm:col-span-2">Event</h2>
			<div class="sm:col-span-2">
				<label class={label} for="title">Title</label>
				<input id="title" required maxlength="200" bind:value={title} class={field} />
			</div>
			<div>
				<label class={label} for="etype">Event type</label>
				<select id="etype" required bind:value={eventType} class={field}>
					<option value="" disabled>Choose…</option>
					{#each eventTypes as t (t)}<option>{t}</option>{/each}
				</select>
			</div>
			<div>
				<label class={label} for="count">Expected attendance</label>
				<input id="count" type="number" min="1" required bind:value={expected} class={field} />
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="desc">Description (optional)</label>
				<textarea id="desc" rows="3" bind:value={description} class={field}></textarea>
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="req">Requirements (optional)</label>
				<input
					id="req"
					bind:value={requirements}
					placeholder="e.g. Python 3 with Jupyter, two cordless microphones"
					class={field}
				/>
			</div>
		</section>

		<section class="{card} grid gap-4 sm:grid-cols-2">
			<h2 class="text-lg font-semibold sm:col-span-2">Venue and time</h2>
			<div class="sm:col-span-2">
				<label class={label} for="venue">Venue</label>
				<select id="venue" required bind:value={venue} class={field}>
					<option value="" disabled>Choose a venue…</option>
					{#each venues as v (v.code)}
						<option value={v.code}>{v.code} · {v.name} ({v.capacity} seats)</option>
					{/each}
				</select>
			</div>
			<div>
				<label class={label} for="from">{multiDay ? 'First day' : 'Date'}</label>
				<input id="from" type="date" required bind:value={dateFrom} class={field} />
			</div>
			<div>
				{#if multiDay}
					<label class={label} for="to">Last day</label>
					<input id="to" type="date" min={dateFrom} bind:value={dateTo} class={field} />
				{/if}
				<label class="mt-2 flex items-center gap-2 {multiDay ? '' : 'sm:mt-9'}">
					<input type="checkbox" bind:checked={multiDay} class="h-5 w-5" /> Runs over several days
				</label>
			</div>
			<div>
				<label class={label} for="start">Starts</label>
				<input id="start" type="time" required bind:value={start} class={field} />
			</div>
			<div>
				<label class={label} for="end">Ends</label>
				<input id="end" type="time" required bind:value={end} class={field} />
			</div>

			<div class="sm:col-span-2" aria-live="polite">
				{#if checkError}
					<p class="text-danger">{checkError}</p>
				{:else if check}
					{@const days = check.days.length}
					{#if check.outcome === 'free'}
						<p class="rounded-lg bg-success/15 px-4 py-3 text-success">
							{check.venue.code} is free{days > 1
								? ` on all ${days} days (Sundays skipped)`
								: ` on ${prettyDate(check.days[0])}`}.
						</p>
					{:else if check.outcome === 'blocked'}
						<div class="rounded-lg bg-danger/10 px-4 py-3">
							<p class="font-medium text-danger">{check.venue.code} can't be booked then.</p>
							<ul class="mt-1 text-sm">
								{#each check.blocked as b, i (i)}<li>{b.label}</li>{/each}
							</ul>
						</div>
					{:else if check.outcome === 'waitlist'}
						<div class="rounded-lg bg-warning/15 px-4 py-3">
							<p class="font-medium">Already booked: {check.taken[0].label}</p>
							<p class="mt-1 text-sm">
								You can join the waitlist. If the slot frees up, you get 24 hours to confirm.
							</p>
						</div>
					{/if}

					{#if check.clashes.length && check.outcome !== 'blocked'}
						<div class="mt-3 space-y-3">
							<p class="font-medium">
								A class uses {check.venue.code} then. It can move with the HOD's approval:
							</p>
							{#each check.clashes as c (c.slot_id + c.date)}
								{@const key = `${c.slot_id}|${c.date}`}
								<fieldset class="rounded-lg border border-border p-4">
									<legend class="px-1 font-medium">
										{c.label} · {c.subject_name}, {prettyDate(c.date)}, {c.start.slice(
											0,
											5
										)}–{c.end.slice(0, 5)} ({c.batch_size} students)
									</legend>
									<div class="mt-2 space-y-2">
										{#each c.options as o (o.code)}
											<label class="flex items-start gap-3">
												<input
													type="radio"
													name={key}
													class="mt-1 h-5 w-5"
													checked={moves[key]?.venue_code === o.code}
													onchange={() => choose(key, o.code)}
												/>
												<span
													>Move to <strong>{o.code}</strong> ({o.capacity} seats,
													{o.software_match === 1
														? 'same software'
														: `${pct(o.software_match)} of the software; lacks ${o.missing_software.join(', ')}`})</span
												>
											</label>
										{/each}
										<label class="flex items-start gap-3">
											<input
												type="radio"
												name={key}
												class="mt-1 h-5 w-5"
												checked={moves[key]?.action === 'byod_classroom'}
												onchange={() => choose(key, 'byod')}
											/>
											<span>BYOD in the classroom (students bring laptops)</span>
										</label>
									</div>
								</fieldset>
							{/each}
						</div>
					{/if}

					{#if check.warnings.length}
						<ul class="mt-3 space-y-1">
							{#each check.warnings as w, i (i)}
								<li class="rounded-lg border border-warning/40 bg-warning/10 px-4 py-2">
									{w.message}
									{#if w.kind === 'recurring'}
										<a class="text-accent underline" href="/documents?tab=events&venue={venue}"
											>Past events in {venue}</a
										>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}

					{#if check.alternatives.length}
						<div class="mt-3">
							<p class="text-sm text-muted">Free at that time instead:</p>
							<div class="mt-2 flex flex-wrap gap-2">
								{#each check.alternatives as a (a.code)}
									<button type="button" class={btnSecondary} onclick={() => (venue = a.code)}
										>{a.code} ({a.capacity} seats)</button
									>
								{/each}
							</div>
						</div>
					{/if}
				{:else if checking}
					<p class="text-muted">Checking…</p>
				{/if}
			</div>
		</section>

		{#if submitError}<p class="text-danger" role="alert">{submitError}</p>{/if}
		<div class="flex flex-wrap items-center gap-3">
			<button
				type="submit"
				class={btnPrimary}
				disabled={submitting || !check || check.outcome === 'blocked'}
			>
				{check?.outcome === 'waitlist'
					? 'Join the waitlist'
					: original
						? 'Request the new time'
						: 'Submit request'}
			</button>
			{#if selected && expected && expected > selected.capacity}
				<span class="text-danger">{selected.code} seats only {selected.capacity}.</span>
			{/if}
		</div>
	</form>
{/if}

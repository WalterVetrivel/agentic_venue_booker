<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import { page } from '$app/state';
	import { goto, replaceState } from '$app/navigation';
	import { untrack } from 'svelte';
	import { api } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { chat } from '#lib/stores/chat.svelte.ts';
	import { isoDate, prettyDate } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { Booking, BookingCheck, BookingDraft, Move, Venue } from '#lib/types.ts';

	const rescheduleId = page.url.searchParams.get('reschedule');

	let venues = $state<Venue[]>([]);
	let eventTypes = $state<string[]>([]);
	let original = $state<Booking | null>(null);

	let fromAssistant = $state(false);
	// Which chat card the draft came from, so it can show as submitted.
	let fromMessage = $state<number | null>(null);
	let fromCard = $state(-1);
	let title = $state('');
	let eventType = $state('');
	let expected = $state<number | null>(null);
	let description = $state('');
	let requirements = $state('');
	let venue = $state('');
	let dateFrom = $state(isoDate(new Date()));
	let multiDay = $state(false);
	let dateTo = $state('');
	let start = $state('10:00');
	let end = $state('12:00');

	// The assistant's drafts link here with what it knows filled in (and via=agent). A later
	// draft, after the person tells it a missing detail, fills in what it has and keeps the rest.
	function fill(params: { get(key: string): string | null }) {
		const has = (key: string) => !!params.get(key);
		if (params.get('via') === 'agent') fromAssistant = true;
		if (has('from_msg')) fromMessage = Number(params.get('from_msg'));
		if (has('from_card')) fromCard = Number(params.get('from_card'));
		if (has('title')) title = params.get('title')!;
		if (has('type')) eventType = params.get('type')!;
		if (has('count')) expected = Number(params.get('count')) || null;
		if (has('description')) description = params.get('description')!;
		if (has('requirements')) requirements = params.get('requirements')!;
		if (has('venue')) venue = params.get('venue')!;
		if (has('date')) dateFrom = params.get('date')!;
		if (has('to')) [multiDay, dateTo] = [true, params.get('to')!];
		if (has('start')) start = params.get('start')!;
		if (has('end')) end = params.get('end')!;
	}
	fill(page.url.searchParams);
	let filled = page.url.search;
	$effect(() => {
		if (page.url.search === filled) return;
		filled = page.url.search;
		untrack(() => fill(page.url.searchParams));
	});

	let check = $state<BookingCheck | null>(null);
	let checkError = $state('');
	let checking = $state(false);
	let moves = $state<Record<string, Move>>({});
	let submitError = $state('');
	let submitting = $state(false);

	// A saved, unsubmitted form. It holds nothing, so the slot can be taken meanwhile.
	let draftId = $state<number | null>(Number(page.url.searchParams.get('draft')) || null);
	let takenSinceSaved = $state(false);
	let savingDraft = $state(false);
	let draftNote = $state('');
	let draftError = $state('');

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
			} else if (draftId) {
				try {
					loadDraft(await api<BookingDraft>(`/booking-drafts/${draftId}`));
				} catch (e) {
					draftId = null;
					draftError = e instanceof Error ? e.message : 'Could not open the draft';
				}
			}
		});
	});

	function loadDraft(d: BookingDraft) {
		title = d.title;
		eventType = d.event_type ?? '';
		expected = d.expected_count;
		description = d.description ?? '';
		requirements = d.requirements ?? '';
		venue = d.venue ?? '';
		if (d.date_from) dateFrom = d.date_from;
		multiDay = !!d.date_to && d.date_to !== d.date_from;
		dateTo = multiDay ? d.date_to! : '';
		if (d.start_time) start = d.start_time.slice(0, 5);
		if (d.end_time) end = d.end_time.slice(0, 5);
		takenSinceSaved = d.taken_since_saved;
	}

	async function saveDraft() {
		savingDraft = true;
		draftError = '';
		try {
			const d = await api<BookingDraft>(
				draftId ? `/booking-drafts/${draftId}` : '/booking-drafts',
				{
					method: draftId ? 'PUT' : 'POST',
					body: JSON.stringify({
						venue: venue || null,
						title,
						event_type: eventType || null,
						expected_count: expected || null,
						date_from: dateFrom || null,
						date_to: multiDay && dateTo ? dateTo : null,
						start_time: start || null,
						end_time: end || null,
						description: description || null,
						requirements: requirements || null
					})
				}
			);
			// Shallow: the form keeps what is on screen, and a reload reopens the draft.
			if (!draftId) replaceState(`/book?draft=${d.id}`, {});
			draftId = d.id;
			takenSinceSaved = false;
			draftNote = `Draft saved at ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`;
		} catch (e) {
			draftError = e instanceof Error ? e.message : 'Could not save the draft';
		} finally {
			savingDraft = false;
		}
	}

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
				headers: fromAssistant ? { 'X-Via': 'agent' } : {},
				body: JSON.stringify({
					...body(),
					join_waitlist: check?.outcome === 'waitlist',
					reschedule_of: rescheduleId ? Number(rescheduleId) : null,
					draft_id: draftId
				})
			});
			if (fromMessage && fromCard >= 0)
				await chat.draftSubmitted(fromMessage, fromCard, `Submitted as ${b.ref}.`);
			chat.formSubmitted('/book', `Submitted as ${b.ref}.`);
			goto(`/bookings/${b.id}`);
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Could not submit';
			await runCheck();
		} finally {
			submitting = false;
		}
	}

	const selected = $derived(venues.find((v) => v.code === venue));
	const complete = $derived(
		!!(title.trim() && eventType && expected && venue && dateFrom && start && end) &&
			(!multiDay || !!dateTo)
	);

	// Tell the assistant what is on the form, so "add …" in the chat means this form.
	$effect(() => {
		if (original) return;
		chat.form = {
			kind: 'staff',
			fields: {
				venue,
				title,
				event_type: eventType,
				expected_count: expected,
				date: dateFrom,
				date_to: multiDay ? dateTo : null,
				start,
				end,
				description,
				requirements
			}
		};
		return () => (chat.form = null);
	});
	const pct = (n: number) => `${Math.round(n * 100)}%`;
</script>

<h1 class="text-2xl font-semibold">
	{original ? `Reschedule ${original.ref}` : 'Book a venue'}
</h1>
{#if !session.loaded}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.can('book')}
	<div class="mt-6 {card}">
		<p>
			Students: <a class="text-accent underline" href="/book/student"
				>request a lab for group work</a
			>, no login needed.
		</p>
		<p class="mt-2">
			Faculty and staff:
			<a
				class="font-medium text-accent underline"
				href="/login?next={encodeURIComponent(page.url.pathname + page.url.search)}"
				>log in to book a venue</a
			>. You'll come back here{page.url.search ? ' with the details filled in' : ''}.
		</p>
	</div>
{:else}
	<p class="mt-2 text-muted">
		{original
			? 'Your current slot stays booked until the new time is approved.'
			: 'Availability is checked as you type. Requests go to the venue in-charge, and to the HOD for CSE venues or when a class has to move.'}
	</p>

	<p class="mt-2 text-sm text-muted">
		Fields marked <span class="text-danger">*</span> are required.
	</p>
	<form class="mt-4 space-y-6" onsubmit={submit}>
		<section class="{card} grid gap-4 sm:grid-cols-2">
			<h2 class="text-lg font-semibold sm:col-span-2">Event</h2>
			<div class="sm:col-span-2">
				<label class={label} for="title"
					>Title<span class="text-danger" aria-hidden="true"> *</span></label
				>
				<input id="title" required maxlength="200" bind:value={title} class={field} />
			</div>
			<div>
				<label class={label} for="etype"
					>Event type<span class="text-danger" aria-hidden="true"> *</span></label
				>
				<select id="etype" required bind:value={eventType} class={field}>
					<option value="" disabled>Choose…</option>
					{#each eventTypes as t (t)}<option>{t}</option>{/each}
				</select>
			</div>
			<div>
				<label class={label} for="count"
					>Expected attendance<span class="text-danger" aria-hidden="true"> *</span></label
				>
				<input id="count" type="number" min="1" required bind:value={expected} class={field} />
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="desc">Description</label>
				<textarea id="desc" rows="3" bind:value={description} class={field}></textarea>
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="req">Requirements</label>
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
				<label class={label} for="venue"
					>Venue<span class="text-danger" aria-hidden="true"> *</span></label
				>
				<select id="venue" required bind:value={venue} class={field}>
					<option value="" disabled>Choose a venue…</option>
					{#each venues as v (v.code)}
						<option value={v.code}>{v.code} · {v.name} ({v.capacity} seats)</option>
					{/each}
				</select>
			</div>
			<div>
				<label class={label} for="from"
					>{multiDay ? 'First day' : 'Date'}<span class="text-danger" aria-hidden="true">
						*</span
					></label
				>
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
				<label class={label} for="start"
					>Starts<span class="text-danger" aria-hidden="true"> *</span></label
				>
				<input id="start" type="time" required bind:value={start} class={field} />
			</div>
			<div>
				<label class={label} for="end"
					>Ends<span class="text-danger" aria-hidden="true"> *</span></label
				>
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
							{#if takenSinceSaved}
								<p class="mt-1 text-sm font-medium" data-testid="taken-since-saved">
									This slot was booked by someone else after you saved the draft, so it can only
									join the waitlist now.
								</p>
							{/if}
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
				class="{btnPrimary} inline-flex items-center gap-2"
				disabled={submitting || !complete || !check || check.outcome === 'blocked'}
				title={complete ? undefined : 'Fill in the fields marked *'}
			>
				<Icon name="send" size={18} />
				{check?.outcome === 'waitlist'
					? 'Join the waitlist'
					: original
						? 'Request the new time'
						: 'Submit request'}
			</button>
			{#if !original}
				<button type="button" class={btnSecondary} disabled={savingDraft} onclick={saveDraft}
					>{draftId ? 'Save draft' : 'Save as draft'}</button
				>
			{/if}
			{#if draftNote}
				<span class="text-muted" role="status"
					>{draftNote} <a class="text-accent underline" href="/bookings#drafts">My drafts</a></span
				>
			{/if}
			{#if draftError}<span class="text-danger" role="alert">{draftError}</span>{/if}
			{#if selected && expected && expected > selected.capacity}
				<span class="text-danger">{selected.code} seats only {selected.capacity}.</span>
			{/if}
		</div>
	</form>
{/if}

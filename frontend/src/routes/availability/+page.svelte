<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import AvailabilityGrid from '#lib/components/AvailabilityGrid.svelte';
	import Calendar from '#lib/components/Calendar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import ViewToggle, { savedView } from '#lib/components/ViewToggle.svelte';
	import { addDays, isoDate, minutesOf, minutesOnDay, prettyDate } from '#lib/time.ts';
	import type { DayAvailability } from '#lib/types.ts';

	const params = page.url.searchParams;
	let day = $state(params.get('date') ?? isoDate(new Date()));
	let type = $state(params.get('type') ?? '');
	let minCapacity = $state(params.get('min_capacity') ?? '');
	let needs = $state(params.get('needs') ?? '');
	let from = $state(params.get('from') ?? '');
	let to = $state(params.get('to') ?? '');
	let mode = $state(
		(params.get('view') as 'grid' | 'calendar' | null) ??
			savedView('availability', ['grid', 'calendar'] as const, 'grid')
	);
	let calVenue = $state(params.get('venue') ?? 'CC1');
	let calDate = $state(params.get('date') ?? isoDate(new Date()));

	function syncCalendarUrl() {
		const q = new URLSearchParams({ view: 'calendar', venue: calVenue, date: calDate });
		replaceState(`?${q}`, {});
	}

	let data = $state<DayAvailability | null>(null);
	let error = $state('');

	async function load() {
		const q = new URLSearchParams({ date: day });
		if (type) q.set('type', type);
		if (minCapacity) q.set('min_capacity', minCapacity);
		if (needs.trim()) q.set('needs', needs.trim());
		error = '';
		try {
			data = await api<DayAvailability>(`/availability?${q}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load availability';
		}
		if (from && to) {
			q.set('from', from);
			q.set('to', to);
		}
		replaceState(`?${q}`, {});
	}

	$effect(() => {
		void [day, type, minCapacity];
		if (mode === 'grid') load();
	});

	$effect(() => {
		void [calVenue, calDate];
		if (mode === 'calendar') syncCalendarUrl();
	});

	// With a time window, keep only venues with nothing (not even a class) inside it.
	const shown = $derived.by(() => {
		if (!data) return null;
		if (!from || !to || minutesOf(to) <= minutesOf(from)) return data;
		const s = minutesOf(from);
		const e = minutesOf(to);
		return {
			...data,
			venues: data.venues.filter(
				(v) =>
					!v.blocks.some(
						(b) => minutesOnDay(b.start, data!.date) < e && s < minutesOnDay(b.end, data!.date)
					)
			)
		};
	});

	function bookHref(code: string) {
		const q = new URLSearchParams({ venue: code, date: day });
		if (from) q.set('start', from);
		if (to) q.set('end', to);
		return `/book?${q}`;
	}

	const field =
		'w-full rounded-lg border border-border bg-bg px-3 py-2.5 focus:border-accent focus:outline-none';
</script>

<div class="flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold">Availability</h1>
		<p class="mt-2 text-muted">See which labs, Centres of Excellence and seminar halls are free.</p>
	</div>
	<ViewToggle
		bind:value={mode}
		key="availability"
		label="Availability view"
		options={[
			{ value: 'grid', label: 'All venues', icon: 'table' },
			{ value: 'calendar', label: 'Calendar', icon: 'calendar' }
		]}
	/>
</div>

{#if mode === 'calendar'}
	<div class="mt-6">
		<Calendar bind:venue={calVenue} bind:date={calDate} />
	</div>
{:else}
	<form
		class="mt-6 grid gap-4 glass rounded-2xl border p-5 sm:grid-cols-2 lg:grid-cols-3"
		onsubmit={(e) => {
			e.preventDefault();
			load();
		}}
	>
		<div>
			<label for="day" class="mb-1.5 block font-medium">Date</label>
			<div class="flex gap-2">
				<button
					type="button"
					class="rounded-lg border border-border px-3 hover:bg-surface-2"
					aria-label="Previous day"
					onclick={() => (day = addDays(day, -1))}>‹</button
				>
				<input id="day" type="date" bind:value={day} class={field} />
				<button
					type="button"
					class="rounded-lg border border-border px-3 hover:bg-surface-2"
					aria-label="Next day"
					onclick={() => (day = addDays(day, 1))}>›</button
				>
			</div>
		</div>
		<div>
			<label for="type" class="mb-1.5 block font-medium">Venue type</label>
			<select id="type" bind:value={type} class={field}>
				<option value="">All venues</option>
				<option value="lab">Labs</option>
				<option value="coe">Centres of Excellence</option>
				<option value="seminar_hall">Seminar halls</option>
			</select>
		</div>
		<div>
			<label for="cap" class="mb-1.5 block font-medium">At least this many seats</label>
			<input
				id="cap"
				type="number"
				min="1"
				bind:value={minCapacity}
				placeholder="Any"
				class={field}
			/>
		</div>
		<div class="sm:col-span-2 lg:col-span-1">
			<label for="needs" class="mb-1.5 block font-medium">Needs software or equipment</label>
			<input id="needs" bind:value={needs} placeholder="e.g. Power BI, Docker" class={field} />
		</div>
		<div>
			<label for="from" class="mb-1.5 block font-medium">Free from</label>
			<input id="from" type="time" step="1800" bind:value={from} class={field} />
		</div>
		<div>
			<label for="to" class="mb-1.5 block font-medium">Free until</label>
			<input id="to" type="time" step="1800" bind:value={to} class={field} />
		</div>
		<div class="flex items-end sm:col-span-2 lg:col-span-3">
			<button type="submit" class="btn-cta rounded-lg px-5 py-2.5 font-medium">
				Apply filters
			</button>
		</div>
	</form>

	<h2 class="mt-8 text-lg font-semibold">{prettyDate(day)}</h2>
	{#if error}
		<p class="mt-4 text-danger" role="alert">{error}</p>
	{:else if !shown}
		<p class="mt-4 text-muted">Loading…</p>
	{:else if shown.venues.length === 0}
		<p class="mt-4 glass rounded-2xl border p-6 text-muted">
			No venue matches these filters. Try fewer requirements or a different time.
		</p>
	{:else}
		{#if !shown.open_from}
			<p class="mt-2 text-muted">The college is closed on Sundays.</p>
		{/if}
		{@const warned = shown.venues.filter((v) => v.warnings.length)}
		{@const alertCount = warned.reduce((n, v) => n + v.warnings.length, 0)}
		{#if alertCount}
			<details class="group glass mt-4 rounded-2xl border">
				<summary
					class="flex list-none items-center gap-2 rounded-2xl px-4 py-3 font-medium select-none hover:bg-surface-2 [&::-webkit-details-marker]:hidden"
				>
					<Icon
						name="chevron"
						size={18}
						class="-rotate-90 transition-transform duration-200 group-open:rotate-0"
					/>
					Alerts
					<span
						class="rounded-full bg-warning/20 px-2 text-sm font-semibold text-warning"
						aria-label="{alertCount} alert{alertCount === 1 ? '' : 's'}">{alertCount}</span
					>
				</summary>
				<ul class="space-y-2 px-4 pb-4">
					{#each warned as v (v.code)}
						{#each v.warnings as w, i (i)}
							<li class="rounded-lg border border-warning/40 bg-warning/10 px-4 py-2.5">
								<strong>{v.code}:</strong>
								{w.message}
							</li>
						{/each}
					{/each}
				</ul>
			</details>
		{/if}
		<p class="mt-2 text-sm text-muted">
			{shown.venues.length} venue{shown.venues.length === 1 ? '' : 's'}
		</p>
		<div class="mt-3">
			<AvailabilityGrid
				data={shown}
				from={from || null}
				to={to || null}
				bookHref={session.can('book') ? bookHref : null}
			/>
		</div>
	{/if}
{/if}

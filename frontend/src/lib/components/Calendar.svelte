<script lang="ts">
	import Icon from './Icon.svelte';
	import ViewToggle, { savedView } from './ViewToggle.svelte';
	import WeekGrid, { KIND_LABEL, KIND_STYLE, type GridRow } from './WeekGrid.svelte';
	import { api } from '#lib/api.ts';
	import { addDays, isoDate, minutesOnDay } from '#lib/time.ts';
	import type { Block, Venue, VenueRange, VenueRangeDay } from '#lib/types.ts';

	type View = 'day' | 'week' | 'month';
	const VIEWS: View[] = ['day', 'week', 'month'];

	let {
		venue = $bindable('CC1'),
		date = $bindable(isoDate(new Date())),
		view = $bindable(savedView('calendar', VIEWS, 'week')),
		pickVenue = true,
		onchange
	}: {
		venue?: string;
		date?: string;
		view?: View;
		/** Show the venue dropdown (off on a venue's own page). */
		pickVenue?: boolean;
		onchange?: () => void;
	} = $props();

	let venues = $state<Venue[]>([]);
	let data = $state<VenueRange | null>(null);
	let error = $state('');
	let loading = $state(false);
	const today = isoDate(new Date());

	$effect(() => {
		if (pickVenue && !venues.length)
			api<Venue[]>('/venues')
				.then((v) => (venues = v))
				.catch(() => {});
	});

	function parse(iso: string) {
		const [y, m, d] = iso.split('-').map(Number);
		return new Date(y, m - 1, d);
	}
	function monday(iso: string) {
		const wd = (parse(iso).getDay() + 6) % 7;
		return addDays(iso, -wd);
	}

	const range = $derived.by(() => {
		if (view === 'day') return { start: date, end: date };
		if (view === 'week') {
			const start = monday(date);
			return { start, end: addDays(start, 6) };
		}
		const first = date.slice(0, 8) + '01';
		const d = parse(first);
		const last = isoDate(new Date(d.getFullYear(), d.getMonth() + 1, 0));
		const start = monday(first);
		return { start, end: addDays(monday(last), 6) };
	});

	let request = 0;
	$effect(() => {
		const { start, end } = range;
		const code = venue;
		const mine = ++request;
		loading = true;
		error = '';
		api<VenueRange>(`/availability/venue/${encodeURIComponent(code)}?start=${start}&end=${end}`)
			.then((r) => {
				if (mine === request) data = r;
			})
			.catch((e) => {
				if (mine === request)
					error = e instanceof Error ? e.message : 'Could not load the calendar';
			})
			.finally(() => {
				if (mine === request) loading = false;
			});
	});

	function move(step: number) {
		if (view === 'day') date = addDays(date, step);
		else if (view === 'week') date = addDays(date, step * 7);
		else {
			const d = parse(date);
			date = isoDate(new Date(d.getFullYear(), d.getMonth() + step, 1));
		}
		onchange?.();
	}

	const title = $derived.by(() => {
		const d = parse(date);
		if (view === 'day')
			return d.toLocaleDateString('en-IN', {
				weekday: 'long',
				day: 'numeric',
				month: 'long',
				year: 'numeric'
			});
		if (view === 'month') return d.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
		const s = parse(range.start);
		const e = parse(addDays(range.start, 5));
		const fmt = (x: Date) => x.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
		return `${fmt(s)} – ${fmt(e)} ${e.getFullYear()}`;
	});

	// Blocks shown as events: everything but the Sunday "closed" marker.
	function events(day: VenueRangeDay): Block[] {
		return day.blocks.filter((b) => b.kind !== 'closed');
	}

	function shortDay(iso: string) {
		return parse(iso).toLocaleDateString('en-IN', { weekday: 'short' });
	}
	function dayMonth(iso: string) {
		return parse(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
	}

	const rows = $derived.by((): GridRow[] => {
		if (!data || view === 'month') return [];
		return data.days
			.filter((d) => view === 'day' || d.open_from || events(d).length)
			.map((d) => ({
				key: d.date,
				label: shortDay(d.date),
				sub: dayMonth(d.date),
				highlight: d.date === today,
				closed: d.open_from ? null : 'Closed',
				items: events(d).map((b) => ({
					start: minutesOnDay(b.start, d.date),
					end: minutesOnDay(b.end, d.date),
					title: b.label,
					kind: b.kind
				}))
			}));
	});

	const hours = $derived.by(() => {
		let from = 480;
		let to = 1080;
		for (const r of rows)
			for (const i of r.items) {
				if (i.start > 0) from = Math.min(from, Math.floor(i.start / 60) * 60);
				if (i.end < 1440) to = Math.max(to, Math.ceil(i.end / 60) * 60);
			}
		return { from, to };
	});

	const month = $derived(date.slice(0, 7));
	const kinds = $derived(
		[...new Set((data?.days ?? []).flatMap((d) => events(d).map((b) => b.kind)))].filter(
			(k) => KIND_LABEL[k]
		)
	);

	function openDay(iso: string) {
		date = iso;
		view = 'day';
		onchange?.();
	}

	const fmtTime = (iso: string, day: string) => {
		const m = minutesOnDay(iso, day);
		return m <= 0
			? ''
			: `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')} `;
	};
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-3">
		{#if pickVenue}
			<label class="flex items-center gap-2">
				<span class="text-sm font-medium">Venue</span>
				<select
					bind:value={venue}
					onchange={() => onchange?.()}
					class="rounded-lg border border-border bg-glass-strong px-3 py-2 focus:border-accent focus:outline-none"
				>
					{#if !venues.some((v) => v.code === venue)}<option value={venue}>{venue}</option>{/if}
					{#each venues as v (v.code)}
						<option value={v.code}>{v.code} · {v.name}</option>
					{/each}
				</select>
			</label>
		{/if}
		<div class="flex items-center gap-1">
			<button
				type="button"
				class="press rounded-lg border border-border px-2.5 py-1.5 hover:bg-surface-2"
				aria-label="Previous {view}"
				onclick={() => move(-1)}>‹</button
			>
			<button
				type="button"
				class="press rounded-lg border border-border px-3 py-1.5 text-sm font-medium hover:bg-surface-2"
				onclick={() => {
					date = today;
					onchange?.();
				}}>Today</button
			>
			<button
				type="button"
				class="press rounded-lg border border-border px-2.5 py-1.5 hover:bg-surface-2"
				aria-label="Next {view}"
				onclick={() => move(1)}>›</button
			>
		</div>
		<h3 class="text-lg font-semibold" aria-live="polite">{title}</h3>
		{#if loading}<span class="spin text-muted" aria-hidden="true"
				><Icon name="retry" size={16} /></span
			>{/if}
		<div class="ml-auto">
			<ViewToggle
				bind:value={view}
				key="calendar"
				label="Calendar view"
				options={[
					{ value: 'day', label: 'Day' },
					{ value: 'week', label: 'Week' },
					{ value: 'month', label: 'Month' }
				]}
			/>
		</div>
	</div>

	{#if error}
		<p class="text-danger" role="alert">{error}</p>
	{:else if !data}
		<div class="glass h-64 animate-pulse rounded-2xl border"></div>
	{:else if view === 'month'}
		<div
			class="glass overflow-hidden rounded-2xl border"
			role="region"
			aria-label="{title} at {venue}"
		>
			<div
				class="grid grid-cols-7 border-b border-border text-center text-xs font-medium text-muted"
				aria-hidden="true"
			>
				{#each ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as d (d)}
					<div class="py-2">{d}</div>
				{/each}
			</div>
			<div class="grid grid-cols-7">
				{#each data.days as d (d.date)}
					{@const ev = events(d)}
					{@const inMonth = d.date.startsWith(month)}
					<button
						type="button"
						class="group flex min-h-16 flex-col items-stretch justify-start border-r border-b border-border p-1.5 text-left align-top transition-colors hover:bg-accent-soft sm:min-h-28 [&:nth-child(7n)]:border-r-0 {inMonth
							? ''
							: 'opacity-60'} {d.open_from ? '' : 'bg-muted/5'}"
						aria-label="{parse(d.date).toLocaleDateString('en-IN', {
							weekday: 'long',
							day: 'numeric',
							month: 'long'
						})}: {ev.length ? `${ev.length} event${ev.length === 1 ? '' : 's'}` : 'nothing booked'}"
						onclick={() => openDay(d.date)}
					>
						<span
							class="inline-grid h-6 min-w-6 place-items-center self-start rounded-full px-1 text-sm {d.date ===
							today
								? 'bg-accent font-semibold text-accent-fg'
								: 'font-medium'}">{Number(d.date.slice(8))}</span
						>
						<span class="mt-1 flex flex-wrap gap-1 sm:hidden">
							{#each ev.slice(0, 4) as b, i (i)}
								<span
									class="h-1.5 w-1.5 rounded-full border-l-4 {KIND_STYLE[b.kind] ??
										KIND_STYLE.closed}"
								></span>
							{/each}
						</span>
						<span class="mt-1 hidden space-y-1 sm:block">
							{#each ev.slice(0, 3) as b, i (i)}
								<span
									class="block truncate rounded border-l-4 px-1.5 py-0.5 text-xs {KIND_STYLE[
										b.kind
									] ?? KIND_STYLE.closed}">{fmtTime(b.start, d.date)}{b.label}</span
								>
							{/each}
							{#if ev.length > 3}
								<span class="block px-1 text-xs text-muted">+{ev.length - 3} more</span>
							{/if}
						</span>
					</button>
				{/each}
			</div>
		</div>
	{:else}
		<WeekGrid {rows} from={hours.from} to={hours.to} label="{title} at {venue}" />
	{/if}

	{#if kinds.length}
		<ul class="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted" aria-label="Legend">
			{#each kinds as k (k)}
				<li class="flex items-center gap-1.5">
					<span class="h-3 w-3 rounded-sm border-l-4 {KIND_STYLE[k]}"></span>{KIND_LABEL[k]}
				</li>
			{/each}
		</ul>
	{/if}
</div>

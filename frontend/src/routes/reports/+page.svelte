<script lang="ts">
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import BarChart, { type BarRow } from '#lib/components/BarChart.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { addDays, isoDate } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field } from '#lib/ui.ts';

	type Count = { name: string; count: number };
	type Stats = { count: number; average_hours: number | null; median_hours: number | null };
	type UseRow = {
		venue: string;
		name: string;
		open_hours: number;
		closed_hours: number;
		class_hours: number;
		event_hours: number;
		free_hours: number;
		class_pct: number;
		event_pct: number;
		used_pct: number;
	};
	type Report = {
		scope: string;
		period_label: string | null;
		from: string;
		to: string;
		utilisation: {
			venues: UseRow[];
			total: {
				open_hours: number;
				class_hours: number;
				event_hours: number;
				class_pct: number;
				event_pct: number;
				used_pct: number;
			};
		};
		events: {
			count: number;
			by_type: Count[];
			by_department: Count[];
			by_month: { month: string; count: number }[];
			rows: {
				date: string;
				title: string;
				event_type: string;
				department: string;
				venues: string;
				participants: number | null;
				source: string;
				ref: string | null;
			}[];
		};
		turnaround: Stats & {
			within_a_day: number;
			approved: number;
			rejected: number;
			by_step: Record<'incharge' | 'hod', Stats>;
		};
		waitlist: { count: number; converted: number; conversion_pct: number; outcomes: Count[] };
		equipment: {
			count: number;
			by_venue: Count[];
			out_of_service: { venue: string; item: string; status: string; since: string | null }[];
			rows: {
				date: string;
				venue: string;
				item: string;
				status: string;
				reported_by: string;
				via: string;
			}[];
		};
	};

	const PRESETS = [
		{ key: 'term', label: 'Term so far' },
		{ key: '30', label: 'Last 30 days' },
		{ key: 'month', label: 'This month' },
		{ key: 'last-month', label: 'Last month' },
		{ key: 'custom', label: 'Choose dates' }
	];
	const SERIES = [
		{ key: 'class', label: 'Classes', color: 'var(--series-1)' },
		{ key: 'event', label: 'Events', color: 'var(--series-2)' }
	];
	const STEP = { incharge: 'Venue in-charge', hod: 'HOD' };

	const params = page.url.searchParams;
	let preset = $state(params.get('start') ? 'custom' : 'term');
	let start = $state(params.get('start') ?? '');
	let end = $state(params.get('end') ?? '');
	let report = $state<Report | null>(null);
	let error = $state('');
	let loading = $state(false);
	let view = $state<'chart' | 'table'>('chart');

	function rangeFor(key: string): [string, string] | null {
		const today = isoDate(new Date());
		const [y, m] = today.split('-').map(Number);
		if (key === '30') return [addDays(today, -29), today];
		if (key === 'month') return [isoDate(new Date(y, m - 1, 1)), today];
		if (key === 'last-month')
			return [isoDate(new Date(y, m - 2, 1)), isoDate(new Date(y, m - 1, 0))];
		return null;
	}

	function query(): string {
		return start && end ? `?start=${start}&end=${end}` : '';
	}

	async function load() {
		loading = true;
		error = '';
		try {
			report = await api<Report>(`/reports/summary${query()}`);
			if (!start) [start, end] = [report.from, report.to];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the reports';
		} finally {
			loading = false;
		}
	}

	function choose(key: string) {
		preset = key;
		const range = rangeFor(key);
		if (key === 'term') [start, end] = ['', ''];
		else if (range) [start, end] = range;
		if (key !== 'custom') apply();
	}

	function apply() {
		replaceState(`/reports${query()}`, {});
		load();
	}

	$effect(() => {
		if (session.user) untrack(load);
	});

	const pretty = (iso: string) =>
		new Date(iso.slice(0, 10) + 'T00:00').toLocaleDateString('en-IN', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	const monthName = (ym: string) =>
		new Date(ym + '-01T00:00').toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
	const hours = (h: number | null) =>
		h === null ? '–' : h < 48 ? `${h} h` : `${Math.round((h / 24) * 10) / 10} days`;
	const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
	const csv = (section: string) => `/api/reports/${section}.csv${query()}`;

	const useRows = $derived<BarRow[]>(
		(report?.utilisation.venues ?? [])
			.toSorted((a, b) => b.used_pct - a.used_pct || a.venue.localeCompare(b.venue))
			.map((v) => ({
				label: v.venue,
				href: `/venues/${v.venue}`,
				segments: [
					{ key: 'class', value: v.class_pct, tip: `classes ${v.class_pct}% (${v.class_hours} h)` },
					{ key: 'event', value: v.event_pct, tip: `events ${v.event_pct}% (${v.event_hours} h)` }
				],
				total: `${v.used_pct}% used`
			}))
	);
	const typeRows = $derived<BarRow[]>(foldOther(report?.events.by_type ?? [], 8));
	const deptRows = $derived<BarRow[]>(foldOther(report?.events.by_department ?? [], 6));
	const monthMax = $derived(Math.max(1, ...(report?.events.by_month ?? []).map((m) => m.count)));

	function foldOther(counts: Count[], keep: number): BarRow[] {
		const top = counts.slice(0, keep);
		const rest = counts.slice(keep).reduce((n, c) => n + c.count, 0);
		const all = rest ? [...top, { name: 'Other', count: rest }] : top;
		return all.map((c) => ({
			label: c.name,
			segments: [{ key: 'n', value: c.count, tip: `${c.count}` }],
			total: String(c.count)
		}));
	}
	const maxOf = (rows: BarRow[]) => Math.max(1, ...rows.map((r) => r.segments[0]?.value ?? 0));
</script>

<h1 class="text-2xl font-semibold">Reports</h1>
{#if !session.user}
	<p class="mt-6 {card}">
		Please <a class="text-accent underline" href="/login">log in</a> to see reports.
	</p>
{:else}
	<p class="mt-2 text-muted">
		{#if report}{report.scope} · {pretty(report.from)} to {pretty(
				report.to
			)}{#if report.period_label}
				{` (${report.period_label})`}{/if}{:else}How the venues are used, and how bookings are
			handled.{/if}
	</p>

	<div class="mt-5 flex flex-wrap items-end gap-3">
		<div role="group" aria-label="Period" class="flex flex-wrap gap-2">
			{#each PRESETS as p (p.key)}
				<button
					class="rounded-full border px-3.5 py-1.5 text-sm font-medium {preset === p.key
						? 'border-accent bg-accent-soft text-accent'
						: 'border-border hover:bg-surface-2'}"
					aria-pressed={preset === p.key}
					onclick={() => choose(p.key)}>{p.label}</button
				>
			{/each}
		</div>
		{#if preset === 'custom'}
			<form
				class="flex flex-wrap items-end gap-2"
				onsubmit={(e) => {
					e.preventDefault();
					apply();
				}}
			>
				<label class="text-sm"
					><span class="mb-1 block font-medium">From</span>
					<input type="date" required bind:value={start} class="{field} py-1.5" /></label
				>
				<label class="text-sm"
					><span class="mb-1 block font-medium">To</span>
					<input type="date" required bind:value={end} min={start} class="{field} py-1.5" /></label
				>
				<button class="{btnPrimary} py-2">Show</button>
			</form>
		{/if}
	</div>

	{#if error}
		<div class="mt-6 {card} border-danger/40" role="alert">
			<p class="font-medium text-danger">{error}</p>
			<button class="{btnSecondary} mt-3" onclick={load}>Try again</button>
		</div>
	{:else if !report}
		<p class="mt-8 text-muted" aria-live="polite">Loading reports…</p>
	{:else}
		{@const t = report.turnaround}
		{@const w = report.waitlist}
		<div aria-busy={loading} class={loading ? 'opacity-60' : ''}>
			<dl class="mt-6 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
				<div class="glass rounded-2xl border p-4">
					<dt class="text-sm text-muted">Venues in use</dt>
					<dd class="text-2xl font-semibold">{report.utilisation.total.used_pct}%</dd>
					<dd class="text-sm text-muted">of open hours</dd>
				</div>
				<div class="glass rounded-2xl border p-4">
					<dt class="text-sm text-muted">Events</dt>
					<dd class="text-2xl font-semibold">{report.events.count}</dd>
					<dd class="text-sm text-muted">{report.utilisation.total.event_hours} hours</dd>
				</div>
				<div class="glass rounded-2xl border p-4">
					<dt class="text-sm text-muted">Typical approval</dt>
					<dd class="text-2xl font-semibold">{hours(t.median_hours)}</dd>
					<dd class="text-sm text-muted">median per step</dd>
				</div>
				<div class="glass rounded-2xl border p-4">
					<dt class="text-sm text-muted">Waitlist</dt>
					<dd class="text-2xl font-semibold">{w.converted} of {w.count}</dd>
					<dd class="text-sm text-muted">got the venue</dd>
				</div>
				<div class="glass rounded-2xl border p-4">
					<dt class="text-sm text-muted">Equipment out</dt>
					<dd class="text-2xl font-semibold">{report.equipment.out_of_service.length}</dd>
					<dd class="text-sm text-muted">{plural(report.equipment.count, 'fault')} reported</dd>
				</div>
			</dl>

			<!-- Utilisation -->
			<section class="mt-8 {card}" aria-labelledby="use-h">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<h2 id="use-h" class="text-lg font-semibold">Venue utilisation</h2>
					<div class="flex gap-2">
						<div role="group" aria-label="Show as" class="flex rounded-lg border border-border">
							{#each ['chart', 'table'] as const as v (v)}
								<button
									class="px-3 py-1.5 text-sm font-medium first:rounded-l-lg last:rounded-r-lg {view ===
									v
										? 'bg-accent-soft text-accent'
										: 'hover:bg-surface-2'}"
									aria-pressed={view === v}
									onclick={() => (view = v)}>{v === 'chart' ? 'Chart' : 'Table'}</button
								>
							{/each}
						</div>
						<a
							class="{btnSecondary} flex items-center gap-1.5 py-1.5 text-sm"
							href={csv('utilisation')}
							download><Icon name="download" size={16} />CSV</a
						>
					</div>
				</div>
				<p class="mt-1 text-sm text-muted">
					Share of open hours (08:00–18:00 weekdays, 08:00–17:00 Saturdays) taken by timetabled
					classes and by confirmed bookings or past events. Closed days are left out.
				</p>
				{#if report.utilisation.total.open_hours === 0}
					<p class="mt-4 text-muted">The venues were not open in this period.</p>
				{:else if view === 'chart'}
					<div class="mt-4">
						<BarChart rows={useRows} series={SERIES} max={100} label="Utilisation by venue" />
					</div>
				{:else}
					<div class="mt-4 overflow-x-auto">
						<table class="w-full text-left text-sm">
							<caption class="sr-only">Utilisation by venue</caption>
							<thead class="text-muted">
								<tr class="border-b border-border">
									<th scope="col" class="py-2 pr-3 font-medium">Venue</th>
									<th scope="col" class="py-2 pr-3 text-right font-medium">Open h</th>
									<th scope="col" class="py-2 pr-3 text-right font-medium">Classes h</th>
									<th scope="col" class="py-2 pr-3 text-right font-medium">Events h</th>
									<th scope="col" class="py-2 pr-3 text-right font-medium">Free h</th>
									<th scope="col" class="py-2 text-right font-medium">Used</th>
								</tr>
							</thead>
							<tbody class="tabular-nums">
								{#each report.utilisation.venues as v (v.venue)}
									<tr class="border-b border-border/60">
										<th scope="row" class="py-2 pr-3 font-medium"
											>{v.venue}{#if v.closed_hours}<span class="font-normal text-muted">
													· closed {v.closed_hours} h</span
												>{/if}</th
										>
										<td class="py-2 pr-3 text-right">{v.open_hours}</td>
										<td class="py-2 pr-3 text-right">{v.class_hours}</td>
										<td class="py-2 pr-3 text-right">{v.event_hours}</td>
										<td class="py-2 pr-3 text-right">{v.free_hours}</td>
										<td class="py-2 text-right">{v.used_pct}%</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>

			<!-- Events -->
			<section class="mt-6 {card}" aria-labelledby="events-h">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<h2 id="events-h" class="text-lg font-semibold">Events</h2>
					<a
						class="{btnSecondary} flex items-center gap-1.5 py-1.5 text-sm"
						href={csv('events')}
						download><Icon name="download" size={16} />CSV</a
					>
				</div>
				<p class="mt-1 text-sm text-muted">
					Confirmed bookings and past events from circulars and reports, in these venues.
				</p>
				{#if report.events.count === 0}
					<p class="mt-4 text-muted">No events in this period.</p>
				{:else}
					<h3 class="mt-5 font-medium">By month</h3>
					<div
						class="mt-3 flex h-40 items-end gap-2 border-b border-border"
						role="img"
						aria-label={report.events.by_month
							.map((m) => `${monthName(m.month)}: ${m.count}`)
							.join(', ')}
					>
						{#each report.events.by_month as m (m.month)}
							<div class="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
								<span class="text-sm tabular-nums">{m.count}</span>
								<span
									class="w-full max-w-12 rounded-t-[4px] bg-series-1"
									style="height: {(100 * m.count) / monthMax}%"
									title="{monthName(m.month)}: {m.count} events"
								></span>
							</div>
						{/each}
					</div>
					<div class="mt-1 flex gap-2" aria-hidden="true">
						{#each report.events.by_month as m (m.month)}
							<span class="min-w-0 flex-1 truncate text-center text-xs text-muted"
								>{monthName(m.month)}</span
							>
						{/each}
					</div>
					<div class="mt-6 grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-8">
						<div>
							<h3 class="mb-3 font-medium">By type</h3>
							<BarChart
								rows={typeRows}
								series={[{ key: 'n', label: 'Events', color: 'var(--series-1)' }]}
								max={maxOf(typeRows)}
								label="Events by type"
							/>
						</div>
						<div>
							<h3 class="mb-3 font-medium">By department</h3>
							<BarChart
								rows={deptRows}
								series={[{ key: 'n', label: 'Events', color: 'var(--series-1)' }]}
								max={maxOf(deptRows)}
								label="Events by department"
							/>
						</div>
					</div>
					<details class="mt-6">
						<summary class="cursor-pointer font-medium text-accent">
							List all {report.events.count} events
						</summary>
						<div class="mt-3 max-h-96 overflow-auto">
							<table class="w-full text-left text-sm">
								<thead class="sticky top-0 bg-glass-strong backdrop-blur-md text-muted">
									<tr class="border-b border-border">
										<th scope="col" class="py-2 pr-3 font-medium">Date</th>
										<th scope="col" class="py-2 pr-3 font-medium">Event</th>
										<th scope="col" class="py-2 pr-3 font-medium">Type</th>
										<th scope="col" class="py-2 pr-3 font-medium">Venue</th>
										<th scope="col" class="py-2 font-medium">Source</th>
									</tr>
								</thead>
								<tbody>
									{#each report.events.rows as e, i (i)}
										<tr class="border-b border-border/60 align-top">
											<td class="py-2 pr-3 whitespace-nowrap">{pretty(e.date)}</td>
											<td class="py-2 pr-3">{e.title}</td>
											<td class="py-2 pr-3">{e.event_type}</td>
											<td class="py-2 pr-3">{e.venues}</td>
											<td class="py-2 text-muted">{e.ref ?? e.source}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</details>
				{/if}
			</section>

			<div class="mt-6 grid grid-cols-[repeat(auto-fit,minmax(20rem,1fr))] gap-6">
				<!-- Turnaround -->
				<section class={card} aria-labelledby="turn-h">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<h2 id="turn-h" class="text-lg font-semibold">Approval turnaround</h2>
						<a
							class="{btnSecondary} flex items-center gap-1.5 py-1.5 text-sm"
							href={csv('turnaround')}
							download><Icon name="download" size={16} />CSV</a
						>
					</div>
					{#if t.count === 0}
						<p class="mt-4 text-muted">No approval decisions in this period.</p>
					{:else}
						<p class="mt-2">
							{t.count} decisions ({t.approved} approved, {t.rejected} rejected).
							{Math.round((100 * t.within_a_day) / t.count)}% were made within a day.
						</p>
						<div class="mt-4 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<caption class="sr-only">Time taken per approval step</caption>
								<thead class="text-muted">
									<tr class="border-b border-border">
										<th scope="col" class="py-2 pr-3 font-medium">Step</th>
										<th scope="col" class="py-2 pr-3 text-right font-medium">Decisions</th>
										<th scope="col" class="py-2 pr-3 text-right font-medium">Median</th>
										<th scope="col" class="py-2 text-right font-medium">Average</th>
									</tr>
								</thead>
								<tbody class="tabular-nums">
									{#each Object.entries(t.by_step).filter(([, x]) => x.count) as [step, s] (step)}
										<tr class="border-b border-border/60">
											<th scope="row" class="py-2 pr-3 font-medium">{STEP[step as 'hod']}</th>
											<td class="py-2 pr-3 text-right">{s.count}</td>
											<td class="py-2 pr-3 text-right">{hours(s.median_hours)}</td>
											<td class="py-2 text-right">{hours(s.average_hours)}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
						<p class="mt-3 text-sm text-muted">
							Counted from when the request reached that person. Steps people approve for themselves
							are left out.
						</p>
					{/if}
				</section>

				<!-- Waitlist -->
				<section class={card} aria-labelledby="wait-h">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<h2 id="wait-h" class="text-lg font-semibold">Waitlist</h2>
						<a
							class="{btnSecondary} flex items-center gap-1.5 py-1.5 text-sm"
							href={csv('waitlist')}
							download><Icon name="download" size={16} />CSV</a
						>
					</div>
					{#if w.count === 0}
						<p class="mt-4 text-muted">Nobody joined a waitlist in this period.</p>
					{:else}
						<p class="mt-2">
							{plural(w.count, 'request')} joined a waitlist; {w.converted} accepted an offer ({w.conversion_pct}%).
						</p>
						<ul class="mt-4 space-y-2">
							{#each w.outcomes as o (o.name)}
								<li class="flex justify-between border-b border-border/60 pb-2">
									<span>{o.name}</span><span class="tabular-nums">{o.count}</span>
								</li>
							{/each}
						</ul>
					{/if}
				</section>
			</div>

			<!-- Equipment -->
			<section class="mt-6 {card}" aria-labelledby="kit-h">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<h2 id="kit-h" class="text-lg font-semibold">Equipment faults</h2>
					<a
						class="{btnSecondary} flex items-center gap-1.5 py-1.5 text-sm"
						href={csv('equipment')}
						download><Icon name="download" size={16} />CSV</a
					>
				</div>
				<div class="mt-4 grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-8">
					<div>
						<h3 class="font-medium">Out of service now</h3>
						{#if report.equipment.out_of_service.length === 0}
							<p class="mt-2 text-muted">Everything is working.</p>
						{:else}
							<ul class="mt-2 space-y-2">
								{#each report.equipment.out_of_service as e (e.venue + e.item)}
									<li
										class="flex flex-wrap items-baseline justify-between gap-2 border-b border-border/60 pb-2"
									>
										<span
											><a
												class="font-medium hover:text-accent hover:underline"
												href="/venues/{e.venue}">{e.venue}</a
											>
											· {e.item}</span
										>
										<span class="text-sm {e.status === 'faulty' ? 'text-danger' : 'text-warning'}"
											>{e.status === 'faulty' ? '✕ Faulty' : '⚠ Under repair'}{#if e.since}<span
													class="text-muted">{` since ${pretty(e.since)}`}</span
												>{/if}</span
										>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
					<div>
						<h3 class="font-medium">Faults reported in this period</h3>
						{#if report.equipment.count === 0}
							<p class="mt-2 text-muted">No faults were reported.</p>
						{:else}
							<ul class="mt-2 space-y-2">
								{#each report.equipment.rows.toReversed().slice(0, 8) as r, i (i)}
									<li class="border-b border-border/60 pb-2 text-sm">
										<span class="font-medium">{r.venue} · {r.item}</span>
										<span class="block text-muted"
											>{pretty(r.date)} · {r.status === 'faulty' ? 'faulty' : 'under repair'} · {r.reported_by}{r.via ===
											'Assistant'
												? ' (via the assistant)'
												: ''}</span
										>
									</li>
								{/each}
							</ul>
							{#if report.equipment.count > 8}
								<p class="mt-2 text-sm text-muted">The CSV has all {report.equipment.count}.</p>
							{/if}
						{/if}
					</div>
				</div>
			</section>
		</div>
	{/if}
{/if}

<script lang="ts">
	import type { DayAvailability, VenueDay } from '#lib/types.ts';
	import { hhmm, minutesOf, minutesOnDay } from '#lib/time.ts';

	let {
		data,
		from = null,
		to = null,
		bookHref = null
	}: {
		data: DayAvailability;
		from?: string | null;
		to?: string | null;
		/** When set, each venue gets a "Book" link. */
		bookHref?: ((code: string) => string) | null;
	} = $props();

	const open = $derived(data.open_from ? minutesOf(data.open_from) : 480);
	const close = $derived(data.open_to ? minutesOf(data.open_to) : 1080);
	const slots = $derived(
		Array.from(
			{ length: (close - open) / data.slot_minutes },
			(_, i) => open + i * data.slot_minutes
		)
	);

	type Cell = { state: string; label: string };

	function cellsFor(v: VenueDay): Cell[] {
		return slots.map((s) => {
			const e = s + data.slot_minutes;
			const here = v.blocks.filter(
				(b) => minutesOnDay(b.start, data.date) < e && s < minutesOnDay(b.end, data.date)
			);
			const block = here.find((b) => b.hard) ?? here[0];
			return block ? { state: block.kind, label: block.label } : { state: 'free', label: 'Free' };
		});
	}

	const STATE_CLASS: Record<string, string> = {
		free: 'bg-success/15',
		status: 'bg-danger/35',
		seasonal: 'bg-warning/40',
		closed: 'bg-muted/25',
		class: 'bg-accent/40',
		booking: 'bg-fg/45',
		pending: 'bg-warning/60'
	};

	function span(b: { start: string; end: string }) {
		const s = minutesOnDay(b.start, data.date);
		const e = minutesOnDay(b.end, data.date);
		return s === 0 && e === 1440 ? 'All day' : `${hhmm(s)}–${hhmm(e)}`;
	}

	function inWindow(slot: number) {
		if (!from || !to) return false;
		return slot >= minutesOf(from) && slot < minutesOf(to);
	}
</script>

<!-- Desktop / tablet: time grid -->
<div class="hidden overflow-x-auto rounded-xl border border-border bg-surface md:block">
	<table class="w-full border-collapse text-sm">
		<thead>
			<tr>
				<th
					class="sticky left-0 z-10 min-w-28 border-b border-border bg-surface px-4 py-3 text-left font-semibold"
					>Venue</th
				>
				{#each slots as s (s)}
					<th
						class="min-w-6 border-b border-border px-0 py-3 text-left text-xs font-normal text-muted {inWindow(
							s
						)
							? 'bg-accent-soft'
							: ''}"
					>
						{s % 60 === 0 ? hhmm(s).replace(/^0/, '') : ''}
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each data.venues as v (v.code)}
				<tr class="border-b border-border last:border-0">
					<th class="sticky left-0 z-10 bg-surface px-4 py-2 text-left font-normal">
						<a href="/venues/{v.code}" class="font-medium hover:text-accent">{v.code}</a>
						<span class="block text-xs text-muted">{v.capacity} seats{v.byod ? ' · BYOD' : ''}</span
						>
						{#if bookHref}
							<a href={bookHref(v.code)} class="text-xs font-medium text-accent hover:underline"
								>Book</a
							>
						{/if}
						{#each v.blocks.filter((b) => b.hard && span(b) === 'All day' && b.kind !== 'closed') as b, i (i)}
							<span class="block max-w-48 text-xs text-danger">{b.label}</span>
						{/each}
					</th>
					{#each cellsFor(v) as c, i (i)}
						<td class="p-0.5 {inWindow(slots[i]) ? 'bg-accent-soft' : ''}">
							<div
								class="h-9 rounded {STATE_CLASS[c.state] ?? 'bg-muted/25'}"
								title="{hhmm(slots[i])} · {c.label}"
							></div>
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<!-- Mobile: one card per venue -->
<ul class="space-y-3 md:hidden">
	{#each data.venues as v (v.code)}
		{@const hard = v.blocks}
		<li class="rounded-xl border border-border bg-surface p-4">
			<div class="flex items-baseline justify-between">
				<a href="/venues/{v.code}" class="font-semibold">{v.name}</a>
				<span class="text-sm text-muted">{v.capacity} seats</span>
			</div>
			{#if bookHref}
				<a href={bookHref(v.code)} class="text-sm font-medium text-accent">Book {v.code}</a>
			{/if}
			{#if hard.length === 0}
				<p class="mt-1 text-success">Free all day</p>
			{:else}
				<ul class="mt-1 space-y-0.5 text-sm">
					{#each hard as b, i (i)}
						<li>
							<span class="font-medium">{span(b)}</span>
							· {b.label}
						</li>
					{/each}
				</ul>
			{/if}
			<div class="mt-3 flex h-3 overflow-hidden rounded-full">
				{#each cellsFor(v) as c, i (i)}
					<div class="flex-1 {STATE_CLASS[c.state] ?? 'bg-muted/25'}"></div>
				{/each}
			</div>
		</li>
	{/each}
</ul>

<div class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
	{#each [['free', 'Free'], ['class', 'Class'], ['booking', 'Booked'], ['pending', 'Awaiting approval'], ['status', 'Maintenance / closed'], ['seasonal', 'Reserved for the season'], ['closed', 'College closed']] as [k, label] (k)}
		<span class="flex items-center gap-2"
			><span class="inline-block h-4 w-4 rounded {STATE_CLASS[k]}"></span>{label}</span
		>
	{/each}
</div>

<script lang="ts" module>
	export type GridItem = {
		/** Minutes since midnight. */
		start: number;
		end: number;
		title: string;
		detail?: string;
		/** Block kind: class, booking, pending, status, seasonal, closed. */
		kind: string;
		href?: string;
	};

	export type GridRow = {
		key: string;
		label: string;
		sub?: string;
		/** Greyed out with this note, e.g. "Closed". */
		closed?: string | null;
		highlight?: boolean;
		items: GridItem[];
	};

	export const KIND_STYLE: Record<string, string> = {
		class: 'border-accent bg-accent/12',
		booking: 'border-series-2 bg-series-2/15',
		pending: 'border-warning border-dashed bg-warning/12',
		status: 'border-danger bg-danger/12',
		seasonal: 'border-warning bg-warning/15',
		closed: 'border-muted bg-muted/15'
	};

	export const KIND_LABEL: Record<string, string> = {
		class: 'Class',
		booking: 'Booked',
		pending: 'Awaiting approval',
		status: 'Maintenance or closure',
		seasonal: 'Reserved season'
	};
</script>

<script lang="ts">
	import { hhmm } from '#lib/time.ts';

	let {
		rows,
		from = 480,
		to = 1080,
		label
	}: { rows: GridRow[]; from?: number; to?: number; label: string } = $props();

	const hours = $derived(
		Array.from({ length: Math.floor((to - from) / 60) + 1 }, (_, i) => from + i * 60)
	);

	function pct(m: number) {
		return ((Math.min(Math.max(m, from), to) - from) / (to - from)) * 100;
	}

	/** Put overlapping items on separate lanes. */
	function lanes(items: GridItem[]) {
		const sorted = items
			.filter((i) => i.end > from && i.start < to)
			.sort((a, b) => a.start - b.start || b.end - a.end);
		const ends: number[] = [];
		const placed = sorted.map((item) => {
			let lane = ends.findIndex((e) => e <= item.start);
			if (lane < 0) lane = ends.push(0) - 1;
			ends[lane] = item.end;
			return { item, lane };
		});
		return { placed, count: Math.max(ends.length, 1) };
	}

	function time(i: GridItem) {
		return i.start <= 0 && i.end >= 1440 ? 'All day' : `${hhmm(i.start)}–${hhmm(i.end)}`;
	}
</script>

<!-- Focusable so keyboard users can scroll it sideways on small screens. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="glass overflow-x-auto rounded-2xl border" role="region" aria-label={label} tabindex="0">
	<div class="min-w-[44rem]">
		<div class="flex h-8 border-b border-border text-xs text-muted">
			<div class="w-24 shrink-0 px-3 py-2 font-medium">&nbsp;</div>
			<div class="relative mr-4 flex-1">
				{#each hours as h, i (h)}
					<span
						class="absolute top-2 {i === 0
							? ''
							: i === hours.length - 1
								? '-translate-x-full'
								: '-translate-x-1/2'}"
						style="left: {pct(h)}%">{hhmm(h).replace(/^0/, '')}</span
					>
				{/each}
			</div>
		</div>
		{#each rows as row (row.key)}
			{@const l = lanes(row.items)}
			<div
				class="flex border-b border-border last:border-0 {row.highlight ? 'bg-accent-soft/60' : ''}"
				data-row={row.key}
			>
				<div class="w-24 shrink-0 px-3 py-2">
					<div class="font-semibold">{row.label}</div>
					{#if row.sub}<div class="text-xs text-muted">{row.sub}</div>{/if}
				</div>
				<div class="relative mr-4 flex-1" style="height: {Math.max(l.count * 3.25, 3.5)}rem">
					{#each hours as h (h)}
						<span
							class="absolute inset-y-0 border-l border-border/70"
							style="left: {pct(h)}%"
							aria-hidden="true"
						></span>
					{/each}
					{#if row.closed}
						<div
							class="absolute inset-1 grid place-items-center rounded-lg bg-muted/10 text-sm text-muted"
						>
							{row.closed}
						</div>
					{:else}
						{#each l.placed as { item, lane }, i (i)}
							{@const style = `left: calc(${pct(item.start)}% + 2px); width: calc(${pct(item.end) - pct(item.start)}% - 4px); top: calc(${lane * 3.25}rem + 0.25rem); height: 2.9rem`}
							{#if item.href}
								<a
									href={item.href}
									class="lift absolute overflow-hidden rounded-lg border-l-4 px-2 py-1 text-xs leading-tight {KIND_STYLE[
										item.kind
									] ?? KIND_STYLE.closed}"
									{style}
									title="{time(item)} · {item.title}{item.detail ? ` · ${item.detail}` : ''}"
								>
									<span class="block truncate font-semibold">{item.title}</span>
									<span class="block truncate"
										>{time(item)}{item.detail ? ` · ${item.detail}` : ''}</span
									>
								</a>
							{:else}
								<div
									class="absolute overflow-hidden rounded-lg border-l-4 px-2 py-1 text-xs leading-tight {KIND_STYLE[
										item.kind
									] ?? KIND_STYLE.closed}"
									{style}
									title="{time(item)} · {item.title}{item.detail ? ` · ${item.detail}` : ''}"
								>
									<span class="block truncate font-semibold">{item.title}</span>
									<span class="block truncate"
										>{time(item)}{item.detail ? ` · ${item.detail}` : ''}</span
									>
								</div>
							{/if}
						{/each}
					{/if}
				</div>
			</div>
		{/each}
	</div>
</div>

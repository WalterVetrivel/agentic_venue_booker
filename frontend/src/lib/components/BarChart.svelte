<script lang="ts" module>
	export type Segment = { key: string; value: number; tip: string };
	export type BarRow = { label: string; href?: string; segments: Segment[]; total: string };
	export type Series = { key: string; label: string; color: string };
</script>

<script lang="ts">
	/**
	 * Horizontal bars, stacked when a row has several segments. The bars are a picture of the
	 * numbers next to them (and of the table view), so screen readers get the text, not the shapes.
	 */
	let {
		rows,
		series,
		max,
		label
	}: { rows: BarRow[]; series: Series[]; max: number; label: string } = $props();

	const color = (key: string) => series.find((s) => s.key === key)?.color ?? 'var(--series-1)';
	let tip = $state<{ text: string; x: number; y: number } | null>(null);
	let box: HTMLElement;

	function show(e: PointerEvent, text: string) {
		const r = box.getBoundingClientRect();
		tip = { text, x: e.clientX - r.left, y: e.clientY - r.top };
	}
</script>

<div class="relative" bind:this={box}>
	{#if series.length > 1}
		<ul class="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted" aria-label="Legend">
			{#each series as s (s.key)}
				<li class="flex items-center gap-2">
					<span class="inline-block h-3 w-3 rounded-sm" style="background: {s.color}"></span>
					{s.label}
				</li>
			{/each}
		</ul>
	{/if}
	<ul class="space-y-2" aria-label={label}>
		{#each rows as row (row.label)}
			<li class="grid grid-cols-[minmax(4.5rem,8rem)_minmax(4rem,1fr)_auto] items-center gap-3">
				<span class="truncate font-medium">
					{#if row.href}<a class="hover:text-accent hover:underline" href={row.href}>{row.label}</a
						>{:else}{row.label}{/if}
				</span>
				<span class="flex h-4 gap-[2px] rounded-sm bg-surface-2" aria-hidden="true">
					{#each row.segments.filter((s) => s.value > 0) as s, i (s.key)}
						<span
							role="presentation"
							class="h-full {i === row.segments.filter((x) => x.value > 0).length - 1
								? 'rounded-r-[4px]'
								: ''}"
							style="width: {max ? (100 * s.value) / max : 0}%; background: {color(s.key)}"
							onpointermove={(e) => show(e, `${row.label}: ${s.tip}`)}
							onpointerleave={() => (tip = null)}
						></span>
					{/each}
				</span>
				<span class="min-w-[2ch] text-right text-sm tabular-nums">{row.total}</span>
			</li>
		{/each}
	</ul>
	{#if tip}
		<div
			class="pointer-events-none absolute z-10 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm whitespace-nowrap shadow-lg"
			style="left: {tip.x + 12}px; top: {tip.y - 36}px"
			aria-hidden="true"
		>
			{tip.text}
		</div>
	{/if}
</div>

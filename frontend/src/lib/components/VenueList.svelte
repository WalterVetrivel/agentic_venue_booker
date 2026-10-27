<script lang="ts">
	import { api } from '#lib/api.ts';
	import { VENUE_TYPE_LABELS, type Venue } from '#lib/types.ts';

	const venues = api<Venue[]>('/venues');
	const order: Venue['type'][] = ['lab', 'coe', 'seminar_hall'];
</script>

{#await venues}
	<p class="text-muted">Loading venues…</p>
{:then list}
	{#each order as type (type)}
		<section class="mt-8">
			<h2 class="text-lg font-semibold">{VENUE_TYPE_LABELS[type]}</h2>
			<div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each list.filter((v) => v.type === type) as v (v.id)}
					<a
						href="/venues/{v.code}"
						class="block rounded-xl border border-border bg-surface p-5 transition hover:border-accent"
					>
						<div class="flex items-baseline justify-between gap-2">
							<span class="font-semibold">{v.name}</span>
							<span class="text-sm text-muted">{v.code}</span>
						</div>
						<div class="mt-2 flex flex-wrap gap-2 text-sm">
							<span class="rounded-full bg-surface-2 px-2.5 py-0.5">{v.capacity} seats</span>
							{#if v.byod}<span class="rounded-full bg-surface-2 px-2.5 py-0.5">BYOD</span>{/if}
							{#if v.block}<span class="rounded-full bg-surface-2 px-2.5 py-0.5">{v.block}</span
								>{/if}
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/each}
{:catch e}
	<p class="text-danger">Couldn't load venues: {e.message}</p>
{/await}

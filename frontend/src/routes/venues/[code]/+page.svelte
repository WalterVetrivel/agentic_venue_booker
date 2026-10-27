<script lang="ts">
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import type { Equipment, VenueDetail } from '#lib/types.ts';

	const venue = $derived(api<VenueDetail>(`/venues/${page.params.code}`));
	const groups: [Equipment['category'], string][] = [
		['software', 'Software'],
		['hardware', 'Hardware'],
		['av', 'Audio-visual'],
		['facility', 'Facilities']
	];
</script>

<a href="/venues" class="text-accent">← All venues</a>
{#await venue}
	<p class="mt-6 text-muted">Loading…</p>
{:then v}
	<h1 class="mt-4 text-2xl font-semibold">{v.name} <span class="text-muted">({v.code})</span></h1>
	<dl class="mt-6 grid gap-4 rounded-xl border border-border bg-surface p-6 sm:grid-cols-2">
		<div><dt class="text-sm text-muted">Capacity</dt><dd class="font-medium">{v.capacity}</dd></div>
		<div><dt class="text-sm text-muted">Location</dt><dd class="font-medium">{v.block ?? '—'}</dd></div>
		<div>
			<dt class="text-sm text-muted">In-charge</dt>
			<dd class="font-medium">{v.in_charge?.name ?? '—'}</dd>
		</div>
		<div>
			<dt class="text-sm text-muted">Approval</dt>
			<dd class="font-medium">In-charge{v.needs_hod_approval ? ', then HOD' : ''}</dd>
		</div>
	</dl>
	{#each groups as [cat, label] (cat)}
		{@const items = v.equipment.filter((e) => e.category === cat)}
		{#if items.length}
			<h2 class="mt-8 text-lg font-semibold">{label}</h2>
			<ul class="mt-3 grid gap-2 sm:grid-cols-2">
				{#each items as e (e.id)}
					<li class="flex justify-between rounded-lg border border-border bg-surface px-4 py-2.5">
						<span>{e.name}</span>
						<span class="shrink-0 text-sm whitespace-nowrap text-muted">{e.quantity > 1 ? `× ${e.quantity}` : ''}</span>
					</li>
				{/each}
			</ul>
		{/if}
	{/each}
{:catch e}
	<p class="mt-6 text-danger">{e.message}</p>
{/await}

<script lang="ts">
	import ViewToggle, { savedView } from './ViewToggle.svelte';
	import WeekGrid, { type GridRow } from './WeekGrid.svelte';
	import { minutesOf } from '#lib/time.ts';
	import { WEEKDAYS, type ClassSlot } from '#lib/types.ts';

	let { slots, show }: { slots: ClassSlot[]; show: 'venue' | 'section' } = $props();
	const days = $derived(WEEKDAYS.filter((d) => slots.some((s) => s.weekday === d)));
	let view = $state(savedView('schedule', ['grid', 'cards'] as const, 'grid'));

	function detail(s: ClassSlot) {
		return `${s.subject_name}${s.batch !== 'all' ? ` (${s.batch})` : ''}${s.faculty_name ? ` · ${s.faculty_name}` : ''}`;
	}

	const rows = $derived(
		WEEKDAYS.map((day): GridRow => ({
			key: day,
			label: day,
			items: slots
				.filter((s) => s.weekday === day)
				.map((s) => ({
					start: minutesOf(s.start.slice(0, 5)),
					end: minutesOf(s.end.slice(0, 5)),
					title: show === 'venue' ? s.section : s.venue,
					detail: detail(s),
					kind: 'class',
					href: show === 'section' ? `/venues/${encodeURIComponent(s.venue)}` : undefined
				}))
		}))
	);

	const hours = $derived.by(() => {
		let from = 480;
		let to = 1020;
		for (const s of slots) {
			from = Math.min(from, Math.floor(minutesOf(s.start.slice(0, 5)) / 60) * 60);
			to = Math.max(to, Math.ceil(minutesOf(s.end.slice(0, 5)) / 60) * 60);
		}
		return { from, to };
	});
</script>

{#if slots.length === 0}
	<p class="mt-2 text-muted">No classes are timetabled here.</p>
{:else}
	<div class="mt-3 flex justify-end">
		<ViewToggle
			bind:value={view}
			key="schedule"
			label="Schedule view"
			options={[
				{ value: 'grid', label: 'Grid', icon: 'table' },
				{ value: 'cards', label: 'Cards', icon: 'list' }
			]}
		/>
	</div>
	{#if view === 'grid'}
		<div class="mt-3">
			<WeekGrid
				{rows}
				from={hours.from}
				to={hours.to}
				label={show === 'venue' ? 'Weekly class timetable' : 'Weekly lab timetable'}
			/>
		</div>
	{:else}
		<div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each days as day (day)}
				<div class="glass rounded-2xl border p-4">
					<h3 class="font-semibold">{day}</h3>
					<ul class="mt-2 space-y-2">
						{#each slots.filter((s) => s.weekday === day) as s (s.id)}
							<li class="text-sm">
								<span class="font-medium">{s.start.slice(0, 5)}–{s.end.slice(0, 5)}</span>
								· {show === 'venue' ? s.section : s.venue}
								<span class="block text-muted">{detail(s)}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>
	{/if}
{/if}

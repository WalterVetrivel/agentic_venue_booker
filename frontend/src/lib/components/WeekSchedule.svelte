<script lang="ts">
	import { WEEKDAYS, type ClassSlot } from '#lib/types.ts';

	let { slots, show }: { slots: ClassSlot[]; show: 'venue' | 'section' } = $props();
	const days = $derived(WEEKDAYS.filter((d) => slots.some((s) => s.weekday === d)));
</script>

{#if slots.length === 0}
	<p class="mt-2 text-muted">No classes are timetabled here.</p>
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
							<span class="block text-muted"
								>{s.subject_name}{s.batch !== 'all' ? ` (${s.batch})` : ''}{s.faculty_name
									? ` · ${s.faculty_name}`
									: ''}</span
							>
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>
{/if}

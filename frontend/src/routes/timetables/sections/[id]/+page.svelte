<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import WeekSchedule from '#lib/components/WeekSchedule.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { btnSecondary } from '#lib/ui.ts';
	import type { ClassSlot, Section } from '#lib/types.ts';

	const id = $derived(Number((page.params as Record<string, string>).id));
	let section = $state<Section | null>(null);
	let slots = $state<ClassSlot[]>([]);

	$effect(() => {
		api<Section[]>('/timetables/sections').then((all) => {
			section = all.find((s) => s.id === id) ?? null;
			if (section) ui.crumb = section.label;
		});
		api<ClassSlot[]>(`/timetables/slots?section_id=${id}`).then((s) => (slots = s));
	});

	async function clear() {
		if (!confirm(`Remove all lab slots for ${section?.label}? You can upload the PDF again later.`))
			return;
		await api(`/timetables/sections/${id}`, { method: 'DELETE' });
		goto('/timetables');
	}
</script>

<div class="mt-4 flex flex-wrap items-start justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold">{section?.label ?? 'Class'} lab schedule</h1>
		{#if section?.advisor}<p class="mt-1 text-muted">Class advisor: {section.advisor}</p>{/if}
	</div>
	{#if session.can('upload_timetables') && slots.length}
		<button class={btnSecondary} onclick={clear}>Remove this timetable</button>
	{/if}
</div>
<WeekSchedule {slots} show="section" />

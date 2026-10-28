<script lang="ts">
	import type { Student } from '#lib/types.ts';

	let { students }: { students: Student[] } = $props();

	const TONE = {
		pending: 'bg-surface-2 text-muted',
		approved: 'bg-success/15 text-success',
		rejected: 'bg-danger/15 text-danger'
	};
	const LABEL = { pending: 'Waiting for guide', approved: 'Approved', rejected: 'Not approved' };
</script>

<ul class="divide-y divide-border">
	{#each students as s (s.id)}
		<li class="flex flex-wrap items-start justify-between gap-2 py-2">
			<span>
				<span class="font-medium">{s.name}</span>
				<span class="text-muted">· {s.class_label}{s.register_no ? ` · ${s.register_no}` : ''}</span
				>
				{#if s.comment}<span class="block text-sm text-muted">“{s.comment}”</span>{/if}
			</span>
			<span class="rounded-full px-2.5 py-0.5 text-sm font-medium {TONE[s.decision]}"
				>{LABEL[s.decision]}</span
			>
		</li>
	{/each}
</ul>

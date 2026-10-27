<script lang="ts">
	import { STATUS_LABELS, STATUS_TONE } from '#lib/types.ts';

	let { status }: { status: string } = $props();
</script>

<span
	class="rounded-full px-2.5 py-0.5 text-sm font-medium whitespace-nowrap {STATUS_TONE[status] ??
		''}">{STATUS_LABELS[status] ?? status}</span
>

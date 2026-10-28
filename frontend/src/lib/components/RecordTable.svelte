<script lang="ts" module>
	export type RecordRow = {
		key: string | number;
		href: string;
		title: string;
		/** Small text under the title, e.g. the booking reference. */
		sub?: string;
		venue: string;
		when: string;
		extra?: string;
		/** A booking status (shown as a badge) ... */
		status?: string;
		/** ... or plain status text with an optional tone class. */
		statusText?: string;
		statusTone?: string;
	};
</script>

<script lang="ts">
	import StatusBadge from './StatusBadge.svelte';

	let {
		rows,
		label,
		extraLabel = '',
		statusLabel = 'Status'
	}: { rows: RecordRow[]; label: string; extraLabel?: string; statusLabel?: string } = $props();
</script>

<div class="glass overflow-x-auto rounded-2xl border">
	<table class="w-full min-w-[40rem] border-collapse text-left text-sm">
		<caption class="sr-only">{label}</caption>
		<thead class="text-muted">
			<tr class="border-b border-border">
				<th scope="col" class="px-4 py-3 font-medium">Title</th>
				<th scope="col" class="px-4 py-3 font-medium">Venue</th>
				<th scope="col" class="px-4 py-3 font-medium">Date and time</th>
				{#if extraLabel}<th scope="col" class="px-4 py-3 font-medium">{extraLabel}</th>{/if}
				<th scope="col" class="px-4 py-3 font-medium">{statusLabel}</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r.key)}
				<tr class="border-b border-border transition-colors last:border-0 hover:bg-glass-strong">
					<td class="px-4 py-3">
						<a href={r.href} class="font-medium hover:text-accent hover:underline">{r.title}</a>
						{#if r.sub}<span class="block text-xs text-muted">{r.sub}</span>{/if}
					</td>
					<td class="px-4 py-3 whitespace-nowrap">{r.venue}</td>
					<td class="px-4 py-3">{r.when}</td>
					{#if extraLabel}<td class="px-4 py-3">{r.extra ?? ''}</td>{/if}
					<td class="px-4 py-3">
						{#if r.status}
							<StatusBadge status={r.status} />
						{:else if r.statusText}
							<span
								class="rounded-full px-2.5 py-0.5 text-sm font-medium whitespace-nowrap {r.statusTone ??
									'bg-surface-2'}">{r.statusText}</span
							>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

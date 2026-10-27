<script lang="ts">
	import VenueList from '#lib/components/VenueList.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { btnPrimary } from '#lib/ui.ts';
</script>

<div class="flex flex-wrap items-start justify-between gap-4">
	<div>
		<h1 class="text-2xl font-semibold">Venues</h1>
		<p class="mt-2 text-muted">
			Labs, Centres of Excellence and seminar halls, with their equipment and software.
		</p>
	</div>
	{#if session.can('create_venue')}<a href="/venues/new" class={btnPrimary}>Add venue</a>{/if}
</div>
<VenueList />

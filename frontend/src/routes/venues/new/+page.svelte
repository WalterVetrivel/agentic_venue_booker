<script lang="ts">
	import { goto } from '$app/navigation';
	import VenueForm from '#lib/components/VenueForm.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { card } from '#lib/ui.ts';
</script>

<h1 class="mt-4 text-2xl font-semibold">Add a venue</h1>
{#if session.can('create_venue')}
	<div class="mt-6 {card}">
		<VenueForm
			restricted
			onsaved={(v) => goto(`/venues/${v.code}`)}
			oncancel={() => goto('/venues')}
		/>
	</div>
{:else}
	<p class="mt-6 {card}">Only the Director - Infrastructure Management can add venues.</p>
{/if}

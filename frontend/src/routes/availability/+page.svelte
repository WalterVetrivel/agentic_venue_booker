<script lang="ts">
	import VenueList from '#lib/components/VenueList.svelte';
</script>

<h1 class="text-2xl font-semibold">Availability</h1>
<div class="mt-6 rounded-xl border border-dashed border-border bg-surface p-6">
	<p class="text-sm font-medium tracking-wide text-accent uppercase">Coming in Phases 1 and 2</p>
	<p class="mt-2 text-muted">
		A day-by-time grid showing which venues are free, in class or booked. For now, here are all
		the venues.
	</p>
</div>
<VenueList />

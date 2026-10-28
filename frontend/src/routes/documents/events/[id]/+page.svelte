<script lang="ts">
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';
	import { dateRangeText } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { EventFacets, PastEvent, Venue } from '#lib/types.ts';

	const id = $derived((page.params as Record<string, string>).id);

	let event = $state<PastEvent | null>(null);
	let error = $state('');
	let editing = $state(false);
	let venues = $state<Venue[]>([]);
	let types = $state<string[]>([]);
	let saveError = $state('');
	let saving = $state(false);

	let form = $state({
		title: '',
		event_type: '',
		venue_codes: [] as string[],
		start_date: '',
		end_date: '',
		start_time: '',
		end_time: '',
		participants: null as number | null,
		resource_persons: ''
	});

	$effect(() => {
		if (!session.user) return;
		api<PastEvent>(`/events/${id}`)
			.then((e) => {
				event = e;
				ui.crumb = e.title;
			})
			.catch((e) => (error = e.message));
	});

	async function startEditing() {
		if (!event) return;
		if (!venues.length) {
			const [v, f] = await Promise.all([
				api<Venue[]>('/venues'),
				api<EventFacets>('/events/facets')
			]);
			venues = v;
			types = f.event_types;
		}
		form = {
			title: event.title,
			event_type: event.event_type,
			venue_codes: event.venues.map((v) => v.code),
			start_date: event.start_date ?? '',
			end_date: event.end_date ?? '',
			start_time: event.start_time?.slice(0, 5) ?? '',
			end_time: event.end_time?.slice(0, 5) ?? '',
			participants: event.participants,
			resource_persons: event.resource_persons ?? ''
		};
		saveError = '';
		editing = true;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		saveError = '';
		try {
			event = await api<PastEvent>(`/events/${id}`, {
				method: 'PUT',
				body: JSON.stringify({
					...form,
					end_date: form.end_date || null,
					start_time: form.start_time || null,
					end_time: form.end_time || null,
					resource_persons: form.resource_persons || null
				})
			});
			editing = false;
		} catch (err) {
			saveError = err instanceof Error ? err.message : 'Could not save';
		} finally {
			saving = false;
		}
	}

	function toggleVenue(code: string, on: boolean) {
		form.venue_codes = on
			? [...form.venue_codes, code]
			: form.venue_codes.filter((c) => c !== code);
	}

	const hm = (t: string | null) => t?.slice(0, 5) ?? '?';
</script>

{#if error}
	<p class="mt-6 text-danger">{error}</p>
{:else if !event}
	<p class="mt-6 text-muted">Loading…</p>
{:else}
	<h1 class="mt-2 text-2xl font-semibold">{event.title}</h1>
	<p class="mt-1 text-muted">
		{event.event_type}{event.department ? ` · ${event.department}` : ''}{event.edited
			? ' · corrected by hand'
			: ''}
	</p>

	{#if event.needs_review}
		<div class="mt-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3">
			<p class="font-medium">This event needs checking</p>
			<ul class="mt-1 text-sm">
				{#each event.problems as p, i (i)}<li>{p}</li>{/each}
			</ul>
		</div>
	{/if}

	{#if !editing}
		<dl class="mt-6 grid gap-x-8 gap-y-4 {card} sm:grid-cols-2">
			<div>
				<dt class="text-sm text-muted">When</dt>
				<dd>
					{dateRangeText(event.start_date, event.end_date)}{event.start_time
						? `, ${hm(event.start_time)}–${hm(event.end_time)}`
						: ''}
				</dd>
			</div>
			<div>
				<dt class="text-sm text-muted">Where</dt>
				<dd>
					{event.venues.map((v) => `${v.code} (${v.name})`).join(', ') || event.venue_text}
				</dd>
			</div>
			{#if event.audience}
				<div>
					<dt class="text-sm text-muted">For</dt>
					<dd>{event.audience}</dd>
				</div>
			{/if}
			{#if event.participants || event.expected_count}
				<div>
					<dt class="text-sm text-muted">Attendance</dt>
					<dd>
						{#if event.participants}{event.participants} attended{event.registered
								? ` (${event.registered} registered)`
								: ''}{:else}About {event.expected_count} expected{/if}
					</dd>
				</div>
			{/if}
			{#if event.resource_persons}
				<div class="sm:col-span-2">
					<dt class="text-sm text-muted">Resource persons</dt>
					<dd>{event.resource_persons}</dd>
				</div>
			{/if}
			{#if event.topics.length}
				<div class="sm:col-span-2">
					<dt class="text-sm text-muted">Topics</dt>
					<dd>{event.topics.join(', ')}</dd>
				</div>
			{/if}
			{#if event.rating}
				<div>
					<dt class="text-sm text-muted">Feedback</dt>
					<dd>{event.rating} / 5</dd>
				</div>
			{/if}
			<div class="sm:col-span-2">
				<dt class="text-sm text-muted">Documents</dt>
				<dd class="mt-1 flex flex-wrap gap-2">
					{#each [event.circular, event.report] as d (d?.id)}
						{#if d}
							<a href={d.file_url} target="_blank" rel="noopener" class={btnSecondary}
								>{d.kind === 'circular' ? 'Circular' : 'Report'} {d.ref_no ?? ''}</a
							>
						{/if}
					{/each}
					{#if !event.report}<span class="self-center text-sm text-muted">No report yet.</span>{/if}
				</dd>
			</div>
		</dl>
		{#if session.can('upload_documents')}
			<button class="mt-4 {btnPrimary}" onclick={startEditing}>Correct the details</button>
		{/if}
	{:else}
		<form class="mt-6 grid gap-4 {card} sm:grid-cols-2" onsubmit={save}>
			<div class="sm:col-span-2">
				<label class={label} for="t">Title</label>
				<input id="t" required minlength="3" bind:value={form.title} class={field} />
			</div>
			<div>
				<label class={label} for="ty">Type</label>
				<select id="ty" bind:value={form.event_type} class={field}>
					{#each types as t (t)}<option>{t}</option>{/each}
				</select>
			</div>
			<div>
				<label class={label} for="p">Attended</label>
				<input id="p" type="number" min="0" bind:value={form.participants} class={field} />
			</div>
			<div>
				<label class={label} for="sd">First day</label>
				<input id="sd" type="date" required bind:value={form.start_date} class={field} />
			</div>
			<div>
				<label class={label} for="ed">Last day</label>
				<input id="ed" type="date" min={form.start_date} bind:value={form.end_date} class={field} />
			</div>
			<div>
				<label class={label} for="st">Starts</label>
				<input id="st" type="time" bind:value={form.start_time} class={field} />
			</div>
			<div>
				<label class={label} for="et">Ends</label>
				<input id="et" type="time" bind:value={form.end_time} class={field} />
			</div>
			<fieldset class="sm:col-span-2">
				<legend class={label}>Venues</legend>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
					{#each venues as v (v.code)}
						<label class="flex items-center gap-2">
							<input
								type="checkbox"
								class="h-5 w-5"
								checked={form.venue_codes.includes(v.code)}
								onchange={(e) => toggleVenue(v.code, e.currentTarget.checked)}
							/>
							{v.code}
						</label>
					{/each}
				</div>
			</fieldset>
			<div class="sm:col-span-2">
				<label class={label} for="rp">Resource persons</label>
				<input id="rp" bind:value={form.resource_persons} class={field} />
			</div>
			{#if saveError}<p class="text-danger sm:col-span-2" role="alert">{saveError}</p>{/if}
			<div class="flex gap-3 sm:col-span-2">
				<button class={btnPrimary} disabled={saving}>Save</button>
				<button type="button" class={btnSecondary} onclick={() => (editing = false)}>Cancel</button>
			</div>
		</form>
	{/if}
{/if}

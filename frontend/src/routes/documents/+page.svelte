<script lang="ts">
	import RecordTable from '#lib/components/RecordTable.svelte';
	import ViewToggle, { savedView } from '#lib/components/ViewToggle.svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api, uploadFiles } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { dateRangeText } from '#lib/time.ts';
	import { btnDanger, btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type {
		DocumentInfo,
		EventFacets,
		PastEvent,
		SearchResult,
		UploadResult
	} from '#lib/types.ts';

	type Tab = 'search' | 'events' | 'documents';
	const tab = $derived((page.url.searchParams.get('tab') ?? 'search') as Tab);
	const canUpload = $derived(session.can('upload_documents'));

	let facets = $state<EventFacets | null>(null);

	// Search
	let query = $state(page.url.searchParams.get('q') ?? '');
	let kind = $state('');
	let result = $state<SearchResult | null>(null);
	let searching = $state(false);
	let searchError = $state('');

	// Past events
	let events = $state<PastEvent[]>([]);
	let title = $state('');
	let venue = $state(page.url.searchParams.get('venue') ?? '');
	let eventType = $state('');
	let year = $state('');
	let reviewOnly = $state(page.url.searchParams.get('review') === '1');
	let loadingEvents = $state(false);
	let layout = $state(savedView('events', ['cards', 'table'] as const, 'cards'));

	// Documents
	let documents = $state<DocumentInfo[]>([]);
	let uploads = $state<UploadResult[]>([]);
	let uploading = $state(false);
	let embedding = $state(false);

	function loadFacets() {
		api<EventFacets>('/events/facets').then((f) => (facets = f));
	}

	$effect(() => {
		if (session.user) loadFacets();
	});

	async function runSearch(e?: SubmitEvent) {
		e?.preventDefault();
		if (query.trim().length < 2) return;
		searching = true;
		searchError = '';
		try {
			const params = new URLSearchParams({ q: query.trim(), limit: '10' });
			if (kind) params.set('kind', kind);
			result = await api<SearchResult>(`/search?${params}`);
		} catch (err) {
			searchError = err instanceof Error ? err.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	// Run a search passed in the link (e.g. from the booking form) once.
	let initialSearchDone = false;
	$effect(() => {
		if (session.user && !initialSearchDone && query) {
			initialSearchDone = true;
			runSearch();
		}
	});

	$effect(() => {
		if (!session.user || tab !== 'events') return;
		const params = new URLSearchParams();
		if (title.trim()) params.set('q', title.trim());
		if (venue.trim()) params.set('venue', venue.trim());
		if (eventType) params.set('event_type', eventType);
		if (year) params.set('year', year);
		if (reviewOnly) params.set('needs_review', 'true');
		const timer = setTimeout(async () => {
			loadingEvents = true;
			events = await api<PastEvent[]>(`/events?${params}`);
			loadingEvents = false;
		}, 250);
		return () => clearTimeout(timer);
	});

	async function loadDocuments() {
		documents = await api<DocumentInfo[]>('/documents');
	}
	$effect(() => {
		if (session.user && tab === 'documents') loadDocuments();
	});

	async function onFiles(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		if (!files.length) return;
		uploading = true;
		uploads = [];
		try {
			// A few at a time keeps each request small and shows progress.
			for (let i = 0; i < files.length; i += 10) {
				uploads = [
					...uploads,
					...(await uploadFiles<UploadResult[]>('/documents', files.slice(i, i + 10)))
				];
			}
		} catch (err) {
			uploads = [
				...uploads,
				{
					filename: 'Upload',
					document: null,
					error: err instanceof Error ? err.message : 'Failed',
					replaced: false
				}
			];
		}
		input.value = '';
		uploading = false;
		loadFacets();
		loadDocuments();
	}

	async function remove(d: DocumentInfo) {
		if (
			!confirm(
				`Delete ${d.ref_no ?? d.filename}? Its past event goes too if nothing else describes it.`
			)
		)
			return;
		await api(`/documents/${d.id}`, { method: 'DELETE' });
		loadFacets();
		loadDocuments();
	}

	async function embedMissing() {
		embedding = true;
		await api('/documents/embed', { method: 'POST' }).catch(() => {});
		embedding = false;
		loadFacets();
	}

	function setTab(t: Tab) {
		goto(`?tab=${t}`, { replace: true, reset: false });
	}

	/** Split a search snippet into plain and highlighted parts (the API marks matches with \x02…\x03). */
	function parts(snippet: string): { text: string; hit: boolean }[] {
		return snippet
			.split(/(\x02[^\x03]*\x03)/)
			.map((p) =>
				p.startsWith('\x02') ? { text: p.slice(1, -1), hit: true } : { text: p, hit: false }
			);
	}

	const tabs = $derived<[Tab, string][]>([
		['search', 'Search'],
		['events', 'Past events'],
		...(canUpload ? ([['documents', 'Upload & manage']] as [Tab, string][]) : [])
	]);
	const kindLabel = (k: string) => (k === 'circular' ? 'Circular' : 'Report');
</script>

<h1 class="text-2xl font-semibold">Past events</h1>
{#if !session.loaded}
	<p class="mt-6 text-muted">Loading…</p>
{:else if !session.user}
	<p class="mt-6 {card}">Log in to search past circulars and event reports.</p>
{:else}
	<p class="mt-2 text-muted">
		Every circular and event report, turned into a list of past events. Use it to see what was held
		where and when; the booking form warns you about events that happen every year.
	</p>
	{#if facets}
		<p class="mt-2 text-sm text-muted">
			{facets.events} events from {facets.documents} documents{#if facets.needs_review}{' · '}<a
					class="text-accent underline"
					href="?tab=events&review=1"
					onclick={() => (reviewOnly = true)}>{facets.needs_review} need checking</a
				>{/if}
		</p>
	{/if}

	<div class="mt-6 flex gap-1 border-b border-border" role="tablist">
		{#each tabs as [key, text] (key)}
			<button
				role="tab"
				aria-selected={tab === key}
				class="-mb-px border-b-2 px-4 py-2.5 font-medium {tab === key
					? 'border-accent text-fg'
					: 'border-transparent text-muted hover:text-fg'}"
				onclick={() => setTab(key)}>{text}</button
			>
		{/each}
	</div>

	{#if tab === 'search'}
		<form class="mt-6 flex flex-wrap items-end gap-3" onsubmit={runSearch}>
			<div class="min-w-64 flex-1">
				<label class={label} for="q">Search circulars and reports</label>
				<input
					id="q"
					type="search"
					bind:value={query}
					placeholder="e.g. hackathon in the COE labs, guest lecture on cloud"
					class={field}
				/>
			</div>
			<div>
				<label class={label} for="kind">In</label>
				<select id="kind" bind:value={kind} class={field}>
					<option value="">Both</option>
					<option value="circular">Circulars</option>
					<option value="report">Reports</option>
				</select>
			</div>
			<button class={btnPrimary} disabled={searching || query.trim().length < 2}>Search</button>
		</form>
		{#if searchError}<p class="mt-4 text-danger">{searchError}</p>{/if}
		{#if result}
			<p class="mt-4 text-sm text-muted">
				{result.hits.length ? `${result.hits.length} results` : 'Nothing found'} · matched by {result.mode ===
				'hybrid'
					? 'keywords and meaning'
					: 'keywords'}
			</p>
			<ol class="mt-3 space-y-3">
				{#each result.hits as h (h.document.id)}
					<li class="glass rounded-2xl border p-4">
						<div class="flex flex-wrap items-baseline justify-between gap-2">
							{#if h.event}
								<a href="/documents/events/{h.event.id}" class="font-semibold hover:text-accent"
									>{h.event.title}</a
								>
							{:else}
								<span class="font-semibold">{h.document.filename}</span>
							{/if}
							<a
								href={h.document.file_url}
								target="_blank"
								rel="noopener"
								class="text-sm text-accent"
								>{kindLabel(h.document.kind)} {h.document.ref_no ?? ''} (PDF)</a
							>
						</div>
						{#if h.event}
							<p class="text-sm text-muted">
								{dateRangeText(h.event.start_date, h.event.end_date)} · {h.event.venues.join(', ')} ·
								{h.event.event_type}
							</p>
						{/if}
						<p class="mt-2 text-sm">
							{#each parts(h.snippet) as p, i (i)}{#if p.hit}<mark
										class="rounded bg-accent-soft px-0.5 text-fg">{p.text}</mark
									>{:else}{p.text}{/if}{/each}
						</p>
					</li>
				{/each}
			</ol>
		{/if}
	{:else if tab === 'events'}
		<div class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
			<div class="lg:col-span-2">
				<label class={label} for="title">Title contains</label>
				<input id="title" bind:value={title} placeholder="e.g. hackathon" class={field} />
			</div>
			<div>
				<label class={label} for="venue">Venue code</label>
				<input id="venue" bind:value={venue} placeholder="e.g. COE1" class={field} />
			</div>
			<div>
				<label class={label} for="etype">Type</label>
				<select id="etype" bind:value={eventType} class={field}>
					<option value="">Any</option>
					{#each facets?.event_types ?? [] as t (t)}<option>{t}</option>{/each}
				</select>
			</div>
			<div>
				<label class={label} for="year">Academic year</label>
				<select id="year" bind:value={year} class={field}>
					<option value="">Any</option>
					{#each facets?.years ?? [] as y (y)}<option>{y}</option>{/each}
				</select>
			</div>
		</div>
		<label class="mt-3 flex items-center gap-2">
			<input type="checkbox" bind:checked={reviewOnly} class="h-5 w-5" /> Only events that need checking
		</label>

		<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
			<p class="text-sm text-muted" aria-live="polite">
				{loadingEvents ? 'Loading…' : `${events.length} events`}
			</p>
			<ViewToggle
				bind:value={layout}
				key="events"
				label="Layout"
				options={[
					{ value: 'cards', label: 'Cards', icon: 'list' },
					{ value: 'table', label: 'Table', icon: 'table' }
				]}
			/>
		</div>
		{#if layout === 'table'}
			<div class="mt-3">
				<RecordTable
					label="Past events"
					extraLabel="Type"
					statusLabel="Attended"
					rows={events.map((e) => ({
						key: e.id,
						href: `/documents/events/${e.id}`,
						title: e.title,
						venue: e.venues.map((v) => v.code).join(', ') || e.venue_text || '—',
						when:
							dateRangeText(e.start_date, e.end_date) +
							(e.start_time && e.end_time
								? `, ${e.start_time.slice(0, 5)}–${e.end_time.slice(0, 5)}`
								: ''),
						extra: e.event_type,
						statusText: e.needs_review
							? 'Needs checking'
							: e.participants
								? `${e.participants}`
								: '—',
						statusTone: e.needs_review ? 'bg-warning/20 text-warning' : ''
					}))}
				/>
			</div>
		{:else}
			<ul class="mt-2 space-y-2">
				{#each events as e (e.id)}
					<li>
						<a
							href="/documents/events/{e.id}"
							class="block lift glass rounded-xl border px-4 py-3 hover:border-accent/50"
						>
							<span class="flex flex-wrap items-baseline justify-between gap-2">
								<strong>{e.title}</strong>
								{#if e.needs_review}
									<span class="rounded-full bg-warning/20 px-2.5 py-0.5 text-sm text-warning"
										>Needs checking</span
									>
								{/if}
							</span>
							<span class="block text-sm text-muted">
								{dateRangeText(e.start_date, e.end_date)} · {e.venues
									.map((v) => v.code)
									.join(', ') || e.venue_text} · {e.event_type}{e.participants
									? ` · ${e.participants} attended`
									: ''}
							</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	{:else if tab === 'documents' && canUpload}
		<div class="mt-6 {card}">
			<label for="pdfs" class="block font-medium">Upload circulars or event reports (PDF)</label>
			<p class="mt-1 text-sm text-muted">
				Choose as many as you like. Uploading a circular or report again replaces the old copy.
			</p>
			<input
				id="pdfs"
				type="file"
				accept="application/pdf,.pdf"
				multiple
				disabled={uploading}
				onchange={onFiles}
				class="mt-3 block w-full rounded-lg border border-dashed border-border bg-bg p-4 file:mr-4 file:rounded-lg file:border-0 file:bg-accent file:px-4 file:py-2 file:font-medium file:text-accent-fg"
			/>
			{#if uploading}<p class="mt-3 text-muted">Reading the PDFs…</p>{/if}
			{#if uploads.length}
				<ul class="mt-4 space-y-1 text-sm">
					{#each uploads as u, i (i)}
						<li>
							<strong>{u.filename}</strong> ·
							{#if u.error}
								<span class="text-danger">{u.error}</span>
							{:else if u.document}
								{u.replaced ? 'Replaced' : 'Added'}
								{u.document.ref_no}{#if u.document.event}
									· <a class="text-accent" href="/documents/events/{u.document.event.id}"
										>{u.document.event.needs_review ? 'needs checking' : u.document.event.title}</a
									>{/if}
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		{#if facets}
			<div class="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted">
				{#if facets.embeddings === 'on'}
					<span
						>{facets.embedded} of {facets.documents} documents are indexed for meaning-based search.</span
					>
					{#if facets.embedded < facets.documents}
						<button class={btnSecondary} disabled={embedding} onclick={embedMissing}
							>{embedding ? 'Indexing…' : 'Index the rest'}</button
						>
					{/if}
				{:else}
					<span>Search uses keywords only (embeddings are off in the server settings).</span>
				{/if}
			</div>
		{/if}

		<h2 class="mt-8 text-lg font-semibold">Documents ({documents.length})</h2>
		<ul class="mt-3 divide-y divide-border glass rounded-2xl border">
			{#each documents as d (d.id)}
				<li class="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
					<span class="min-w-0">
						<a
							href={d.file_url}
							target="_blank"
							rel="noopener"
							class="font-medium hover:text-accent">{kindLabel(d.kind)} {d.ref_no ?? d.filename}</a
						>
						<span class="block text-sm text-muted">
							{d.event?.title ?? d.filename}
							{#if d.problems.length}· <span class="text-warning">{d.problems.join(' ')}</span>{/if}
						</span>
					</span>
					<button class={btnDanger} onclick={() => remove(d)}>Delete</button>
				</li>
			{/each}
		</ul>
	{/if}
{/if}

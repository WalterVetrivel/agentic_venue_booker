<script lang="ts">
	import { api, uploadFile } from '#lib/api.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { btnPrimary, card } from '#lib/ui.ts';
	import type { Section, TimetableUpload, UploadBrief } from '#lib/types.ts';

	let uploads = $state<UploadBrief[]>([]);
	let sections = $state<Section[]>([]);
	let progress = $state<{ name: string; state: string }[]>([]);
	let busy = $state(false);

	async function load() {
		[uploads, sections] = await Promise.all([
			api<UploadBrief[]>('/timetables/uploads'),
			api<Section[]>('/timetables/sections')
		]);
	}
	$effect(() => {
		if (session.can('upload_timetables')) load();
	});

	async function onFiles(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		if (!files.length) return;
		busy = true;
		progress = files.map((f) => ({ name: f.name, state: 'Waiting…' }));
		for (const [i, f] of files.entries()) {
			progress[i].state = 'Reading…';
			try {
				const up = await uploadFile<TimetableUpload>('/timetables/uploads', f);
				progress[i].state = up.can_commit
					? `Ready: ${up.slots.length} lab slots found`
					: 'Needs review';
			} catch (err) {
				progress[i].state = err instanceof Error ? err.message : 'Failed';
			}
		}
		input.value = '';
		busy = false;
		await load();
	}

	async function commitAll() {
		busy = true;
		for (const u of uploads.filter((u) => u.can_commit)) {
			await api(`/timetables/uploads/${u.id}/commit`, { method: 'POST' }).catch(() => {});
		}
		busy = false;
		progress = [];
		await load();
	}

	const pending = $derived(uploads.filter((u) => u.status === 'parsed'));
	const ready = $derived(pending.filter((u) => u.can_commit));
</script>

<h1 class="text-2xl font-semibold">Timetables</h1>
{#if !session.can('upload_timetables')}
	<p class="mt-6 {card}">Only the office assistant, HOD and Director can upload timetables.</p>
{:else}
	<p class="mt-2 text-muted">
		Upload class timetable PDFs. Lab sessions are read from each PDF, checked against the other
		classes, and added to the availability grid when you commit them.
	</p>

	<div class="mt-6 {card}">
		<label for="pdfs" class="block font-medium">Upload timetable PDFs</label>
		<p class="mt-1 text-sm text-muted">You can choose several files at once.</p>
		<input
			id="pdfs"
			type="file"
			accept="application/pdf,.pdf"
			multiple
			disabled={busy}
			onchange={onFiles}
			class="mt-3 block w-full rounded-lg border border-dashed border-border bg-bg p-4 file:mr-4 file:rounded-lg file:border-0 file:bg-accent file:px-4 file:py-2 file:font-medium file:text-accent-fg"
		/>
		{#if progress.length}
			<ul class="mt-4 space-y-1 text-sm">
				{#each progress as p, i (i)}<li><strong>{p.name}</strong> · {p.state}</li>{/each}
			</ul>
		{/if}
	</div>

	<section class="mt-10">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<h2 class="text-lg font-semibold">Waiting for review ({pending.length})</h2>
			{#if ready.length > 1}
				<button class={btnPrimary} disabled={busy} onclick={commitAll}
					>Commit all {ready.length} ready timetables</button
				>
			{/if}
		</div>
		{#if pending.length === 0}
			<p class="mt-2 text-muted">Nothing waiting.</p>
		{:else}
			<ul class="mt-3 space-y-2">
				{#each pending as u (u.id)}
					<li>
						<a
							href="/timetables/{u.id}"
							class="flex flex-wrap items-center justify-between gap-2 lift glass rounded-xl border px-4 py-3 hover:border-accent/50"
						>
							<span><strong>{u.section ?? u.filename}</strong> · {u.slots} lab slots</span>
							<span
								class="rounded-full px-2.5 py-0.5 text-sm {u.can_commit
									? 'bg-success/15 text-success'
									: 'bg-warning/20 text-warning'}">{u.can_commit ? 'Ready' : 'Needs fixing'}</span
							>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="mt-10">
		<h2 class="text-lg font-semibold">Classes with timetables ({sections.length})</h2>
		{#if sections.length === 0}
			<p class="mt-2 text-muted">No timetables committed yet.</p>
		{:else}
			<div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
				{#each sections as s (s.id)}
					<a
						href="/timetables/sections/{s.id}"
						class="lift glass rounded-2xl border p-4 hover:border-accent/50"
					>
						<span class="block font-semibold">{s.label}</span>
						<span class="text-sm text-muted">{s.lab_slots} lab slots a week</span>
					</a>
				{/each}
			</div>
		{/if}
	</section>
{/if}

<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { btnDanger, btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import { WEEKDAYS, type ParsedSlot, type TimetableUpload } from '#lib/types.ts';

	let upload = $state<TimetableUpload | null>(null);
	let error = $state('');
	let busy = $state(false);
	let dirty = $state(false);

	async function load() {
		upload = await api<TimetableUpload>(
			`/timetables/uploads/${(page.params as Record<string, string>).id}`
		);
		dirty = false;
	}
	$effect(() => {
		void (page.params as Record<string, string>).id;
		load().catch((e) => (error = e.message));
	});

	async function save() {
		if (!upload) return;
		busy = true;
		error = '';
		try {
			upload = await api<TimetableUpload>(`/timetables/uploads/${upload.id}`, {
				method: 'PUT',
				body: JSON.stringify({ header: upload.header, slots: upload.slots })
			});
			dirty = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save';
		} finally {
			busy = false;
		}
	}

	async function commit() {
		if (!upload) return;
		if (dirty) await save();
		if (!upload.can_commit) return;
		busy = true;
		try {
			await api(`/timetables/uploads/${upload.id}/commit`, { method: 'POST' });
			goto('/timetables');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not commit';
			await load();
		} finally {
			busy = false;
		}
	}

	async function discard() {
		if (!upload || !confirm('Discard this upload?')) return;
		await api(`/timetables/uploads/${upload.id}`, { method: 'DELETE' });
		goto('/timetables');
	}

	function addSlot() {
		upload!.slots.push({
			weekday: 'Mon',
			start: '09:00',
			end: '10:40',
			subject_code: '',
			subject_name: '',
			faculty_name: '',
			batch: 'all',
			venue: ''
		} as ParsedSlot);
		dirty = true;
	}

	const isLab = (cell: string | null) =>
		!!cell && /\((B\d,\s*)?[A-Z]+\s?\d*\)/.test(cell) && !/\(T\)/.test(cell);
	const small = 'block w-full rounded-md border border-border bg-bg px-2 py-1.5 text-fg';
</script>

{#if !upload}
	<p class="mt-6 {error ? 'text-danger' : 'text-muted'}">{error || 'Loading…'}</p>
{:else}
	{@const h = upload.header}
	<div class="mt-4 flex flex-wrap items-start justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold">
				Review {h.dept ?? '?'}
				{h.year ?? '?'}-{h.section ?? '?'}
			</h1>
			<p class="mt-1 text-muted">{upload.filename}</p>
		</div>
		{#if upload.status === 'committed'}
			<span class="rounded-full bg-success/15 px-3 py-1 text-success">Committed</span>
		{/if}
	</div>

	{#if upload.problems.length}
		<ul class="mt-4 space-y-1 rounded-xl border border-warning/40 bg-warning/10 p-4">
			{#each upload.problems as p, i (i)}<li>{p}</li>{/each}
		</ul>
	{/if}

	<!-- Header -->
	<form
		class="mt-6 grid gap-4 {card} sm:grid-cols-3"
		oninput={() => (dirty = true)}
		onsubmit={(e) => e.preventDefault()}
	>
		<div>
			<label class={label} for="dept">Department</label><input
				id="dept"
				bind:value={h.dept}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="year">Year</label><input
				id="year"
				bind:value={h.year}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="sec">Section</label><input
				id="sec"
				bind:value={h.section}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="term">Term</label><input
				id="term"
				bind:value={h.term_name}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="vf">Valid from</label><input
				id="vf"
				type="date"
				bind:value={h.valid_from}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="vt">Valid to</label><input
				id="vt"
				type="date"
				bind:value={h.valid_to}
				class={field}
			/>
		</div>
	</form>

	<!-- What the PDF looks like, with lab cells highlighted -->
	<details class="mt-6 {card}">
		<summary class="cursor-pointer font-semibold">Timetable as read from the PDF</summary>
		<div class="mt-4 overflow-x-auto">
			<table class="w-full border-collapse text-sm">
				<thead>
					<tr>
						<th class="border border-border p-2"></th>
						{#each upload.periods as p (p.no)}
							<th class="border border-border p-2 font-normal text-muted">{p.no}<br />{p.start}</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each Object.entries(upload.grid) as [day, cells] (day)}
						<tr>
							<th class="border border-border p-2">{day}</th>
							{#each cells as c, i (i)}
								<td class="border border-border p-2 {isLab(c) ? 'bg-accent-soft font-medium' : ''}"
									>{c ?? ''}</td
								>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</details>

	<!-- Lab slots -->
	<h2 class="mt-8 text-lg font-semibold">Lab slots ({upload.slots.length})</h2>
	<ul class="mt-3 space-y-3">
		{#each upload.slots as s, i (i)}
			<li
				class="glass rounded-2xl border p-4 {s.issues?.length
					? 'border-danger/50 bg-danger/5'
					: 'border-border'}"
				oninput={() => (dirty = true)}
				onchange={() => (dirty = true)}
			>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
					<label class="text-sm text-muted"
						>Day
						<select aria-label="Day" bind:value={s.weekday} class="mt-1 {small}">
							{#each WEEKDAYS as d (d)}<option>{d}</option>{/each}
						</select>
					</label>
					<label class="text-sm text-muted"
						>Start
						<input aria-label="Start" type="time" bind:value={s.start} class="mt-1 {small}" />
					</label>
					<label class="text-sm text-muted"
						>End
						<input aria-label="End" type="time" bind:value={s.end} class="mt-1 {small}" />
					</label>
					<label class="text-sm text-muted"
						>Subject
						<input aria-label="Subject code" bind:value={s.subject_code} class="mt-1 {small}" />
					</label>
					<label class="text-sm text-muted"
						>Batch
						<select aria-label="Batch" bind:value={s.batch} class="mt-1 {small}">
							<option value="all">Whole class</option><option>B1</option><option>B2</option>
						</select>
					</label>
					<label class="text-sm text-muted"
						>Venue
						<input aria-label="Venue" bind:value={s.venue} class="mt-1 {small}" />
					</label>
				</div>
				<div class="mt-2 flex items-start justify-between gap-3">
					<div class="text-sm">
						<span class="text-muted">{s.subject_name}</span>
						{#each s.issues ?? [] as issue, j (j)}<span class="block text-danger">{issue}</span
							>{/each}
					</div>
					<button
						class={btnDanger}
						onclick={() => {
							upload!.slots.splice(i, 1);
							dirty = true;
						}}>Remove</button
					>
				</div>
			</li>
		{/each}
	</ul>

	{#if error}<p class="mt-4 text-danger" role="alert">{error}</p>{/if}
	{#if upload.status !== 'committed'}
		<div class="mt-6 flex flex-wrap gap-3">
			<button class={btnSecondary} onclick={addSlot}>Add a slot</button>
			<button class={btnSecondary} disabled={busy || !dirty} onclick={save}
				>Save and re-check</button
			>
			<button class={btnPrimary} disabled={busy || (!dirty && !upload.can_commit)} onclick={commit}
				>Commit timetable</button
			>
			<button class="{btnDanger} ml-auto" onclick={discard}>Discard upload</button>
		</div>
		{#if !upload.can_commit && !dirty}
			<p class="mt-3 text-sm text-muted">Fix the highlighted rows, then save and re-check.</p>
		{/if}
	{/if}
{/if}

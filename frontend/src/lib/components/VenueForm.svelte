<script lang="ts">
	import { untrack } from 'svelte';
	import { api } from '#lib/api.ts';
	import { field, label, btnPrimary, btnSecondary } from '#lib/ui.ts';
	import type { VenueFull } from '#lib/types.ts';

	type UserBrief = { id: number; name: string; email: string; roles: string[] };

	let {
		venue = null,
		restricted,
		onsaved,
		oncancel
	}: {
		venue?: VenueFull | null;
		restricted: boolean;
		onsaved: (v: VenueFull) => void;
		oncancel?: () => void;
	} = $props();

	// The form edits a copy of the venue as it was when opened.
	const initial = untrack(() => venue);
	let form = $state({
		code: initial?.code ?? '',
		name: initial?.name ?? '',
		type: initial?.type ?? 'lab',
		block: initial?.block ?? '',
		department: initial?.department ?? 'CSE',
		capacity: initial?.capacity ?? 40,
		byod: initial?.byod ?? false,
		needs_hod_approval: initial?.needs_hod_approval ?? true,
		in_charge_email: initial?.in_charge?.email ?? '',
		technician_email: initial?.technician?.email ?? '',
		notes: initial?.notes ?? ''
	});
	let users = $state<UserBrief[]>([]);
	let error = $state('');
	let busy = $state(false);

	$effect(() => {
		if (restricted) api<UserBrief[]>('/users').then((u) => (users = u));
	});

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		busy = true;
		const common = {
			name: form.name,
			block: form.block || null,
			notes: form.notes || null,
			byod: form.byod
		};
		const director = {
			type: form.type,
			department: form.department || null,
			capacity: Number(form.capacity),
			needs_hod_approval: form.needs_hod_approval,
			in_charge_email: form.in_charge_email || null,
			technician_email: form.technician_email || null
		};
		try {
			const saved = venue
				? await api<VenueFull>(`/venues/${venue.code}`, {
						method: 'PATCH',
						body: JSON.stringify(restricted ? { ...common, ...director } : common)
					})
				: await api<VenueFull>('/venues', {
						method: 'POST',
						body: JSON.stringify({ code: form.code, ...common, ...director })
					});
			onsaved(saved);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not save';
		} finally {
			busy = false;
		}
	}
</script>

<form class="grid gap-5 sm:grid-cols-2" onsubmit={save}>
	{#if !venue}
		<div>
			<label class={label} for="code">Code</label>
			<input id="code" required bind:value={form.code} placeholder="CC13" class={field} />
		</div>
	{/if}
	<div class={venue ? 'sm:col-span-2' : ''}>
		<label class={label} for="name">Name</label>
		<input id="name" required bind:value={form.name} class={field} />
	</div>
	<div>
		<label class={label} for="block">Location</label>
		<input id="block" bind:value={form.block} placeholder="CSE Block" class={field} />
	</div>
	{#if restricted}
		<div>
			<label class={label} for="vtype">Type</label>
			<select id="vtype" bind:value={form.type} class={field}>
				<option value="lab">Lab</option>
				<option value="coe">Centre of Excellence</option>
				<option value="seminar_hall">Seminar hall</option>
			</select>
		</div>
		<div>
			<label class={label} for="capacity">Capacity</label>
			<input
				id="capacity"
				type="number"
				min="1"
				required
				bind:value={form.capacity}
				class={field}
			/>
		</div>
		<div>
			<label class={label} for="dept">Department</label>
			<input id="dept" bind:value={form.department} class={field} />
		</div>
		<div>
			<label class={label} for="incharge">In-charge</label>
			<select id="incharge" bind:value={form.in_charge_email} class={field}>
				<option value="">None</option>
				{#each users as u (u.id)}<option value={u.email}>{u.name} ({u.email})</option>{/each}
			</select>
		</div>
		<div>
			<label class={label} for="tech">Lab technician</label>
			<select id="tech" bind:value={form.technician_email} class={field}>
				<option value="">None</option>
				{#each users as u (u.id)}<option value={u.email}>{u.name} ({u.email})</option>{/each}
			</select>
		</div>
		<label class="flex items-center gap-3 sm:col-span-2">
			<input type="checkbox" bind:checked={form.needs_hod_approval} class="h-5 w-5" />
			Bookings also need the HOD's approval
		</label>
	{/if}
	<label class="flex items-center gap-3 sm:col-span-2">
		<input type="checkbox" bind:checked={form.byod} class="h-5 w-5" />
		Bring your own device (no PCs)
	</label>
	<div class="sm:col-span-2">
		<label class={label} for="notes">Notes</label>
		<textarea id="notes" rows="3" bind:value={form.notes} class={field}></textarea>
	</div>
	{#if error}<p class="text-danger sm:col-span-2" role="alert">{error}</p>{/if}
	<div class="flex gap-3 sm:col-span-2">
		<button type="submit" class={btnPrimary} disabled={busy}
			>{venue ? 'Save changes' : 'Add venue'}</button
		>
		{#if oncancel}<button type="button" class={btnSecondary} onclick={oncancel}>Cancel</button>{/if}
	</div>
</form>

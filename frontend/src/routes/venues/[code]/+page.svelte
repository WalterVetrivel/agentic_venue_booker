<script lang="ts">
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';

	import { session } from '#lib/stores/session.svelte.ts';
	import VenueForm from '#lib/components/VenueForm.svelte';
	import WeekSchedule from '#lib/components/WeekSchedule.svelte';
	import Calendar from '#lib/components/Calendar.svelte';
	import ViewToggle, { savedView } from '#lib/components/ViewToggle.svelte';
	import { btnDanger, btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import { MONTHS, type ClassSlot, type Equipment, type VenueFull } from '#lib/types.ts';

	let venue = $state<VenueFull | null>(null);
	let scheduleView = $state(
		savedView('venue-schedule', ['calendar', 'timetable'] as const, 'calendar')
	);
	let classes = $state<ClassSlot[]>([]);
	let error = $state('');
	let editing = $state(false);
	let actionError = $state('');

	async function load() {
		try {
			[venue, classes] = await Promise.all([
				api<VenueFull>(`/venues/${page.params.code}`),
				api<ClassSlot[]>(`/timetables/slots?venue=${page.params.code}`)
			]);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load venue';
		}
	}
	$effect(() => {
		void page.params.code;
		load();
	});

	async function act(path: string, method: string, body?: unknown) {
		actionError = '';
		try {
			await api(path, { method, body: body ? JSON.stringify(body) : undefined });
			await load();
			return true;
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Something went wrong';
			return false;
		}
	}

	const groups: [Equipment['category'], string][] = [
		['software', 'Software'],
		['hardware', 'Hardware'],
		['av', 'Audio-visual'],
		['facility', 'Facilities']
	];
	const STATUS_TEXT: Record<string, string> = {
		working: 'Working',
		faulty: 'Faulty',
		under_repair: 'Under repair'
	};

	let newItem = $state({ name: '', category: 'software', quantity: 1 });
	let newPeriod = $state({ status: 'maintenance', from_date: '', to_date: '', reason: '' });
	let newRule = $state({ start_month: 3, end_month: 7, kind: 'soft_warning', reason: '' });

	async function addItem(e: SubmitEvent) {
		e.preventDefault();
		if (
			await act(`/venues/${venue!.code}/equipment`, 'POST', {
				...newItem,
				quantity: Number(newItem.quantity)
			})
		)
			newItem = { name: '', category: newItem.category, quantity: 1 };
	}
	async function addPeriod(e: SubmitEvent) {
		e.preventDefault();
		const body = {
			...newPeriod,
			to_date: newPeriod.to_date || null,
			reason: newPeriod.reason || null
		};
		if (await act(`/venues/${venue!.code}/status-periods`, 'POST', body))
			newPeriod = { status: 'maintenance', from_date: '', to_date: '', reason: '' };
	}
	async function addRule(e: SubmitEvent) {
		e.preventDefault();
		const body = {
			...newRule,
			start_month: Number(newRule.start_month),
			end_month: Number(newRule.end_month)
		};
		if (await act(`/venues/${venue!.code}/seasonal-rules`, 'POST', body))
			newRule = { start_month: 3, end_month: 7, kind: 'soft_warning', reason: '' };
	}

	function fmt(d: string | null) {
		if (!d) return 'until further notice';
		return new Date(d + 'T00:00').toLocaleDateString('en-IN', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}
</script>

{#if error}
	<p class="mt-6 text-danger">{error}</p>
{:else if !venue}
	<p class="mt-6 text-muted">Loading…</p>
{:else}
	{@const v = venue}
	<div class="mt-4 flex flex-wrap items-start justify-between gap-4">
		<h1 class="text-2xl font-semibold">{v.name} <span class="text-muted">({v.code})</span></h1>
		<div class="flex gap-3">
			<a href="/availability?type={v.type}" class={btnSecondary}>Availability</a>
			{#if session.can('book')}
				<a href="/book?venue={v.code}" class="{btnPrimary} inline-flex items-center gap-2"
					><Icon name="plus" size={18} /> Book this venue</a
				>
			{/if}
			{#if v.can_edit && !editing}
				<button class={btnPrimary} onclick={() => (editing = true)}>Edit details</button>
			{/if}
		</div>
	</div>

	{#if actionError}<p class="mt-4 text-danger" role="alert">{actionError}</p>{/if}

	{#if editing}
		<div class="mt-6 {card}">
			<VenueForm
				venue={v}
				restricted={v.can_edit_restricted}
				onsaved={(saved) => {
					venue = saved;
					editing = false;
				}}
				oncancel={() => (editing = false)}
			/>
		</div>
	{:else}
		<dl class="mt-6 grid gap-5 {card} sm:grid-cols-2 lg:grid-cols-3">
			<div>
				<dt class="text-sm text-muted">Capacity</dt>
				<dd class="font-medium">{v.capacity}{v.byod ? ' (BYOD)' : ''}</dd>
			</div>
			<div>
				<dt class="text-sm text-muted">Department</dt>
				<dd class="font-medium">{v.department ?? '—'}</dd>
			</div>
			<div>
				<dt class="text-sm text-muted">In-charge</dt>
				<dd class="font-medium">{v.in_charge?.name ?? '—'}</dd>
			</div>
			<div>
				<dt class="text-sm text-muted">Lab technician</dt>
				<dd class="font-medium">{v.technician?.name ?? '—'}</dd>
			</div>
			<div>
				<dt class="text-sm text-muted">Approval</dt>
				<dd class="font-medium">In-charge{v.needs_hod_approval ? ', then HOD' : ''}</dd>
			</div>
			{#if v.notes}<div class="sm:col-span-2 lg:col-span-3">
					<dt class="text-sm text-muted">Notes</dt>
					<dd>{v.notes}</dd>
				</div>{/if}
		</dl>
	{/if}

	{@const hasTimetable = v.type !== 'seminar_hall' || classes.length > 0}
	<section class="mt-10">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<h2 class="text-lg font-semibold">
				{scheduleView === 'calendar' || !hasTimetable ? 'Schedule' : 'Weekly class schedule'}
			</h2>
			{#if hasTimetable}
				<ViewToggle
					bind:value={scheduleView}
					key="venue-schedule"
					label="Schedule"
					options={[
						{ value: 'calendar', label: 'Calendar', icon: 'calendar' },
						{ value: 'timetable', label: 'Class timetable', icon: 'table' }
					]}
				/>
			{/if}
		</div>
		<div class="mt-4">
			{#if scheduleView === 'calendar' || !hasTimetable}
				<Calendar venue={v.code} pickVenue={false} />
			{:else}
				<WeekSchedule slots={classes} show="venue" />
			{/if}
		</div>
	</section>

	<!-- Status periods -->
	<section class="mt-10">
		<h2 class="text-lg font-semibold">Maintenance and closures</h2>
		{#if v.status_periods.length === 0}
			<p class="mt-2 text-muted">No maintenance or closures scheduled.</p>
		{:else}
			<ul class="mt-3 space-y-2">
				{#each v.status_periods as p (p.id)}
					<li
						class="flex flex-wrap items-center justify-between gap-2 glass rounded-xl border px-4 py-3"
					>
						<span
							><strong class="capitalize">{p.status}</strong> · {fmt(p.from_date)} to {fmt(
								p.to_date
							)}{p.reason ? ` · ${p.reason}` : ''}</span
						>
						{#if v.can_edit}<button
								class={btnDanger}
								onclick={() => act(`/status-periods/${p.id}`, 'DELETE')}>Remove</button
							>{/if}
					</li>
				{/each}
			</ul>
		{/if}
		{#if v.can_edit}
			<form class="mt-4 grid gap-4 {card} sm:grid-cols-2 lg:grid-cols-4" onsubmit={addPeriod}>
				<div>
					<label class={label} for="pstatus">Status</label>
					<select id="pstatus" bind:value={newPeriod.status} class={field}>
						<option value="maintenance">Under maintenance</option>
						<option value="renovation">Under renovation</option>
						<option value="closed">Closed</option>
					</select>
				</div>
				<div>
					<label class={label} for="pfrom">From</label><input
						id="pfrom"
						type="date"
						required
						bind:value={newPeriod.from_date}
						class={field}
					/>
				</div>
				<div>
					<label class={label} for="pto">To (optional)</label><input
						id="pto"
						type="date"
						bind:value={newPeriod.to_date}
						class={field}
					/>
				</div>
				<div>
					<label class={label} for="preason">Reason</label><input
						id="preason"
						bind:value={newPeriod.reason}
						class={field}
					/>
				</div>
				<div class="sm:col-span-2 lg:col-span-4">
					<button class={btnSecondary}>Add period</button>
				</div>
			</form>
		{/if}
	</section>

	<!-- Seasonal rules -->
	{#if v.seasonal_rules.length || v.can_edit_restricted}
		<section class="mt-10">
			<h2 class="text-lg font-semibold">Seasonal rules</h2>
			<ul class="mt-3 space-y-2">
				{#each v.seasonal_rules as r (r.id)}
					<li
						class="flex flex-wrap items-center justify-between gap-2 glass rounded-xl border px-4 py-3"
					>
						<span
							><strong>{MONTHS[r.start_month - 1]}–{MONTHS[r.end_month - 1]}</strong> · {r.kind ===
							'blocked'
								? 'Not bookable'
								: 'Warning only'} · {r.reason}</span
						>
						{#if v.can_edit_restricted}<button
								class={btnDanger}
								onclick={() => act(`/seasonal-rules/${r.id}`, 'DELETE')}>Remove</button
							>{/if}
					</li>
				{/each}
			</ul>
			{#if v.can_edit_restricted}
				<form class="mt-4 grid gap-4 {card} sm:grid-cols-2 lg:grid-cols-4" onsubmit={addRule}>
					<div>
						<label class={label} for="rfrom">From month</label>
						<select id="rfrom" bind:value={newRule.start_month} class={field}
							>{#each MONTHS as m, i (m)}<option value={i + 1}>{m}</option>{/each}</select
						>
					</div>
					<div>
						<label class={label} for="rto">To month</label>
						<select id="rto" bind:value={newRule.end_month} class={field}
							>{#each MONTHS as m, i (m)}<option value={i + 1}>{m}</option>{/each}</select
						>
					</div>
					<div>
						<label class={label} for="rkind">Effect</label>
						<select id="rkind" bind:value={newRule.kind} class={field}
							><option value="soft_warning">Warning only</option><option value="blocked"
								>Not bookable</option
							></select
						>
					</div>
					<div>
						<label class={label} for="rreason">Reason</label><input
							id="rreason"
							required
							bind:value={newRule.reason}
							class={field}
						/>
					</div>
					<div class="sm:col-span-2 lg:col-span-4">
						<button class={btnSecondary}>Add rule</button>
					</div>
				</form>
			{/if}
		</section>
	{/if}

	<!-- Equipment -->
	<section class="mt-10">
		<h2 class="text-lg font-semibold">Equipment and software</h2>
		{#each groups as [cat, title] (cat)}
			{@const items = v.equipment.filter((e) => e.category === cat)}
			{#if items.length}
				<h3 class="mt-6 font-semibold text-muted">{title}</h3>
				<ul class="mt-2 grid gap-2 sm:grid-cols-2">
					{#each items as e (e.id)}
						<li class="flex items-center justify-between gap-3 glass rounded-xl border px-4 py-2.5">
							<span class="min-w-0">
								{e.name}
								{#if e.quantity > 1}<span class="text-sm whitespace-nowrap text-muted">
										× {e.quantity}</span
									>{/if}
							</span>
							<span class="flex shrink-0 items-center gap-1">
								{#if v.can_update_equipment}
									<label class="sr-only" for="st-{e.id}">Status of {e.name}</label>
									<select
										id="st-{e.id}"
										value={e.status}
										onchange={(ev) =>
											act(`/equipment/${e.id}`, 'PATCH', {
												status: (ev.currentTarget as HTMLSelectElement).value
											})}
										class="rounded-md border border-border bg-bg px-2 py-1 text-sm"
									>
										{#each Object.entries(STATUS_TEXT) as [val, text] (val)}<option value={val}
												>{text}</option
											>{/each}
									</select>
								{:else if e.status !== 'working'}
									<span class="rounded-full bg-danger/15 px-2.5 py-0.5 text-sm text-danger"
										>{STATUS_TEXT[e.status]}</span
									>
								{/if}
								{#if v.can_edit}
									<button
										class={btnDanger}
										aria-label="Remove {e.name}"
										onclick={() => act(`/equipment/${e.id}`, 'DELETE')}>✕</button
									>
								{/if}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		{/each}
		{#if v.can_edit}
			<form
				class="mt-6 grid gap-4 {card} sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end"
				onsubmit={addItem}
			>
				<div>
					<label class={label} for="iname">Add item</label><input
						id="iname"
						required
						bind:value={newItem.name}
						placeholder="e.g. Android Studio"
						class={field}
					/>
				</div>
				<div>
					<label class={label} for="icat">Category</label>
					<select id="icat" bind:value={newItem.category} class={field}>
						<option value="software">Software</option><option value="hardware">Hardware</option
						><option value="av">Audio-visual</option><option value="facility">Facility</option>
					</select>
				</div>
				<div>
					<label class={label} for="iqty">Quantity</label><input
						id="iqty"
						type="number"
						min="1"
						bind:value={newItem.quantity}
						class={field}
					/>
				</div>
				<button class={btnSecondary}>Add</button>
			</form>
		{/if}
	</section>
{/if}

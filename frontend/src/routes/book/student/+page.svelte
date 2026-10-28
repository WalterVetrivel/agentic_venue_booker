<script lang="ts">
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import { api } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';
	import { chat } from '#lib/stores/chat.svelte.ts';
	import { addDays, isoDate, prettyDate } from '#lib/time.ts';
	import { btnPrimary, btnSecondary, btnDanger, card, field, label } from '#lib/ui.ts';
	import type { StudentCheck, StudentOptions, StudentTrack } from '#lib/types.ts';

	type Row = { name: string; register_no: string; section_id: number | '' };

	let options = $state<StudentOptions | null>(null);
	let loadError = $state('');
	let fromAssistant = $state(false);
	let fromMessage = $state<number | null>(null);
	let fromCard = $state(-1);
	let venue = $state('');
	let dateFrom = $state(addDays(isoDate(new Date()), 1));
	let multiDay = $state(false);
	let dateTo = $state('');
	let start = $state('14:00');
	let end = $state('16:00');
	let reason = $state('');
	let guideId = $state<number | ''>('');
	let email = $state('');
	let students = $state<Row[]>([{ name: '', register_no: '', section_id: '' }]);

	// The assistant's drafts link here with what it knows filled in (and via=agent). A later
	// draft, after the group tells it a missing detail, fills in what it has and keeps the rest.
	function fill(params: { get(key: string): string | null }) {
		const has = (key: string) => !!params.get(key);
		if (params.get('via') === 'agent') fromAssistant = true;
		if (has('from_msg')) fromMessage = Number(params.get('from_msg'));
		if (has('from_card')) fromCard = Number(params.get('from_card'));
		if (has('venue')) venue = params.get('venue')!;
		if (has('date')) dateFrom = params.get('date')!;
		if (has('to')) [multiDay, dateTo] = [true, params.get('to')!];
		if (has('start')) start = params.get('start')!;
		if (has('end')) end = params.get('end')!;
		if (has('reason')) reason = params.get('reason')!;
		if (has('guide')) guideId = Number(params.get('guide')) || '';
		if (has('email')) email = params.get('email')!;
		let drafted: Partial<Row>[] = [];
		try {
			drafted = JSON.parse(params.get('students') ?? '[]');
		} catch {
			/* not a draft */
		}
		for (const d of drafted) {
			const key = (d.name ?? '').trim().toLowerCase();
			const row =
				students.find((r) => r.name.trim().toLowerCase() === key) ??
				students.find((r) => !r.name.trim());
			const next: Row = {
				name: d.name ?? row?.name ?? '',
				register_no: d.register_no || row?.register_no || '',
				section_id: d.section_id || row?.section_id || ''
			};
			if (row) Object.assign(row, next);
			else if (students.length < (options?.max_students ?? 10)) students.push(next);
		}
	}
	fill(page.url.searchParams);
	let filled = page.url.search;
	$effect(() => {
		if (page.url.search === filled) return;
		filled = page.url.search;
		untrack(() => fill(page.url.searchParams));
	});

	let check = $state<StudentCheck | null>(null);
	let checkError = $state('');
	let checking = $state(false);
	let submitError = $state('');
	let submitting = $state(false);
	let submitted = $state<StudentTrack | null>(null);
	let copied = $state(false);

	$effect(() => {
		untrack(async () => {
			try {
				options = await api<StudentOptions>('/student/options');
			} catch (e) {
				loadError = e instanceof Error ? e.message : 'Could not load the form';
			}
		});
	});

	function slot() {
		return {
			venue,
			date_from: dateFrom,
			date_to: multiDay && dateTo ? dateTo : null,
			start_time: start,
			end_time: end
		};
	}

	// Re-check whenever the venue, time or group size changes (debounced).
	$effect(() => {
		void [venue, dateFrom, dateTo, multiDay, start, end, students.length];
		if (!venue || !dateFrom || !start || !end) return;
		const timer = setTimeout(runCheck, 350);
		return () => clearTimeout(timer);
	});

	async function runCheck() {
		checking = true;
		checkError = '';
		try {
			check = await api<StudentCheck>('/student/check', {
				method: 'POST',
				body: JSON.stringify({ ...slot(), count: Math.max(students.length, 1) })
			});
		} catch (e) {
			check = null;
			checkError = e instanceof Error ? e.message : 'Could not check';
		} finally {
			checking = false;
		}
	}

	function addStudent() {
		const last = students.at(-1);
		// Most groups are from one class: start the next row with the same one.
		students.push({ name: '', register_no: '', section_id: last?.section_id ?? '' });
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		submitting = true;
		submitError = '';
		try {
			submitted = await api<StudentTrack>('/student/bookings', {
				method: 'POST',
				headers: fromAssistant ? { 'X-Via': 'agent' } : {},
				body: JSON.stringify({
					...slot(),
					reason,
					guide_id: Number(guideId),
					contact_email: email,
					students: students.map((s) => ({
						name: s.name,
						register_no: s.register_no || null,
						section_id: Number(s.section_id)
					}))
				})
			});
			if (fromMessage && fromCard >= 0)
				await chat.draftSubmitted(
					fromMessage,
					fromCard,
					`Submitted. Tracking number ${submitted.tracking_code}.`
				);
			window.scrollTo({ top: 0 });
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Could not submit';
			await runCheck();
		} finally {
			submitting = false;
		}
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(submitted!.tracking_code);
			copied = true;
		} catch {
			/* clipboard blocked: the number is on screen */
		}
	}

	const max = $derived(options?.max_students ?? 10);
	const domain = $derived(options?.email_domain);
</script>

<h1 class="text-2xl font-semibold">Request a lab for group work</h1>

{#if submitted}
	<section class="mt-6 {card} border-success/40" aria-live="polite">
		<p class="text-lg font-semibold text-success">Request sent to {submitted.guide}.</p>
		<p class="mt-3">Your tracking number:</p>
		<div class="mt-2 flex flex-wrap items-center gap-3">
			<code
				class="rounded-lg bg-surface-2 px-4 py-2 text-2xl font-semibold tracking-wider"
				data-testid="tracking-code">{submitted.tracking_code}</code
			>
			<button type="button" class={btnSecondary} onclick={copy}>{copied ? 'Copied' : 'Copy'}</button
			>
		</div>
		<p class="mt-3 text-muted">
			We've emailed it to {submitted.contact_email}, with an update at each step. The request goes
			to your faculty guide, then the venue in-charge, then the HOD.
		</p>
		<div class="mt-4 flex flex-wrap gap-3">
			<a href="/track?code={submitted.tracking_code}" class={btnPrimary}>Track this request</a>
			<a href="/book/student" class={btnSecondary} data-sveltekit-reload>Send another request</a>
		</div>
	</section>
{:else if session.user}
	<p class="mt-6 {card}">
		This form is for students. Staff book through <a class="text-accent underline" href="/book"
			>Book a venue</a
		>.
	</p>
{:else if loadError}
	<p class="mt-6 text-danger">{loadError}</p>
{:else if !options}
	<p class="mt-6 text-muted">Loading…</p>
{:else}
	<p class="mt-2 text-muted">
		No login needed. Labs and centres of excellence only. Your faculty guide approves each student
		first, then the venue in-charge and the HOD. You get a tracking number to follow it.
	</p>
	<aside
		class="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3"
		aria-label="For faculty and staff"
	>
		<Icon name="users" size={18} class="text-accent" />
		<p class="flex-1">
			<span class="font-medium">Faculty member?</span> Log in to book any venue, including seminar halls,
			for classes and events.
		</p>
		<a href="/login?next=/book" class="{btnPrimary} py-2 text-sm">Log in to book</a>
	</aside>

	<form class="mt-6 space-y-6" onsubmit={submit}>
		<section class="{card} grid gap-4 sm:grid-cols-2">
			<h2 class="text-lg font-semibold sm:col-span-2">Lab and time</h2>
			<div class="sm:col-span-2">
				<label class={label} for="venue">Lab</label>
				<select id="venue" required bind:value={venue} class={field}>
					<option value="" disabled>Choose a lab…</option>
					{#each options.venues as v (v.code)}
						<option value={v.code}>{v.code} · {v.name} ({v.capacity} seats)</option>
					{/each}
				</select>
			</div>
			<div>
				<label class={label} for="from">{multiDay ? 'First day' : 'Date'}</label>
				<input id="from" type="date" required bind:value={dateFrom} class={field} />
			</div>
			<div>
				{#if multiDay}
					<label class={label} for="to">Last day</label>
					<input id="to" type="date" min={dateFrom} bind:value={dateTo} class={field} />
				{/if}
				<label class="mt-2 flex items-center gap-2 {multiDay ? '' : 'sm:mt-9'}">
					<input type="checkbox" bind:checked={multiDay} class="h-5 w-5" /> Several days
				</label>
			</div>
			<div>
				<label class={label} for="start">Starts</label>
				<input id="start" type="time" required bind:value={start} class={field} />
			</div>
			<div>
				<label class={label} for="end">Ends</label>
				<input id="end" type="time" required bind:value={end} class={field} />
			</div>

			<div class="sm:col-span-2" aria-live="polite">
				{#if checkError}
					<p class="text-danger">{checkError}</p>
				{:else if check}
					{@const days = check.days.length}
					{#if check.ok}
						<p class="rounded-lg bg-success/15 px-4 py-3 text-success">
							{check.venue.code} is free{days > 1
								? ` on all ${days} days (Sundays skipped)`
								: ` on ${prettyDate(check.days[0])}`}.
						</p>
					{:else}
						<p class="rounded-lg bg-danger/10 px-4 py-3 font-medium text-danger">
							{check.problem} Choose another time or lab.
						</p>
					{/if}
					{#if check.warnings.length}
						<ul class="mt-3 space-y-1">
							{#each check.warnings as w, i (i)}
								<li class="rounded-lg border border-warning/40 bg-warning/10 px-4 py-2">
									{w.message}
								</li>
							{/each}
						</ul>
					{/if}
					{#if check.alternatives.length}
						<div class="mt-3">
							<p class="text-sm text-muted">Free at that time instead:</p>
							<div class="mt-2 flex flex-wrap gap-2">
								{#each check.alternatives as a (a.code)}
									<button type="button" class={btnSecondary} onclick={() => (venue = a.code)}
										>{a.code} ({a.capacity} seats)</button
									>
								{/each}
							</div>
						</div>
					{/if}
				{:else if checking}
					<p class="text-muted">Checking…</p>
				{/if}
			</div>
		</section>

		<section class="{card} grid gap-4 sm:grid-cols-2">
			<h2 class="text-lg font-semibold sm:col-span-2">Your project</h2>
			<div class="sm:col-span-2">
				<label class={label} for="reason">What will the group work on?</label>
				<textarea
					id="reason"
					rows="3"
					required
					minlength="5"
					maxlength="2000"
					bind:value={reason}
					placeholder="e.g. Mini project: attendance app with face recognition"
					class={field}></textarea>
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="guide">Faculty guide</label>
				<select id="guide" required bind:value={guideId} class={field}>
					<option value="" disabled>Choose your guide…</option>
					{#each options.guides as g (g.id)}
						<option value={g.id}>{g.name}{g.designation ? ` · ${g.designation}` : ''}</option>
					{/each}
				</select>
				<p class="mt-1 text-sm text-muted">
					The faculty member you're working under. For a contest or hackathon, choose the
					department's contest coordinator. Groups working on different things send separate
					requests.
				</p>
			</div>
		</section>

		<section class={card}>
			<h2 class="text-lg font-semibold">Students ({students.length} of up to {max})</h2>
			<p class="mt-1 text-muted">Everyone who needs the lab, including you.</p>
			<ol class="mt-4 space-y-4">
				{#each students as s, i (i)}
					<li
						class="grid gap-3 rounded-lg border border-border p-4 sm:grid-cols-[2fr_1.2fr_1.2fr_auto]"
					>
						<div>
							<label class={label} for="sname-{i}">Name</label>
							<input id="sname-{i}" required maxlength="120" bind:value={s.name} class={field} />
						</div>
						<div>
							<label class={label} for="sclass-{i}">Class</label>
							<select id="sclass-{i}" required bind:value={s.section_id} class={field}>
								<option value="" disabled>Choose…</option>
								{#each options.sections as c (c.id)}
									<option value={c.id}>{c.label}</option>
								{/each}
							</select>
						</div>
						<div>
							<label class={label} for="sreg-{i}">Register no. (optional)</label>
							<input id="sreg-{i}" maxlength="30" bind:value={s.register_no} class={field} />
						</div>
						<div class="flex items-end">
							{#if students.length > 1}
								<button
									type="button"
									class={btnDanger}
									aria-label="Remove {s.name || `student ${i + 1}`}"
									onclick={() => students.splice(i, 1)}>Remove</button
								>
							{/if}
						</div>
					</li>
				{/each}
			</ol>
			{#if students.length < max}
				<button type="button" class="{btnSecondary} mt-4" onclick={addStudent}>Add a student</button
				>
			{/if}
			{#if options.sections.length === 0}
				<p class="mt-3 text-warning">
					No class timetables have been uploaded yet, so there are no classes to choose from.
				</p>
			{/if}
		</section>

		<section class={card}>
			<h2 class="text-lg font-semibold">Contact email</h2>
			<label class="{label} mt-3" for="email">One email for the group</label>
			<input
				id="email"
				type="email"
				required
				maxlength="120"
				bind:value={email}
				placeholder={domain ? `name@${domain}` : 'name@example.com'}
				class={field}
			/>
			<p class="mt-1 text-sm text-muted">
				Gets the tracking number and an update at each step{domain
					? `. Use your @${domain} address.`
					: '.'}
			</p>
		</section>

		{#if submitError}<p class="text-danger" role="alert">{submitError}</p>{/if}
		<button type="submit" class={btnPrimary} disabled={submitting || !check?.ok}>
			Send the request
		</button>
	</form>
{/if}

<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import Icon from '#lib/components/Icon.svelte';
	import { session } from '#lib/stores/session.svelte.ts';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);
	// Where to go after logging in, e.g. back to the booking form. Only paths on this site.
	const raw = page.url.searchParams.get('next') ?? '/';
	const next = raw.startsWith('/') && !raw.startsWith('//') ? raw : '/';

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		busy = true;
		try {
			await session.login(email, password);
			goto(next);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Login failed';
		} finally {
			busy = false;
		}
	}
</script>

<div class="mx-auto max-w-md">
	<h1 class="text-2xl font-semibold">Staff login</h1>
	<p class="mt-2 text-muted">
		Students don't need to log in: they can check availability,
		<a class="text-accent underline" href="/book/student">request a lab</a> and
		<a class="text-accent underline" href="/track">track a request</a>.
	</p>

	<form class="mt-8 space-y-5 glass rounded-2xl border p-6" onsubmit={submit}>
		<div>
			<label for="email" class="mb-1.5 block font-medium">Email</label>
			<input
				id="email"
				type="email"
				autocomplete="username"
				required
				bind:value={email}
				placeholder="name@kiot.ac.in"
				class="w-full rounded-lg border border-border bg-bg px-3 py-2.5 focus:border-accent focus:outline-none"
			/>
		</div>
		<div>
			<label for="password" class="mb-1.5 block font-medium">Password</label>
			<input
				id="password"
				type="password"
				autocomplete="current-password"
				required
				bind:value={password}
				class="w-full rounded-lg border border-border bg-bg px-3 py-2.5 focus:border-accent focus:outline-none"
			/>
		</div>
		{#if error}
			<p class="text-danger" role="alert">{error}</p>
		{/if}
		<button
			type="submit"
			disabled={busy}
			class="btn-cta inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 font-medium disabled:opacity-60"
		>
			<Icon name="login" size={18} />
			{busy ? 'Logging in…' : 'Log in'}
		</button>
	</form>
</div>

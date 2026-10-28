<script lang="ts">
	import { goto } from '$app/navigation';
	import { session } from '#lib/stores/session.svelte.ts';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		busy = true;
		try {
			await session.login(email, password);
			goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Login failed';
		} finally {
			busy = false;
		}
	}
</script>

<div class="mx-auto max-w-md">
	<h1 class="text-2xl font-semibold">Staff login</h1>
	<p class="mt-2 text-muted">Students don't need to log in to check availability.</p>

	<form class="mt-8 space-y-5 glass rounded-2xl border p-6" onsubmit={submit}>
		<div>
			<label for="email" class="mb-1.5 block font-medium">Email</label>
			<input
				id="email"
				type="email"
				autocomplete="username"
				required
				bind:value={email}
				placeholder="swvcse@kiot.ac.in"
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
			class="btn-cta w-full rounded-lg px-4 py-2.5 font-medium disabled:opacity-60"
		>
			{busy ? 'Logging in…' : 'Log in'}
		</button>
	</form>

	<details class="mt-6 rounded-xl bg-surface-2 p-4 text-sm">
		<summary class="cursor-pointer font-medium">Demo accounts (password: password)</summary>
		<ul class="mt-3 space-y-1 text-muted">
			<li><code>swvcse@kiot.ac.in</code> · Faculty and CC10 in-charge</li>
			<li><code>tkcse@kiot.ac.in</code> · Faculty</li>
			<li><code>hod.cse@kiot.ac.in</code> · HOD</li>
			<li><code>dirim@kiot.ac.in</code> · Director IM</li>
			<li><code>cseoa@kiot.ac.in</code> · OA / DEO</li>
			<li><code>sh.dblock@kiot.ac.in</code> · D Block Seminar Hall in-charge</li>
		</ul>
	</details>
</div>

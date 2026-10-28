<script lang="ts">
	import { api } from '#lib/api.ts';
	import { chat } from '#lib/stores/chat.svelte.ts';
	import { session } from '#lib/stores/session.svelte.ts';
	import { btnPrimary, btnSecondary, card, field, label } from '#lib/ui.ts';
	import type { LLMSettings, MailSettings } from '#lib/types.ts';

	let current = $state<LLMSettings | null>(null);
	let error = $state('');
	let form = $state({
		provider: 'groq' as 'groq' | 'ollama',
		groq_api_key: '',
		groq_model: '',
		groq_fallback_model: '',
		ollama_base_url: '',
		ollama_model: ''
	});
	let ollamaModels = $state<string[]>([]);
	let saving = $state(false);
	let saved = $state('');
	let tests = $state<Record<string, { ok: boolean; message: string } | 'running'>>({});
	let mcp = $state<{ token: string; expires_in_hours: number } | null>(null);
	let mail = $state<MailSettings | null>(null);
	let mailForm = $state({ host: '', port: 587, user: '', password: '', from_addr: '' });
	let mailSaved = $state('');
	let mailError = $state('');
	let mailTo = $state('');
	let mailTest = $state<{ ok: boolean; message: string } | 'running' | null>(null);

	function fillMail(m: MailSettings) {
		mail = m;
		mailForm = { host: m.host, port: m.port, user: m.user, password: '', from_addr: m.from_addr };
	}

	async function saveMail(e: SubmitEvent) {
		e.preventDefault();
		mailSaved = '';
		mailError = '';
		const { password, ...rest } = mailForm;
		try {
			fillMail(
				await api<MailSettings>('/settings/email', {
					method: 'PUT',
					body: JSON.stringify(password.trim() ? { ...rest, password } : rest)
				})
			);
			mailSaved = 'Saved.';
		} catch (err) {
			mailError = err instanceof Error ? err.message : 'Could not save';
		}
	}

	async function removeMailPassword() {
		fillMail(
			await api<MailSettings>('/settings/email', {
				method: 'PUT',
				body: JSON.stringify({ password: '' })
			})
		);
		mailSaved = 'Saved password removed.';
	}

	async function testMail() {
		mailTest = 'running';
		mailTest = await api<{ ok: boolean; message: string }>('/settings/email/test', {
			method: 'POST',
			body: JSON.stringify({ to: mailTo })
		});
	}
	let copied = $state(false);

	function fill(s: LLMSettings) {
		current = s;
		form = {
			provider: s.provider,
			groq_api_key: '',
			groq_model: s.groq_model,
			groq_fallback_model: s.groq_fallback_model,
			ollama_base_url: s.ollama_base_url,
			ollama_model: s.ollama_model
		};
	}

	$effect(() => {
		if (!session.can('manage_settings')) return;
		api<LLMSettings>('/settings/llm')
			.then(fill)
			.catch((e) => (error = e.message));
		api<string[]>('/settings/ollama-models').then((m) => (ollamaModels = m));
		api<MailSettings>('/settings/email').then(fillMail);
	});

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		saved = '';
		error = '';
		const { groq_api_key, ...rest } = form;
		try {
			fill(
				await api<LLMSettings>('/settings/llm', {
					method: 'PUT',
					body: JSON.stringify(groq_api_key.trim() ? { ...rest, groq_api_key } : rest)
				})
			);
			saved = 'Saved.';
			chat.providers = null; // the chat panel reloads the providers and models
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not save';
		} finally {
			saving = false;
		}
	}

	async function removeKey() {
		fill(
			await api<LLMSettings>('/settings/llm', {
				method: 'PUT',
				body: JSON.stringify({ groq_api_key: '' })
			})
		);
		saved = 'Saved key removed.';
	}

	async function test(provider: 'groq' | 'ollama') {
		tests[provider] = 'running';
		const model = provider === 'groq' ? form.groq_model : form.ollama_model;
		tests[provider] = await api<{ ok: boolean; message: string }>('/settings/llm/test', {
			method: 'POST',
			body: JSON.stringify({ provider, model })
		});
	}

	async function makeToken() {
		mcp = await api('/auth/mcp-token');
		copied = false;
	}

	const mcpUrl = $derived(`${location.origin}/mcp/`);
	const mcpConfig = $derived(
		mcp
			? JSON.stringify(
					{
						mcpServers: {
							'kiot-venues': {
								command: 'npx',
								args: ['-y', 'mcp-remote', mcpUrl, '--header', 'Authorization:${AUTH}'],
								env: { AUTH: `Bearer ${mcp.token}` }
							}
						}
					},
					null,
					2
				)
			: ''
	);

	async function copy() {
		await navigator.clipboard.writeText(mcpConfig);
		copied = true;
	}
</script>

<h1 class="text-2xl font-semibold">Settings</h1>
<p class="mt-1 text-muted">
	Choose the model the assistant uses (everything else works without it), and how student emails are
	sent.
</p>

{#if !session.can('manage_settings')}
	<p class="mt-6 text-danger">Only the Director can change settings.</p>
{:else if error && !current}
	<p class="mt-6 text-danger">{error}</p>
{:else if current}
	<form class="mt-6 space-y-6" onsubmit={save}>
		<fieldset class={card}>
			<legend class="sr-only">Default model</legend>
			<p class="font-semibold">Default for new chats</p>
			<p class="text-sm text-muted">People can still pick the other one in the chat panel.</p>
			<div class="mt-3 flex flex-wrap gap-6">
				<label class="flex items-center gap-2">
					<input type="radio" class="h-5 w-5" value="groq" bind:group={form.provider} />
					Groq (online, fast, free tier)
				</label>
				<label class="flex items-center gap-2">
					<input type="radio" class="h-5 w-5" value="ollama" bind:group={form.provider} />
					Ollama (runs on this computer)
				</label>
			</div>
		</fieldset>

		<section class="grid gap-4 {card} sm:grid-cols-2" aria-labelledby="groq-h">
			<h2 id="groq-h" class="text-lg font-semibold sm:col-span-2">Groq</h2>
			<div class="sm:col-span-2">
				<label class={label} for="key">API key</label>
				<input
					id="key"
					type="password"
					autocomplete="off"
					placeholder={current.groq_key_set
						? `${current.groq_key_masked} (leave blank to keep)`
						: 'gsk_…'}
					bind:value={form.groq_api_key}
					class={field}
				/>
				<p class="mt-1 text-sm text-muted">
					{#if current.groq_key_source === 'settings'}
						Saved here.
						<button type="button" class="text-danger underline" onclick={removeKey}
							>Remove saved key</button
						>
					{:else if current.groq_key_source === 'env'}
						Using GROQ_API_KEY from backend/.env. A key saved here takes its place.
					{:else}
						No key yet. Get one free at
						<a
							class="text-accent underline"
							href="https://console.groq.com/keys"
							target="_blank"
							rel="noopener">console.groq.com/keys</a
						>.
					{/if}
				</p>
			</div>
			<div>
				<label class={label} for="gm">Model</label>
				<input id="gm" required bind:value={form.groq_model} class={field} />
			</div>
			<div>
				<label class={label} for="gf">Fallback model</label>
				<input id="gf" required bind:value={form.groq_fallback_model} class={field} />
				<p class="mt-1 text-sm text-muted">Used if Groq retires the first model.</p>
			</div>
			<div class="flex flex-wrap items-center gap-3 sm:col-span-2">
				<button type="button" class={btnSecondary} onclick={() => test('groq')}>Test Groq</button>
				{#if tests.groq === 'running'}<span class="text-muted">Testing…</span>
				{:else if tests.groq}<span class={tests.groq.ok ? 'text-success' : 'text-danger'}
						>{tests.groq.message}</span
					>{/if}
			</div>
		</section>

		<section class="grid gap-4 {card} sm:grid-cols-2" aria-labelledby="ollama-h">
			<h2 id="ollama-h" class="text-lg font-semibold sm:col-span-2">Ollama</h2>
			<div>
				<label class={label} for="ou">Address</label>
				<input id="ou" required bind:value={form.ollama_base_url} class={field} />
			</div>
			<div>
				<label class={label} for="om">Model</label>
				{#if ollamaModels.length}
					<select id="om" bind:value={form.ollama_model} class={field}>
						{#if !ollamaModels.includes(form.ollama_model)}
							<option value={form.ollama_model}>{form.ollama_model} (not pulled)</option>
						{/if}
						{#each ollamaModels as m (m)}<option>{m}</option>{/each}
					</select>
				{:else}
					<input id="om" required bind:value={form.ollama_model} class={field} />
					<p class="mt-1 text-sm text-muted">
						Ollama isn't running, so its models can't be listed.
					</p>
				{/if}
			</div>
			<div class="flex flex-wrap items-center gap-3 sm:col-span-2">
				<button type="button" class={btnSecondary} onclick={() => test('ollama')}
					>Test Ollama</button
				>
				{#if tests.ollama === 'running'}<span class="text-muted"
						>Testing… (a first run can take a minute)</span
					>
				{:else if tests.ollama}<span class={tests.ollama.ok ? 'text-success' : 'text-danger'}
						>{tests.ollama.message}</span
					>{/if}
			</div>
		</section>

		<div class="flex items-center gap-3">
			<button class={btnPrimary} disabled={saving}>Save settings</button>
			{#if saved}<span class="text-success" role="status">{saved}</span>{/if}
			{#if error}<span class="text-danger" role="alert">{error}</span>{/if}
		</div>
	</form>

	{#if mail}
		<form
			class="mt-6 grid gap-4 {card} sm:grid-cols-2"
			aria-labelledby="mail-h"
			onsubmit={saveMail}
		>
			<div class="sm:col-span-2">
				<h2 id="mail-h" class="text-lg font-semibold">Email for student requests</h2>
				<p class="mt-1 text-muted">
					Students get their tracking number and each update by email.
					{mail.configured
						? `Sending through ${mail.host}.`
						: 'No mail server yet, so emails are saved to backend/storage/outbox instead of being sent.'}
					For Gmail: server <code>smtp.gmail.com</code>, port 587, the Gmail address and an app
					password (see docs/EMAIL.md).
				</p>
				<p class="mt-1 text-sm text-muted">
					{mail.student_email_domain
						? `Students must use an @${mail.student_email_domain} address (STUDENT_EMAIL_DOMAIN in backend/.env).`
						: 'Any email address is accepted. Set STUDENT_EMAIL_DOMAIN=kiot.ac.in in backend/.env to accept college addresses only.'}
				</p>
			</div>
			<div>
				<label class={label} for="sh">SMTP server</label>
				<input id="sh" bind:value={mailForm.host} placeholder="smtp.gmail.com" class={field} />
			</div>
			<div>
				<label class={label} for="sp">Port</label>
				<input id="sp" type="number" min="1" max="65535" bind:value={mailForm.port} class={field} />
			</div>
			<div>
				<label class={label} for="su">Username</label>
				<input id="su" bind:value={mailForm.user} placeholder="venues@gmail.com" class={field} />
			</div>
			<div>
				<label class={label} for="spw">Password (app password for Gmail)</label>
				<input
					id="spw"
					type="password"
					autocomplete="off"
					bind:value={mailForm.password}
					placeholder={mail.password_set ? '•••••••• (leave blank to keep)' : ''}
					class={field}
				/>
				<p class="mt-1 text-sm text-muted">
					{#if mail.password_source === 'settings'}
						Saved here.
						<button type="button" class="text-danger underline" onclick={removeMailPassword}
							>Remove saved password</button
						>
					{:else if mail.password_source === 'env'}
						Using SMTP_PASSWORD from backend/.env.
					{/if}
				</p>
			</div>
			<div class="sm:col-span-2">
				<label class={label} for="sf">From address (optional)</label>
				<input
					id="sf"
					bind:value={mailForm.from_addr}
					placeholder="Same as the username"
					class={field}
				/>
			</div>
			<div class="flex flex-wrap items-center gap-3 sm:col-span-2">
				<button class={btnPrimary}>Save email settings</button>
				{#if mailSaved}<span class="text-success" role="status">{mailSaved}</span>{/if}
				{#if mailError}<span class="text-danger" role="alert">{mailError}</span>{/if}
			</div>
			<div class="flex flex-wrap items-end gap-3 sm:col-span-2">
				<div class="min-w-64 flex-1">
					<label class={label} for="st">Send a test email to</label>
					<input id="st" type="email" bind:value={mailTo} class={field} />
				</div>
				<button type="button" class={btnSecondary} disabled={!mailTo} onclick={testMail}
					>Send test</button
				>
			</div>
			{#if mailTest === 'running'}<p class="text-muted sm:col-span-2">Sending…</p>
			{:else if mailTest}<p class="sm:col-span-2 {mailTest.ok ? 'text-success' : 'text-danger'}">
					{mailTest.message}
				</p>{/if}
		</form>
	{/if}

	<section class="mt-6 {card}" aria-labelledby="mcp-h">
		<h2 id="mcp-h" class="text-lg font-semibold">Use the tools from Claude Desktop (MCP)</h2>
		<p class="mt-1 text-muted">
			The assistant's tools are also an MCP server at <code>{mcpUrl}</code>. Without a token a
			client gets the public, read-only tools; with your token it gets the tools your roles allow.
			Changes are still confirmed in this app.
		</p>
		<button class="mt-3 {btnSecondary}" onclick={makeToken}>Create a token</button>
		{#if mcp}
			<p class="mt-3 text-sm text-muted">
				Valid for {mcp.expires_in_hours} hours. Add this to claude_desktop_config.json:
			</p>
			<pre class="mt-2 overflow-x-auto rounded-lg bg-surface-2 p-3 text-sm">{mcpConfig}</pre>
			<button class="mt-2 {btnSecondary}" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button>
		{/if}
	</section>
{/if}

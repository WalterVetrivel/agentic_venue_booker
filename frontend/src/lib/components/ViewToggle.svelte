<script lang="ts" module>
	function read(key: string): string | null {
		try {
			return localStorage.getItem(key);
		} catch {
			return null;
		}
	}

	/** The view someone last picked under `key`, if it is still one of `options`. */
	export function savedView<T extends string>(key: string, options: readonly T[], fallback: T): T {
		const v = read(`view:${key}`);
		return v && (options as readonly string[]).includes(v) ? (v as T) : fallback;
	}
</script>

<script lang="ts" generics="T extends string">
	import Icon from './Icon.svelte';

	let {
		value = $bindable(),
		options,
		label,
		key = ''
	}: {
		value: T;
		options: { value: T; label: string; icon?: string }[];
		/** Names the group for screen readers. */
		label: string;
		/** When set, the choice is remembered on this device. */
		key?: string;
	} = $props();

	function choose(v: T) {
		value = v;
		if (key)
			try {
				localStorage.setItem(`view:${key}`, v);
			} catch {
				/* storage unavailable */
			}
	}
</script>

<div class="glass inline-flex rounded-xl border p-1" role="group" aria-label={label}>
	{#each options as o (o.value)}
		<button
			type="button"
			class="press inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors {value ===
			o.value
				? 'bg-accent-soft text-accent shadow-sm'
				: 'text-muted hover:text-fg'}"
			aria-pressed={value === o.value}
			onclick={() => choose(o.value)}
		>
			{#if o.icon}<Icon name={o.icon} size={16} />{/if}
			{o.label}
		</button>
	{/each}
</div>

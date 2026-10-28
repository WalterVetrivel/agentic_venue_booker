<script lang="ts">
	import Icon from './Icon.svelte';
	import { page } from '$app/state';
	import { NAV } from '#lib/nav.ts';
	import { ui } from '#lib/stores/ui.svelte.ts';

	type Crumb = { label: string; href: string | null };

	const LABELS: Record<string, string> = Object.fromEntries(
		NAV.map((n) => [n.href.slice(1), n.label])
	);
	// Folders with no page of their own name the item that follows them.
	const GROUPS: Record<string, string> = { sections: 'Class', events: 'Event' };
	const NAMED: Record<string, string> = { new: 'Add new' };

	const crumbs = $derived.by(() => {
		const parts = page.url.pathname.split('/').filter(Boolean);
		const out: Crumb[] = [];
		let path = '';
		for (let i = 0; i < parts.length; i++) {
			const part = decodeURIComponent(parts[i]);
			path += `/${parts[i]}`;
			if (GROUPS[part] && i + 1 < parts.length) {
				out.push({ label: `${GROUPS[part]} ${decodeURIComponent(parts[i + 1])}`, href: null });
				path += `/${parts[++i]}`;
				continue;
			}
			const label =
				i === 0
					? (LABELS[part] ?? part)
					: (NAMED[part] ?? (/^\d+$/.test(part) ? `#${part}` : part));
			out.push({ label, href: path });
		}
		const last = out.at(-1);
		if (last) {
			if (ui.crumb) last.label = ui.crumb;
			last.href = null;
		}
		return out;
	});
</script>

{#if crumbs.length}
	<div class="rise mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
		<a
			href="/"
			class="press glass group inline-flex items-center gap-1.5 rounded-full border py-1.5 pr-4 pl-2.5 text-sm font-medium hover:border-accent/50 hover:text-accent"
		>
			<Icon
				name="back"
				size={18}
				class="transition-transform duration-200 group-hover:-translate-x-0.5"
			/>
			Dashboard
		</a>
		<nav aria-label="Breadcrumb" class="min-w-0">
			<ol class="flex flex-wrap items-center gap-1.5 text-sm text-muted">
				<li><a href="/" class="hover:text-accent hover:underline">Home</a></li>
				{#each crumbs as c, i (i)}
					<li aria-hidden="true" class="opacity-60">/</li>
					<li class="max-w-64 truncate">
						{#if c.href}
							<a href={c.href} class="hover:text-accent hover:underline">{c.label}</a>
						{:else}
							<span aria-current="page" class="font-medium text-fg">{c.label}</span>
						{/if}
					</li>
				{/each}
			</ol>
		</nav>
	</div>
{/if}
